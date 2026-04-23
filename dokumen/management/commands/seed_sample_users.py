"""
Management command: seed 4 user sample dengan berbagai scope untuk testing.

Usage:
    python manage.py seed_sample_users
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connection

from core.models import User, ScopeUser


# User sample dengan password = "siakred2026"
SAMPLE_USERS = [
    {
        "username": "rektorat",
        "email": "rektorat@unisan.ac.id",
        "nama_lengkap": "Rektorat UNISAN",
        "password": "siakred2026",
        "scope": {
            "role": "PIMP_REKTORAT",
            "level": "UNIVERSITAS",
            "is_pimpinan": True,
        },
    },
    {
        "username": "lp2m",
        "email": "lp2m@unisan.ac.id",
        "nama_lengkap": "Kepala LP2M UNISAN",
        "password": "siakred2026",
        "scope": {
            "role": "PIMP_BIRO",
            "level": "BIRO",
            "is_pimpinan": True,
            "unit_kerja_code": "LP2M",
        },
    },
    {
        "username": "dekan_teknik",
        "email": "dekan.teknik@unisan.ac.id",
        "nama_lengkap": "Dekan Fakultas Teknik",
        "password": "siakred2026",
        "scope": {
            "role": "PIMP_FAKULTAS",
            "level": "FAKULTAS",
            "is_pimpinan": True,
            "fakultas_code": "FT",
        },
    },
    {
        "username": "kaprodi_elektro",
        "email": "kaprodi.elektro@unisan.ac.id",
        "nama_lengkap": "Kaprodi Teknik Elektro",
        "password": "siakred2026",
        "scope": {
            "role": "PIMP_PRODI",
            "level": "PRODI",
            "is_pimpinan": True,
            "prodi_code": "T21",
            "fakultas_code": "FT",
        },
    },
]


class Command(BaseCommand):
    help = "Seed 4 user sample (rektorat, lp2m, dekan_teknik, kaprodi_elektro)"

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO("SEED SAMPLE USERS — SIAKRED"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))

        # Cache lookups from SIMDA
        fakultas_map = self._get_fakultas_ids()
        prodi_kode_valid = self._get_prodi_codes()
        unit_kerja_map = self._get_unit_kerja_ids()

        with transaction.atomic():
            for data in SAMPLE_USERS:
                username = data["username"]

                # Check/create user
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": data["email"],
                        "first_name": data["nama_lengkap"].split()[0],
                        "last_name": " ".join(data["nama_lengkap"].split()[1:]),
                        "is_active": True,
                        "is_staff": False,
                    },
                )
                if created:
                    user.set_password(data["password"])
                    user.save()
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ USER BARU: {username} (password: {data['password']})"
                    ))
                else:
                    user.set_password(data["password"])  # reset password
                    user.save()
                    self.stdout.write(
                        f"  → UPDATE: {username} (password di-reset: {data['password']})"
                    )

                # Build scope
                sc = data["scope"]
                defaults = {
                    "role": sc["role"],
                    "level": sc["level"],
                    "is_pimpinan": sc.get("is_pimpinan", False),
                    "aktif": True,
                }

                # Fakultas
                if sc.get("fakultas_code"):
                    fak_id = fakultas_map.get(sc["fakultas_code"])
                    if fak_id:
                        defaults["fakultas_id"] = fak_id

                # Prodi (varchar kode_prodi PK)
                if sc.get("prodi_code"):
                    if sc["prodi_code"] in prodi_kode_valid:
                        defaults["prodi_id"] = sc["prodi_code"]

                # Unit kerja
                if sc.get("unit_kerja_code"):
                    uk_id = unit_kerja_map.get(sc["unit_kerja_code"])
                    if uk_id:
                        defaults["unit_kerja_id"] = uk_id

                # Create ScopeUser (always recreate untuk pastikan fresh)
                ScopeUser.objects.filter(user=user, role=sc["role"]).delete()
                ScopeUser.objects.create(user=user, **defaults)

                scope_info = []
                if defaults.get("fakultas_id"):
                    scope_info.append(f"fakultas={sc['fakultas_code']}")
                if defaults.get("prodi_id"):
                    scope_info.append(f"prodi={sc['prodi_code']}")
                if defaults.get("unit_kerja_id"):
                    scope_info.append(f"unit={sc['unit_kerja_code']}")

                self.stdout.write(
                    f"    Scope: {sc['role']} / {sc['level']}"
                    f"{' (' + ', '.join(scope_info) + ')' if scope_info else ''}"
                )

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("SELESAI — 4 SAMPLE USERS SIAP TESTING"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
        self.stdout.write("Login credentials (semua password: siakred2026):")
        self.stdout.write("  • rektorat         → scope UNIVERSITAS")
        self.stdout.write("  • lp2m             → scope BIRO (LP2M)")
        self.stdout.write("  • dekan_teknik     → scope FAKULTAS (FT)")
        self.stdout.write("  • kaprodi_elektro  → scope PRODI (T21)")
        self.stdout.write("")

    def _get_fakultas_ids(self):
        """Map kode_fakultas → id dari master.fakultas."""
        # master.fakultas PK is probably kode_fakultas (varchar) juga
        # kita cek dulu by probing
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='master' AND table_name='fakultas' AND column_name LIKE '%kode%'
                """)
                cols = [r[0] for r in cursor.fetchall()]

                if "kode_fakultas" in cols:
                    cursor.execute("SELECT kode_fakultas FROM master.fakultas")
                    return {row[0]: row[0] for row in cursor.fetchall()}
        except Exception:
            pass
        return {}

    def _get_prodi_codes(self):
        """Daftar kode_prodi valid."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT kode_prodi FROM master.program_studi")
            return {row[0] for row in cursor.fetchall()}

    def _get_unit_kerja_ids(self):
        """Map kode_unit → id dari master.unit_kerja."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='master' AND table_name='unit_kerja'
                """)
                cols = [r[0] for r in cursor.fetchall()]
                if "kode" in cols:
                    cursor.execute("SELECT id, kode FROM master.unit_kerja")
                    return {row[1]: row[0] for row in cursor.fetchall()}
        except Exception:
            pass
        return {}