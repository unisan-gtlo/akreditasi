"""
Isi dokumen bertipe Tautan Aplikasi untuk butir bukti aplikasi kampus
(daftar: dokumen/tautan.py TAUTAN_APLIKASI). Idempoten.

    python manage.py isi_tautan_aplikasi            # preview
    python manage.py isi_tautan_aplikasi --apply    # simpan
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import User
from dokumen.tautan import isi_tautan_aplikasi


class Command(BaseCommand):
    help = "Buat dokumen Tautan Aplikasi (LMS, SIAKAD, Digital Library, SIAMI) di butir bukti aplikasi."

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
        baru = isi_tautan_aplikasi(user, apply=opts["apply"], log=self.stdout.write)
        if not opts["apply"] and baru:
            self.stdout.write(self.style.WARNING("Preview saja. Tambahkan --apply untuk menyimpan."))
