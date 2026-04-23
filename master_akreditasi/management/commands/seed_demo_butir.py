"""
Management command: seed contoh SubStandar + ButirDokumen untuk 5 instrumen.

Tujuan: supaya tree view dan tampilan punya data dummy yang representatif.
Data ini BUKAN data resmi dari BAN-PT/LAM — hanya contoh terstruktur.
Admin akan replace dengan data resmi via Import Excel nanti.

Usage:
    python manage.py seed_demo_butir           # isi contoh (idempotent)
    python manage.py seed_demo_butir --reset   # hapus dulu lalu isi ulang
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from master_akreditasi.models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    KategoriKepemilikan,
)


# =========================================================
# TEMPLATE STRUKTUR CONTOH
# =========================================================
# Struktur: untuk tiap (instrumen, nomor_standar), kita definisikan
# sub-standar (bisa bertingkat) dan butir dokumen di bawahnya.
#
# Format:
#   {
#     "nomor": "X.Y",
#     "nama": "...",
#     "butir": [ { "kode": ..., "nama": ..., "kategori": ..., ...} ],
#     "children": [ sub-standar lagi kalau perlu ],
#   }


# Butir UNIVERSITAS — dipakai di hampir semua standar
BUTIR_VMTS_UNIV = [
    {
        "kode": "VMTS-1", "nama": "Dokumen SK Senat: Visi, Misi, Tujuan, Sasaran UNISAN",
        "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF",
        "deskripsi": "SK Senat Akademik yang mengesahkan VMTS institusi.",
    },
    {
        "kode": "VMTS-2", "nama": "Rencana Strategis (Renstra) UNISAN 5 Tahun",
        "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF",
    },
]


# =========================================================
# DATA SEED — Per Instrumen per Standar
# =========================================================

SEED_STRUKTUR = {
    # ==================== IAPS40 (BAN-PT) ====================
    "IAPS40": {
        "1": {  # Visi, Misi, Tujuan, dan Strategi
            "children": [
                {
                    "nomor": "1.1", "nama": "Kejelasan, Kerealistikan, dan Keterkaitan VMTS",
                    "butir": [
                        *BUTIR_VMTS_UNIV,
                        {"kode": "1.1-F", "nama": "Dokumen VMTS Fakultas (selaras UNISAN)",
                         "kategori": "FAKULTAS", "wajib": True, "format": "PDF"},
                        {"kode": "1.1-P", "nama": "Dokumen VMTS Program Studi (selaras Fakultas)",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "1.2", "nama": "Strategi Pencapaian VMTS",
                    "butir": [
                        {"kode": "1.2-P", "nama": "Dokumen strategi pencapaian VMTS prodi (5 tahun)",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                        {"kode": "1.2-P2", "nama": "Laporan monitoring evaluasi pencapaian VMTS",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
            ],
        },
        "2": {  # Tata Pamong, Tata Kelola, dan Kerjasama
            "children": [
                {
                    "nomor": "2.1", "nama": "Sistem Tata Pamong",
                    "butir": [
                        {"kode": "2.1-U", "nama": "Statuta UNISAN",
                         "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF"},
                        {"kode": "2.1-U2", "nama": "Struktur Organisasi & Tata Kerja (OTK)",
                         "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "2.2", "nama": "Kepemimpinan Operasional, Organisasi, dan Publik",
                    "butir": [
                        {"kode": "2.2-P", "nama": "Rekam jejak kepemimpinan Kaprodi (3 tahun)",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "2.3", "nama": "Kerjasama",
                    "butir": [
                        {"kode": "2.3-P", "nama": "Daftar MoU/PKS mitra kerjasama prodi",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                        {"kode": "2.3-P2", "nama": "Scan MoU/PKS aktif (last 3 years)",
                         "kategori": "PRODI", "wajib": False, "format": "PDF"},
                    ],
                },
            ],
        },
        "3": {  # Mahasiswa
            "children": [
                {
                    "nomor": "3.1", "nama": "Kualitas Input Mahasiswa",
                    "butir": [
                        {"kode": "3.1-U", "nama": "Kebijakan PMB UNISAN",
                         "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF"},
                        {"kode": "3.1-P", "nama": "Data pendaftar & diterima prodi (5 tahun)",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    ],
                },
                {
                    "nomor": "3.2", "nama": "Layanan Kemahasiswaan",
                    "butir": [
                        {"kode": "3.2-B", "nama": "Pedoman layanan BAKM (Biro Akademik & Kemahasiswaan)",
                         "kategori": "BIRO", "wajib": True, "format": "PDF"},
                    ],
                },
            ],
        },
        "4": {  # SDM
            "children": [
                {
                    "nomor": "4.1", "nama": "Profil Dosen",
                    "butir": [
                        {"kode": "4.1-P", "nama": "CV Dosen Tetap Prodi",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                        {"kode": "4.1-P2", "nama": "Sertifikat Jabatan Fungsional (JAFA) Dosen",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "4.2", "nama": "Tenaga Kependidikan",
                    "butir": [
                        {"kode": "4.2-B", "nama": "Profil Tendik & struktur SDM biro",
                         "kategori": "BIRO", "wajib": True, "format": "XLSX"},
                    ],
                },
            ],
        },
        "5": {  # Keuangan, Sarana, Prasarana
            "children": [
                {
                    "nomor": "5.1", "nama": "Keuangan",
                    "butir": [
                        {"kode": "5.1-U", "nama": "Laporan Keuangan UNISAN (3 tahun)",
                         "kategori": "UNIVERSITAS", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "5.2", "nama": "Sarana & Prasarana",
                    "butir": [
                        {"kode": "5.2-F", "nama": "Daftar sarana & prasarana Fakultas",
                         "kategori": "FAKULTAS", "wajib": True, "format": "XLSX"},
                        {"kode": "5.2-P", "nama": "Daftar lab & fasilitas khusus prodi",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    ],
                },
            ],
        },
        "6": {  # Pendidikan
            "children": [
                {
                    "nomor": "6.1", "nama": "Kurikulum",
                    "butir": [
                        {"kode": "6.1-P", "nama": "Dokumen Kurikulum Prodi (Profil Lulusan, CPL, MK, SKS)",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                        {"kode": "6.1-P2", "nama": "RPS (Rencana Pembelajaran Semester) semua MK",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
                {
                    "nomor": "6.2", "nama": "Pelaksanaan Pembelajaran",
                    "butir": [
                        {"kode": "6.2-P", "nama": "Laporan hasil monev pembelajaran per semester",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    ],
                },
            ],
        },
        "7": {  # Penelitian
            "children": [
                {
                    "nomor": "7.1", "nama": "Produktivitas Penelitian",
                    "butir": [
                        {"kode": "7.1-B", "nama": "Roadmap Penelitian UNISAN dari LP2M",
                         "kategori": "BIRO", "wajib": True, "format": "PDF"},
                        {"kode": "7.1-P", "nama": "Daftar publikasi dosen prodi (Scopus/Sinta)",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    ],
                },
            ],
        },
        "8": {  # PkM
            "children": [
                {
                    "nomor": "8.1", "nama": "Produktivitas PkM",
                    "butir": [
                        {"kode": "8.1-B", "nama": "Roadmap PkM UNISAN dari LP2M",
                         "kategori": "BIRO", "wajib": True, "format": "PDF"},
                        {"kode": "8.1-P", "nama": "Daftar kegiatan PkM dosen prodi",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    ],
                },
            ],
        },
        "9": {  # Luaran Tridharma
            "children": [
                {
                    "nomor": "9.1", "nama": "Capaian Lulusan",
                    "butir": [
                        {"kode": "9.1-P", "nama": "Tracer Study Lulusan (3 tahun)",
                         "kategori": "PRODI", "wajib": True, "format": "PDF"},
                        {"kode": "9.1-P2", "nama": "Masa tunggu kerja & kesesuaian bidang",
                         "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    ],
                },
                {
                    "nomor": "9.2", "nama": "Luaran Penelitian & PkM",
                    "butir": [
                        {"kode": "9.2-P", "nama": "HKI / Paten / Buku dosen prodi",
                         "kategori": "PRODI", "wajib": False, "format": "PDF"},
                    ],
                },
            ],
        },
    },

    # ==================== LAMTEKNIK ====================
    "LAMTEKNIK": {
        "1": {
            "children": [{
                "nomor": "1.1", "nama": "VMTS Prodi Teknik",
                "butir": [
                    {"kode": "LT-1.1-P", "nama": "Dokumen VMTS prodi teknik (spesifik keteknikan)",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "2": {
            "children": [{
                "nomor": "2.1", "nama": "Tata Pamong Prodi Teknik",
                "butir": [
                    {"kode": "LT-2.1-P", "nama": "SK Kaprodi & struktur organisasi prodi",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "4": {
            "children": [{
                "nomor": "4.1", "nama": "Dosen Teknik (Sertifikasi PII)",
                "butir": [
                    {"kode": "LT-4.1-P", "nama": "Daftar Dosen dengan Sertifikat Insinyur Profesional (IP)",
                     "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                ],
            }],
        },
        "6": {
            "children": [{
                "nomor": "6.1", "nama": "Kurikulum OBE Teknik",
                "butir": [
                    {"kode": "LT-6.1-P", "nama": "Kurikulum Outcome-Based Education (OBE) prodi teknik",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    {"kode": "LT-6.1-P2", "nama": "Assessment CPL berbasis OBE",
                     "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                ],
            }],
        },
    },

    # ==================== LAMINFOKOM ====================
    "LAMINFOKOM": {
        "1": {
            "children": [{
                "nomor": "1.1", "nama": "VMTS Prodi Informatika & Komputer",
                "butir": [
                    {"kode": "LI-1.1-P", "nama": "VMTS prodi (mengacu body of knowledge ACM/IEEE)",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "4": {
            "children": [{
                "nomor": "4.1", "nama": "Dosen Bidang Komputer",
                "butir": [
                    {"kode": "LI-4.1-P", "nama": "Sertifikasi profesi IT dosen (CISSP, CCNA, Oracle, dll)",
                     "kategori": "PRODI", "wajib": False, "format": "PDF"},
                ],
            }],
        },
        "6": {
            "children": [{
                "nomor": "6.1", "nama": "Kurikulum Berbasis ACM/IEEE",
                "butir": [
                    {"kode": "LI-6.1-P", "nama": "Pemetaan kurikulum ke body of knowledge ACM/IEEE",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    {"kode": "LI-6.1-P2", "nama": "Silabus praktikum lab komputer",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
    },

    # ==================== LAMEMBA ====================
    "LAMEMBA": {
        "1": {
            "children": [{
                "nomor": "1.1", "nama": "VMTS Prodi EMBA (International Benchmark)",
                "butir": [
                    {"kode": "EM-1.1-P", "nama": "VMTS prodi (selaras standar AACSB/EQUIS)",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "4": {
            "children": [{
                "nomor": "4.1", "nama": "Kualifikasi Dosen Ekonomi/Bisnis",
                "butir": [
                    {"kode": "EM-4.1-P", "nama": "CV dosen + daftar publikasi terindeks Scopus/WoS",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "6": {
            "children": [{
                "nomor": "6.1", "nama": "Kurikulum EMBA Internasional",
                "butir": [
                    {"kode": "EM-6.1-P", "nama": "Kurikulum dengan muatan internasional (20% minimum)",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                    {"kode": "EM-6.1-P2", "nama": "Case method & exam sample international standard",
                     "kategori": "PRODI", "wajib": False, "format": "PDF"},
                ],
            }],
        },
    },

    # ==================== LAMSPAK ====================
    "LAMSPAK": {
        "1": {
            "children": [{
                "nomor": "1.1", "nama": "VMTS Prodi Sosial-Politik-Administrasi-Komunikasi",
                "butir": [
                    {"kode": "SP-1.1-P", "nama": "VMTS prodi (fokus pada sosial-kemasyarakatan)",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "6": {
            "children": [{
                "nomor": "6.1", "nama": "Kurikulum Berbasis Riset Sosial",
                "butir": [
                    {"kode": "SP-6.1-P", "nama": "Kurikulum dengan metodologi penelitian sosial",
                     "kategori": "PRODI", "wajib": True, "format": "PDF"},
                ],
            }],
        },
        "7": {
            "children": [{
                "nomor": "7.1", "nama": "Penelitian Sosial & Kebijakan Publik",
                "butir": [
                    {"kode": "SP-7.1-P", "nama": "Daftar penelitian dosen di bidang sosial/kebijakan publik",
                     "kategori": "PRODI", "wajib": True, "format": "XLSX"},
                    {"kode": "SP-7.1-P2", "nama": "Laporan kajian kebijakan untuk pemda/stakeholder",
                     "kategori": "PRODI", "wajib": False, "format": "PDF"},
                ],
            }],
        },
    },
}


# =========================================================
# COMMAND
# =========================================================

class Command(BaseCommand):
    help = "Seed contoh SubStandar + ButirDokumen untuk 5 instrumen (data dummy)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hapus SubStandar & ButirDokumen dulu sebelum seed",
        )

    def handle(self, *args, **options):
        reset = options["reset"]

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO("SEED DEMO DATA — SubStandar + ButirDokumen"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))

        with transaction.atomic():
            if reset:
                self.stdout.write(self.style.WARNING("\n[RESET] Menghapus SubStandar & Butir lama..."))
                ButirDokumen.objects.all().delete()
                SubStandar.objects.all().delete()
                self.stdout.write(self.style.SUCCESS("  ✓ Data lama dihapus"))

            total_substandar = 0
            total_butir = 0

            for kode_instrumen, standar_map in SEED_STRUKTUR.items():
                try:
                    instrumen = Instrumen.objects.get(kode=kode_instrumen)
                except Instrumen.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"\n  ⚠ Instrumen {kode_instrumen} tidak ditemukan, skip"
                    ))
                    continue

                self.stdout.write(f"\n[{instrumen.nama_singkat}]")

                for nomor_std, std_data in standar_map.items():
                    try:
                        standar = Standar.objects.get(
                            instrumen=instrumen, nomor=nomor_std
                        )
                    except Standar.DoesNotExist:
                        continue

                    for i, ss_data in enumerate(std_data.get("children", []), 1):
                        ss_count, b_count = self._create_substandar(
                            standar=standar,
                            parent=None,
                            ss_data=ss_data,
                            urutan=i,
                        )
                        total_substandar += ss_count
                        total_butir += b_count

                    self.stdout.write(
                        f"  ✓ Kriteria {nomor_std}: "
                        f"{len(std_data.get('children', []))} sub-standar"
                    )

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("SEED DEMO SELESAI"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  SubStandar dibuat : {total_substandar}")
        self.stdout.write(f"  Butir Dokumen     : {total_butir}")
        self.stdout.write("")
        self.stdout.write("Total di database sekarang:")
        self.stdout.write(f"  SubStandar   : {SubStandar.objects.count()}")
        self.stdout.write(f"  ButirDokumen : {ButirDokumen.objects.count()}")
        self.stdout.write("")
        self.stdout.write("Test di: http://127.0.0.1:8000/master/instrumen/")
        self.stdout.write("")

    def _create_substandar(self, standar, parent, ss_data, urutan):
        """Buat sub-standar + butir + rekursif children. Return (ss_count, b_count)."""
        ss_count = 0
        b_count = 0

        ss, created = SubStandar.objects.update_or_create(
            standar=standar,
            nomor=ss_data["nomor"],
            defaults={
                "parent": parent,
                "nama": ss_data["nama"],
                "deskripsi": ss_data.get("deskripsi", ""),
                "panduan": ss_data.get("panduan", ""),
                "urutan": urutan,
                "aktif": True,
            },
        )
        ss_count += 1

        # Butir dokumen
        for j, butir_data in enumerate(ss_data.get("butir", []), 1):
            _, bcreated = ButirDokumen.objects.update_or_create(
                sub_standar=ss,
                kode=butir_data["kode"],
                defaults={
                    "nama_dokumen": butir_data["nama"],
                    "deskripsi": butir_data.get("deskripsi", ""),
                    "panduan_dokumen": butir_data.get("panduan", ""),
                    "kategori_kepemilikan": butir_data["kategori"],
                    "wajib": butir_data.get("wajib", True),
                    "format_diterima": butir_data.get("format", "PDF"),
                    "ukuran_max_mb": butir_data.get("ukuran_max_mb", 50),
                    "status_akses_default": butir_data.get("status_akses", "INTERNAL"),
                    "urutan": j,
                    "aktif": True,
                },
            )
            b_count += 1

        # Rekursif anak sub-standar
        for k, child_data in enumerate(ss_data.get("children", []), 1):
            c_ss, c_b = self._create_substandar(
                standar=standar,
                parent=ss,
                ss_data=child_data,
                urutan=k,
            )
            ss_count += c_ss
            b_count += c_b

        return ss_count, b_count