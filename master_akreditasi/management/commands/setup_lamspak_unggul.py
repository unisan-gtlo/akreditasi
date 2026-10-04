"""
Buat instrumen LAMSPAK Unggul (11 Standar) dari master_akreditasi/data/lamspak_unggul.json.

Sub-Standar & Butir Dokumen TIDAK dibuat di sini; masuk lewat menu
Import Excel (file LAMSPAK-UNGGUL_import.xlsx) supaya ada preview + log.

Pakai:
    python manage.py setup_lamspak_unggul --dry-run
    python manage.py setup_lamspak_unggul --map-prodi S21
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from master_akreditasi.models import Instrumen, MappingProdiInstrumen, Standar

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "lamspak_unggul.json"


class Command(BaseCommand):
    help = "Buat/perbarui instrumen LAMSPAK Unggul + 11 standar, opsional pindahkan mapping prodi."

    def add_arguments(self, parser):
        parser.add_argument("--map-prodi", nargs="*", default=[], metavar="KODE",
                            help="Kode prodi yang dipindah ke LAMSPAK Unggul, contoh: S21")
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan rencana tanpa menyimpan.")

    def handle(self, *args, **opts):
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        info = data["instrumen"]
        dry_run = opts["dry_run"]

        with transaction.atomic():
            instrumen, created = Instrumen.objects.update_or_create(
                kode=info["kode"],
                defaults={k: v for k, v in info.items() if k != "kode"},
            )
            self.stdout.write(f"Instrumen {instrumen.kode}: {'DIBUAT' if created else 'diperbarui'}")

            for idx, std in enumerate(data["standar"], start=1):
                obj, std_created = Standar.objects.update_or_create(
                    instrumen=instrumen,
                    nomor=std["nomor"],
                    defaults={
                        "nama": std["nama"],
                        "deskripsi": std["deskripsi"],
                        "urutan": idx,
                        "aktif": True,
                    },
                )
                self.stdout.write(
                    f"  Standar {obj.nomor}: {obj.nama} "
                    f"({'baru' if std_created else 'diperbarui'}, {len(std['butir'])} butir di file import)"
                )

            for kode_prodi in opts["map_prodi"]:
                kode_prodi = kode_prodi.strip().upper()
                try:
                    mapping = MappingProdiInstrumen.objects.select_related("instrumen").get(kode_prodi=kode_prodi)
                except MappingProdiInstrumen.DoesNotExist:
                    raise CommandError(f"Mapping prodi {kode_prodi} tidak ditemukan.")
                lama = mapping.instrumen.kode
                mapping.instrumen = instrumen
                mapping.save()
                self.stdout.write(f"  Mapping {kode_prodi} ({mapping.nama_prodi}): {lama} -> {instrumen.kode}")

                from sesi.models import SesiAkreditasi
                sesi_lama = SesiAkreditasi.objects.filter(kode_prodi=kode_prodi).exclude(instrumen=instrumen)
                for s in sesi_lama:
                    self.stdout.write(self.style.WARNING(
                        f"    Catatan: sesi #{s.pk} '{s}' masih memakai instrumen {s.instrumen.kode} (tidak diubah)"
                    ))

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("DRY RUN: tidak ada yang disimpan."))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "Selesai. Lanjutkan: menu Import Excel -> pilih instrumen LAMSPAK Unggul -> unggah LAMSPAK-UNGGUL_import.xlsx"
                ))
