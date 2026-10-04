"""
Isi dokumen bertipe Tautan Aplikasi untuk butir bukti aplikasi kampus.

Butir dicari lewat kode_bersama, jadi berlaku di semua instrumen yang memakai
kode yang sama. Dokumen dibuat sebagai dokumen Universitas (scope kosong) agar
terhitung untuk semua prodi. Idempoten: tautan yang sudah ada dilewati.
Verifikasi dibiarkan PENDING (diverifikasi LPM seperti dokumen lain).

    python manage.py isi_tautan_aplikasi            # preview
    python manage.py isi_tautan_aplikasi --apply    # simpan
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import User
from dokumen.models import Dokumen, DokumenAccessLog, DokumenRevisi
from dokumen.views import _link_accessible
from master_akreditasi.models import ButirDokumen

TAUTAN = [
    # (kode_bersama, judul dokumen, url)
    ("UNIV-SCREENSHOT-REPOSITORY-DIGITAL-LIBRARY", "Tautan Digital Library / Repository (SIPERPUS)",
     "https://siperpus.unisan.ac.id/"),
    ("UNIV-SCREENSHOT-LMS", "Tautan LMS UNISAN", "https://lms.unisan.ac.id/"),
    ("UNIV-SCREENSHOT-SIAKAD", "Tautan SIAKAD UNISAN (SIAKUN)", "https://siakun.unisan.ac.id/"),
]


class Command(BaseCommand):
    help = "Buat dokumen Tautan Aplikasi (LMS, SIAKAD, Digital Library) di butir bukti aplikasi."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Simpan (default: preview)")
        parser.add_argument("--as-user", default="", help="Username pencatat (default: superuser pertama)")

    def handle(self, *args, **opts):
        user = (
            User.objects.filter(username=opts["as_user"], is_active=True).first() if opts["as_user"]
            else User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        )
        if user is None:
            raise CommandError("User pencatat tidak ditemukan.")

        for kode_bersama, judul, url in TAUTAN:
            butir = (
                ButirDokumen.objects.filter(kode_bersama=kode_bersama, aktif=True)
                .order_by("sub_standar__standar__instrumen__urutan", "kode").first()
            )
            if butir is None:
                self.stdout.write(self.style.WARNING(f"- {kode_bersama}: butir belum ada, dilewati"))
                continue
            group_ids = list(ButirDokumen.objects.filter(kode_bersama=kode_bersama).values_list("pk", flat=True))
            sudah = DokumenRevisi.objects.filter(
                dokumen__butir_dokumen_id__in=group_ids, dokumen__status=Dokumen.Status.FINAL,
                aktif=True, storage_type=DokumenRevisi.StorageType.LINK, gdrive_url=url,
            ).exists()
            if sudah:
                self.stdout.write(f"= {butir.kode} {judul}: sudah ada, dilewati")
                continue
            bisa = _link_accessible(url)
            self.stdout.write(f"+ {butir.kode} {judul} -> {url} ({'bisa diakses' if bisa else 'TIDAK bisa diakses'})")
            if not opts["apply"]:
                continue
            with transaction.atomic():
                dokumen = Dokumen.objects.create(
                    butir_dokumen=butir,
                    kategori_pemilik=butir.kategori_kepemilikan,
                    scope_kode_prodi="",
                    scope_kode_fakultas="",
                    judul=judul,
                    deskripsi="Tautan aplikasi untuk bukti sarana TIK. Lengkapi dengan screenshot di butir yang sama.",
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
                    original_filename=f"[Tautan] {url}",
                    extension="link",
                    aktif=True,
                    uploaded_by=user,
                    last_verified_at=timezone.now(),
                    is_link_broken=not bisa,
                )
                DokumenAccessLog.objects.create(
                    dokumen=dokumen, revisi=revisi, aksi=DokumenAccessLog.AksiType.UPLOAD,
                    user=user, catatan="Tautan aplikasi (isi_tautan_aplikasi)",
                )
        if not opts["apply"]:
            self.stdout.write(self.style.WARNING("Preview saja. Tambahkan --apply untuk menyimpan."))
