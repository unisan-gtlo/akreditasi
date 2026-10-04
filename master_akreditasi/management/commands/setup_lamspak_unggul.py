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

# Butir Standar 6 yang buktinya diambil dari data dosen SIMDA (per DTPS sesi)
DATA_DOSEN_MAPPING = {
    "U6.01": ("SK_PENGANGKATAN", "AKTIF_SAJA", "SK pengangkatan dosen tetap tiap DTPS (SIMDA data dosen)."),
    "U6.02": ("PROFIL", "AKTIF_SAJA", "NIDN & homebase tiap DTPS sebagai bukti terdaftar pada prodi (SIMDA)."),
    "U6.03": ("PENDIDIKAN", "SEMUA", "Ijazah & transkrip tiap jenjang pendidikan DTPS (SIMDA)."),
    "U6.04": ("JABFUNG", "SEMUA", "SK jabatan akademik DTPS; dosen tanpa jabatan akademik tidak dihitung."),
    "U6.05": ("SERDOS", "AKTIF_SAJA", "Sertifikat pendidik DTPS yang sudah tersertifikasi (SIMDA)."),
    "U6.10": ("BKD", "TS_TS_M1_TS_M2", "BKD/LKD DTPS 3 tahun terakhir (TS, TS-1, TS-2) dari SIMDA."),
    "U9.15": ("ID_AKADEMIK", "AKTIF_SAJA",
              "Tautan profil SINTA, Google Scholar, Scopus, ORCID & Garuda tiap DTPS (SIMDA). "
              "Lengkap bila dosen punya profil SINTA atau Google Scholar."),
}


class Command(BaseCommand):
    help = "Buat/perbarui instrumen LAMSPAK Unggul + 11 standar, opsional pindahkan mapping prodi."

    def add_arguments(self, parser):
        parser.add_argument("--map-prodi", nargs="*", default=[], metavar="KODE",
                            help="Kode prodi yang dipindah ke LAMSPAK Unggul, contoh: S21")
        parser.add_argument("--sync-kode-bersama", action="store_true",
                            help="Isi kode_bersama (+ panduan) butir yang sudah diimport, dari file JSON.")
        parser.add_argument("--sync-data-dosen", action="store_true",
                            help="Petakan butir U6.xx ke data dosen SIMDA (ButirDataDosenMapping).")
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

            if opts["sync_kode_bersama"]:
                self._sync_kode_bersama(instrumen, data)

            if opts["sync_data_dosen"]:
                self._sync_data_dosen(instrumen)

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("DRY RUN: tidak ada yang disimpan."))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "Selesai. Lanjutkan: menu Import Excel -> pilih instrumen LAMSPAK Unggul -> unggah LAMSPAK-UNGGUL_import.xlsx"
                ))

    def _sync_kode_bersama(self, instrumen, data):
        from master_akreditasi.models import ButirDokumen

        target = {
            b["kode"]: (b.get("kode_bersama", ""), b.get("panduan_dokumen", ""))
            for std in data["standar"] for b in std["butir"]
        }
        changed = missing = 0
        butirs = {b.kode: b for b in ButirDokumen.objects.filter(sub_standar__standar__instrumen=instrumen)}
        for kode, (kode_bersama, panduan) in target.items():
            butir = butirs.get(kode)
            if butir is None:
                missing += 1
                continue
            if butir.kode_bersama != kode_bersama or butir.panduan_dokumen != panduan:
                butir.kode_bersama = kode_bersama
                butir.panduan_dokumen = panduan
                butir.save(update_fields=["kode_bersama", "panduan_dokumen", "tanggal_diubah"])
                changed += 1
        terisi = sum(1 for v, _ in target.values() if v)
        self.stdout.write(
            f"  Kode bersama: {changed} butir diperbarui, {terisi} butir punya kode, "
            f"{missing} butir belum ada di database (import Excel dulu)."
        )

    def _sync_data_dosen(self, instrumen):
        from master_akreditasi.models import ButirDokumen
        from master_akreditasi.models_dosen_link import ButirDataDosenMapping

        for kode, (jenis, filter_periode, keterangan) in DATA_DOSEN_MAPPING.items():
            butir = ButirDokumen.objects.filter(sub_standar__standar__instrumen=instrumen, kode=kode).first()
            if butir is None:
                self.stdout.write(self.style.WARNING(f"  {kode}: butir tidak ditemukan (import Excel dulu)"))
                continue
            _m, created = ButirDataDosenMapping.objects.update_or_create(
                butir=butir,
                defaults={
                    "jenis_data": jenis,
                    "filter_periode": filter_periode,
                    "deskripsi_filter": keterangan,
                    "aktif": True,
                },
            )
            self.stdout.write(f"  Data dosen {kode} {butir.nama_dokumen[:35]:35} -> {jenis} ({'baru' if created else 'diperbarui'})")
