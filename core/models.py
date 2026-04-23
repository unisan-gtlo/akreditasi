"""
Core models untuk SIAKRED:
- User (Custom User Model extending AbstractUser)
- ScopeUser (mapping user ke role + level + unit organisasi)
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


# ============================================
# CUSTOM USER MODEL
# ============================================

class User(AbstractUser):
    """
    Custom User Model untuk SIAKRED.
    Extend Django's AbstractUser dengan field tambahan
    untuk sinkronisasi dengan SIMDA (dosen/tendik).
    """

    nidn = models.CharField(
        _("NIDN"),
        max_length=20,
        blank=True,
        null=True,
        help_text=_("Nomor Induk Dosen Nasional (untuk dosen)"),
    )
    nip = models.CharField(
        _("NIP"),
        max_length=30,
        blank=True,
        null=True,
        help_text=_("Nomor Induk Pegawai (untuk tendik)"),
    )
    no_telepon = models.CharField(
        _("No. Telepon"),
        max_length=20,
        blank=True,
        null=True,
    )
    foto_profil = models.ImageField(
        _("Foto Profil"),
        upload_to="users/foto/",
        blank=True,
        null=True,
    )

    # Link ke SIMDA (ID tabel master.data_dosen / master.data_tendik)
    # Bukan FK Django (karena beda schema) — hanya ID bigint
    data_dosen_id = models.BigIntegerField(
        _("ID Dosen SIMDA"),
        blank=True,
        null=True,
        help_text=_("Link ke master.data_dosen.id di SIMDA"),
    )
    data_tendik_id = models.BigIntegerField(
        _("ID Tendik SIMDA"),
        blank=True,
        null=True,
        help_text=_("Link ke master.data_tendik.id di SIMDA"),
    )

    # Metadata
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pengguna")
        verbose_name_plural = _("Pengguna")
        db_table = "user"
        ordering = ["username"]

    def __str__(self):
        nama = self.get_full_name() or self.username
        return f"{nama} ({self.username})"

    @property
    def nama_lengkap(self):
        return self.get_full_name() or self.username


# ============================================
# SCOPE USER (ROLE & HIERARKI)
# ============================================

class ScopeUser(models.Model):
    """
    Mapping user ke role dan level organisasi (universitas/biro/fakultas/prodi).
    Satu user BISA punya lebih dari satu scope (misal Dekan merangkap Kaprodi).
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", _("Super Admin Pustikom")
        PIMP_REKTORAT = "PIMP_REKTORAT", _("Pimpinan Rektorat")
        LPM = "LPM", _("LPM / GKM (Validator Mutu)")
        OP_UNIVERSITAS = "OP_UNIVERSITAS", _("Operator Universitas")
        PIMP_BIRO = "PIMP_BIRO", _("Pimpinan Biro/Lembaga")
        OP_BIRO = "OP_BIRO", _("Operator Biro/Lembaga")
        PIMP_FAKULTAS = "PIMP_FAKULTAS", _("Pimpinan Fakultas")
        OP_FAKULTAS = "OP_FAKULTAS", _("Operator Fakultas")
        PIMP_PRODI = "PIMP_PRODI", _("Pimpinan Prodi")
        OP_PRODI = "OP_PRODI", _("Operator Prodi")
        ASESOR = "ASESOR", _("Asesor Eksternal")

    class Level(models.TextChoices):
        UNIVERSITAS = "UNIVERSITAS", _("Universitas")
        BIRO = "BIRO", _("Biro / Lembaga")
        FAKULTAS = "FAKULTAS", _("Fakultas")
        PRODI = "PRODI", _("Program Studi")

    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="scopes",
        verbose_name=_("Pengguna"),
    )
    role = models.CharField(
        _("Role"),
        max_length=30,
        choices=Role.choices,
    )
    level = models.CharField(
        _("Level Organisasi"),
        max_length=20,
        choices=Level.choices,
    )

    # Link ke unit organisasi di SIMDA (nullable, sesuai level)
    unit_kerja_id = models.BigIntegerField(
        _("ID Unit Kerja (Biro/Lembaga)"),
        blank=True,
        null=True,
        help_text=_("Link ke master.unit_kerja.id (jika level=BIRO)"),
    )
    fakultas_id = models.CharField(
        _("Fakultas (Kode)"),
        max_length=10,
        blank=True,
        null=True,
        help_text=_("Link ke master.fakultas.kode_fakultas (varchar cross-schema)"),
    )
    prodi_id = models.CharField(
        _("Prodi (Kode)"),
        max_length=10,
        blank=True,
        null=True,
        help_text=_("Link ke master.program_studi.kode_prodi (varchar cross-schema)"),
    )

    is_pimpinan = models.BooleanField(
        _("Pimpinan?"),
        default=False,
        help_text=_("True untuk pimpinan, False untuk operator"),
    )
    aktif = models.BooleanField(
        _("Aktif"),
        default=True,
    )
    tanggal_mulai = models.DateField(
        _("Tanggal Mulai Berlaku"),
        auto_now_add=True,
    )
    tanggal_berakhir = models.DateField(
        _("Tanggal Berakhir"),
        blank=True,
        null=True,
        help_text=_("Kosongkan jika tidak ada batas (terutama untuk Asesor)"),
    )

    # Metadata
    dibuat_oleh = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scope_dibuat",
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Scope Pengguna")
        verbose_name_plural = _("Scope Pengguna")
        db_table = "scope_user"
        ordering = ["user__username", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "unit_kerja_id", "fakultas_id", "prodi_id"],
                name="unique_user_role_unit",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} ({self.get_level_display()})"

    @property
    def is_level_universitas(self):
        return self.level == self.Level.UNIVERSITAS

    @property
    def is_level_biro(self):
        return self.level == self.Level.BIRO

    @property
    def is_level_fakultas(self):
        return self.level == self.Level.FAKULTAS

    @property
    def is_level_prodi(self):
        return self.level == self.Level.PRODI

    # ============================================
# LOGIN ATTEMPT (Tracking login gagal)
# ============================================

class LoginAttempt(models.Model):
    """
    Track semua percobaan login (sukses & gagal).
    Digunakan untuk:
    - Memicu CAPTCHA setelah 2x gagal dari IP yang sama
    - Lockout setelah 5x gagal (bekerja sama dengan django-axes)
    - Audit log keamanan
    """

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", _("Berhasil")
        FAILED_PASSWORD = "FAILED_PASSWORD", _("Password Salah")
        FAILED_USERNAME = "FAILED_USERNAME", _("Username Tidak Ditemukan")
        FAILED_INACTIVE = "FAILED_INACTIVE", _("Akun Tidak Aktif")
        FAILED_CAPTCHA = "FAILED_CAPTCHA", _("CAPTCHA Salah")
        LOCKED_OUT = "LOCKED_OUT", _("Akun Dikunci")

    username_attempted = models.CharField(
        _("Username/Email Dicoba"),
        max_length=200,
    )
    user = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts",
    )
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=Status.choices,
    )
    ip_address = models.GenericIPAddressField(_("IP Address"))
    user_agent = models.TextField(_("User Agent"), blank=True)
    waktu = models.DateTimeField(_("Waktu"), auto_now_add=True)

    class Meta:
        verbose_name = _("Percobaan Login")
        verbose_name_plural = _("Percobaan Login")
        db_table = "login_attempt"
        ordering = ["-waktu"]
        indexes = [
            models.Index(fields=["-waktu"]),
            models.Index(fields=["ip_address", "-waktu"]),
            models.Index(fields=["username_attempted", "-waktu"]),
        ]

    def __str__(self):
        return f"{self.username_attempted} - {self.get_status_display()} @ {self.waktu}"


# ============================================
# DEVICE SESSION (Tracking device login)
# ============================================

class DeviceSession(models.Model):
    """
    Track semua device/browser yang pernah login.
    Digunakan untuk:
    - Notifikasi email jika login dari device baru
    - Force logout dari semua device
    - Menampilkan riwayat login di profil user
    """

    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="device_sessions",
    )
    device_fingerprint = models.CharField(
        _("Device Fingerprint"),
        max_length=64,
        help_text=_("Hash dari user-agent + IP prefix"),
    )
    ip_address = models.GenericIPAddressField(_("IP Address"))
    user_agent = models.TextField(_("User Agent"))
    browser_name = models.CharField(_("Browser"), max_length=50, blank=True)
    os_name = models.CharField(_("OS"), max_length=50, blank=True)
    device_type = models.CharField(
        _("Tipe Device"),
        max_length=20,
        blank=True,
        help_text=_("Desktop / Mobile / Tablet"),
    )
    is_trusted = models.BooleanField(
        _("Dipercaya"),
        default=False,
        help_text=_("User telah mengkonfirmasi device ini dipercaya"),
    )
    first_seen = models.DateTimeField(_("Pertama Login"), auto_now_add=True)
    last_seen = models.DateTimeField(_("Login Terakhir"), auto_now=True)
    last_ip = models.GenericIPAddressField(_("IP Terakhir"), null=True, blank=True)
    aktif = models.BooleanField(_("Sesi Aktif"), default=True)

    class Meta:
        verbose_name = _("Device Session")
        verbose_name_plural = _("Device Sessions")
        db_table = "device_session"
        ordering = ["-last_seen"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device_fingerprint"],
                name="unique_user_device",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.browser_name} {self.os_name} ({self.ip_address})"
        