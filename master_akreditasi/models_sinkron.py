"""
Log Sinkronisasi: riwayat sinkron data dari sistem lain (SI-OBE, SIMDA, portal)
yang dipicu tombol Pusat Sinkronisasi (superadmin) atau cron malam.
"""
from django.conf import settings
from django.db import models


class SinkronLog(models.Model):
    class Jenis(models.TextChoices):
        RPS = "RPS", "RPS SI-OBE"
        DTPS = "DTPS", "DTPS & Data Dosen SIMDA"
        TAUTAN = "TAUTAN", "Tautan Aplikasi & Portal"
        CACHE = "CACHE", "Bersihkan Cache"
        SEMUA = "SEMUA", "Sinkron Semua"

    class Status(models.TextChoices):
        ANTRI = "ANTRI", "Antri"
        BERJALAN = "BERJALAN", "Berjalan"
        SUKSES = "SUKSES", "Sukses"
        GAGAL = "GAGAL", "Gagal"

    jenis = models.CharField(max_length=10, choices=Jenis.choices)
    lingkup = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Kosong = semua prodi; atau kode prodi (mis. S21) untuk sinkron per sesi.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ANTRI, db_index=True)
    sumber = models.CharField(max_length=10, default="TOMBOL", help_text="TOMBOL / CRON / CLI")
    dipicu_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sinkron_dipicu",
    )
    mulai = models.DateTimeField(auto_now_add=True)
    selesai = models.DateTimeField(null=True, blank=True)
    ringkasan = models.CharField(max_length=500, blank=True, default="")
    output = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sinkron_log"
        verbose_name = "Log Sinkronisasi"
        verbose_name_plural = "Log Sinkronisasi"
        ordering = ["-mulai"]

    def __str__(self):
        return f"{self.get_jenis_display()} {self.lingkup or 'semua'} — {self.get_status_display()}"

    @property
    def durasi_detik(self):
        if self.selesai and self.mulai:
            return int((self.selesai - self.mulai).total_seconds())
        return None

    @property
    def aktif(self):
        return self.status in (self.Status.ANTRI, self.Status.BERJALAN)
