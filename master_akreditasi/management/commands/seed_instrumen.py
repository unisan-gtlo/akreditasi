"""
Management command: seed 5 instrumen akreditasi UNISAN + mapping 16 prodi.

Usage:
    python manage.py seed_instrumen           # buat/update (idempotent)
    python manage.py seed_instrumen --reset   # hapus semua dulu lalu buat ulang
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connection

from master_akreditasi.models import (
    Instrumen,
    Standar,
    MappingProdiInstrumen,
)


# =========================================================
# DATA 5 INSTRUMEN AKREDITASI UNISAN
# =========================================================

INSTRUMEN_DATA = [
    {
        "kode": "IAPS40",
        "nama_resmi": "Instrumen Akreditasi Program Studi 4.0 BAN-PT",
        "nama_singkat": "BAN-PT IAPS 4.0",
        "versi": "4.0",
        "lembaga": "BAN-PT",
        "label_standar": "Kriteria",
        "label_substandar": "Sub-Kriteria",
        "label_butir": "Butir Dokumen",
        "deskripsi": "Instrumen Akreditasi Program Studi versi 4.0 dari Badan Akreditasi Nasional Perguruan Tinggi (BAN-PT) berlaku untuk prodi di rumpun ilmu yang belum memiliki LAM spesifik.",
        "tahun_berlaku": "2018-sekarang",
        "url_referensi": "https://www.banpt.or.id",
        "urutan": 1,
    },
    {
        "kode": "LAMTEKNIK",
        "nama_resmi": "Instrumen Akreditasi Program Studi LAM Teknik",
        "nama_singkat": "LAM Teknik",
        "versi": "2024",
        "lembaga": "LAM Teknik (PII)",
        "label_standar": "Kriteria",
        "label_substandar": "Sub-Kriteria",
        "label_butir": "Butir Dokumen",
        "deskripsi": "Lembaga Akreditasi Mandiri Teknik yang diprakarsai oleh Persatuan Insinyur Indonesia (PII). Mengakreditasi prodi di rumpun keteknikan.",
        "tahun_berlaku": "2021-sekarang",
        "url_referensi": "https://lamteknik.or.id",
        "urutan": 2,
    },
    {
        "kode": "LAMINFOKOM",
        "nama_resmi": "Instrumen Akreditasi Program Studi LAM Informatika & Komputer",
        "nama_singkat": "LAM Infokom",
        "versi": "2024",
        "lembaga": "LAM Infokom (APTIKOM)",
        "label_standar": "Kriteria",
        "label_substandar": "Sub-Kriteria",
        "label_butir": "Butir Dokumen",
        "deskripsi": "Lembaga Akreditasi Mandiri Informatika dan Komputer yang diprakarsai oleh APTIKOM. Mengakreditasi prodi di rumpun informatika, komputer, sistem informasi, dan rekayasa perangkat lunak.",
        "tahun_berlaku": "2021-sekarang",
        "url_referensi": "https://laminfokom.or.id",
        "urutan": 3,
    },
    {
        "kode": "LAMEMBA",
        "nama_resmi": "Instrumen Akreditasi Program Studi LAMEMBA",
        "nama_singkat": "LAMEMBA",
        "versi": "2024",
        "lembaga": "LAMEMBA (ISEI, IAI, AFEBI)",
        "label_standar": "Kriteria",
        "label_substandar": "Sub-Kriteria",
        "label_butir": "Butir Dokumen",
        "deskripsi": "Lembaga Akreditasi Mandiri Ekonomi, Manajemen, Bisnis & Akuntansi. Diprakarsai oleh ISEI, IAI, dan AFEBI. Mengakreditasi prodi ekonomi, manajemen, bisnis, dan akuntansi.",
        "tahun_berlaku": "2022-sekarang",
        "url_referensi": "https://lamemba.or.id",
        "urutan": 4,
    },
    {
        "kode": "LAMSPAK",
        "nama_resmi": "Instrumen Akreditasi Program Studi LAMSPAK IAPS 2.0",
        "nama_singkat": "LAMSPAK",
        "versi": "2.0",
        "lembaga": "LAMSPAK",
        "label_standar": "Kriteria",
        "label_substandar": "Sub-Kriteria",
        "label_butir": "Butir Dokumen",
        "deskripsi": "Lembaga Akreditasi Mandiri Bidang Ilmu Sosial, Politik, Administrasi, dan Komunikasi. Resmi beroperasi sejak 22 Januari 2025. Instrumen IAPS 2.0 diluncurkan tahun 2026.",
        "tahun_berlaku": "2025-sekarang",
        "url_referensi": "https://www.lamspak.id",
        "urutan": 5,
    },
]


# =========================================================
# 9 KRITERIA STANDAR (Umum dipakai semua instrumen)
# =========================================================

STANDAR_9_KRITERIA = [
    {
        "nomor": "1", "urutan": 1,
        "nama": "Visi, Misi, Tujuan, dan Strategi",
        "bobot": 3.12,
        "deskripsi": "Kejelasan rumusan visi, misi, tujuan, strategi, dan keterkaitannya dengan pelaksanaan tri dharma.",
    },
    {
        "nomor": "2", "urutan": 2,
        "nama": "Tata Pamong, Tata Kelola, dan Kerjasama",
        "bobot": 6.25,
        "deskripsi": "Sistem tata pamong yang baik, kredibel, transparan, akuntabel, bertanggung jawab, dan adil, serta kerjasama yang mendukung visi misi.",
    },
    {
        "nomor": "3", "urutan": 3,
        "nama": "Mahasiswa",
        "bobot": 6.25,
        "deskripsi": "Kebijakan penerimaan, keragaman, kualitas, layanan, dan prestasi mahasiswa.",
    },
    {
        "nomor": "4", "urutan": 4,
        "nama": "Sumber Daya Manusia",
        "bobot": 12.50,
        "deskripsi": "Kualitas dan kecukupan dosen dan tenaga kependidikan, serta pengembangan profesionalisme.",
    },
    {
        "nomor": "5", "urutan": 5,
        "nama": "Keuangan, Sarana, dan Prasarana",
        "bobot": 6.25,
        "deskripsi": "Kecukupan, aksesibilitas, dan kualitas sumber daya keuangan, sarana, dan prasarana untuk mendukung tri dharma.",
    },
    {
        "nomor": "6", "urutan": 6,
        "nama": "Pendidikan",
        "bobot": 18.75,
        "deskripsi": "Kurikulum, proses pembelajaran, suasana akademik, dan pencapaian capaian pembelajaran lulusan (CPL).",
    },
    {
        "nomor": "7", "urutan": 7,
        "nama": "Penelitian",
        "bobot": 6.25,
        "deskripsi": "Kebijakan, produktivitas, kualitas, dan relevansi penelitian dengan visi-misi prodi.",
    },
    {
        "nomor": "8", "urutan": 8,
        "nama": "Pengabdian kepada Masyarakat",
        "bobot": 6.25,
        "deskripsi": "Kebijakan, produktivitas, kualitas, dan relevansi PkM dengan visi-misi prodi serta kebutuhan masyarakat.",
    },
    {
        "nomor": "9", "urutan": 9,
        "nama": "Luaran dan Capaian Tridharma",
        "bobot": 34.38,
        "deskripsi": "Capaian pembelajaran lulusan, kinerja lulusan, publikasi, HKI, dan prestasi mahasiswa.",
    },
]


# =========================================================
# MAPPING 16 PRODI UNISAN
# =========================================================

# Format: (kode_prodi, nama_prodi, kode_instrumen)
MAPPING_PRODI = [
    # Fakultas Teknik → LAM Teknik
    ("T21", "S1 Teknik Elektro", "LAMTEKNIK"),
    ("T11", "S1 Teknik Arsitektur", "LAMTEKNIK"),

    # Fakultas Pertanian → BAN-PT
    ("P23", "S1 Teknologi Hasil Pertanian", "IAPS40"),
    ("P22", "S1 Agribisnis", "IAPS40"),
    ("P21", "S1 Agroteknologi", "IAPS40"),

    # Fakultas Ilmu Komputer → LAM Infokom (kecuali DKV → BAN-PT)
    ("T31", "S1 Teknik Informatika", "LAMINFOKOM"),
    ("K11", "S1 Sistem Informasi", "LAMINFOKOM"),
    ("T41", "S1 Desain Komunikasi Visual", "IAPS40"),

    # Fakultas Hukum → BAN-PT
    ("H11", "S1 Ilmu Hukum", "IAPS40"),

    # Fakultas Ekonomi → LAMEMBA
    ("E21", "S1 Manajemen", "LAMEMBA"),
    ("E11", "S1 Akuntansi", "LAMEMBA"),

    # Fakultas Ilmu Sosial & Politik → LAMSPAK
    ("S21", "S1 Ilmu Pemerintahan", "LAMSPAK"),
    ("S22", "S1 Ilmu Komunikasi", "LAMSPAK"),

    # Pascasarjana
    ("HS2", "S2 Ilmu Hukum", "IAPS40"),
    ("ES2", "S2 Manajemen", "LAMEMBA"),
    ("SS2", "S2 Ilmu Pemerintahan", "LAMSPAK"),
]


# =========================================================
# MANAGEMENT COMMAND
# =========================================================

class Command(BaseCommand):
    help = "Seed 5 instrumen akreditasi + 9 kriteria tiap instrumen + mapping 16 prodi UNISAN"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hapus semua data master akreditasi dulu sebelum seed",
        )

    def handle(self, *args, **options):
        reset = options["reset"]

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO("SEED DATA — MASTER AKREDITASI SIAKRED"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))

        with transaction.atomic():
            if reset:
                self.stdout.write(self.style.WARNING("\n[RESET] Menghapus data lama..."))
                MappingProdiInstrumen.objects.all().delete()
                Standar.objects.all().delete()
                Instrumen.objects.all().delete()
                self.stdout.write(self.style.SUCCESS("  ✓ Data lama dihapus"))

            # === 1. SEED INSTRUMEN ===
            self.stdout.write("\n[1/3] Menyeed 5 Instrumen Akreditasi...")
            instrumen_map = {}
            for data in INSTRUMEN_DATA:
                instrumen, created = Instrumen.objects.update_or_create(
                    kode=data["kode"],
                    defaults={k: v for k, v in data.items() if k != "kode"},
                )
                instrumen_map[data["kode"]] = instrumen
                status = "BARU" if created else "UPDATE"
                self.stdout.write(
                    f"  ✓ [{status}] {instrumen.nama_singkat} — {instrumen.lembaga}"
                )

            # === 2. SEED 9 STANDAR per INSTRUMEN ===
            self.stdout.write("\n[2/3] Menyeed 9 Kriteria untuk tiap instrumen...")
            total_standar = 0
            for kode_instrumen, instrumen in instrumen_map.items():
                count = 0
                for std_data in STANDAR_9_KRITERIA:
                    standar, created = Standar.objects.update_or_create(
                        instrumen=instrumen,
                        nomor=std_data["nomor"],
                        defaults={
                            "nama": std_data["nama"],
                            "deskripsi": std_data["deskripsi"],
                            "bobot": std_data["bobot"],
                            "urutan": std_data["urutan"],
                            "aktif": True,
                        },
                    )
                    count += 1
                    total_standar += 1
                self.stdout.write(
                    f"  ✓ {instrumen.nama_singkat}: {count} kriteria"
                )
            self.stdout.write(self.style.SUCCESS(
                f"  Total: {total_standar} standar berhasil di-seed"
            ))

            # === 3. SEED MAPPING PRODI ===
            self.stdout.write("\n[3/3] Menyeed Mapping 16 Prodi UNISAN → Instrumen...")

            # Validasi kode_prodi dari SIMDA (cross-schema)
            valid_prodi = self._get_valid_prodi_codes()

            total_mapping = 0
            for kode_prodi, nama_prodi, kode_instrumen in MAPPING_PRODI:
                if kode_prodi not in valid_prodi:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠ Prodi {kode_prodi} tidak ditemukan di SIMDA, skip"
                    ))
                    continue

                # Pakai nama_prodi dari SIMDA (lebih akurat daripada hardcode)
                nama_dari_simda = valid_prodi[kode_prodi]

                mapping, created = MappingProdiInstrumen.objects.update_or_create(
                    kode_prodi=kode_prodi,
                    defaults={
                        "nama_prodi": nama_dari_simda,
                        "instrumen": instrumen_map[kode_instrumen],
                        "aktif": True,
                    },
                )
                status = "BARU" if created else "UPDATE"
                instrumen_nama = instrumen_map[kode_instrumen].nama_singkat
                self.stdout.write(
                    f"  ✓ [{status}] {kode_prodi} ({nama_prodi}) → {instrumen_nama}"
                )
                total_mapping += 1

            self.stdout.write(self.style.SUCCESS(
                f"  Total: {total_mapping} mapping prodi berhasil di-seed"
            ))

        # === SUMMARY ===
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("SEED DATA SELESAI"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Instrumen     : {Instrumen.objects.count()}")
        self.stdout.write(f"  Standar       : {Standar.objects.count()}")
        self.stdout.write(f"  Mapping Prodi : {MappingProdiInstrumen.objects.count()}")
        self.stdout.write("")
        self.stdout.write("Langkah berikutnya:")
        self.stdout.write("  - Akses Django admin → /admin/master_akreditasi/")
        self.stdout.write("  - Input SubStandar dan ButirDokumen via admin atau UI CRUD")
        self.stdout.write("")

    def _get_valid_prodi_codes(self):
        """Query master.program_studi untuk dapat daftar kode_prodi yang valid."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT kode_prodi, nama_prodi FROM master.program_studi
            """)
            rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}