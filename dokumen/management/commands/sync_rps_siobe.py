"""
Sinkron RPS Disahkan dari SI-OBE ke dokumen SIAKRED (lihat dokumen/siobe_rps.py).

    python manage.py sync_rps_siobe --prodi S21            # preview (dry-run)
    python manage.py sync_rps_siobe --prodi S21 --apply    # simpan
    python manage.py sync_rps_siobe --all --apply          # semua prodi yg instrumennya punya butir RPS

Default dry-run: tidak mengunduh dan tidak menyimpan apa pun.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import User
from dokumen.siobe_rps import (
    KODE_BERSAMA_RPS, SiobeError, prodi_dengan_butir_rps, sync_prodi,
)


class Command(BaseCommand):
    help = "Sinkron RPS Disahkan dari SI-OBE menjadi dokumen butir RPS seluruh mata kuliah."

    def add_arguments(self, parser):
        parser.add_argument("--prodi", nargs="*", default=[], metavar="KODE", help="Kode prodi, mis. S21")
        parser.add_argument("--all", action="store_true",
                            help=f"Semua prodi yang instrumennya punya butir {KODE_BERSAMA_RPS}")
        parser.add_argument("--apply", action="store_true", help="Simpan perubahan (default: preview)")
        parser.add_argument("--tahun-kurikulum", type=int, default=None,
                            help="Tahun kurikulum SI-OBE (default: terbaru per prodi)")
        parser.add_argument("--as-user", default="",
                            help="Username pencatat upload (default: superuser aktif pertama)")

    def handle(self, *args, **opts):
        prodi_list = [p.strip().upper() for p in opts["prodi"] if p.strip()]
        if opts["all"]:
            prodi_list = prodi_dengan_butir_rps()
        if not prodi_list:
            raise CommandError("Isi --prodi KODE atau --all.")

        if opts["as_user"]:
            user = User.objects.filter(username=opts["as_user"], is_active=True).first()
        else:
            user = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if user is None:
            raise CommandError("User pencatat tidak ditemukan.")

        mode = "APPLY" if opts["apply"] else "DRY-RUN (tambahkan --apply untuk menyimpan)"
        self.stdout.write(self.style.WARNING(f"Mode: {mode} | pencatat: {user.username}"))

        gagal_total = 0
        for kode in prodi_list:
            try:
                r = sync_prodi(kode, user, apply=opts["apply"], tahun_kurikulum=opts["tahun_kurikulum"])
            except SiobeError as exc:
                self.stdout.write(self.style.ERROR(f"\n[{kode}] {exc}"))
                gagal_total += 1
                continue

            self.stdout.write(
                f"\n[{kode}] butir {r.butir.kode} | kurikulum {r.tahun_kurikulum} | {r.total_mk} MK di SI-OBE"
            )
            self.stdout.write(
                f"  RPS tersedia {r.dengan_rps}/{r.total_mk} | baru {len(r.dibuat)} | "
                f"diperbarui {len(r.diperbarui)} | tetap {len(r.tetap)} | diarsipkan {len(r.diarsipkan)}"
            )
            if r.penciri_diperbarui or r.penciri_diarsipkan:
                self.stdout.write(
                    f"  MK penciri: {r.penciri_diperbarui} diperbarui, {r.penciri_diarsipkan} diarsipkan"
                )
            for judul in r.dibuat:
                self.stdout.write(f"    + {judul}")
            for judul in r.diperbarui:
                self.stdout.write(f"    ~ {judul}")
            for judul in r.diarsipkan:
                self.stdout.write(f"    - {judul} (diarsipkan: RPS dicabut / MK tidak ada lagi)")
            if r.tanpa_rps:
                self.stdout.write(self.style.WARNING(f"  Belum ada RPS disahkan ({len(r.tanpa_rps)}):"))
                for judul in r.tanpa_rps:
                    self.stdout.write(f"    ! {judul}")
            for g in r.gagal:
                self.stdout.write(self.style.ERROR(f"    x {g}"))
            gagal_total += len(r.gagal)

        if gagal_total:
            raise CommandError(f"{gagal_total} kegagalan, lihat di atas.")
        self.stdout.write(self.style.SUCCESS("\nSelesai."))
