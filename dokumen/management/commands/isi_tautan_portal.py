"""
Isi dokumen Tautan Portal UNISAN (prodi, fakultas, universitas) + Portal Alumni
untuk satu prodi (daftar: dokumen/tautan.py TAUTAN_PORTAL). Idempoten.

Slug diambil dari Mapping Prodi (portal_slug, portal_fakultas_slug); --slug dan
--fakultas-slug bisa dipakai untuk menimpa sementara.

    python manage.py isi_tautan_portal --prodi S21            # preview
    python manage.py isi_tautan_portal --prodi S21 --apply    # simpan
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import User
from dokumen.tautan import isi_tautan_portal
from master_akreditasi.models import MappingProdiInstrumen


class Command(BaseCommand):
    help = "Buat dokumen tautan Portal UNISAN & Portal Alumni untuk butir instrumen satu prodi."

    def add_arguments(self, parser):
        parser.add_argument("--prodi", required=True, help="Kode prodi, mis. S21")
        parser.add_argument("--slug", default="", help="Slug prodi di portal (default: dari Mapping Prodi)")
        parser.add_argument("--fakultas-slug", default="", help="Slug fakultas di portal (default: dari Mapping Prodi)")
        parser.add_argument("--apply", action="store_true", help="Simpan (default: preview)")
        parser.add_argument("--as-user", default="", help="Username pencatat (default: superuser pertama)")

    def handle(self, *args, **o):
        mapping = MappingProdiInstrumen.objects.select_related("instrumen").filter(
            kode_prodi=o["prodi"].strip().upper(), aktif=True).first()
        if mapping is None:
            raise CommandError(f"Mapping prodi {o['prodi']} tidak ditemukan.")
        if o["slug"]:
            mapping.portal_slug = o["slug"]
        if o["fakultas_slug"]:
            mapping.portal_fakultas_slug = o["fakultas_slug"]
        user = (
            User.objects.filter(username=o["as_user"], is_active=True).first() if o["as_user"]
            else User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        )
        if user is None:
            raise CommandError("User pencatat tidak ditemukan.")
        baru = isi_tautan_portal(mapping, user, apply=o["apply"], log=self.stdout.write)
        self.stdout.write(f"{baru} tautan baru.")
        if not o["apply"] and baru:
            self.stdout.write(self.style.WARNING("Preview saja. Tambahkan --apply untuk menyimpan."))
