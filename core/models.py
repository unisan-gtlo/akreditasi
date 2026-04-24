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


# ============================================
# NOTIFIKASI (Step 9H)
# ============================================

class Notifikasi(models.Model):
    """Notifikasi untuk user, terutama feedback hasil verifikasi dokumen."""
    
    class Tipe(models.TextChoices):
        VERIFIKASI_APPROVED = 'VERIF_APPROVED', 'Dokumen Disetujui'
        VERIFIKASI_REJECTED = 'VERIF_REJECTED', 'Dokumen Ditolak'
        VERIFIKASI_NEED_REVISION = 'VERIF_NEED_REVISION', 'Dokumen Perlu Revisi'
        VERIFIKASI_RESET = 'VERIF_RESET', 'Verifikasi Di-reset'
        SISTEM = 'SISTEM', 'Pemberitahuan Sistem'
    
    penerima = models.ForeignKey(
        'core.User',
        on_delete=models.CASCADE,
        related_name='notifikasi_diterima',
        verbose_name='Penerima',
    )
    tipe = models.CharField(
        max_length=30,
        choices=Tipe.choices,
        default=Tipe.SISTEM,
        db_index=True,
    )
    judul = models.CharField(max_length=200, verbose_name='Judul')
    pesan = models.TextField(blank=True, default='', verbose_name='Pesan')
    
    # Links ke object terkait (nullable karena sistem notif bisa generic)
    dokumen = models.ForeignKey(
        'dokumen.Dokumen',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='notifikasi_terkait',
    )
    verifikasi = models.ForeignKey(
        'dokumen.VerifikasiDokumen',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='notifikasi_terkait',
    )
    url_action = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='URL Aksi',
        help_text='URL target saat notifikasi di-klik',
    )
    
    dibuat_oleh = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifikasi_dibuat',
        verbose_name='Pemicu',
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True, db_index=True)
    
    sudah_dibaca = models.BooleanField(default=False, db_index=True, verbose_name='Sudah Dibaca')
    tanggal_dibaca = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'notifikasi'
        verbose_name = 'Notifikasi'
        verbose_name_plural = 'Notifikasi'
        ordering = ['-tanggal_dibuat']
        indexes = [
            models.Index(fields=['penerima', '-tanggal_dibuat']),
            models.Index(fields=['penerima', 'sudah_dibaca']),
        ]
    
    def __str__(self):
        return f'[{self.get_tipe_display()}] {self.judul} - {self.penerima}'
    
    def tandai_dibaca(self):
        """Mark notifikasi sebagai sudah dibaca."""
        if not self.sudah_dibaca:
            from django.utils import timezone
            self.sudah_dibaca = True
            self.tanggal_dibaca = timezone.now()
            self.save(update_fields=['sudah_dibaca', 'tanggal_dibaca'])
    
    def icon_class(self):
        """Return class nama icon untuk UI (approved/rejected/revision/neutral)."""
        return {
            'VERIF_APPROVED': 'approved',
            'VERIF_REJECTED': 'rejected',
            'VERIF_NEED_REVISION': 'revision',
            'VERIF_RESET': 'neutral',
            'SISTEM': 'neutral',
        }.get(self.tipe, 'neutral')


# ============================================
# HELPER: BUAT NOTIFIKASI VERIFIKASI (Step 9H.2)
# ============================================

def buat_notifikasi_verifikasi(verifikasi, aksi, dibuat_oleh, catatan=''):
    """Buat record Notifikasi untuk uploader dokumen setelah aksi verifikasi.
    
    Args:
        verifikasi: instance VerifikasiDokumen yang baru di-update
        aksi: 'APPROVED', 'REJECTED', 'NEED_REVISION', atau 'RESET'
        dibuat_oleh: User yang men-trigger aksi (verifikator)
        catatan: catatan verifikator (optional)
    
    Return: instance Notifikasi yang dibuat, atau None kalau di-skip.
    """
    revisi = verifikasi.revisi
    dokumen = revisi.dokumen
    uploader = revisi.uploaded_by
    
    # Skip kalau uploader tidak ada atau sama dengan verifikator
    if not uploader:
        return None
    if dibuat_oleh and uploader.pk == dibuat_oleh.pk:
        return None
    
    # Mapping aksi -> tipe + judul + emoji
    mapping = {
        'APPROVED': {
            'tipe': Notifikasi.Tipe.VERIFIKASI_APPROVED,
            'judul': f'Dokumen disetujui: {dokumen.judul[:100]}',
            'emoji': 'disetujui',
        },
        'REJECTED': {
            'tipe': Notifikasi.Tipe.VERIFIKASI_REJECTED,
            'judul': f'Dokumen ditolak: {dokumen.judul[:100]}',
            'emoji': 'ditolak',
        },
        'NEED_REVISION': {
            'tipe': Notifikasi.Tipe.VERIFIKASI_NEED_REVISION,
            'judul': f'Perlu revisi: {dokumen.judul[:100]}',
            'emoji': 'perlu direvisi',
        },
        'RESET': {
            'tipe': Notifikasi.Tipe.VERIFIKASI_RESET,
            'judul': f'Verifikasi di-reset: {dokumen.judul[:100]}',
            'emoji': 'direset ke pending',
        },
    }
    
    info = mapping.get(aksi)
    if not info:
        return None
    
    # Build pesan body
    verifikator_nama = dibuat_oleh.get_full_name() or dibuat_oleh.username if dibuat_oleh else 'Sistem'
    pesan_lines = [
        f'Dokumen Anda "{dokumen.judul}" {info["emoji"]} oleh {verifikator_nama}.',
    ]
    if catatan:
        pesan_lines.append(f'Catatan: {catatan}')
    
    pesan = '\n\n'.join(pesan_lines)
    
    # Build URL action
    url_action = f'/dokumen/{dokumen.pk}/'  # fallback ke detail dokumen
    try:
        from django.urls import reverse
        url_action = reverse('dokumen:dokumen_detail', args=[dokumen.pk])
    except Exception:
        pass
    
    return Notifikasi.objects.create(
        penerima=uploader,
        tipe=info['tipe'],
        judul=info['judul'],
        pesan=pesan,
        dokumen=dokumen,
        verifikasi=verifikasi,
        url_action=url_action,
        dibuat_oleh=dibuat_oleh,
    )


class SiteProfile(models.Model):
    """Singleton model untuk profil universitas yang ditampilkan di landing publik."""
    
    nama_institusi = models.CharField(max_length=200, default='Universitas Ichsan Gorontalo')
    nama_singkat = models.CharField(max_length=50, default='UNISAN')
    tagline = models.CharField(max_length=200, default='Sistem Informasi Arsip Akreditasi')
    tahun_berdiri = models.IntegerField(null=True, blank=True)
    
    deskripsi_singkat = models.TextField(blank=True)
    visi = models.TextField(blank=True)
    misi = models.TextField(blank=True)
    
    alamat = models.TextField(blank=True)
    telepon = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    twitter_x = models.URLField(max_length=500, blank=True, verbose_name="Twitter / X", help_text="URL Twitter / X")
    tiktok = models.URLField(max_length=500, blank=True, help_text="URL TikTok")
    linkedin = models.URLField(max_length=500, blank=True, help_text="URL LinkedIn")
    whatsapp_channel = models.URLField(max_length=500, blank=True, verbose_name="WhatsApp Channel", help_text="URL WhatsApp Channel")
    telegram = models.URLField(max_length=500, blank=True, help_text="URL Telegram")
    
    # Rektor (tidak ada di SIMDA, SIAKRED-only)
    nama_rektor = models.CharField(max_length=200, blank=True, help_text="Nama lengkap Rektor dengan gelar")
    foto_rektor = models.ImageField(upload_to="profile/institusi/", blank=True, null=True, help_text="Foto close-up Rektor")
    periode_rektor = models.CharField(max_length=50, blank=True, help_text="Periode jabatan (e.g. 2023-2027)")
    kata_sambutan = models.TextField(blank=True, help_text="Kata sambutan Rektor untuk publik")
    
    # Tujuan (extension visi/misi)
    tujuan = models.TextField(blank=True, help_text="Tujuan universitas (1 poin per baris)")
    
    # Akreditasi Institusi (extend dari SIMDA)
    akreditasi_peringkat = models.CharField(max_length=30, blank=True, help_text="e.g. 'Unggul', 'Baik Sekali', 'B'")
    akreditasi_no_sk = models.CharField(max_length=100, blank=True, help_text="Nomor SK akreditasi institusi")
    akreditasi_tanggal_sk = models.DateField(blank=True, null=True, help_text="Tanggal SK akreditasi")
    akreditasi_berlaku_sampai = models.DateField(blank=True, null=True, help_text="Berlaku sampai tanggal")
    akreditasi_lembaga = models.CharField(max_length=50, blank=True, default="BAN-PT", help_text="Lembaga pemberi akreditasi")
    
    aktif = models.BooleanField(default=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Profil Institusi'
        verbose_name_plural = 'Profil Institusi'
    
    def __str__(self):
        return self.nama_institusi
    
    def save(self, *args, **kwargs):
        if not self.pk and SiteProfile.objects.exists():
            existing = SiteProfile.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    @classmethod
    def get_instance(cls):
        obj, created = cls.objects.get_or_create(pk=1, defaults={
            'nama_institusi': 'Universitas Ichsan Gorontalo',
            'nama_singkat': 'UNISAN',
            'tagline': 'Sistem Informasi Arsip Akreditasi',
        })
        return obj


class FakultasTheme(models.Model):
    """Theme warna per fakultas, sync via kode_fakultas dengan SIMDA.
    
    Tujuan: Kasih identitas visual konsisten untuk setiap fakultas di:
    - Landing page (card border, icon tint, arrow circle)
    - Laporan (heatmap, chart)
    - Badge fakultas di list dokumen, sesi, dll
    
    Data SIMDA master.fakultas di-lookup by kode_fakultas,
    lalu di-enrich dengan warna dari model ini.
    """
    kode_fakultas = models.CharField(
        max_length=10,
        unique=True,
        help_text="Kode fakultas (sync dengan SIMDA master.fakultas.kode_fakultas). Contoh: FE, FH, FT",
    )
    nama_fakultas = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nama fakultas (cached dari SIMDA untuk display cepat)",
    )
    warna_primary = models.CharField(
        max_length=7,
        default="#2563EB",
        help_text="Hex color utama, dipakai untuk border-top, icon, arrow. Contoh: #059669",
    )
    warna_light = models.CharField(
        max_length=7,
        default="#DBEAFE",
        help_text="Hex color terang, dipakai untuk background tint kartu. Contoh: #D1FAE5",
    )
    icon_nama = models.CharField(
        max_length=50,
        blank=True,
        default="graduation-cap",
        help_text="Nama icon Lucide (opsional, default graduation-cap)",
    )
    urutan = models.IntegerField(
        default=0,
        help_text="Urutan tampil di UI (lower = first). Biasanya ikut urutan SIMDA.",
    )
    aktif = models.BooleanField(
        default=True,
        help_text="Nonaktifkan untuk sembunyikan dari UI tanpa delete",
    )
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Theme Fakultas"
        verbose_name_plural = "Theme Fakultas"
        ordering = ["urutan", "kode_fakultas"]
    
    def __str__(self):
        return f"{self.kode_fakultas} - {self.nama_fakultas}"
    
    @classmethod
    def get_theme_map(cls):
        """Return dict {kode_fakultas: {primary, light, icon}} untuk enrich data landing.
        
        Dipakai di helper _get_fakultas_list() untuk inject warna ke setiap fakultas.
        """
        return {
            t.kode_fakultas: {
                "primary": t.warna_primary,
                "light": t.warna_light,
                "icon": t.icon_nama,
            }
            for t in cls.objects.filter(aktif=True)
        }


# ============================================================
# PROFILE ENRICHMENT: Foto & Visi Misi (SIAKRED override SIMDA)
# ============================================================

def _foto_dekan_path(instance, filename):
    ext = filename.split(".")[-1]
    return f"profile/fakultas/{instance.kode_fakultas}.{ext}"


def _foto_kaprodi_path(instance, filename):
    ext = filename.split(".")[-1]
    return f"profile/prodi/{instance.kode_prodi}.{ext}"


class FakultasProfile(models.Model):
    """Profile lengkap fakultas untuk landing publik.
    
    Sync via kode_fakultas dengan SIMDA master.fakultas.
    Menambahkan data yang tidak ada di SIMDA (foto dekan) atau override kalau SIMDA kosong (visi/misi).
    """
    kode_fakultas = models.CharField(
        max_length=10, unique=True,
        help_text="Kode fakultas sync dengan SIMDA master.fakultas.kode_fakultas (FE, FH, FS, FK, FP, FT, S2)",
    )
    
    # Pejabat
    nama_dekan = models.CharField(
        max_length=200, blank=True,
        help_text="Nama lengkap dekan dengan gelar (e.g. Dr. H. Budi Santoso, M.Si.)",
    )
    foto_dekan = models.ImageField(
        upload_to=_foto_dekan_path, blank=True, null=True,
        help_text="Foto close-up dekan, ratio 1:1 atau 3:4 (min 400x400px)",
    )
    periode_dekan = models.CharField(
        max_length=50, blank=True,
        help_text="Periode jabatan (e.g. 2023-2027)",
    )
    
    # Visi Misi (override SIMDA kalau kosong)
    visi = models.TextField(
        blank=True,
        help_text="Visi fakultas. Kalau kosong, fallback ke SIMDA.",
    )
    misi = models.TextField(
        blank=True,
        help_text="Misi fakultas (bisa multi-line, 1 baris per poin).",
    )
    tujuan = models.TextField(
        blank=True,
        help_text="Tujuan fakultas (opsional).",
    )
    
    # Meta
    aktif = models.BooleanField(default=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Profile Fakultas"
        verbose_name_plural = "Profile Fakultas"
        ordering = ["kode_fakultas"]
    
    def __str__(self):
        return f"{self.kode_fakultas} Profile"
    
    def get_misi_list(self):
        """Return misi sebagai list dari baris-baris yang non-empty."""
        if not self.misi:
            return []
        return [line.strip() for line in self.misi.splitlines() if line.strip()]
    
    def get_foto_dekan_url(self):
        """Return URL foto dekan atau None."""
        if self.foto_dekan and hasattr(self.foto_dekan, "url"):
            try:
                return self.foto_dekan.url
            except Exception:
                return None
        return None


class ProdiProfile(models.Model):
    """Profile lengkap program studi untuk landing publik."""
    kode_prodi = models.CharField(
        max_length=10, unique=True,
        help_text="Kode prodi sync dengan SIMDA master.program_studi.kode_prodi",
    )
    
    # Pejabat
    nama_kaprodi = models.CharField(
        max_length=200, blank=True,
        help_text="Nama lengkap ketua program studi dengan gelar",
    )
    foto_kaprodi = models.ImageField(
        upload_to=_foto_kaprodi_path, blank=True, null=True,
        help_text="Foto close-up kaprodi, ratio 1:1 atau 3:4 (min 400x400px)",
    )
    periode_kaprodi = models.CharField(
        max_length=50, blank=True,
        help_text="Periode jabatan (e.g. 2024-2028)",
    )
    
    # Visi Misi
    visi = models.TextField(blank=True, help_text="Visi prodi")
    misi = models.TextField(blank=True, help_text="Misi prodi (1 baris per poin)")
    tujuan = models.TextField(blank=True, help_text="Tujuan prodi (opsional)")
    profil_lulusan = models.TextField(
        blank=True,
        help_text="Profil lulusan / kompetensi utama (opsional)",
    )
    
    # Meta
    aktif = models.BooleanField(default=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Profile Prodi"
        verbose_name_plural = "Profile Prodi"
        ordering = ["kode_prodi"]
    
    def __str__(self):
        return f"{self.kode_prodi} Profile"
    
    def get_misi_list(self):
        if not self.misi:
            return []
        return [line.strip() for line in self.misi.splitlines() if line.strip()]
    
    def get_foto_kaprodi_url(self):
        if self.foto_kaprodi and hasattr(self.foto_kaprodi, "url"):
            try:
                return self.foto_kaprodi.url
            except Exception:
                return None
        return None

