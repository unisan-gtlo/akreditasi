"""
Model Master Struktur Akreditasi SIAKRED.

Hirarki:
    Instrumen (BAN-PT IAPS 4.0, LAM Teknik, LAM Infokom, LAMEMBA, LAMSPAK)
      └── Standar (Kriteria 1-9)
           └── SubStandar (bertingkat bebas via self-FK)
                └── ButirDokumen (item dokumen yang harus diarsipkan)

Plus: MappingProdiInstrumen — mapping prodi ke instrumen akreditasi yang dipakai.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


# ============================================
# CONSTANTS
# ============================================

class KategoriKepemilikan(models.TextChoices):
    UNIVERSITAS = "UNIVERSITAS", _("Universitas")
    BIRO = "BIRO", _("Biro / Lembaga")
    FAKULTAS = "FAKULTAS", _("Fakultas")
    PRODI = "PRODI", _("Program Studi")


# ============================================
# INSTRUMEN AKREDITASI
# ============================================

class Instrumen(models.Model):
    """
    Instrumen akreditasi yang dipakai UNISAN:
    - BAN-PT IAPS 4.0
    - LAM Teknik
    - LAM Infokom
    - LAMEMBA
    - LAMSPAK IAPS 2.0
    - atau instrumen lain yang muncul di masa depan.
    """

    kode = models.CharField(
        _("Kode Instrumen"),
        max_length=30,
        unique=True,
        help_text=_("Kode singkat, contoh: IAPS40, LAMTEKNIK, LAMINFOKOM"),
    )
    nama_resmi = models.CharField(
        _("Nama Resmi"),
        max_length=200,
        help_text=_("Nama lengkap instrumen, contoh: BAN-PT IAPS 4.0"),
    )
    nama_singkat = models.CharField(
        _("Nama Singkat"),
        max_length=50,
        help_text=_("Contoh: IAPS 4.0, LAM Teknik"),
    )
    versi = models.CharField(
        _("Versi"),
        max_length=20,
        blank=True,
        help_text=_("Contoh: 4.0, 2.0, 2024"),
    )
    lembaga = models.CharField(
        _("Lembaga Penyelenggara"),
        max_length=150,
        help_text=_("Contoh: BAN-PT, LAM Teknik, LAMSPAK"),
    )

    # Label kolom dinamis — tiap instrumen bisa pakai istilah berbeda
    label_standar = models.CharField(
        _("Label untuk Standar"),
        max_length=50,
        default="Kriteria",
        help_text=_("Contoh: 'Kriteria' (BAN-PT) atau 'Standar' (LAM lain)"),
    )
    label_substandar = models.CharField(
        _("Label untuk Sub-Standar"),
        max_length=50,
        default="Sub-Kriteria",
        help_text=_("Contoh: 'Sub-Kriteria', 'Indikator', 'Butir'"),
    )
    label_butir = models.CharField(
        _("Label untuk Butir Dokumen"),
        max_length=50,
        default="Butir Dokumen",
        help_text=_("Contoh: 'Butir Dokumen', 'Item'"),
    )

    # Info
    deskripsi = models.TextField(_("Deskripsi"), blank=True)
    tahun_berlaku = models.CharField(
        _("Tahun Berlaku"),
        max_length=20,
        blank=True,
        help_text=_("Contoh: 2018-sekarang, 2024-sekarang"),
    )
    url_referensi = models.URLField(
        _("URL Referensi"),
        blank=True,
        help_text=_("Link ke halaman resmi instrumen"),
    )
    logo = models.ImageField(
        _("Logo Lembaga"),
        upload_to="instrumen/logo/",
        blank=True,
        null=True,
    )

    # Status
    aktif = models.BooleanField(_("Aktif"), default=True)
    urutan = models.PositiveIntegerField(_("Urutan Tampil"), default=0)

    # Metadata
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Instrumen Akreditasi")
        verbose_name_plural = _("Instrumen Akreditasi")
        db_table = "instrumen"
        ordering = ["urutan", "kode"]

    def __str__(self):
        return f"{self.nama_singkat} — {self.lembaga}"

    @property
    def jumlah_standar(self):
        return self.standar.count()

    @property
    def jumlah_butir(self):
        return ButirDokumen.objects.filter(
            sub_standar__standar__instrumen=self
        ).count()


# ============================================
# STANDAR / KRITERIA
# ============================================

class Standar(models.Model):
    """
    Standar (atau Kriteria) dalam sebuah Instrumen.
    Contoh untuk IAPS 4.0:
      Kriteria 1: Visi, Misi, Tujuan, dan Strategi
      Kriteria 2: Tata Pamong, Tata Kelola, dan Kerjasama
      ...dan seterusnya.

    Jumlah standar per instrumen BEBAS — bisa 5, 9, atau berapa pun.
    """

    instrumen = models.ForeignKey(
        Instrumen,
        on_delete=models.CASCADE,
        related_name="standar",
        verbose_name=_("Instrumen"),
    )
    nomor = models.CharField(
        _("Nomor Standar"),
        max_length=20,
        help_text=_("Contoh: 1, 2, A, B, I, II"),
    )
    nama = models.CharField(
        _("Nama Standar"),
        max_length=300,
        help_text=_("Contoh: 'Visi, Misi, Tujuan, dan Strategi'"),
    )
    deskripsi = models.TextField(_("Deskripsi"), blank=True)

    # Bobot nilai (opsional, untuk sistem scoring nanti)
    bobot = models.DecimalField(
        _("Bobot Nilai (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Persentase bobot standar dari total, contoh: 11.11"),
    )

    urutan = models.PositiveIntegerField(_("Urutan"), default=0)
    aktif = models.BooleanField(_("Aktif"), default=True)

    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Standar / Kriteria")
        verbose_name_plural = _("Standar / Kriteria")
        db_table = "standar"
        ordering = ["instrumen", "urutan", "nomor"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrumen", "nomor"],
                name="unique_instrumen_standar_nomor",
            )
        ]

    def __str__(self):
        return f"{self.instrumen.nama_singkat} — {self.label_lengkap}"

    @property
    def label_lengkap(self):
        """Format: '{Label Instrumen} {Nomor}: {Nama}'"""
        label = self.instrumen.label_standar
        return f"{label} {self.nomor}: {self.nama}"

    @property
    def jumlah_substandar(self):
        return self.sub_standar.filter(parent__isnull=True).count()

    @property
    def jumlah_butir(self):
        return ButirDokumen.objects.filter(sub_standar__standar=self).count()


# ============================================
# SUB-STANDAR (Bertingkat)
# ============================================

class SubStandar(models.Model):
    """
    Sub-bagian dalam Standar. BERTINGKAT BEBAS via self-FK (parent).

    Contoh (IAPS 4.0):
      Kriteria 2 → SubStandar 2.1 (Sistem Tata Pamong) ← parent: null
                   └── SubStandar 2.1.1 (Dokumen formal) ← parent: 2.1
                        └── SubStandar 2.1.1.a ← parent: 2.1.1
    """

    standar = models.ForeignKey(
        Standar,
        on_delete=models.CASCADE,
        related_name="sub_standar",
        verbose_name=_("Standar Induk"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Sub-Standar Induk"),
        help_text=_("Kosongkan jika level paling atas"),
    )
    nomor = models.CharField(
        _("Nomor"),
        max_length=30,
        help_text=_("Contoh: 2.1, 2.1.1, 2.1.1.a"),
    )
    nama = models.CharField(
        _("Nama Sub-Standar"),
        max_length=300,
        help_text=_("Contoh: 'Sistem Tata Pamong'"),
    )
    deskripsi = models.TextField(_("Deskripsi"), blank=True)
    panduan = models.TextField(
        _("Panduan Penilaian"),
        blank=True,
        help_text=_("Panduan untuk asesor/tim akreditasi"),
    )

    urutan = models.PositiveIntegerField(_("Urutan"), default=0)
    aktif = models.BooleanField(_("Aktif"), default=True)

    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Sub-Standar")
        verbose_name_plural = _("Sub-Standar")
        db_table = "sub_standar"
        ordering = ["standar", "urutan", "nomor"]
        constraints = [
            models.UniqueConstraint(
                fields=["standar", "nomor"],
                name="unique_standar_substandar_nomor",
            )
        ]

    def __str__(self):
        return f"{self.nomor} — {self.nama}"

    @property
    def level(self):
        """Tingkatan kedalaman sub-standar (1 = atas, 2, 3, dst)."""
        level = 1
        p = self.parent
        while p is not None:
            level += 1
            p = p.parent
        return level

    @property
    def path(self):
        """Path lengkap, contoh: '2 > 2.1 > 2.1.1'"""
        parts = [self.nomor]
        p = self.parent
        while p is not None:
            parts.insert(0, p.nomor)
            p = p.parent
        parts.insert(0, self.standar.nomor)
        return " > ".join(parts)

    @property
    def jumlah_butir_langsung(self):
        """Butir dokumen yang langsung di bawah sub-standar ini (tidak termasuk anak)."""
        return self.butir_dokumen.count()

    @property
    def jumlah_children(self):
        return self.children.count()


# ============================================
# BUTIR DOKUMEN
# ============================================

class ButirDokumen(models.Model):
    """
    Item dokumen konkret yang harus diarsipkan di bawah sebuah Sub-Standar.

    Contoh:
      SubStandar 2.1.1 ('Dokumen formal tata pamong')
        → Butir 'SK Senat Akademik' (UNIVERSITAS, wajib)
        → Butir 'Renstra Fakultas' (FAKULTAS, wajib)
        → Butir 'Renstra Prodi' (PRODI, wajib)
    """

    class FormatFile(models.TextChoices):
        PDF = "PDF", _("PDF")
        DOCX = "DOCX", _("Word (DOCX)")
        XLSX = "XLSX", _("Excel (XLSX)")
        PPTX = "PPTX", _("PowerPoint (PPTX)")
        GAMBAR = "GAMBAR", _("Gambar (JPG/PNG)")
        APAPUN = "APAPUN", _("Format Apapun")

    sub_standar = models.ForeignKey(
        SubStandar,
        on_delete=models.CASCADE,
        related_name="butir_dokumen",
        verbose_name=_("Sub-Standar"),
    )
    kode = models.CharField(
        _("Kode Butir"),
        max_length=50,
        help_text=_("Kode unik, contoh: 2.1.1-A"),
    )
    nama_dokumen = models.CharField(
        _("Nama Dokumen"),
        max_length=300,
        help_text=_("Contoh: 'SK Senat Akademik tentang Tata Pamong'"),
    )
    deskripsi = models.TextField(_("Deskripsi"), blank=True)
    panduan_dokumen = models.TextField(
        _("Panduan Isi Dokumen"),
        blank=True,
        help_text=_("Hal-hal yang wajib ada di dalam dokumen"),
    )

    # Kategori kepemilikan — ini PENTING untuk visibility rule
    kategori_kepemilikan = models.CharField(
        _("Kategori Kepemilikan"),
        max_length=15,
        choices=KategoriKepemilikan.choices,
        help_text=_("Menentukan siapa yang bertanggung jawab mengunggah"),
    )

    # Aturan
    wajib = models.BooleanField(
        _("Wajib"),
        default=True,
        help_text=_("Jika True, dokumen ini wajib diunggah untuk akreditasi"),
    )
    format_diterima = models.CharField(
        _("Format File"),
        max_length=15,
        choices=FormatFile.choices,
        default=FormatFile.PDF,
    )
    ukuran_max_mb = models.PositiveIntegerField(
        _("Ukuran Maks (MB)"),
        default=50,
    )

    # Status akses default (user bisa override saat upload)
    status_akses_default = models.CharField(
        _("Status Akses Default"),
        max_length=10,
        choices=[("TERBUKA", _("Terbuka")), ("INTERNAL", _("Internal"))],
        default="INTERNAL",
        help_text=_("Default saat upload. User bisa override (dengan hak akses)."),
    )

    urutan = models.PositiveIntegerField(_("Urutan"), default=0)
    aktif = models.BooleanField(_("Aktif"), default=True)

    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Butir Dokumen")
        verbose_name_plural = _("Butir Dokumen")
        db_table = "butir_dokumen"
        ordering = ["sub_standar", "urutan", "kode"]
        constraints = [
            models.UniqueConstraint(
                fields=["sub_standar", "kode"],
                name="unique_substandar_butir_kode",
            )
        ]

    def __str__(self):
        return f"{self.kode} — {self.nama_dokumen}"


# ============================================
# MAPPING PRODI → INSTRUMEN
# ============================================

class MappingProdiInstrumen(models.Model):
    """
    Mapping antara Program Studi (dari SIMDA) dengan Instrumen Akreditasi.

    Contoh:
      Prodi T21 (Teknik Elektro) → LAM Teknik
      Prodi E21 (Manajemen) → LAMEMBA
      Prodi P21 (Agroteknologi) → BAN-PT IAPS 4.0

    kode_prodi = PK di master.program_studi (varchar, cross-schema).
    """

    kode_prodi = models.CharField(
        _("Kode Prodi"),
        max_length=10,
        unique=True,
        help_text=_("Link ke master.program_studi.kode_prodi (PK)"),
    )
    
    nama_prodi = models.CharField(
        _("Nama Prodi"),
        max_length=200,
        help_text=_("Cached dari SIMDA untuk display cepat"),
    )
    instrumen = models.ForeignKey(
        Instrumen,
        on_delete=models.PROTECT,
        related_name="prodi_terdaftar",
        verbose_name=_("Instrumen Akreditasi"),
    )
    catatan = models.TextField(_("Catatan"), blank=True)

    aktif = models.BooleanField(_("Aktif"), default=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)
    tanggal_diubah = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Mapping Prodi ↔ Instrumen")
        verbose_name_plural = _("Mapping Prodi ↔ Instrumen")
        db_table = "mapping_prodi_instrumen"
        ordering = ["kode_prodi"]

    def __str__(self):
        return f"{self.kode_prodi} ({self.nama_prodi}) → {self.instrumen.nama_singkat}"

# ============================================
# IMPORT LOG (untuk Import Excel)
# ============================================

class ImportLog(models.Model):
    """
    Log audit untuk tiap upaya import data master dari file Excel.
    Satu file upload = satu ImportLog dengan banyak ImportLogItem.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Menunggu Preview")
        PREVIEWED = "PREVIEWED", _("Preview Ditampilkan")
        COMMITTED = "COMMITTED", _("Tersimpan ke Database")
        CANCELLED = "CANCELLED", _("Dibatalkan")
        FAILED = "FAILED", _("Gagal")

    class Mode(models.TextChoices):
        UPDATE = "UPDATE", _("Update jika sudah ada")
        SKIP = "SKIP", _("Skip jika sudah ada")
        ERROR = "ERROR", _("Error jika sudah ada")

    # File info
    file_name = models.CharField(_("Nama File"), max_length=255)
    file_size_kb = models.PositiveIntegerField(_("Ukuran (KB)"), default=0)
    file = models.FileField(
        _("File Excel"),
        upload_to="import_master/%Y/%m/",
        null=True,
        blank=True,
    )

    # Target
    instrumen = models.ForeignKey(
        Instrumen,
        on_delete=models.PROTECT,
        related_name="import_logs",
        verbose_name=_("Instrumen Target"),
        help_text=_("Data akan di-import ke instrumen ini"),
    )

    # Config
    mode = models.CharField(
        _("Mode Import"),
        max_length=10,
        choices=Mode.choices,
        default=Mode.UPDATE,
    )

    # Counters
    total_rows = models.PositiveIntegerField(_("Total Baris"), default=0)
    valid_rows = models.PositiveIntegerField(_("Baris Valid"), default=0)
    error_rows = models.PositiveIntegerField(_("Baris Error"), default=0)
    substandar_created = models.PositiveIntegerField(default=0)
    substandar_updated = models.PositiveIntegerField(default=0)
    butir_created = models.PositiveIntegerField(default=0)
    butir_updated = models.PositiveIntegerField(default=0)

    # Status
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(_("Pesan Error"), blank=True)

    # Metadata
    uploaded_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="master_imports",
        verbose_name=_("Uploader"),
    )
    waktu_upload = models.DateTimeField(auto_now_add=True)
    waktu_commit = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Log Import Excel")
        verbose_name_plural = _("Log Import Excel")
        db_table = "import_log"
        ordering = ["-waktu_upload"]

    def __str__(self):
        return f"{self.file_name} - {self.get_status_display()} ({self.waktu_upload:%d %b %Y %H:%M})"

    @property
    def is_final(self):
        return self.status in [self.Status.COMMITTED, self.Status.CANCELLED, self.Status.FAILED]

    @property
    def is_valid_for_commit(self):
        return self.status == self.Status.PREVIEWED and self.valid_rows > 0


class ImportLogItem(models.Model):
    """
    Detail per baris yang diproses dari file Excel.
    Dipakai untuk preview (sebelum commit) & audit (setelah commit).
    """

    class Sheet(models.TextChoices):
        SUBSTANDAR = "SUBSTANDAR", _("Sub-Standar")
        BUTIR = "BUTIR", _("Butir Dokumen")

    class ItemStatus(models.TextChoices):
        VALID = "VALID", _("Valid")
        INVALID = "INVALID", _("Tidak Valid")
        DUPLICATE = "DUPLICATE", _("Duplikat (akan di-skip)")
        WILL_UPDATE = "WILL_UPDATE", _("Akan di-update")
        WILL_CREATE = "WILL_CREATE", _("Akan dibuat baru")
        CREATED = "CREATED", _("Berhasil dibuat")
        UPDATED = "UPDATED", _("Berhasil di-update")
        SKIPPED = "SKIPPED", _("Dilewati")
        FAILED = "FAILED", _("Gagal")

    import_log = models.ForeignKey(
        ImportLog,
        on_delete=models.CASCADE,
        related_name="items",
    )
    sheet = models.CharField(
        _("Sheet Asal"),
        max_length=15,
        choices=Sheet.choices,
    )
    row_number = models.PositiveIntegerField(_("Nomor Baris"))

    # Parsed data (store as JSON-like dict via TextField)
    raw_data = models.JSONField(_("Data Baris"), default=dict)

    # Validation result
    status = models.CharField(
        _("Status Item"),
        max_length=15,
        choices=ItemStatus.choices,
    )
    error_detail = models.TextField(_("Detail Error"), blank=True)

    # Reference to created/updated object
    substandar = models.ForeignKey(
        SubStandar, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    butir = models.ForeignKey(
        ButirDokumen, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("Item Import")
        verbose_name_plural = _("Item Import")
        db_table = "import_log_item"
        ordering = ["import_log", "sheet", "row_number"]

    def __str__(self):
        return f"Row {self.row_number} ({self.sheet}) — {self.get_status_display()}"

# ============================================================================
# IMPORT MODEL UNMANAGED — REFERENSI SIMDA
# ============================================================================
# File terpisah agar tidak mencampur model managed SIAKRED dengan referensi
# read-only ke schema `master` (SIMDA). Lihat models_simda_ref.py untuk detail.
from .models_simda_ref import (  # noqa: E402, F401
    FakultasRef,
    ProgramStudiRef,
    TahunAkademikRef,
    JabatanFungsionalRef,
    DataDosenRef,
    RiwayatBKDRef,
    RiwayatJabfungRef,
    RiwayatPendidikanDosenRef,
)

# ============================================================================
# IMPORT MODEL MANAGED — INTEGRASI DOSEN-AKREDITASI
# ============================================================================
from .models_dosen_link import (  # noqa: E402, F401
    ButirDataDosenMapping,
    DTPSDosenSesi,
    SnapshotDataSimda,
)