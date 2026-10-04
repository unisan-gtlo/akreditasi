"""
Sinkronisasi RPS Disahkan dari SI-OBE menjadi Dokumen SIAKRED.

Sumber: API baca-saja SI-OBE (sama dengan yang dipakai Portal UNISAN)
    GET {SIOBE_BASE_URL}/api/external/rps-disahkan/?study_program=<kode prodi>
    Header: Authorization: Token <SIOBE_API_TOKEN>

Setiap mata kuliah yang RPS-nya sudah disahkan menjadi satu Dokumen
("RPS <kode MK> — <nama MK>") pada butir ber-kode_bersama
KODE_BERSAMA_RPS di instrumen prodi tersebut. Karena kode bersama, RPS
otomatis terhitung di semua butir RPS seluruh MK (mis. U2.01 & U5.09).

- RPS berupa BERKAS -> diunduh (pakai token) dan disimpan sebagai file lokal,
  jadi ikut di preview, Bundle, dan Export ZIP tanpa perlu akses SI-OBE.
- RPS berupa TAUTAN -> disimpan sebagai link.
- Hanya disinkron ulang kalau RPS di SI-OBE berubah (jadi revisi baru).
- RPS yang dicabut / MK yang hilang dari SI-OBE -> dokumen diarsipkan.
- Verifikasi otomatis APPROVED: RPS sudah melalui pengesahan di SI-OBE.

SI-OBE tetap satu-satunya tempat RPS diubah; SIAKRED hanya membaca.
"""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone

from master_akreditasi.models import ButirDokumen, MappingProdiInstrumen

from .models import Dokumen, DokumenAccessLog, DokumenRevisi, VerifikasiDokumen

KODE_BERSAMA_RPS = "PRODI-RPS-SELURUH-MATA-KULIAH"
MARKER = "SIOBE"
TIMEOUT_LIST = 30
TIMEOUT_DOWNLOAD = 60


class SiobeError(Exception):
    pass


@dataclass
class SyncReport:
    kode_prodi: str
    butir: object = None
    tahun_kurikulum: object = None
    total_mk: int = 0
    dibuat: list = field(default_factory=list)
    diperbarui: list = field(default_factory=list)
    tetap: list = field(default_factory=list)
    diarsipkan: list = field(default_factory=list)
    tanpa_rps: list = field(default_factory=list)
    gagal: list = field(default_factory=list)
    penciri_diperbarui: int = 0
    penciri_diarsipkan: int = 0

    @property
    def dengan_rps(self):
        return len(self.dibuat) + len(self.diperbarui) + len(self.tetap)


# =========================================================
# API SI-OBE
# =========================================================

def _api_config():
    base = (getattr(settings, "SIOBE_BASE_URL", "") or "").rstrip("/")
    token = getattr(settings, "SIOBE_API_TOKEN", "") or ""
    if not base or not token:
        raise SiobeError("SIOBE_BASE_URL atau SIOBE_API_TOKEN belum diisi di .env SIAKRED.")
    return base, {"Authorization": f"Token {token}"}


def fetch_rps(kode_prodi):
    """Daftar MK (yang sudah punya penugasan dosen) + status RPS Disahkan untuk 1 prodi."""
    base, headers = _api_config()
    try:
        resp = requests.get(
            f"{base}/api/external/rps-disahkan/",
            params={"study_program": kode_prodi},
            headers=headers,
            timeout=TIMEOUT_LIST,
        )
    except requests.RequestException as exc:
        raise SiobeError(f"Tidak bisa menghubungi SI-OBE: {type(exc).__name__}: {str(exc)[:150]}")
    if resp.status_code == 401:
        raise SiobeError("Token SI-OBE ditolak (401). Periksa SIOBE_API_TOKEN / klien di SI-OBE masih aktif.")
    if resp.status_code != 200:
        raise SiobeError(f"SI-OBE membalas HTTP {resp.status_code}: {resp.text[:150]}")
    try:
        return resp.json().get("results", [])
    except ValueError:
        raise SiobeError("Respons SI-OBE bukan JSON.")


def _download(url):
    _, headers = _api_config()
    resp = requests.get(url, headers=headers, timeout=TIMEOUT_DOWNLOAD)
    if resp.status_code != 200:
        raise SiobeError(f"Unduh RPS gagal (HTTP {resp.status_code})")
    m = re.search(r'filename="?([^";]+)"?', resp.headers.get("Content-Disposition", ""))
    filename = m.group(1) if m else ""
    return resp.content, filename, resp.headers.get("Content-Type", "").split(";")[0]


# =========================================================
# HELPER MURNI (mudah diuji)
# =========================================================

def pilih_baris(rows, tahun_kurikulum=None):
    """Ambil baris satu tahun kurikulum, satu baris per kode MK.

    Default: tahun kurikulum dengan MK terbanyak (kurikulum yang berjalan),
    seri -> yang terbaru. Bukan sekadar "terbaru", karena kurikulum baru yang
    baru berisi sedikit MK akan menyembunyikan kurikulum berjalan.
    """
    if not rows:
        return None, []
    if tahun_kurikulum is None:
        from collections import Counter
        jumlah = Counter(r.get("academic_year") or 0 for r in rows if r.get("course_code"))
        tahun_kurikulum = max(jumlah, key=lambda th: (jumlah[th], th))
    hasil = {}
    for r in rows:
        if r.get("academic_year") == tahun_kurikulum and r.get("course_code"):
            hasil.setdefault(r["course_code"].strip(), r)
    return tahun_kurikulum, list(hasil.values())


def signature(row):
    """Penanda versi RPS (disimpan di catatan revisi) untuk deteksi perubahan."""
    return "%s jenis=%s; disahkan=%s; url=%s" % (
        MARKER,
        row.get("rps_disahkan_jenis") or "",
        row.get("rps_disahkan_uploaded_at") or "",
        row.get("rps_disahkan_url") or "",
    )


def judul_rps(row):
    return ("RPS %s — %s" % (row["course_code"].strip(), (row.get("course_name") or "").strip()))[:300]


def kode_dari_judul(judul):
    parts = (judul or "").split(" ", 2)
    return parts[1] if len(parts) >= 2 and parts[0] == "RPS" else ""


# =========================================================
# SINKRONISASI
# =========================================================

def target_butir(kode_prodi):
    """Butir RPS seluruh MK pada instrumen prodi (butir pertama dengan kode bersama RPS)."""
    mapping = MappingProdiInstrumen.objects.filter(kode_prodi=kode_prodi, aktif=True).first()
    if not mapping:
        return None
    return (
        ButirDokumen.objects.filter(
            sub_standar__standar__instrumen_id=mapping.instrumen_id,
            kode_bersama=KODE_BERSAMA_RPS,
            aktif=True,
        )
        .order_by("sub_standar__standar__urutan", "sub_standar__urutan", "urutan", "kode")
        .first()
    )


def prodi_dengan_butir_rps():
    """Kode prodi yang instrumennya punya butir RPS ber-kode bersama."""
    instrumen_ids = set(
        ButirDokumen.objects.filter(kode_bersama=KODE_BERSAMA_RPS, aktif=True)
        .values_list("sub_standar__standar__instrumen_id", flat=True)
    )
    return list(
        MappingProdiInstrumen.objects.filter(aktif=True, instrumen_id__in=instrumen_ids)
        .order_by("kode_prodi").values_list("kode_prodi", flat=True)
    )


def _kode_fakultas(kode_prodi):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT kode_fakultas FROM master.program_studi WHERE kode_prodi = %s", [kode_prodi])
            row = cur.fetchone()
            return (row[0] or "") if row else ""
    except Exception:
        return ""


def _sync_docs(butir, kode_prodi):
    """{kode MK: Dokumen} hasil sinkron sebelumnya untuk prodi ini."""
    docs = {}
    for d in Dokumen.objects.filter(butir_dokumen=butir, scope_kode_prodi=kode_prodi, judul__startswith="RPS "):
        rev = d.revisi.filter(aktif=True).order_by("-nomor_revisi").first()
        if rev and rev.catatan_revisi.startswith(MARKER):
            docs[kode_dari_judul(d.judul)] = (d, rev)
    return docs


def _tulis_revisi(dokumen, row, user, nomor_rev):
    jenis = row.get("rps_disahkan_jenis")
    sig = signature(row)
    if jenis == "berkas":
        konten, filename, mime = _download(row["rps_disahkan_download_url"])
        filename = filename or f"RPS_{row['course_code'].strip()}.pdf"
        revisi = DokumenRevisi.objects.create(
            dokumen=dokumen,
            nomor_revisi=nomor_rev,
            storage_type=DokumenRevisi.StorageType.LOCAL,
            file=ContentFile(konten, name=filename),
            original_filename=filename[:300],
            file_size_kb=int(len(konten) / 1024),
            file_hash=hashlib.sha256(konten).hexdigest(),
            mime_type=mime or "application/pdf",
            extension=Path(filename).suffix.lower().lstrip(".")[:10],
            catatan_revisi=sig,
            aktif=True,
            uploaded_by=user,
        )
    else:
        from .gdrive_helper import extract_gdrive_file_id
        url = row["rps_disahkan_url"]
        revisi = DokumenRevisi.objects.create(
            dokumen=dokumen,
            nomor_revisi=nomor_rev,
            storage_type=DokumenRevisi.StorageType.GDRIVE,
            gdrive_url=url[:500],
            gdrive_file_id=extract_gdrive_file_id(url) or "",
            original_filename=f"[Tautan SI-OBE] {dokumen.judul}"[:300],
            extension="gdrive",
            catatan_revisi=sig,
            aktif=True,
            uploaded_by=user,
            last_verified_at=timezone.now(),
        )
    # RPS sudah disahkan di SI-OBE -> verifikasi otomatis disetujui
    VerifikasiDokumen.objects.filter(revisi=revisi).update(
        status=VerifikasiDokumen.Status.APPROVED,
        catatan="RPS sudah disahkan di SI-OBE (sinkron otomatis).",
        tanggal_verifikasi=timezone.now(),
    )
    return revisi


def sync_prodi(kode_prodi, user, apply=False, tahun_kurikulum=None):
    """Sinkron RPS 1 prodi. apply=False -> hanya laporan (tanpa unduh/simpan)."""
    report = SyncReport(kode_prodi=kode_prodi)
    butir = target_butir(kode_prodi)
    report.butir = butir
    if butir is None:
        raise SiobeError(
            f"Prodi {kode_prodi}: instrumennya tidak punya butir ber-kode bersama {KODE_BERSAMA_RPS}."
        )

    tahun, rows = pilih_baris(fetch_rps(kode_prodi), tahun_kurikulum)
    report.tahun_kurikulum = tahun
    report.total_mk = len(rows)
    existing = _sync_docs(butir, kode_prodi)
    kode_fakultas = _kode_fakultas(kode_prodi)
    kode_aktif = set()

    for row in rows:
        kode = row["course_code"].strip()
        label = judul_rps(row)
        if not row.get("rps_disahkan_jenis"):
            report.tanpa_rps.append(label)
            continue
        kode_aktif.add(kode)
        doc_rev = existing.get(kode)
        if doc_rev and doc_rev[0].status == Dokumen.Status.FINAL and doc_rev[1].catatan_revisi == signature(row):
            report.tetap.append(label)
            continue
        if not apply:
            (report.diperbarui if doc_rev else report.dibuat).append(label)
            continue
        try:
            with transaction.atomic():
                deskripsi = "RPS Disahkan dari SI-OBE. Kurikulum %s." % (row.get("academic_year") or "-")
                if doc_rev:
                    dokumen = doc_rev[0]
                    dokumen.judul = label
                    dokumen.deskripsi = deskripsi
                    dokumen.status = Dokumen.Status.FINAL
                    dokumen.last_updated_by = user
                    dokumen.save()
                    dokumen.revisi.update(aktif=False)
                    last = dokumen.revisi.order_by("-nomor_revisi").first()
                    nomor = (last.nomor_revisi + 1) if last else 1
                    aksi = DokumenAccessLog.AksiType.REVISI
                else:
                    dokumen = Dokumen.objects.create(
                        butir_dokumen=butir,
                        kategori_pemilik=butir.kategori_kepemilikan,
                        scope_kode_prodi=kode_prodi,
                        scope_kode_fakultas=kode_fakultas,
                        judul=label,
                        deskripsi=deskripsi,
                        status_akses=Dokumen.StatusAkses.TERBUKA,
                        tahun_akademik="",
                        uploaded_by=user,
                        last_updated_by=user,
                    )
                    nomor = 1
                    aksi = DokumenAccessLog.AksiType.UPLOAD
                revisi = _tulis_revisi(dokumen, row, user, nomor)
                DokumenAccessLog.objects.create(
                    dokumen=dokumen, revisi=revisi, aksi=aksi, user=user,
                    catatan="Sinkron otomatis dari SI-OBE",
                )
            (report.diperbarui if doc_rev else report.dibuat).append(label)
        except Exception as exc:
            report.gagal.append(f"{label}: {type(exc).__name__}: {str(exc)[:120]}")

    # RPS dicabut atau MK hilang dari SI-OBE -> arsipkan dokumen hasil sinkron
    for kode, (dokumen, _rev) in existing.items():
        if kode not in kode_aktif and dokumen.status == Dokumen.Status.FINAL:
            report.diarsipkan.append(dokumen.judul)
            if apply:
                dokumen.status = Dokumen.Status.ARSIP
                dokumen.last_updated_by = user
                dokumen.save(update_fields=["status", "last_updated_by", "tanggal_diubah"])

    # Dokumen RPS MK penciri (cermin) ikut versi terbaru RPS sumber
    if apply:
        report.penciri_diperbarui, report.penciri_diarsipkan = refresh_penciri(kode_prodi, user)
    return report


# =========================================================
# RPS MATA KULIAH PENCIRI
# =========================================================
# Prodi memilih MK penciri dari RPS hasil sinkron. Tiap pilihan menjadi
# Dokumen "cermin" di butir ber-kode bersama KODE_BERSAMA_PENCIRI (mis. U2.02
# & U5.10) yang MEMAKAI FILE YANG SAMA dengan dokumen RPS sumber -- tidak ada
# salinan berkas. Cermin ikut diperbarui saat RPS sumber direvisi
# (refresh_penciri dipanggil di akhir sync_prodi) dan diarsipkan kalau
# RPS sumber dicabut.

KODE_BERSAMA_PENCIRI = "PRODI-RPS-MK-PENCIRI"
MARKER_PENCIRI = "PENCIRI"


def penciri_butir(kode_prodi):
    """Butir RPS MK penciri pada instrumen prodi, atau None."""
    mapping = MappingProdiInstrumen.objects.filter(kode_prodi=kode_prodi, aktif=True).first()
    if not mapping:
        return None
    return (
        ButirDokumen.objects.filter(
            sub_standar__standar__instrumen_id=mapping.instrumen_id,
            kode_bersama=KODE_BERSAMA_PENCIRI,
            aktif=True,
        )
        .order_by("sub_standar__standar__urutan", "sub_standar__urutan", "urutan", "kode")
        .first()
    )


def rps_sumber(kode_prodi):
    """{kode MK: (Dokumen, revisi aktif)} RPS hasil sinkron yang masih FINAL."""
    butir = target_butir(kode_prodi)
    if butir is None:
        return {}
    return {
        kode: (dok, rev)
        for kode, (dok, rev) in _sync_docs(butir, kode_prodi).items()
        if dok.status == Dokumen.Status.FINAL
    }


def _penciri_docs(butir, kode_prodi):
    """{kode MK: (Dokumen, revisi aktif)} dokumen cermin penciri (FINAL maupun ARSIP)."""
    docs = {}
    for d in Dokumen.objects.filter(butir_dokumen=butir, scope_kode_prodi=kode_prodi, judul__startswith="RPS "):
        rev = d.revisi.filter(aktif=True).order_by("-nomor_revisi").first()
        if rev and rev.catatan_revisi.startswith(MARKER_PENCIRI):
            docs[kode_dari_judul(d.judul)] = (d, rev)
    return docs


def _penanda_penciri(src_rev):
    return f"{MARKER_PENCIRI} src={src_rev.pk}; {src_rev.catatan_revisi}"[:2000]


def _cermin_revisi(dokumen, src_rev, user, nomor_rev):
    revisi = DokumenRevisi.objects.create(
        dokumen=dokumen,
        nomor_revisi=nomor_rev,
        storage_type=src_rev.storage_type,
        file=src_rev.file.name if src_rev.file else None,  # file yang sama, tanpa salinan
        original_filename=src_rev.original_filename,
        file_size_kb=src_rev.file_size_kb,
        file_hash=src_rev.file_hash,
        mime_type=src_rev.mime_type,
        extension=src_rev.extension,
        gdrive_url=src_rev.gdrive_url,
        gdrive_file_id=src_rev.gdrive_file_id,
        last_verified_at=src_rev.last_verified_at,
        catatan_revisi=_penanda_penciri(src_rev),
        aktif=True,
        uploaded_by=user,
    )
    VerifikasiDokumen.objects.filter(revisi=revisi).update(
        status=VerifikasiDokumen.Status.APPROVED,
        catatan="RPS MK penciri dari RPS Disahkan SI-OBE.",
        tanggal_verifikasi=timezone.now(),
    )
    return revisi


def _tulis_cermin(butir, kode_prodi, src_doc, src_rev, cermin, user):
    """Buat / perbarui / aktifkan kembali dokumen cermin. Return True kalau ada perubahan."""
    if cermin:
        dokumen, rev = cermin
        if dokumen.status == Dokumen.Status.FINAL and rev.catatan_revisi == _penanda_penciri(src_rev):
            return False
        dokumen.judul = src_doc.judul
        dokumen.status = Dokumen.Status.FINAL
        dokumen.last_updated_by = user
        dokumen.save()
        dokumen.revisi.update(aktif=False)
        last = dokumen.revisi.order_by("-nomor_revisi").first()
        nomor, aksi = (last.nomor_revisi + 1 if last else 1), DokumenAccessLog.AksiType.REVISI
    else:
        dokumen = Dokumen.objects.create(
            butir_dokumen=butir,
            kategori_pemilik=butir.kategori_kepemilikan,
            scope_kode_prodi=kode_prodi,
            scope_kode_fakultas=src_doc.scope_kode_fakultas,
            judul=src_doc.judul,
            deskripsi="RPS mata kuliah penciri prodi (dipilih dari RPS Disahkan SI-OBE).",
            status_akses=src_doc.status_akses,
            tahun_akademik="",
            uploaded_by=user,
            last_updated_by=user,
        )
        nomor, aksi = 1, DokumenAccessLog.AksiType.UPLOAD
    revisi = _cermin_revisi(dokumen, src_rev, user, nomor)
    DokumenAccessLog.objects.create(
        dokumen=dokumen, revisi=revisi, aksi=aksi, user=user,
        catatan="Dipilih sebagai MK penciri (RPS SI-OBE)",
    )
    return True


def _arsipkan(dokumen, user):
    if dokumen.status != Dokumen.Status.ARSIP:
        dokumen.status = Dokumen.Status.ARSIP
        dokumen.last_updated_by = user
        dokumen.save(update_fields=["status", "last_updated_by", "tanggal_diubah"])
        return True
    return False


def set_penciri(kode_prodi, kode_mk_terpilih, user):
    """Simpan pilihan MK penciri. Return dict ringkasan {ditambah, dihapus, tetap}."""
    butir = penciri_butir(kode_prodi)
    if butir is None:
        raise SiobeError(f"Instrumen prodi {kode_prodi} tidak punya butir {KODE_BERSAMA_PENCIRI}.")
    sumber = rps_sumber(kode_prodi)
    terpilih = {k for k in kode_mk_terpilih if k in sumber}
    cermin = _penciri_docs(butir, kode_prodi)
    hasil = {"ditambah": 0, "dihapus": 0, "tetap": 0}
    with transaction.atomic():
        for kode in sorted(terpilih):
            src_doc, src_rev = sumber[kode]
            if _tulis_cermin(butir, kode_prodi, src_doc, src_rev, cermin.get(kode), user):
                hasil["ditambah"] += 1
            else:
                hasil["tetap"] += 1
        for kode, (dokumen, _rev) in cermin.items():
            if kode not in terpilih and _arsipkan(dokumen, user):
                hasil["dihapus"] += 1
    return hasil


def penciri_terpilih(kode_prodi):
    """Set kode MK yang saat ini terpilih sebagai penciri (dokumen cermin FINAL)."""
    butir = penciri_butir(kode_prodi)
    if butir is None:
        return set()
    return {k for k, (d, _r) in _penciri_docs(butir, kode_prodi).items() if d.status == Dokumen.Status.FINAL}


def refresh_penciri(kode_prodi, user):
    """Ikutkan perubahan RPS sumber ke dokumen cermin penciri. Return (diperbarui, diarsipkan)."""
    butir = penciri_butir(kode_prodi)
    if butir is None:
        return 0, 0
    sumber = rps_sumber(kode_prodi)
    diperbarui = diarsipkan = 0
    for kode, cermin in _penciri_docs(butir, kode_prodi).items():
        dokumen, _rev = cermin
        if dokumen.status != Dokumen.Status.FINAL:
            continue
        if kode not in sumber:
            diarsipkan += _arsipkan(dokumen, user)
            continue
        with transaction.atomic():
            diperbarui += _tulis_cermin(butir, kode_prodi, sumber[kode][0], sumber[kode][1], cermin, user)
    return diperbarui, diarsipkan
