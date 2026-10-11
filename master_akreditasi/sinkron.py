"""
Pusat Sinkronisasi: perbarui data SIAKRED dari sistem lain.

Jenis:
    RPS    -> RPS Disahkan SI-OBE (dokumen per MK + MK penciri)
    DTPS   -> DTPS sesi aktif dari SIMDA (dosen homebase baru, snapshot, penanda)
    TAUTAN -> tautan aplikasi kampus + Portal UNISAN/Alumni per prodi + cek ulang tautan
    VMTS   -> VMTS universitas/fakultas/prodi dari view SIMDA (sama dengan Portal UNISAN)
    CACHE  -> bersihkan cache (beranda publik, sidebar, kelengkapan, badge)
    SEMUA  -> keempatnya berurutan

Dijalankan lewat command `sinkron` (tombol Pusat Sinkronisasi memanggilnya
sebagai proses latar belakang; cron malam memanggilnya langsung).
"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models_sinkron import SinkronLog

URUTAN_SEMUA = ["RPS", "DTPS", "TAUTAN", "VMTS", "CACHE"]
BATAS_BERJALAN = timedelta(minutes=30)  # proses lebih lama dari ini dianggap macet


# =========================================================
# KUNCI (cegah sinkron ganda)
# =========================================================

def sedang_berjalan(jenis, kecuali_pk=None):
    """Log sinkron yang masih berjalan & bentrok dengan jenis ini (SEMUA bentrok dengan apa pun)."""
    qs = SinkronLog.objects.filter(
        status__in=[SinkronLog.Status.ANTRI, SinkronLog.Status.BERJALAN],
        mulai__gte=timezone.now() - BATAS_BERJALAN,
    )
    if kecuali_pk:
        qs = qs.exclude(pk=kecuali_pk)
    if jenis != SinkronLog.Jenis.SEMUA:
        qs = qs.filter(jenis__in=[jenis, SinkronLog.Jenis.SEMUA])
    return qs.first()


# =========================================================
# JENIS SINKRON
# =========================================================

def sinkron_rps(user, kode_prodi="", log=print):
    from dokumen.siobe_rps import SiobeError, prodi_dengan_butir_rps, sync_prodi

    prodi_list = [kode_prodi] if kode_prodi else prodi_dengan_butir_rps()
    if kode_prodi and kode_prodi not in prodi_dengan_butir_rps():
        return "lewat (instrumen prodi tidak punya butir RPS)"
    ringkas = []
    for kode in prodi_list:
        try:
            r = sync_prodi(kode, user, apply=True)
        except SiobeError as exc:
            log(f"[{kode}] GAGAL: {exc}")
            raise
        log(f"[{kode}] RPS tersedia {r.dengan_rps}/{r.total_mk} | baru {len(r.dibuat)} | "
            f"diperbarui {len(r.diperbarui)} | diarsipkan {len(r.diarsipkan)} | "
            f"MK penciri diperbarui {r.penciri_diperbarui}")
        for j in r.dibuat + r.diperbarui:
            log(f"    ~ {j}")
        for j in r.tanpa_rps:
            log(f"    ! belum ada RPS: {j}")
        for g in r.gagal:
            log(f"    x {g}")
        ringkas.append(f"{kode} {r.dengan_rps}/{r.total_mk}"
                       + (f" (+{len(r.dibuat) + len(r.diperbarui)})" if r.dibuat or r.diperbarui else ""))
    return "RPS: " + ", ".join(ringkas) if ringkas else "RPS: tidak ada prodi"


def refresh_dtps_sesi(sesi, user=None, log=print):
    """Perbarui pool DTPS 1 sesi dari SIMDA tanpa mengubah status aktif/sumber.

    - Dosen homebase aktif baru di SIMDA -> ditambahkan (AUTO_HOMEBASE)
    - Snapshot nama/homebase/jabfung diperbarui
    - Dosen AUTO_HOMEBASE yang di SIMDA tidak lagi homebase prodi ini / nonaktif /
      tidak ditemukan -> ditandai perlu_ditinjau (TIDAK dinonaktifkan)
    Return dict ringkasan.
    """
    from .models_dosen_link import DTPSDosenSesi
    from .models_simda_ref import DataDosenRef
    from .simda_dosen import get_dosen_homebase_prodi

    now = timezone.now()
    pool = {d.dosen_nidn: d for d in DTPSDosenSesi.objects.filter(sesi=sesi)}
    homebase = {d.nidn: d for d in get_dosen_homebase_prodi(sesi.kode_prodi, hanya_aktif=True)}
    simda = {
        d.nidn: d for d in DataDosenRef.objects.filter(nidn__in=list(pool))
        .select_related("kode_prodi", "kode_fakultas", "jabatan_fungsional")
    }
    hasil = {"baru": 0, "diperbarui": 0, "ditandai": 0}

    for nidn, dosen in homebase.items():
        if nidn in pool:
            continue
        DTPSDosenSesi.objects.create(
            sesi=sesi, dosen_nidn=nidn, sumber="AUTO_HOMEBASE", peran="DTPS_HOMEBASE", aktif=True,
            dosen_nama_snapshot=dosen.nama_lengkap,
            dosen_homebase_prodi_snapshot=dosen.kode_prodi_id,
            dosen_homebase_fakultas_snapshot=dosen.kode_fakultas_id,
            dosen_jabfung_snapshot=dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else "",
            snapshot_at=now, dibuat_oleh=user,
            catatan_sinkron=f"Ditambahkan sinkron {now:%d-%m-%Y}: dosen homebase baru di SIMDA",
        )
        hasil["baru"] += 1
        log(f"    + {nidn} {dosen.nama_lengkap} (homebase baru)")

    for nidn, dtps in pool.items():
        dosen = simda.get(nidn)
        tandai, catatan = False, ""
        if dosen is None:
            tandai, catatan = True, "Tidak ditemukan di SIMDA"
        elif dtps.sumber == "AUTO_HOMEBASE":
            if not dosen.is_active:
                tandai, catatan = True, "Nonaktif di SIMDA"
            elif dosen.kode_prodi_id != sesi.kode_prodi:
                tandai, catatan = True, f"Homebase di SIMDA kini {dosen.kode_prodi_id}"
        ubah = {}
        if dosen is not None:
            jabfung = dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else ""
            baru = {
                "dosen_nama_snapshot": dosen.nama_lengkap,
                "dosen_homebase_prodi_snapshot": dosen.kode_prodi_id or "",
                "dosen_homebase_fakultas_snapshot": dosen.kode_fakultas_id or "",
                "dosen_jabfung_snapshot": jabfung,
            }
            ubah = {k: v for k, v in baru.items() if getattr(dtps, k) != v}
        if dtps.perlu_ditinjau != tandai or (tandai and dtps.catatan_sinkron != catatan):
            ubah["perlu_ditinjau"] = tandai
            ubah["catatan_sinkron"] = catatan if tandai else ""
            if tandai and dtps.aktif:
                hasil["ditandai"] += 1
                log(f"    ? {nidn} {dtps.dosen_nama_snapshot}: {catatan} (perlu ditinjau admin)")
        if ubah:
            ubah.update({"snapshot_at": now, "snapshot_outdated": False})
            DTPSDosenSesi.objects.filter(pk=dtps.pk).update(**ubah)
            if any(k.startswith("dosen_") for k in ubah):
                hasil["diperbarui"] += 1
    return hasil


def sinkron_dtps(user, kode_prodi="", log=print):
    from sesi.models import SesiAkreditasi
    from .dosen_data import invalidate_kelengkapan

    sesi_qs = SesiAkreditasi.objects.exclude(status__in=["SELESAI", "DIBATALKAN"])
    if kode_prodi:
        sesi_qs = sesi_qs.filter(kode_prodi=kode_prodi)
    total = {"baru": 0, "diperbarui": 0, "ditandai": 0}
    n = 0
    for sesi in sesi_qs.order_by("kode_prodi"):
        if not sesi.kode_prodi:
            continue
        log(f"[{sesi.kode_prodi}] sesi #{sesi.pk} {sesi.judul[:50]}")
        h = refresh_dtps_sesi(sesi, user=user, log=log)
        log(f"    DTPS baru {h['baru']} | snapshot diperbarui {h['diperbarui']} | perlu ditinjau {h['ditandai']}")
        for k in total:
            total[k] += h[k]
        n += 1
    invalidate_kelengkapan()
    return (f"DTPS: {n} sesi | {total['baru']} dosen baru | {total['diperbarui']} diperbarui | "
            f"{total['ditandai']} perlu ditinjau")


def sinkron_tautan(user, kode_prodi="", log=print):
    from dokumen.tautan import cek_ulang_tautan, isi_tautan_aplikasi, isi_tautan_portal
    from .models import MappingProdiInstrumen

    baru = isi_tautan_aplikasi(user, apply=True, log=log)
    maps = MappingProdiInstrumen.objects.filter(aktif=True).exclude(portal_slug="")
    if kode_prodi:
        maps = maps.filter(kode_prodi=kode_prodi)
    for m in maps:
        baru += isi_tautan_portal(m, user, apply=True, log=log)
    dicek, rusak = cek_ulang_tautan(log=log)
    return f"Tautan: {baru} baru | {dicek} dicek | {rusak} tidak bisa diakses"


GRANT_VMTS = (
    "GRANT SELECT ON master.v_profil_institusi_publik, master.v_profil_fakultas_publik, "
    "master.v_profil_prodi_publik TO {user};"
)


def _baca_view(sql, params=None):
    """Baca view SIMDA -> list dict. Error izin dijelaskan dengan perintah GRANT yang dibutuhkan."""
    from django.conf import settings
    from django.db import connection

    try:
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            kolom = [c[0] for c in cur.description]
            return [dict(zip(kolom, baris)) for baris in cur.fetchall()]
    except Exception as exc:
        if "permission denied" in str(exc).lower():
            user = settings.DATABASES["default"].get("USER", "akreditasi_user")
            raise RuntimeError(
                "User database SIAKRED belum diizinkan membaca view VMTS SIMDA. Jalankan sekali sebagai "
                "postgres: " + GRANT_VMTS.format(user=user)
            ) from exc
        raise


def _terapkan(obj, nilai, log, label):
    """Tulis nilai SIMDA yang TIDAK kosong ke obj (SIMDA sumber utama; kosong tidak menghapus isian lokal)."""
    berubah = [f for f, v in nilai.items() if (v or "").strip() and (getattr(obj, f) or "") != v.strip()]
    for f in berubah:
        setattr(obj, f, nilai[f].strip())
    obj.vmts_simda_at = timezone.now()
    obj.save()
    kosong = [f for f, v in nilai.items() if not (v or "").strip()]
    log(f"    {label}: {'diperbarui ' + ', '.join(berubah) if berubah else 'tidak berubah'}"
        + (f" | kosong di SIMDA: {', '.join(kosong)}" if kosong else ""))
    return bool(berubah)


def sinkron_vmts(user, kode_prodi="", log=print):
    """VMTS dari view SIMDA (v_profil_*_publik) ke SiteProfile / FakultasProfile / ProdiProfile."""
    from core.models import FakultasProfile, ProdiProfile, SiteProfile
    from .models import MappingProdiInstrumen

    berubah = 0
    if not kode_prodi:
        inst = _baca_view("SELECT visi, misi, tujuan, sasaran FROM master.v_profil_institusi_publik LIMIT 1")
        if inst:
            berubah += _terapkan(SiteProfile.get_instance(), inst[0], log, "Universitas")

    prodi_qs = MappingProdiInstrumen.objects.filter(aktif=True)
    if kode_prodi:
        prodi_qs = prodi_qs.filter(kode_prodi=kode_prodi)
    kode_prodi_list = list(prodi_qs.values_list("kode_prodi", flat=True))
    if not kode_prodi_list:
        return "VMTS: tidak ada prodi"

    prodi_rows = _baca_view(
        "SELECT p.kode_prodi, ps.kode_fakultas, p.visi_keilmuan, p.misi, p.tujuan, p.profil_lulusan, p.sasaran "
        "FROM master.v_profil_prodi_publik p JOIN master.program_studi ps ON ps.kode_prodi = p.kode_prodi "
        "WHERE p.kode_prodi = ANY(%s)", [kode_prodi_list])
    fak_kode = sorted({r["kode_fakultas"] for r in prodi_rows if r["kode_fakultas"]})
    if fak_kode:
        for r in _baca_view("SELECT kode_fakultas, visi, misi, tujuan, sasaran "
                            "FROM master.v_profil_fakultas_publik WHERE kode_fakultas = ANY(%s)", [fak_kode]):
            fp, _ = FakultasProfile.objects.get_or_create(kode_fakultas=r["kode_fakultas"])
            berubah += _terapkan(fp, {k: r[k] for k in ("visi", "misi", "tujuan", "sasaran")},
                                 log, f"Fakultas {r['kode_fakultas']}")
    for r in prodi_rows:
        pp, _ = ProdiProfile.objects.get_or_create(kode_prodi=r["kode_prodi"])
        berubah += _terapkan(pp, {
            "visi": r["visi_keilmuan"], "misi": r["misi"], "tujuan": r["tujuan"],
            "profil_lulusan": r["profil_lulusan"], "sasaran": r["sasaran"],
        }, log, f"Prodi {r['kode_prodi']}")
    from core.cache_utils import invalidate_publik
    invalidate_publik()
    cakupan = "" if kode_prodi else " + universitas"
    return f"VMTS: {len(fak_kode)} fakultas, {len(prodi_rows)} prodi{cakupan} | {berubah} profil berubah"


def sinkron_cache(user, kode_prodi="", log=print):
    cache.clear()
    log("Cache dibersihkan (beranda publik, sidebar, kelengkapan, badge notifikasi/verifikasi).")
    return "Cache dibersihkan"


FUNGSI = {
    "RPS": sinkron_rps,
    "DTPS": sinkron_dtps,
    "TAUTAN": sinkron_tautan,
    "VMTS": sinkron_vmts,
    "CACHE": sinkron_cache,
}


# =========================================================
# RUNNER (dipakai command `sinkron`)
# =========================================================

def jalankan(log_obj, user):
    """Eksekusi 1 SinkronLog. Menulis status, ringkasan, dan output ke log."""
    baris = []

    def tulis(teks):
        baris.append(str(teks))

    bentrok = sedang_berjalan(log_obj.jenis, kecuali_pk=log_obj.pk)
    if bentrok:
        log_obj.status = SinkronLog.Status.GAGAL
        log_obj.ringkasan = f"Dibatalkan: sinkron {bentrok.get_jenis_display()} lain masih berjalan."
        log_obj.selesai = timezone.now()
        log_obj.save()
        return log_obj

    log_obj.status = SinkronLog.Status.BERJALAN
    log_obj.save(update_fields=["status"])
    jenis_list = URUTAN_SEMUA if log_obj.jenis == SinkronLog.Jenis.SEMUA else [log_obj.jenis]
    ringkas, gagal = [], False
    for jenis in jenis_list:
        tulis(f"=== {SinkronLog.Jenis(jenis).label} ===")
        try:
            ringkas.append(FUNGSI[jenis](user, kode_prodi=log_obj.lingkup, log=tulis))
        except Exception as exc:  # satu jenis gagal tidak menghentikan jenis berikutnya
            gagal = True
            ringkas.append(f"{jenis}: GAGAL ({type(exc).__name__})")
            tulis(f"GAGAL: {type(exc).__name__}: {exc}")
        # simpan progres berkala supaya halaman status bisa menampilkan output berjalan
        SinkronLog.objects.filter(pk=log_obj.pk).update(output="\n".join(baris)[-60000:])

    log_obj.status = SinkronLog.Status.GAGAL if gagal else SinkronLog.Status.SUKSES
    log_obj.ringkasan = " | ".join(ringkas)[:500]
    log_obj.output = "\n".join(baris)[-60000:]
    log_obj.selesai = timezone.now()
    log_obj.save()
    return log_obj
