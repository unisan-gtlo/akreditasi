"""
Jalankan sinkronisasi (lihat master_akreditasi/sinkron.py) dan catat ke Log Sinkronisasi.

    python manage.py sinkron --jenis SEMUA --sumber CRON      # cron malam
    python manage.py sinkron --jenis RPS --prodi S21
    python manage.py sinkron --log-id 12                      # dipakai tombol (log sudah dibuat)
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import User
from master_akreditasi.models_sinkron import SinkronLog
from master_akreditasi.sinkron import jalankan


class Command(BaseCommand):
    help = "Sinkronisasi data dari SI-OBE, SIMDA, dan portal ke SIAKRED (dicatat di Log Sinkronisasi)."

    def add_arguments(self, parser):
        parser.add_argument("--jenis", choices=[j for j, _ in SinkronLog.Jenis.choices], default="SEMUA")
        parser.add_argument("--prodi", default="", help="Batasi ke 1 prodi (kode), kosong = semua")
        parser.add_argument("--sumber", default="CLI", help="CLI / CRON / TOMBOL")
        parser.add_argument("--log-id", type=int, default=None, help="Jalankan log yang sudah dibuat tombol")

    def handle(self, *args, **o):
        if o["log_id"]:
            log_obj = SinkronLog.objects.filter(pk=o["log_id"]).first()
            if log_obj is None:
                raise CommandError(f"Log sinkron #{o['log_id']} tidak ditemukan.")
        else:
            log_obj = SinkronLog.objects.create(
                jenis=o["jenis"], lingkup=o["prodi"].strip().upper(), sumber=o["sumber"][:10])

        user = log_obj.dipicu_oleh or User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if user is None:
            raise CommandError("Tidak ada superuser aktif untuk pencatat dokumen.")

        log_obj = jalankan(log_obj, user)
        self.stdout.write(log_obj.output)
        self.stdout.write(f"\n[{log_obj.status}] {log_obj.ringkasan}")
        if log_obj.status == SinkronLog.Status.GAGAL:
            raise CommandError("Sinkronisasi selesai dengan kegagalan.")
