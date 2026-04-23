"""
Model Dokumen Akreditasi SIAKRED.

Alur:
  User upload file → Dokumen dibuat (atau update) → DokumenRevisi tercatat
  User view/download → DokumenAccessLog tercatat
"""
import hashlib
import uuid
from pathlib import Path

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


# =========================================================
# UPLOAD PATH GENERATOR
# =========================================================

def dokumen_upload_path(instance, filename):
    """
    Generate secure filename:
      /media/dokumen/{year}/{month}/{hash}_{original_name}
    """
    year = timezone.now().year
    month = timezone.now().month

    # Hash filename untuk security (no guessable URL)
    unique_str = f"{uuid.uuid4()}-{filename}"
    hash_prefix = hashlib.sha256(unique_str.encode()).hexdigest()[:16]

    # Keep original extension
    ext = Path(filename).suffix.lower()
    clean_name = Path(filename).stem[:50]  # max 50 chars original name
    # Sanitize
    clean_name = "".join(c for c in clean_name if c.isalnum() or c in "-_")

    return f"dokumen/{year}/{month:02d}/{hash_prefix}_{clean_name}{ext}"


# =========================================================
# DOKUMEN (entitas utama)
# =========================================================

class Dokumen(models.Model):
    """
    Dokumen yang di-arsipkan untuk 1 butir_dokumen.
    
    Satu Dokumen bisa punya banyak revisi (DokumenRevisi), 
    tapi hanya 1 yang aktif/dipakai.
    """

    class StatusAkses(models.TextChoices):
        TERBUKA = "TERBUKA", _("Terbuka (Publik)")
        INTERNAL = "INTERNAL", _("Internal (Perlu Login)")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        FINAL = "FINAL", _("Final / Dipublikasikan")
        ARSIP = "ARSIP", _("Diarsipkan")

    # Referensi ke butir dokumen di master
    butir_dokumen = models.ForeignKey(
        "master_akreditasi.ButirDokumen",
        on_delete=models.PROTECT,
        related_name="dokumen_terunggah",
        verbose_name=_("Butir Dokumen"),
    )

    # Scope pemilik (siapa yang upload, berbasis kategori butir)
    # Scope ini akan dicek saat edit / delete
    kategori_pemilik = models.CharField(
        _("Kategori Pemilik"),
        max_length=15,
        help_text=_("UNIVERSITAS / BIRO / FAKULTAS / PRODI"),
    )
    scope_kode_prodi = models.CharField(
        _("Kode Prodi"),
        max_length=10,
        blank=True,
        help_text=_("Diisi kalau kategori = PRODI"),
    )
    scope_kode_fakultas = models.CharField(
        _("Kode Fakultas"),
        max_length=10,
        blank=True,
        help_text=_("Diisi kalau kategori = FAKULTAS atau PRODI"),
    )
    scope_kode_unit_kerja = models.CharField(
        _("Kode Unit Kerja (Biro/Lembaga)"),
        max_length=20,
        blank=True,
        help_text=_("Diisi kalau kategori = BIRO"),
    )

    # Metadata utama
    judul = models.CharField(
        _("Judul Dokumen"),
        max_length=300,
        help_text=_("Judul yang akan tampil ke user. Default: nama dokumen dari butir."),
    )
    deskripsi = models.TextField(_("Deskripsi / Catatan"), blank=True)

    # Akses & Status
    status_akses = models.CharField(
        _("Status Akses"),
        max_length=10,
        choices=StatusAkses.choices,
        default=StatusAkses.INTERNAL,
    )
    status = models.CharField(
        _("Status Dokumen"),
        max_length=10,
        choices=Status.choices,
        default=Status.FINAL,
    )

    # Periode / Tahun
    tahun_akademik = models.CharField(
        _("Tahun Akademik"),
        max_length=20,
        blank=True,
        help_text=_("Contoh: 2024/2025"),
    )

    # Counter
    view_count = models.PositiveIntegerField(_("Jumlah Lihat"), default=0)
    download_count = models.PositiveIntegerField(_("Jumlah Download"), default=0)

    # Audit
    uploaded_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="dokumen_diupload",
        verbose_name=_("Pengupload Pertama"),
    )
    last_updated_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="dokumen_diupdate",
        verbose_name=_("Terakhir Diupdate Oleh"),
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)


    # ========================================
    # VERIFIKASI HELPERS (Step 9)
    # ========================================
    
    def latest_revisi(self):
        """Return DokumenRevisi terakhir yang aktif, atau None."""
        return self.revisi.filter(aktif=True).order_by('-nomor_revisi').first()
    
    def latest_verifikasi(self):
        """Return VerifikasiDokumen untuk revisi terakhir, atau None."""
        rev = self.latest_revisi()
        if not rev:
            return None
        try:
            return rev.verifikasi
        except Exception:
            return None
    
    @property
    def status_verifikasi(self):
        """Return status verifikasi revisi terakhir. 
        Return 'NO_REVISION' kalau belum ada revisi.
        Return 'PENDING' kalau ada revisi tapi belum ada record verifikasi.
        """
        v = self.latest_verifikasi()
        if v:
            return v.status
        if self.latest_revisi():
            return 'PENDING'
        return 'NO_REVISION'
    
    def is_approved(self):
        """True kalau revisi terakhir sudah APPROVED."""
        return self.status_verifikasi == 'APPROVED'
    
    def is_pending_review(self):
        return self.status_verifikasi == 'PENDING'
    
    def is_rejected(self):
        return self.status_verifikasi == 'REJECTED'
    
    def needs_revision(self):
        return self.status_verifikasi == 'NEED_REVISION'

    class Meta:
        verbose_name = _("Dokumen Akreditasi")
        verbose_name_plural = _("Dokumen Akreditasi")
        db_table = "dokumen"
        ordering = ["-tanggal_diubah"]

    def __str__(self):
        return f"{self.judul} ({self.butir_dokumen.kode})"

    @property
    def revisi_aktif(self):
        """Revisi terakhir = yang aktif."""
        return self.revisi.filter(aktif=True).order_by("-nomor_revisi").first()

    @property
    def total_revisi(self):
        return self.revisi.count()

    @property
    def file_terkini(self):
        """Shortcut ke file aktif."""
        rev = self.revisi_aktif
        return rev.file if rev else None

    @property
    def scope_label(self):
        """Label scope untuk display, contoh: 'Fakultas Teknik' atau 'Prodi P21'"""
        if self.kategori_pemilik == "UNIVERSITAS":
            return "Universitas"
        elif self.kategori_pemilik == "BIRO":
            return f"Biro: {self.scope_kode_unit_kerja}"
        elif self.kategori_pemilik == "FAKULTAS":
            return f"Fakultas: {self.scope_kode_fakultas}"
        elif self.kategori_pemilik == "PRODI":
            return f"Prodi: {self.scope_kode_prodi}"
        return "-"


# =========================================================
# DOKUMEN REVISI (version history)
# =========================================================

class DokumenRevisi(models.Model):
    """
    Version history dari Dokumen.
    Setiap kali user upload ulang → nomor_revisi +1, yang lama aktif=False.
    """

    dokumen = models.ForeignKey(
        Dokumen,
        on_delete=models.CASCADE,
        related_name="revisi",
    )
    nomor_revisi = models.PositiveIntegerField(_("Nomor Revisi"))

    # Storage type (LOCAL upload vs GDRIVE link)
    class StorageType(models.TextChoices):
        LOCAL = "LOCAL", _("Upload File Lokal")
        GDRIVE = "GDRIVE", _("Google Drive Link")

    storage_type = models.CharField(
        _("Tipe Storage"),
        max_length=10,
        choices=StorageType.choices,
        default=StorageType.LOCAL,
    )

    # LOCAL storage fields
    file = models.FileField(
        _("File"),
        upload_to=dokumen_upload_path,
        max_length=500,
        null=True,
        blank=True,
        help_text=_("Diisi kalau storage_type=LOCAL"),
    )
    original_filename = models.CharField(_("Nama File Asli"), max_length=300, blank=True)
    file_size_kb = models.PositiveIntegerField(_("Ukuran (KB)"), default=0)
    file_hash = models.CharField(
        _("SHA-256 Hash"),
        max_length=64,
        blank=True,
        help_text=_("Hash untuk verifikasi integrity"),
    )
    mime_type = models.CharField(_("MIME Type"), max_length=100, blank=True)
    extension = models.CharField(_("Ekstensi"), max_length=10, blank=True)

    # GDRIVE storage fields
    gdrive_url = models.URLField(
        _("Google Drive URL"),
        max_length=500,
        blank=True,
        help_text=_("Diisi kalau storage_type=GDRIVE"),
    )
    gdrive_file_id = models.CharField(
        _("Google Drive File ID"),
        max_length=100,
        blank=True,
        help_text=_("Extracted dari URL untuk embed preview"),
    )

    # Link verification (untuk GDRIVE - cek berkala link masih valid)
    last_verified_at = models.DateTimeField(
        _("Terakhir Diverifikasi"),
        null=True,
        blank=True,
    )
    is_link_broken = models.BooleanField(
        _("Link Broken?"),
        default=False,
        help_text=_("Flag kalau link GDrive tidak accessible"),
    )

    # Metadata revisi
    catatan_revisi = models.TextField(
        _("Catatan Revisi"),
        blank=True,
        help_text=_("Kenapa di-update? Perubahan apa?"),
    )

    # Status
    aktif = models.BooleanField(
        _("Aktif"),
        default=True,
        help_text=_("Hanya 1 revisi yang aktif per dokumen"),
    )

    # Audit
    uploaded_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="revisi_diupload",
    )
    tanggal_upload = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Revisi Dokumen")
        verbose_name_plural = _("Revisi Dokumen")
        db_table = "dokumen_revisi"
        ordering = ["-nomor_revisi"]
        constraints = [
            models.UniqueConstraint(
                fields=["dokumen", "nomor_revisi"],
                name="unique_dokumen_revisi_nomor",
            ),
        ]

    def __str__(self):
        return f"{self.dokumen.judul} — Rev.{self.nomor_revisi}"

    @property
    def file_size_display(self):
        """Format ukuran file jadi string user-friendly."""
        kb = self.file_size_kb
        if kb < 1024:
            return f"{kb} KB"
        mb = kb / 1024
        return f"{mb:.1f} MB"

    @property
    def is_pdf(self):
        return self.extension.lower() == "pdf"

    @property
    def is_image(self):
        return self.extension.lower() in ["jpg", "jpeg", "png", "gif", "webp"]

    @property
    def is_office(self):
        return self.extension.lower() in ["docx", "xlsx", "pptx", "doc", "xls", "ppt"]
    @property
    def is_gdrive(self):
        return self.storage_type == self.StorageType.GDRIVE

    @property
    def is_local(self):
        return self.storage_type == self.StorageType.LOCAL

    def get_preview_url(self):
        """Return URL untuk preview inline (iframe src)."""
        if self.is_gdrive and self.gdrive_file_id:
            return f"https://drive.google.com/file/d/{self.gdrive_file_id}/preview"
        if self.is_local and self.file:
            return self.file.url
        return None

    def get_download_url(self):
        """Return URL untuk download langsung."""
        if self.is_gdrive and self.gdrive_file_id:
            return f"https://drive.google.com/uc?export=download&id={self.gdrive_file_id}"
        if self.is_local and self.file:
            return self.file.url
        return None

    def get_external_url(self):
        """URL untuk buka di tab baru (GDrive asli atau file lokal)."""
        if self.is_gdrive:
            return self.gdrive_url
        if self.is_local and self.file:
            return self.file.url
        return None

    @property
    def storage_badge_class(self):
        """CSS class untuk badge storage type."""
        return "badge-emerald" if self.is_local else "badge-amber"


# =========================================================
# ACCESS LOG
# =========================================================

class DokumenAccessLog(models.Model):
    """
    Log setiap akses ke dokumen (view inline, download, upload).
    Penting untuk audit & counter view/download.
    """

    class AksiType(models.TextChoices):
        VIEW = "VIEW", _("Lihat Inline")
        DOWNLOAD = "DOWNLOAD", _("Download")
        UPLOAD = "UPLOAD", _("Upload / Create")
        REVISI = "REVISI", _("Upload Revisi")
        DELETE = "DELETE", _("Hapus")
        EDIT_META = "EDIT_META", _("Edit Metadata")

    dokumen = models.ForeignKey(
        Dokumen,
        on_delete=models.CASCADE,
        related_name="access_logs",
    )
    revisi = models.ForeignKey(
        DokumenRevisi,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    aksi = models.CharField(max_length=15, choices=AksiType.choices)

    # Who (bisa null untuk akses publik/anonim)
    user = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dokumen_access_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    # When
    waktu = models.DateTimeField(auto_now_add=True)

    # Catatan tambahan
    catatan = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("Log Akses Dokumen")
        verbose_name_plural = _("Log Akses Dokumen")
        db_table = "dokumen_access_log"
        ordering = ["-waktu"]

    def __str__(self):
        u = self.user.username if self.user else "anonim"
        return f"{self.waktu:%d/%m/%Y %H:%M} - {u} - {self.get_aksi_display()}"


# ============================================
# VERIFIKASI DOKUMEN (Step 9)
# ============================================

class VerifikasiDokumen(models.Model):
    """Record verifikasi LP3M/Dekan untuk setiap revisi dokumen.
    
    - 1 revisi dokumen -> 1 verifikasi (OneToOne)
    - Saat uploader upload revisi baru, auto-buat Verifikasi baru dengan status PENDING
    - Verifikator mengubah status + memberi catatan
    - Dokumen dianggap 'FINAL APPROVED' jika revisi terakhir status=APPROVED
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Menunggu Review'
        APPROVED = 'APPROVED', 'Disetujui'
        REJECTED = 'REJECTED', 'Ditolak'
        NEED_REVISION = 'NEED_REVISION', 'Perlu Revisi'
    
    revisi = models.OneToOneField(
        'DokumenRevisi',
        on_delete=models.CASCADE,
        related_name='verifikasi',
        verbose_name='Revisi Dokumen',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name='Status Verifikasi',
    )
    catatan = models.TextField(
        blank=True, default='',
        verbose_name='Catatan Verifikator',
        help_text='Disarankan diisi untuk REJECTED/NEED_REVISION agar uploader tau harus fix apa.',
    )
    verifikator = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verifikasi_dilakukan',
        verbose_name='Diverifikasi Oleh',
    )
    tanggal_verifikasi = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Tanggal Verifikasi',
        help_text='Diisi otomatis saat status berubah dari PENDING.',
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True, verbose_name='Dibuat Pada')
    tanggal_diubah = models.DateTimeField(auto_now=True, verbose_name='Diubah Pada')
    
    class Meta:
        db_table = 'verifikasi_dokumen'
        verbose_name = 'Verifikasi Dokumen'
        verbose_name_plural = 'Verifikasi Dokumen'
        ordering = ['-tanggal_dibuat']
        indexes = [
            models.Index(fields=['status', '-tanggal_dibuat']),
        ]
    
    def __str__(self):
        return f'{self.revisi.dokumen.judul} r{self.revisi.nomor_revisi} - {self.get_status_display()}'
    
    def is_final_approved(self):
        """True jika status APPROVED."""
        return self.status == self.Status.APPROVED
    
    def is_pending(self):
        return self.status == self.Status.PENDING
    
    def is_rejected(self):
        return self.status == self.Status.REJECTED
    
    def needs_revision(self):
        return self.status == self.Status.NEED_REVISION


class VerifikasiLog(models.Model):
    """Audit trail: setiap perubahan status verifikasi di-log.
    
    Berguna untuk: tracking kapan approved, siapa yang approve, alasan reject sebelumnya, dll.
    """
    verifikasi = models.ForeignKey(
        VerifikasiDokumen,
        on_delete=models.CASCADE,
        related_name='logs',
    )
    aksi = models.CharField(max_length=20, help_text='APPROVED, REJECTED, NEED_REVISION, RESET')
    status_lama = models.CharField(max_length=20, blank=True)
    status_baru = models.CharField(max_length=20)
    catatan = models.TextField(blank=True, default='')
    dilakukan_oleh = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verifikasi_log',
    )
    tanggal = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'verifikasi_dokumen_log'
        verbose_name = 'Log Verifikasi'
        verbose_name_plural = 'Log Verifikasi'
        ordering = ['-tanggal']
    
    def __str__(self):
        return f'{self.aksi} - {self.verifikasi} @ {self.tanggal:%Y-%m-%d %H:%M}'


# ============================================
# AUTO-CREATE VERIFIKASI SAAT REVISI BARU
# ============================================

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='dokumen.DokumenRevisi')
def auto_create_verifikasi(sender, instance, created, **kwargs):
    """Setiap kali DokumenRevisi baru dibuat, auto-create Verifikasi status PENDING."""
    if created:
        # Import lazy biar tidak circular
        from dokumen.models import VerifikasiDokumen
        VerifikasiDokumen.objects.get_or_create(
            revisi=instance,
            defaults={'status': VerifikasiDokumen.Status.PENDING},
        )

