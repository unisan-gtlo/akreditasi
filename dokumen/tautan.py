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
