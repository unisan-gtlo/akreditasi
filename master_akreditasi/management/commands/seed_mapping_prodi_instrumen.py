"""Seed mapping prodi UNISAN ke instrumen akreditasi."""
from django.core.management.base import BaseCommand
from master_akreditasi.models import MappingProdiInstrumen, Instrumen


# Mapping definitif UNISAN
MAPPING_UNISAN = {
    # LAMEMBA
    "E11": "LAMEMBA",
    "E21": "LAMEMBA",
    "ES2": "LAMEMBA",

    # LAM Teknik
    "T11": "LAM Teknik",
    "T21": "LAM Teknik",

    # LAM Infokom
    "K11": "LAM Infokom",
    "T31": "LAM Infokom",

    # LAMSPAK
    "S21": "LAMSPAK",
    "S22": "LAMSPAK",
    "SS2": "LAMSPAK",

    # BAN-PT IAPS 4.0
    "H11": "BAN-PT IAPS 4.0",
    "HS2": "BAN-PT IAPS 4.0",
    "P21": "BAN-PT IAPS 4.0",
    "P22": "BAN-PT IAPS 4.0",
    "P23": "BAN-PT IAPS 4.0",
    "T41": "BAN-PT IAPS 4.0",
}


class Command(BaseCommand):
    help = "Seed mapping prodi UNISAN ke instrumen akreditasi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hapus semua mapping dulu sebelum seed ulang",
        )

    def handle(self, *args, **opts):
        if opts["reset"]:
            count = MappingProdiInstrumen.objects.count()
            MappingProdiInstrumen.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} existing mapping(s)"))

        # Get all instrumen
        instrumen_map = {}
        for ins in Instrumen.objects.all():
            instrumen_map[ins.nama_singkat] = ins
            # Try alternative names too
            instrumen_map[ins.nama_singkat.upper()] = ins

        if not instrumen_map:
            self.stdout.write(self.style.ERROR(
                "Tidak ada Instrumen di database. Jalankan dulu seed instrumen."
            ))
            return

        # Show available instrumen
        self.stdout.write("\nInstrumen tersedia:")
        unique_ins = set(instrumen_map.values())
        for ins in unique_ins:
            self.stdout.write(f"  - {ins.nama_singkat}")

        # Seed mapping
        created_count = 0
        skipped_count = 0
        not_found = []

        for kode_prodi, nama_instrumen in MAPPING_UNISAN.items():
            ins = instrumen_map.get(nama_instrumen) or instrumen_map.get(nama_instrumen.upper())

            if not ins:
                not_found.append((kode_prodi, nama_instrumen))
                continue

            obj, created = MappingProdiInstrumen.objects.update_or_create(
                kode_prodi=kode_prodi,
                instrumen=ins,
                defaults={"aktif": True},
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  + {kode_prodi} -> {ins.nama_singkat}"
                ))
            else:
                skipped_count += 1
                self.stdout.write(f"  = {kode_prodi} -> {ins.nama_singkat} (already exists)")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Created: {created_count}"))
        self.stdout.write(f"Skipped (existing): {skipped_count}")

        if not_found:
            self.stdout.write(self.style.ERROR(f"\nNot found ({len(not_found)} mapping):"))
            for kode, nama_ins in not_found:
                self.stdout.write(self.style.ERROR(
                    f"  {kode} -> {nama_ins} (instrumen tidak ada)"
                ))
            self.stdout.write(self.style.WARNING(
                "\nTip: Cek nama instrumen di Django Admin dan pastikan match"
            ))