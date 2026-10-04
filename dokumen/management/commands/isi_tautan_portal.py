"""
Isi dokumen Tautan dari Portal UNISAN (prodi, fakultas, universitas) + Portal Alumni
ke butir instrumen prodi.

Scope dokumen mengikuti tingkat tautan:
    prodi    -> scope prodi (hanya terhitung untuk prodi tsb)
    fakultas -> scope fakultas/UPPS (prodi se-fakultas)
    univ     -> umum (semua prodi)
Idempoten: tautan dengan URL & scope sama di butir (grup kode bersama) dilewati.

    python manage.py isi_tautan_portal --prodi S21 --slug ilmu-pemerintahan --fakultas-slug fisip
    python manage.py isi_tautan_portal --prodi S21 --slug ilmu-pemerintahan --fakultas-slug fisip --apply
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import User
from dokumen.tautan import buat_dokumen_tautan, link_accessible, tautan_sudah_ada
from master_akreditasi.models import ButirDokumen, MappingProdiInstrumen

PORTAL = "https://portal.unisan.ac.id"
ALUMNI = "https://alumni.unisan-g.id/"

# (kode butir, tingkat, judul, path/URL). {slug}, {fslug}, {prodi}, {fak} diisi dari argumen.
TAUTAN_PORTAL = [
    ("U1.02", "univ", "VMTS Universitas (Portal UNISAN)", "/profil/"),
    ("U1.02", "fakultas", "VMTS UPPS {fak} (Portal UNISAN)", "/fakultas/{fslug}/#sec-vmts"),
    ("U1.02", "prodi", "VMTS Program Studi {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-vmts"),
    ("U1.12", "prodi", "Publikasi CPL Program Studi {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-cpl"),
    ("U5.03", "prodi", "Profil Lulusan {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-lulusan"),
    ("U5.04", "prodi", "Rumusan CPL {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-cpl"),
    ("U5.08", "prodi", "Sebaran Mata Kuliah per Semester {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-kurikulum"),
    ("U4.17", "prodi", "Halaman Portal Program Studi {prodi} (media promosi)", "/prodi/{slug}/"),
    ("U6.02", "prodi", "Direktori Dosen {prodi} (Portal UNISAN)", "/dosen/?prodi={slug}"),
    ("U6.07", "prodi", "Profil/CV Dosen {prodi} (Portal UNISAN)", "/dosen/?prodi={slug}"),
    ("U4.11", "univ", "Daftar Kerja Sama UNISAN (Portal UNISAN)", "/kerjasama/"),
    ("U4.11", "prodi", "Mitra Kerja Sama {prodi} (Portal UNISAN)", "/prodi/{slug}/#sec-mitra"),
    ("U4.02", "univ", "Profil & Struktur Organisasi Universitas (Portal UNISAN)", "/profil/"),
    ("U4.08", "univ", "Dashboard Kinerja Akademik (Portal UNISAN)", "/kinerja/"),
    ("U1.08", "univ", "Portal Alumni & Tracer Study UNISAN", ALUMNI),
]


class Command(BaseCommand):
    help = "Buat dokumen tautan Portal UNISAN & Portal Alumni untuk butir instrumen satu prodi."

    def add_arguments(self, parser):
        parser.add_argument("--prodi", required=True, help="Kode prodi, mis. S21")
        parser.add_argument("--slug", required=True, help="Slug prodi di portal, mis. ilmu-pemerintahan")
        parser.add_argument("--fakultas-slug", required=True, help="Slug fakultas di portal, mis. fisip")
        parser.add_argument("--apply", action="store_true", help="Simpan (default: preview)")
        parser.add_argument("--as-user", default="", help="Username pencatat (default: superuser pertama)")

    def handle(self, *args, **o):
        kode_prodi = o["prodi"].strip().upper()
        mapping = MappingProdiInstrumen.objects.select_related("instrumen").filter(
            kode_prodi=kode_prodi, aktif=True).first()
        if mapping is None:
            raise CommandError(f"Mapping prodi {kode_prodi} tidak ditemukan.")
        user = (
            User.objects.filter(username=o["as_user"], is_active=True).first() if o["as_user"]
            else User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        )
        if user is None:
            raise CommandError("User pencatat tidak ditemukan.")

        from dokumen.siobe_rps import _kode_fakultas
        kode_fakultas = _kode_fakultas(kode_prodi)
        isian = {
            "slug": o["slug"].strip("/"),
            "fslug": o["fakultas_slug"].strip("/"),
            "prodi": mapping.nama_prodi,
            "fak": o["fakultas_slug"].strip("/").upper(),
        }
        self.stdout.write(f"Prodi {kode_prodi} ({mapping.nama_prodi}) | fakultas {kode_fakultas or '-'} "
                          f"| instrumen {mapping.instrumen.kode}")

        cek_cache = {}
        baru = lewat = 0
        for kode_butir, tingkat, judul, path in TAUTAN_PORTAL:
            butir = ButirDokumen.objects.filter(
                sub_standar__standar__instrumen=mapping.instrumen, kode=kode_butir, aktif=True).first()
            url = path if path.startswith("http") else PORTAL + path.format(**isian)
            judul = judul.format(**isian)
            if butir is None:
                self.stdout.write(self.style.WARNING(f"- {kode_butir}: butir tidak ada di instrumen, dilewati"))
                continue
            scope_prodi = kode_prodi if tingkat == "prodi" else ""
            scope_fak = kode_fakultas if tingkat in ("prodi", "fakultas") else ""
            if tautan_sudah_ada(butir, url, scope_prodi, scope_fak):
                lewat += 1
                self.stdout.write(f"= {kode_butir:6} [{tingkat:8}] sudah ada: {url}")
                continue
            if url not in cek_cache:
                cek_cache[url] = link_accessible(url)
            status = "OK" if cek_cache[url] else "TIDAK BISA DIAKSES"
            self.stdout.write(f"+ {kode_butir:6} [{tingkat:8}] {judul} -> {url} ({status})")
            baru += 1
            if o["apply"]:
                buat_dokumen_tautan(
                    butir, judul, url, user, scope_prodi=scope_prodi, scope_fakultas=scope_fak,
                    deskripsi="Tautan publik Portal UNISAN sebagai bukti publikasi. Dokumen resmi (SK dsb.) "
                              "tetap diunggah terpisah.",
                    bisa_diakses=cek_cache[url], catatan_log="Tautan portal (isi_tautan_portal)",
                )
        self.stdout.write(f"\n{baru} tautan baru, {lewat} sudah ada.")
        if not o["apply"] and baru:
            self.stdout.write(self.style.WARNING("Preview saja. Tambahkan --apply untuk menyimpan."))
