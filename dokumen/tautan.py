"""
Pembuatan dokumen bertipe Tautan Aplikasi/Website secara terprogram
(dipakai command isi_tautan_aplikasi & isi_tautan_portal).
"""
from django.db import transaction
from django.utils import timezone

from master_akreditasi.models import ButirDokumen

from .models import Dokumen, DokumenAccessLog, DokumenRevisi


def link_accessible(url):
    """Cek ringan tautan bisa dibuka (HTTP < 400). Gagal cek tidak menghalangi simpan."""
    import requests
    try:
        resp = requests.get(url, timeout=8, allow_redirects=True, stream=True,
                            headers={"User-Agent": "SIAKRED-LinkCheck/1.0"})
        resp.close()
        return resp.status_code < 400
    except requests.RequestException:
        return False


def tautan_sudah_ada(butir, url, scope_prodi="", scope_fakultas=""):
    """True kalau butir (atau grup kode bersamanya) sudah punya dokumen tautan FINAL ber-URL & scope sama."""
    ids = [butir.pk]
    if butir.kode_bersama:
        ids = list(ButirDokumen.objects.filter(kode_bersama=butir.kode_bersama).values_list("pk", flat=True))
    return DokumenRevisi.objects.filter(
        dokumen__butir_dokumen_id__in=ids,
        dokumen__status=Dokumen.Status.FINAL,
        dokumen__scope_kode_prodi=scope_prodi,
        dokumen__scope_kode_fakultas=scope_fakultas,
        aktif=True,
        storage_type=DokumenRevisi.StorageType.LINK,
        gdrive_url=url,
    ).exists()


def buat_dokumen_tautan(butir, judul, url, user, scope_prodi="", scope_fakultas="",
                        deskripsi="", bisa_diakses=None, catatan_log="Tautan aplikasi/website"):
    """Buat Dokumen + revisi LINK (status akses Terbuka, tahun kosong). Verifikasi tetap PENDING."""
    if bisa_diakses is None:
        bisa_diakses = link_accessible(url)
    with transaction.atomic():
        dokumen = Dokumen.objects.create(
            butir_dokumen=butir,
            kategori_pemilik=butir.kategori_kepemilikan,
            scope_kode_prodi=scope_prodi,
            scope_kode_fakultas=scope_fakultas,
            judul=judul[:300],
            deskripsi=deskripsi,
            status_akses=Dokumen.StatusAkses.TERBUKA,
            tahun_akademik="",
            uploaded_by=user,
            last_updated_by=user,
        )
        revisi = DokumenRevisi.objects.create(
            dokumen=dokumen,
            nomor_revisi=1,
            storage_type=DokumenRevisi.StorageType.LINK,
            gdrive_url=url,
            original_filename=f"[Tautan] {url}"[:300],
            extension="link",
            aktif=True,
            uploaded_by=user,
            last_verified_at=timezone.now(),
            is_link_broken=not bisa_diakses,
        )
        DokumenAccessLog.objects.create(
            dokumen=dokumen, revisi=revisi, aksi=DokumenAccessLog.AksiType.UPLOAD,
            user=user, catatan=catatan_log[:200],
        )
    return dokumen


# =========================================================
# DAFTAR TAUTAN & PENGISIAN (dipakai command + Pusat Sinkronisasi)
# =========================================================

TAUTAN_APLIKASI = [
    # (kode_bersama, judul dokumen, url) -- dokumen Universitas (berlaku semua prodi)
    ("UNIV-SCREENSHOT-REPOSITORY-DIGITAL-LIBRARY", "Tautan Digital Library / Repository (SIPERPUS)",
     "https://siperpus.unisan.ac.id/"),
    ("UNIV-SCREENSHOT-LMS", "Tautan LMS UNISAN", "https://lms.unisan.ac.id/"),
    ("UNIV-SCREENSHOT-SIAKAD", "Tautan SIAKAD UNISAN (SIAKUN)", "https://siakun.unisan.ac.id/"),
    ("PRODI-SCREENSHOT-INPUT-NILAI-SIAKAD", "Tautan SIAKAD (SIAKUN) - Input Nilai", "https://siakun.unisan.ac.id/"),
    ("UNIV-DASHBOARD-SISTEM-INFORMASI-MUTU", "Tautan Sistem Informasi Mutu (SIAMI)", "https://siami.unisan-g.id/"),
]

PORTAL = "https://portal.unisan.ac.id"
ALUMNI = "https://alumni.unisan-g.id/"

# (kode butir, tingkat, judul, path/URL). {slug}, {fslug}, {prodi}, {fak} diisi per prodi.
TAUTAN_PORTAL = [
    ("U1.02", "univ", "VMTS Universitas (Portal UNISAN)", "/profil/"),
    ("U1.02", "fakultas", "VMTS UPPS {fak} (Portal UNISAN)", "/fakultas/{fslug}/#sec-vmts"),
    ("U1.02", "prodi", "VMTS Program Studi {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-vmts"),
    ("U1.12", "prodi", "Publikasi CPL Program Studi {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-cpl"),
    ("U5.03", "prodi", "Profil Lulusan {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-lulusan"),
    ("U5.04", "prodi", "Rumusan CPL {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-cpl"),
    ("U5.08", "prodi", "Sebaran Mata Kuliah per Semester {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-kurikulum"),
    ("U4.17", "prodi", "Halaman Portal Program Studi {prodi} (media promosi)", "/prodi/{slug}/"),
    ("U6.02", "prodi", "Direktori Dosen {prodi} (Portal UNISAN)", "/dosen/?prodi={slug}"),
    ("U6.07", "prodi", "Profil/CV Dosen {prodi} (Portal UNISAN)", "/dosen/?prodi={slug}"),
    ("U4.11", "univ", "Daftar Kerja Sama UNISAN (Portal UNISAN)", "/kerjasama/"),
    ("U4.11", "prodi", "Mitra Kerja Sama {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-mitra"),
    ("U4.02", "univ", "Profil & Struktur Organisasi Universitas (Portal UNISAN)", "/profil/"),
    ("U4.08", "univ", "Dashboard Kinerja Akademik (Portal UNISAN)", "/kinerja/"),
    ("U1.08", "univ", "Portal Alumni & Tracer Study UNISAN", ALUMNI),
]


def isi_tautan_aplikasi(user, apply=False, log=print):
    """Tautan aplikasi kampus (Universitas). Return jumlah tautan baru."""
    baru = 0
    for kode_bersama, judul, url in TAUTAN_APLIKASI:
        butir = (
            ButirDokumen.objects.filter(kode_bersama=kode_bersama, aktif=True)
            .order_by("sub_standar__standar__instrumen__urutan", "kode").first()
        )
        if butir is None:
            log(f"- {kode_bersama}: butir belum ada, dilewati")
            continue
        if tautan_sudah_ada(butir, url):
            log(f"= {butir.kode} {judul}: sudah ada")
            continue
        bisa = link_accessible(url)
        log(f"+ {butir.kode} {judul} -> {url} ({'bisa diakses' if bisa else 'TIDAK bisa diakses'})")
        baru += 1
        if apply:
            buat_dokumen_tautan(
                butir, judul, url, user,
                deskripsi="Tautan aplikasi untuk bukti sarana TIK. Lengkapi dengan screenshot di butir yang sama.",
                bisa_diakses=bisa, catatan_log="Tautan aplikasi (sinkron)",
            )
    return baru


def isi_tautan_portal(mapping, user, apply=False, log=print):
    """Tautan Portal UNISAN + Alumni untuk 1 MappingProdiInstrumen (butuh portal_slug). Return jumlah baru."""
    from .siobe_rps import _kode_fakultas

    if not mapping.portal_slug:
        log(f"- {mapping.kode_prodi}: slug portal belum diisi di Mapping Prodi, dilewati")
        return 0
    kode_prodi = mapping.kode_prodi
    kode_fakultas = _kode_fakultas(kode_prodi)
    fslug = (mapping.portal_fakultas_slug or "").strip("/")
    isian = {"slug": mapping.portal_slug.strip("/"), "fslug": fslug,
             "prodi": mapping.nama_prodi, "fak": fslug.upper()}
    cek, baru = {}, 0
    for kode_butir, tingkat, judul, path in TAUTAN_PORTAL:
        if tingkat == "fakultas" and not fslug:
            continue
        butir = ButirDokumen.objects.filter(
            sub_standar__standar__instrumen_id=mapping.instrumen_id, kode=kode_butir, aktif=True).first()
        if butir is None:
            continue  # instrumen prodi ini tidak punya butir tsb
        url = path if path.startswith("http") else PORTAL + path.format(**isian)
        judul = judul.format(**isian)
        scope_prodi = kode_prodi if tingkat == "prodi" else ""
        scope_fak = kode_fakultas if tingkat in ("prodi", "fakultas") else ""
        if tautan_sudah_ada(butir, url, scope_prodi, scope_fak):
            continue
        if url not in cek:
            cek[url] = link_accessible(url)
        log(f"+ {kode_prodi} {kode_butir} [{tingkat}] {judul} -> {url} ({'OK' if cek[url] else 'TIDAK BISA DIAKSES'})")
        baru += 1
        if apply:
            buat_dokumen_tautan(
                butir, judul, url, user, scope_prodi=scope_prodi, scope_fakultas=scope_fak,
                deskripsi="Tautan publik Portal UNISAN sebagai bukti publikasi. Dokumen resmi (SK dsb.) "
                          "tetap diunggah terpisah.",
                bisa_diakses=cek[url], catatan_log="Tautan portal (sinkron)",
            )
    return baru


def cek_ulang_tautan(log=print):
    """Cek ulang semua dokumen tautan aktif. Return (jumlah dicek, jumlah tidak bisa diakses)."""
    revisi = list(DokumenRevisi.objects.filter(
        aktif=True, storage_type=DokumenRevisi.StorageType.LINK,
        dokumen__status=Dokumen.Status.FINAL).select_related("dokumen"))
    hasil, rusak = {}, 0
    for rev in revisi:
        if rev.gdrive_url not in hasil:
            hasil[rev.gdrive_url] = link_accessible(rev.gdrive_url)
        bisa = hasil[rev.gdrive_url]
        if not bisa:
            rusak += 1
            log(f"! tidak bisa diakses: {rev.dokumen.judul} -> {rev.gdrive_url}")
        DokumenRevisi.objects.filter(pk=rev.pk).update(is_link_broken=not bisa, last_verified_at=timezone.now())
    return len(revisi), rusak
