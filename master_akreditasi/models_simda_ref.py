"""
Model referensi SIMDA untuk SIAKRED.

File ini berisi model "unmanaged" yang memetakan tabel-tabel di schema `master`
(milik SIMDA) ke ORM Django di sisi SIAKRED. Tujuannya:

  1. Memungkinkan SIAKRED query data dosen, BKD, jabfung, pendidikan,
     prodi, fakultas, dan tahun akademik dengan ORM Django (bukan raw SQL).
  2. SIAKRED HANYA membaca (SELECT). Tidak ada INSERT/UPDATE/DELETE.
  3. Migration Django TIDAK PERNAH menyentuh tabel-tabel ini (managed=False).

PRINSIP PENTING:
  - Single Source of Truth: tabel ini dimiliki oleh SIMDA. SIAKRED hanya pointer.
  - Read-only: pastikan permission DB hanya GRANT SELECT.
  - Schema multi-tenant: db_table mencantumkan schema 'master' secara eksplisit
    dengan format 'master"."nama_tabel' (escape PostgreSQL untuk schema-qualified).

CARA QUERY:
  >>> from master_akreditasi.models_simda_ref import DataDosenRef
  >>> dosen = DataDosenRef.objects.filter(kode_prodi='E11', is_active=True)
  >>> for d in dosen:
  ...     print(d.nidn, d.nama_lengkap)
"""

from django.db import models


# ============================================================================
# REFERENSI MASTER UMUM
# ============================================================================

class FakultasRef(models.Model):
    """Referensi ke master.fakultas (SIMDA)."""

    kode_fakultas = models.CharField(max_length=10, primary_key=True)
    nama_fakultas = models.CharField(max_length=150)
    nama_singkat = models.CharField(max_length=30)
    akreditasi = models.CharField(max_length=30)
    no_sk_akreditasi = models.CharField(max_length=100)
    tgl_sk_akreditasi = models.DateField(null=True, blank=True)
    berlaku_sampai_akreditasi = models.DateField(null=True, blank=True)
    telepon = models.CharField(max_length=20)
    email = models.CharField(max_length=254)
    urutan = models.IntegerField()
    status = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'master"."fakultas'
        verbose_name = 'Fakultas (SIMDA)'
        verbose_name_plural = 'Fakultas (SIMDA)'
        ordering = ['urutan', 'kode_fakultas']

    def __str__(self):
        return f"{self.kode_fakultas} - {self.nama_fakultas}"


class ProgramStudiRef(models.Model):
    """Referensi ke master.program_studi (SIMDA)."""

    kode_prodi = models.CharField(max_length=10, primary_key=True)
    kode_prodi_dikti = models.CharField(max_length=20)
    nama_prodi = models.CharField(max_length=150)
    jenjang = models.CharField(max_length=10)
    akreditasi = models.CharField(max_length=30)
    no_sk_akreditasi = models.CharField(max_length=100)
    tgl_sk_akreditasi = models.DateField(null=True, blank=True)
    berlaku_sampai_akreditasi = models.DateField(null=True, blank=True)
    email_prodi = models.CharField(max_length=254)
    urutan = models.IntegerField()
    status = models.CharField(max_length=10)
    kode_fakultas = models.ForeignKey(
        FakultasRef,
        on_delete=models.DO_NOTHING,
        db_column='kode_fakultas',
        to_field='kode_fakultas',
        related_name='prodi_set',
    )

    class Meta:
        managed = False
        db_table = 'master"."program_studi'
        verbose_name = 'Program Studi (SIMDA)'
        verbose_name_plural = 'Program Studi (SIMDA)'
        ordering = ['urutan', 'kode_prodi']

    def __str__(self):
        return f"{self.kode_prodi} - {self.nama_prodi}"


class TahunAkademikRef(models.Model):
    """Referensi ke master.tahun_akademik (SIMDA)."""

    id = models.BigIntegerField(primary_key=True)
    tahun_akademik = models.CharField(max_length=10, unique=True)
    semester_aktif = models.CharField(max_length=10)
    label_lengkap = models.CharField(max_length=50)
    tgl_mulai = models.DateField(null=True, blank=True)
    tgl_selesai = models.DateField(null=True, blank=True)
    urutan = models.IntegerField()
    is_aktif = models.BooleanField()
    keterangan = models.TextField()

    class Meta:
        managed = False
        db_table = 'master"."tahun_akademik'
        verbose_name = 'Tahun Akademik (SIMDA)'
        verbose_name_plural = 'Tahun Akademik (SIMDA)'
        ordering = ['-urutan']

    def __str__(self):
        return self.label_lengkap or self.tahun_akademik


class JabatanFungsionalRef(models.Model):
    """Referensi ke master.jabatan_fungsional (SIMDA)."""

    id = models.BigIntegerField(primary_key=True)
    kode = models.CharField(max_length=10, unique=True)
    nama = models.CharField(max_length=100)
    singkatan = models.CharField(max_length=10)
    angka_kredit_min = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    kualifikasi_min = models.CharField(max_length=5)
    urutan = models.IntegerField()
    status = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'master"."jabatan_fungsional'
        verbose_name = 'Jabatan Fungsional (SIMDA)'
        verbose_name_plural = 'Jabatan Fungsional (SIMDA)'
        ordering = ['urutan']

    def __str__(self):
        return self.nama


# ============================================================================
# REFERENSI DATA DOSEN
# ============================================================================

class DataDosenRef(models.Model):
    """Referensi ke master.data_dosen (SIMDA).

    Catatan field yang DI-OMIT (dari 60+ kolom di SIMDA):
      - Kolom yang tidak relevan untuk akreditasi (alamat, no_hp, no_rekening,
        atas_nama_rekening, kode_pos, dst) di-skip untuk menjaga model tetap
        compact.
      - Kalau butuh tambahan field nanti, tinggal tambah di sini sesuai schema.
    """

    id = models.BigIntegerField(primary_key=True)
    sso_user_id = models.IntegerField(null=True, blank=True)

    # Identitas inti
    nidn = models.CharField(max_length=20, unique=True)
    nip = models.CharField(max_length=30)
    nip_yayasan = models.CharField(max_length=30)
    nik = models.CharField(max_length=20)
    npwp = models.CharField(max_length=20)
    nuptk = models.CharField(max_length=20)

    # Nama & gelar
    nama_lengkap = models.CharField(max_length=150)
    gelar_depan = models.CharField(max_length=50)
    gelar_belakang = models.CharField(max_length=100)

    # Demografi
    jenis_kelamin = models.CharField(max_length=1)
    tempat_lahir = models.CharField(max_length=100)
    tgl_lahir = models.DateField(null=True, blank=True)
    status_pernikahan = models.CharField(max_length=20)

    # Kontak
    no_hp = models.CharField(max_length=20)
    email_pribadi = models.CharField(max_length=254)
    email_kampus = models.CharField(max_length=254)

    # Akademik
    pendidikan_terakhir = models.CharField(max_length=5)

    # Kepegawaian
    tgl_mulai_kerja = models.DateField(null=True, blank=True)
    no_sk_pengangkatan = models.CharField(max_length=100)
    tgl_sk_pengangkatan = models.DateField(null=True, blank=True)

    # ID Akademik & Riset (untuk integrasi SISTER, SINTA, Scopus)
    id_sinta = models.CharField(max_length=20)
    id_scopus = models.CharField(max_length=50)
    id_google_scholar = models.CharField(max_length=100)
    id_garuda = models.CharField(max_length=20)
    orcid = models.CharField(max_length=19)
    h_index_sinta = models.IntegerField(null=True, blank=True)
    h_index_scopus = models.IntegerField(null=True, blank=True)
    nira = models.CharField(max_length=30)
    id_serdos = models.CharField(max_length=30)

    # File
    foto = models.CharField(max_length=100, null=True, blank=True)
    file_ktp = models.CharField(max_length=100, null=True, blank=True)
    file_npwp = models.CharField(max_length=100, null=True, blank=True)
    file_serdos = models.CharField(max_length=100, null=True, blank=True)
    file_sk_pengangkatan = models.CharField(max_length=100, null=True, blank=True)

    # Status
    is_active = models.BooleanField()
    tgl_dibuat = models.DateTimeField()
    tgl_diperbarui = models.DateTimeField()

    # Foreign keys
    kode_prodi = models.ForeignKey(
        ProgramStudiRef,
        on_delete=models.DO_NOTHING,
        db_column='kode_prodi',
        to_field='kode_prodi',
        related_name='dosen_set',
    )
    kode_fakultas = models.ForeignKey(
        FakultasRef,
        on_delete=models.DO_NOTHING,
        db_column='kode_fakultas',
        to_field='kode_fakultas',
        related_name='dosen_set',
    )
    jabatan_fungsional = models.ForeignKey(
        JabatanFungsionalRef,
        on_delete=models.DO_NOTHING,
        db_column='jabatan_fungsional_id',
        related_name='dosen_set',
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = 'master"."data_dosen'
        verbose_name = 'Data Dosen (SIMDA)'
        verbose_name_plural = 'Data Dosen (SIMDA)'
        ordering = ['nama_lengkap']

    def __str__(self):
        gelar_depan = self.gelar_depan or ''
        nama = self.nama_lengkap
        gelar_belakang = self.gelar_belakang or ''
        nama_lengkap = f"{gelar_depan} {nama} {gelar_belakang}".strip().replace('  ', ' ')
        return f"{nama_lengkap} ({self.nidn})"

    @property
    def nama_dengan_gelar(self):
        """Nama lengkap dengan gelar depan dan belakang."""
        parts = [self.gelar_depan, self.nama_lengkap, self.gelar_belakang]
        return ' '.join(p for p in parts if p).replace('  ', ' ').strip()


# ============================================================================
# RIWAYAT DOSEN — BKD, JABFUNG, PENDIDIKAN
# ============================================================================

class RiwayatBKDRef(models.Model):
    """Referensi ke master.riwayat_bkd (SIMDA).

    Sumber data BKD per dosen per periode untuk Tabel 3.a.3 LKPS akreditasi.
    """

    STATUS_CHOICES = [
        ('belum', 'Belum Disahkan'),
        ('disahkan', 'Disahkan'),
        ('ditolak', 'Ditolak'),
    ]

    id = models.BigIntegerField(primary_key=True)
    sks_pengajaran = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sks_penelitian = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sks_pkm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sks_penunjang = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    file_bkd = models.CharField(max_length=100, null=True, blank=True)
    link_bkd = models.CharField(max_length=200)
    status_pengesahan = models.CharField(max_length=20, choices=STATUS_CHOICES)
    keterangan = models.TextField()
    tgl_upload = models.DateTimeField()
    tgl_diperbarui = models.DateTimeField()
    dosen = models.ForeignKey(
        DataDosenRef,
        on_delete=models.DO_NOTHING,
        db_column='dosen_id',
        related_name='riwayat_bkd',
    )
    periode = models.ForeignKey(
        TahunAkademikRef,
        on_delete=models.DO_NOTHING,
        db_column='periode_id',
        related_name='bkd_set',
    )

    class Meta:
        managed = False
        db_table = 'master"."riwayat_bkd'
        verbose_name = 'Riwayat BKD (SIMDA)'
        verbose_name_plural = 'Riwayat BKD (SIMDA)'
        ordering = ['-periode__urutan']

    def __str__(self):
        return f"BKD {self.dosen.nama_lengkap} - {self.periode.label_lengkap}"

    @property
    def total_sks(self):
        """Total SKS semua dharma."""
        from decimal import Decimal
        total = Decimal('0')
        for v in [self.sks_pengajaran, self.sks_penelitian, self.sks_pkm, self.sks_penunjang]:
            if v is not None:
                total += v
        return total


class RiwayatJabfungRef(models.Model):
    """Referensi ke master.riwayat_jabfung (SIMDA)."""

    id = models.BigIntegerField(primary_key=True)
    no_sk = models.CharField(max_length=100)
    tgl_sk = models.DateField(null=True, blank=True)
    tmt = models.DateField(null=True, blank=True)
    tgl_selesai = models.DateField(null=True, blank=True)
    angka_kredit = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    file_sk = models.CharField(max_length=100, null=True, blank=True)
    keterangan = models.TextField()
    dosen = models.ForeignKey(
        DataDosenRef,
        on_delete=models.DO_NOTHING,
        db_column='dosen_id',
        related_name='riwayat_jabfung',
    )
    jabatan_fungsional = models.ForeignKey(
        JabatanFungsionalRef,
        on_delete=models.DO_NOTHING,
        db_column='jabatan_fungsional_id',
        related_name='riwayat_set',
    )

    class Meta:
        managed = False
        db_table = 'master"."riwayat_jabfung'
        verbose_name = 'Riwayat Jabatan Fungsional (SIMDA)'
        verbose_name_plural = 'Riwayat Jabatan Fungsional (SIMDA)'
        ordering = ['-tmt']

    def __str__(self):
        return f"{self.dosen.nama_lengkap} - {self.jabatan_fungsional.nama}"


class RiwayatPendidikanDosenRef(models.Model):
    """Referensi ke master.riwayat_pendidikan_dosen (SIMDA)."""

    JENJANG_CHOICES = [
        ('S1', 'Sarjana (S1)'),
        ('S2', 'Magister (S2)'),
        ('S3', 'Doktor (S3)'),
        ('Sp1', 'Spesialis 1'),
        ('Sp2', 'Spesialis 2'),
    ]

    id = models.BigIntegerField(primary_key=True)
    jenjang = models.CharField(max_length=5, choices=JENJANG_CHOICES)
    institusi = models.CharField(max_length=200)
    prodi_studi = models.CharField(max_length=150)
    tahun_masuk = models.IntegerField(null=True, blank=True)
    tahun_lulus = models.IntegerField(null=True, blank=True)
    no_ijazah = models.CharField(max_length=50)
    judul_thesis = models.TextField()
    file_ijazah = models.CharField(max_length=100, null=True, blank=True)
    file_transkrip = models.CharField(max_length=100, null=True, blank=True)
    dosen = models.ForeignKey(
        DataDosenRef,
        on_delete=models.DO_NOTHING,
        db_column='dosen_id',
        related_name='riwayat_pendidikan',
    )
    pt_asal_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'master"."riwayat_pendidikan_dosen'
        verbose_name = 'Riwayat Pendidikan Dosen (SIMDA)'
        verbose_name_plural = 'Riwayat Pendidikan Dosen (SIMDA)'
        ordering = ['dosen', '-tahun_lulus']

    def __str__(self):
        return f"{self.dosen.nama_lengkap} - {self.jenjang} {self.institusi}"
