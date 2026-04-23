"""
Model Sesi Akreditasi.

1 Sesi = 1 Prodi x 1 Instrumen x 1 Periode siklus akreditasi.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


# =========================================================
# SESI AKREDITASI (entitas utama)
# =========================================================

class SesiAkreditasi(models.Model):
    """1 Sesi = 1 siklus akreditasi 1 prodi 1 instrumen."""

    class Status(models.TextChoices):
        PERSIAPAN = "PERSIAPAN", _("Persiapan Dokumen")
        REVIEW_INTERNAL = "REVIEW_INTERNAL", _("Review Internal")
        SUBMITTED = "SUBMITTED", _("Sudah Submit ke LAM/BAN-PT")
        VISITASI_AKTIF = "VISITASI_AKTIF", _("Visitasi Berlangsung")
        MENUNGGU_HASIL = "MENUNGGU_HASIL", _("Menunggu Hasil")
        SELESAI = "SELESAI", _("Selesai (Sertifikat Terbit)")
        DIBATALKAN = "DIBATALKAN", _("Dibatalkan")

    class TipeAkreditasi(models.TextChoices):
        AKREDITASI_BARU = "AKREDITASI_BARU", _("Akreditasi Baru (Pertama Kali)")
        REAKREDITASI = "REAKREDITASI", _("Re-akreditasi (Perpanjangan)")
        AKREDITASI_KHUSUS = "AKREDITASI_KHUSUS", _("Akreditasi Khusus / Lainnya")

    # Identitas
    judul = models.CharField(_("Judul Sesi"), max_length=300)
    deskripsi = models.TextField(_("Deskripsi"), blank=True)

    # Scope
    instrumen = models.ForeignKey(
        "master_akreditasi.Instrumen",
        on_delete=models.PROTECT,
        related_name="sesi_akreditasi",
    )
    kode_prodi = models.CharField(_("Kode Prodi"), max_length=10)
    nama_prodi_snapshot = models.CharField(_("Nama Prodi (snapshot)"), max_length=200, blank=True)
    kode_fakultas = models.CharField(_("Kode Fakultas"), max_length=10, blank=True)

    tipe = models.CharField(
        _("Tipe Akreditasi"),
        max_length=20,
        choices=TipeAkreditasi.choices,
        default=TipeAkreditasi.REAKREDITASI,
    )

    # Periode TS multi-tahun
    tahun_ts = models.CharField(
        _("Tahun TS (Saat Ini)"),
        max_length=20,
        help_text=_("Tahun akademik saat submit akreditasi. Contoh: 2025/2026"),
    )
    jumlah_tahun_evaluasi = models.PositiveSmallIntegerField(
        _("Jumlah Tahun Evaluasi"),
        default=3,
        help_text=_("3 untuk LAM, 4 untuk BAN-PT IAPS 4.0"),
    )

    # Timeline
    tanggal_mulai = models.DateField(_("Tanggal Mulai Sesi"))
    tanggal_target_selesai = models.DateField(_("Target Selesai"))
    deadline_upload_dokumen = models.DateField(_("Deadline Upload Dokumen Wajib"), null=True, blank=True)
    tanggal_submit = models.DateField(_("Tanggal Submit"), null=True, blank=True)
    tanggal_visitasi_mulai = models.DateField(_("Tanggal Visitasi Mulai"), null=True, blank=True)
    tanggal_visitasi_selesai = models.DateField(_("Tanggal Visitasi Selesai"), null=True, blank=True)
    tanggal_sertifikat = models.DateField(_("Tanggal Sertifikat Terbit"), null=True, blank=True)

    # Status
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PERSIAPAN,
    )

    # Hasil
    nilai_akhir = models.CharField(_("Nilai Akreditasi Akhir"), max_length=20, blank=True)
    nomor_sk_akreditasi = models.CharField(_("Nomor SK Akreditasi"), max_length=100, blank=True)
    berlaku_sampai = models.DateField(_("Berlaku Sampai"), null=True, blank=True)

    # Audit
    dibuat_oleh = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="sesi_dibuat",
    )
    terakhir_diupdate_oleh = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="sesi_diupdate",
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Sesi Akreditasi")
        verbose_name_plural = _("Sesi Akreditasi")
        db_table = "sesi_akreditasi"
        ordering = ["-tanggal_mulai", "-tanggal_dibuat"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrumen", "kode_prodi", "tahun_ts"],
                name="unique_sesi_per_prodi_instrumen_tahun_ts",
            ),
        ]

    def __str__(self):
        return f"{self.judul} ({self.get_status_display()})"

    @property
    def is_aktif(self):
        return self.status not in [self.Status.SELESAI, self.Status.DIBATALKAN]

    @property
    def status_color(self):
        colors = {
            "PERSIAPAN": "blue",
            "REVIEW_INTERNAL": "amber",
            "SUBMITTED": "cyan",
            "VISITASI_AKTIF": "purple",
            "MENUNGGU_HASIL": "amber",
            "SELESAI": "emerald",
            "DIBATALKAN": "rose",
        }
        return colors.get(self.status, "gray")

    @property
    def tahun_periode_list(self):
        """Generate list TA: ['2025/2026', '2024/2025', '2023/2024']."""
        if not self.tahun_ts or "/" not in self.tahun_ts:
            return [self.tahun_ts] if self.tahun_ts else []
        try:
            start_year, end_year = self.tahun_ts.split("/")
            start_year = int(start_year)
            end_year = int(end_year)
        except (ValueError, AttributeError):
            return [self.tahun_ts]
        periode = []
        for offset in range(self.jumlah_tahun_evaluasi):
            ta = f"{start_year - offset}/{end_year - offset}"
            periode.append(ta)
        return periode

    @property
    def periode_label(self):
        """Format: 'TS-2 s/d TS: 2023/2024 -- 2025/2026'."""
        periode = self.tahun_periode_list
        if not periode:
            return "--"
        if len(periode) == 1:
            return f"TS: {periode[0]}"
        ts = periode[0]
        ts_oldest = periode[-1]
        offset = len(periode) - 1
        return f"TS-{offset} s/d TS: {ts_oldest} -- {ts}"

    @property
    def periode_short(self):
        """Versi singkat: '3 tahun (2023-2026)'."""
        periode = self.tahun_periode_list
        if not periode:
            return "--"
        if len(periode) == 1:
            return periode[0]
        try:
            ts_year = self.tahun_ts.split("/")[1]
            oldest_year = periode[-1].split("/")[0]
            return f"{len(periode)} tahun ({oldest_year}-{ts_year})"
        except Exception:
            return f"{len(periode)} tahun"

    @property
    def progress_dokumen(self):
        """Auto-collect dokumen dari TS, TS-1, TS-2 dst."""
        from master_akreditasi.models import ButirDokumen
        from dokumen.models import Dokumen

        butir_qs = ButirDokumen.objects.filter(
            sub_standar__standar__instrumen=self.instrumen,
            aktif=True,
        )
        total = butir_qs.count()
        if total == 0:
            return {"total": 0, "terisi": 0, "percentage": 0, "sisa": 0, "periode": []}

        periode = self.tahun_periode_list

        terisi_butir_ids = Dokumen.objects.filter(
            butir_dokumen__in=butir_qs,
            tahun_akademik__in=periode,
        ).filter(
            models.Q(scope_kode_prodi=self.kode_prodi) |
            models.Q(scope_kode_fakultas=self.kode_fakultas, kategori_pemilik="FAKULTAS") |
            models.Q(kategori_pemilik="UNIVERSITAS")
        ).values_list("butir_dokumen_id", flat=True).distinct()

        terisi = len(set(terisi_butir_ids))
        percentage = round((terisi / total) * 100, 1) if total > 0 else 0

        return {
            "total": total,
            "terisi": terisi,
            "percentage": percentage,
            "sisa": total - terisi,
            "periode": periode,
        }

    @property
    def days_to_deadline(self):
        if not self.deadline_upload_dokumen:
            return None
        delta = self.deadline_upload_dokumen - timezone.now().date()
        return delta.days


# =========================================================
# MILESTONE / TIMELINE
# =========================================================

class MilestoneSesi(models.Model):
    class StatusMilestone(models.TextChoices):
        BELUM = "BELUM", _("Belum Dimulai")
        PROGRESS = "PROGRESS", _("Sedang Berjalan")
        SELESAI = "SELESAI", _("Selesai")
        TERLEWAT = "TERLEWAT", _("Terlewat / Tertunda")

    sesi = models.ForeignKey(SesiAkreditasi, on_delete=models.CASCADE, related_name="milestones")
    judul = models.CharField(_("Judul Milestone"), max_length=200)
    deskripsi = models.TextField(_("Deskripsi"), blank=True)
    tanggal_target = models.DateField(_("Tanggal Target"))
    tanggal_aktual = models.DateField(_("Tanggal Aktual"), null=True, blank=True)
    urutan = models.PositiveIntegerField(_("Urutan"), default=0)
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=StatusMilestone.choices,
        default=StatusMilestone.BELUM,
    )
    catatan = models.TextField(_("Catatan"), blank=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Milestone Sesi")
        verbose_name_plural = _("Milestones Sesi")
        db_table = "milestone_sesi"
        ordering = ["urutan", "tanggal_target"]

    def __str__(self):
        return f"{self.sesi.judul} - {self.judul}"


# =========================================================
# CATATAN
# =========================================================

class CatatanSesi(models.Model):
    class Tipe(models.TextChoices):
        UMUM = "UMUM", _("Catatan Umum")
        REVIEW = "REVIEW", _("Catatan Review")
        VISITASI = "VISITASI", _("Catatan Visitasi")
        ASESOR = "ASESOR", _("Komentar Asesor")
        INTERNAL = "INTERNAL", _("Catatan Internal LP3M")

    sesi = models.ForeignKey(SesiAkreditasi, on_delete=models.CASCADE, related_name="catatan")
    tipe = models.CharField(_("Tipe Catatan"), max_length=15, choices=Tipe.choices, default=Tipe.UMUM)
    isi = models.TextField(_("Isi Catatan"))
    dibuat_oleh = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="catatan_sesi_dibuat",
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Catatan Sesi")
        verbose_name_plural = _("Catatan Sesi")
        db_table = "catatan_sesi"
        ordering = ["-tanggal_dibuat"]

    def __str__(self):
        return f"{self.sesi.judul} - {self.get_tipe_display()}"

# ============================================
# BUNDLE SHARE TOKEN (Step 8 Batch 4)
# ============================================

class BundleShareToken(models.Model):
    """Token untuk akses publik halaman bundle sesi tanpa login.
    
    Digunakan untuk share link ke asesor LAM/BAN-PT atau eksternal
    yang tidak punya akun di SIAKRED.
    """
    sesi = models.ForeignKey(
        'SesiAkreditasi',
        on_delete=models.CASCADE,
        related_name='bundle_tokens',
        verbose_name="Sesi Akreditasi",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="Token",
    )
    label = models.CharField(
        max_length=200,
        verbose_name="Label / Keperluan",
        help_text="Nama atau keperluan token, misal: 'Asesor LAMEMBA Dr. Budi' atau 'Submission BAN-PT'",
    )

    # Access control
    is_active = models.BooleanField(default=True, verbose_name="Aktif")
    expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Kadaluarsa Pada",
        help_text="Kosongkan untuk tanpa expired. Disarankan diisi untuk keamanan.",
    )

    # Tracking
    created_by = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bundle_tokens_created',
        verbose_name="Dibuat Oleh",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    last_accessed_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Terakhir Diakses",
    )
    access_count = models.PositiveIntegerField(default=0, verbose_name="Jumlah Akses")

    class Meta:
        db_table = 'bundle_share_token'
        verbose_name = "Token Share Bundle"
        verbose_name_plural = "Token Share Bundle"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.label} ({self.sesi.judul})"

    @staticmethod
    def generate_token():
        """Generate token random 48-char URL-safe."""
        import secrets
        return secrets.token_urlsafe(36)  # ~48 chars

    def is_valid(self):
        """Cek apakah token masih valid (aktif & belum expired)."""
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    def mark_accessed(self):
        """Tracking: tandai token telah diakses."""
        from django.utils import timezone
        self.last_accessed_at = timezone.now()
        self.access_count += 1
        self.save(update_fields=['last_accessed_at', 'access_count'])