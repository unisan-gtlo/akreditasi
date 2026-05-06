"""
Model untuk integrasi data dosen (SIMDA) dengan butir akreditasi (SIAKRED).

Berisi 3 model managed:

  1. ButirDataDosenMapping
     Setting global per butir dokumen yang menentukan jenis data SIMDA yang
     akan ditampilkan ke asesor (BKD, Jabfung, Pendidikan, Profil).
     Di-set sekali per butir oleh admin LP3M, berlaku untuk semua sesi.

  2. DTPSDosenSesi
     Pool dosen yang dianggap DTPS untuk satu sesi akreditasi tertentu.
     Mendukung praktik nyata akreditasi: dosen DTPS bisa berasal dari
     prodi homebase + dosen pembina MK umum dari prodi lain (mis. Agama,
     Pancasila, Bahasa Indonesia). Auto-populate saat sesi dibuat,
     bisa di-edit operator (tambah dosen lintas prodi atau soft-disable).

  3. SnapshotDataSimda
     Audit trail otomatis saat sesi akreditasi di-finalize. Snapshot
     state data SIMDA pada momen finalize agar tetap permanen kalau
     data SIMDA berubah kemudian.

WORKFLOW:
  1. Admin LP3M setup ButirDataDosenMapping (sekali per butir kinerja dosen)
  2. Operator buat SesiAkreditasi → signal auto-populate DTPSDosenSesi
     dengan semua dosen homebase prodi (sumber=AUTO_HOMEBASE)
  3. Operator buka "Atur DTPS" → bisa tambah dosen lintas prodi (MANUAL_TAMBAHAN)
     atau soft-disable dosen homebase yang tidak relevan (aktif=False)
  4. Asesor buka butir terkait kinerja dosen → sistem fetch:
     - DTPSDosenSesi (aktif=True) untuk daftar NIDN
     - DataDosenRef + RiwayatBKDRef dari SIMDA berdasarkan NIDN tersebut
  5. Sesi finalize → SnapshotDataSimda menyimpan state permanen
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


# ============================================================================
# 1. MAPPING GLOBAL: BUTIR ↔ JENIS DATA SIMDA
# ============================================================================

class ButirDataDosenMapping(models.Model):
    """Mapping global butir akreditasi ke jenis data dosen di SIMDA.

    Di-set sekali oleh admin LP3M. Berlaku untuk SEMUA sesi yang
    menggunakan butir tersebut.
    """

    JENIS_DATA_CHOICES = [
        ('BKD',         'Beban Kerja Dosen'),
        ('JABFUNG',     'Riwayat Jabatan Fungsional'),
        ('PENDIDIKAN',  'Riwayat Pendidikan'),
        ('PROFIL',      'Profil Dosen (Identitas + ID Akademik)'),
    ]

    FILTER_PERIODE_CHOICES = [
        ('TS_ONLY',         'Hanya TS (tahun saat ini)'),
        ('TS_TS_M1',        'TS dan TS-1 (2 tahun terakhir)'),
        ('TS_TS_M1_TS_M2',  'TS, TS-1, TS-2 (3 tahun terakhir)'),
        ('TS_TS_M3',        'TS sampai TS-3 (4 tahun, untuk BAN-PT)'),
        ('SEMUA',           'Semua periode (history lengkap)'),
        ('AKTIF_SAJA',      'Hanya periode aktif (untuk data non-temporal)'),
    ]

    butir = models.OneToOneField(
        'master_akreditasi.ButirDokumen',
        on_delete=models.CASCADE,
        related_name='mapping_data_dosen',
        verbose_name='Butir Dokumen',
    )
    jenis_data = models.CharField(
        max_length=20,
        choices=JENIS_DATA_CHOICES,
        verbose_name='Jenis Data SIMDA',
    )
    filter_periode = models.CharField(
        max_length=30,
        choices=FILTER_PERIODE_CHOICES,
        default='TS_TS_M1_TS_M2',
        verbose_name='Filter Periode',
    )
    deskripsi_filter = models.TextField(
        blank=True, default='',
        verbose_name='Deskripsi Filter',
        help_text='Penjelasan untuk asesor — misal "Data BKD 3 tahun terakhir untuk Tabel 3.a.3 LKPS"',
    )
    aktif = models.BooleanField(default=True, verbose_name='Aktif')

    tanggal_dibuat = models.DateTimeField(default=timezone.now)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='mapping_data_dosen_created',
    )

    class Meta:
        db_table = 'butir_data_dosen_mapping'
        verbose_name = 'Mapping Butir ↔ Data Dosen'
        verbose_name_plural = 'Mapping Butir ↔ Data Dosen'

    def __str__(self):
        return f"{self.butir.kode} → {self.get_jenis_data_display()}"


# ============================================================================
# 2. POOL DTPS PER SESI: AUTO HOMEBASE + MANUAL TAMBAHAN
# ============================================================================

class DTPSDosenSesi(models.Model):
    """Pool dosen yang dianggap DTPS untuk satu sesi akreditasi.

    Mendukung praktik akreditasi nyata: DTPS suatu prodi bisa berasal
    dari beberapa sumber:
      - Dosen homebase prodi tersebut (auto-populated saat sesi dibuat)
      - Dosen pembina MK umum dari prodi lain (Agama, Pancasila, dll)
      - Dosen tetap yayasan yang mengajar MK lintas prodi

    Satu dosen bisa muncul di banyak sesi (di banyak prodi sekaligus).

    Field 'aktif' digunakan untuk soft-delete: kalau operator unchecklist
    seorang dosen homebase (mis. sedang tugas belajar), record tetap ada
    untuk audit trail tapi tidak ikut di-fetch saat asesor lihat butir.
    """

    SUMBER_CHOICES = [
        ('AUTO_HOMEBASE',     'Otomatis dari Homebase Prodi'),
        ('MANUAL_TAMBAHAN',   'Manual Ditambahkan Operator'),
    ]

    PERAN_CHOICES = [
        ('DTPS_HOMEBASE',     'DTPS Homebase Prodi'),
        ('DTPS_BERSAMA',      'DTPS Bersama (lintas prodi tetap)'),
        ('DOSEN_MK_UMUM',     'Dosen MK Umum (Agama, Pancasila, Bahasa, dll)'),
        ('DOSEN_PEMBINA',     'Dosen Pembina/Pendamping'),
        ('LAINNYA',           'Lainnya'),
    ]

    sesi = models.ForeignKey(
        'sesi.SesiAkreditasi',
        on_delete=models.CASCADE,
        related_name='dtps_pool',
        verbose_name='Sesi Akreditasi',
    )
    dosen_nidn = models.CharField(
        max_length=20,
        verbose_name='NIDN Dosen',
        db_index=True,
        help_text='NIDN harus match dengan master.data_dosen.nidn di SIMDA',
    )
    sumber = models.CharField(
        max_length=20,
        choices=SUMBER_CHOICES,
        default='MANUAL_TAMBAHAN',
        verbose_name='Sumber Inklusi',
    )
    peran = models.CharField(
        max_length=20,
        choices=PERAN_CHOICES,
        default='DTPS_HOMEBASE',
        verbose_name='Peran sebagai DTPS',
    )
    mk_diampu = models.TextField(
        blank=True, default='',
        verbose_name='Mata Kuliah Diampu di Prodi Ini',
        help_text='Untuk dosen lintas prodi: contoh "Pendidikan Agama Islam, Pendidikan Pancasila"',
    )
    alasan_inklusi = models.TextField(
        blank=True, default='',
        verbose_name='Alasan Inklusi',
        help_text='Penting untuk dosen MANUAL_TAMBAHAN — dokumentasi audit',
    )

    aktif = models.BooleanField(
        default=True,
        verbose_name='Aktif (dilibatkan dalam akreditasi)',
        help_text='Uncheck untuk soft-disable: record tetap ada untuk audit '
                  'tapi tidak muncul di butir akreditasi.',
    )

    # ---- Snapshot fields — diisi saat record dibuat untuk audit trail ----
    dosen_nama_snapshot = models.CharField(max_length=200, blank=True, default='')
    dosen_homebase_prodi_snapshot = models.CharField(max_length=10, blank=True, default='')
    dosen_homebase_fakultas_snapshot = models.CharField(max_length=10, blank=True, default='')
    dosen_jabfung_snapshot = models.CharField(max_length=100, blank=True, default='')
    snapshot_at = models.DateTimeField(default=timezone.now)
    snapshot_outdated = models.BooleanField(
        default=False,
        verbose_name='Snapshot Outdated',
        help_text='True jika data dosen di SIMDA berbeda dengan snapshot. '
                  'Bisa di-refresh manual oleh operator.',
    )

    # ---- Audit ----
    tanggal_dibuat = models.DateTimeField(default=timezone.now)
    tanggal_diubah = models.DateTimeField(auto_now=True)
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='dtps_dosen_created',
    )

    class Meta:
        db_table = 'dtps_dosen_sesi'
        verbose_name = 'DTPS Dosen per Sesi'
        verbose_name_plural = 'DTPS Dosen per Sesi'
        constraints = [
            models.UniqueConstraint(
                fields=['sesi', 'dosen_nidn'],
                name='unique_sesi_dosen_dtps',
            ),
        ]
        indexes = [
            models.Index(fields=['sesi', 'aktif'], name='dtps_sesi_aktif_idx'),
        ]
        ordering = ['sesi', 'sumber', 'dosen_nama_snapshot']

    def __str__(self):
        status = '✓' if self.aktif else '✗'
        return f"[{status}] {self.dosen_nidn} - {self.dosen_nama_snapshot} ({self.get_sumber_display()})"

    def refresh_snapshot_from_simda(self):
        """Update snapshot fields dari data SIMDA terkini.

        Dipanggil saat operator klik "Refresh" untuk dosen yang snapshot_outdated.
        """
        from .models_simda_ref import DataDosenRef

        try:
            dosen = DataDosenRef.objects.select_related(
                'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
            ).get(nidn=self.dosen_nidn)
        except DataDosenRef.DoesNotExist:
            return False

        self.dosen_nama_snapshot = dosen.nama_lengkap
        self.dosen_homebase_prodi_snapshot = dosen.kode_prodi_id
        self.dosen_homebase_fakultas_snapshot = dosen.kode_fakultas_id
        self.dosen_jabfung_snapshot = (
            dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else ''
        )
        self.snapshot_at = timezone.now()
        self.snapshot_outdated = False
        self.save(update_fields=[
            'dosen_nama_snapshot',
            'dosen_homebase_prodi_snapshot',
            'dosen_homebase_fakultas_snapshot',
            'dosen_jabfung_snapshot',
            'snapshot_at',
            'snapshot_outdated',
            'tanggal_diubah',
        ])
        return True

    def check_snapshot_outdated(self):
        """Check apakah snapshot beda dengan data SIMDA terkini.

        Mengupdate field snapshot_outdated tanpa rewrite snapshot itu sendiri.
        """
        from .models_simda_ref import DataDosenRef

        try:
            dosen = DataDosenRef.objects.select_related(
                'kode_prodi', 'kode_fakultas',
            ).get(nidn=self.dosen_nidn)
        except DataDosenRef.DoesNotExist:
            self.snapshot_outdated = True
            self.save(update_fields=['snapshot_outdated', 'tanggal_diubah'])
            return True

        is_outdated = (
            self.dosen_nama_snapshot != dosen.nama_lengkap
            or self.dosen_homebase_prodi_snapshot != dosen.kode_prodi_id
            or self.dosen_homebase_fakultas_snapshot != dosen.kode_fakultas_id
        )
        if is_outdated != self.snapshot_outdated:
            self.snapshot_outdated = is_outdated
            self.save(update_fields=['snapshot_outdated', 'tanggal_diubah'])
        return is_outdated


# ============================================================================
# 3. SNAPSHOT: AUDIT TRAIL SAAT SESI FINALIZE
# ============================================================================

class SnapshotDataSimda(models.Model):
    """Snapshot data SIMDA saat sesi akreditasi di-finalize.

    Di-trigger otomatis saat operator klik "Finalisasi Sesi" atau saat
    sesi berubah status ke SUBMITTED. Tujuannya: simpan state permanen
    agar kalau data SIMDA berubah (dosen pindah, BKD update), snapshot
    sesi tetap mencerminkan kondisi saat akreditasi diajukan.
    """

    JENIS_DATA_CHOICES = ButirDataDosenMapping.JENIS_DATA_CHOICES + [
        ('DAFTAR_DTPS', 'Daftar DTPS Sesi (snapshot lengkap pool dosen)'),
    ]

    sesi = models.ForeignKey(
        'sesi.SesiAkreditasi',
        on_delete=models.CASCADE,
        related_name='snapshot_simda',
        verbose_name='Sesi Akreditasi',
    )
    butir = models.ForeignKey(
        'master_akreditasi.ButirDokumen',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='snapshot_simda',
        verbose_name='Butir Dokumen',
        help_text='Null = snapshot scope sesi (bukan per-butir)',
    )
    jenis_data = models.CharField(max_length=20, choices=JENIS_DATA_CHOICES)

    data_json = models.JSONField(
        default=list,
        verbose_name='Data Snapshot',
        help_text='List dictionary lengkap hasil query SIMDA pada momen snapshot',
    )
    total_records = models.IntegerField(
        default=0,
        verbose_name='Jumlah Record',
        help_text='Total record di data_json (cached untuk display cepat)',
    )
    keterangan = models.TextField(blank=True, default='')

    tanggal_snapshot = models.DateTimeField(default=timezone.now)
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='snapshot_simda_created',
    )

    class Meta:
        db_table = 'snapshot_data_simda'
        verbose_name = 'Snapshot Data SIMDA'
        verbose_name_plural = 'Snapshot Data SIMDA'
        ordering = ['-tanggal_snapshot']
        indexes = [
            models.Index(fields=['sesi', 'jenis_data'], name='snap_sesi_jenis_idx'),
        ]

    def __str__(self):
        butir_label = self.butir.kode if self.butir else '(sesi-wide)'
        return f"Snapshot {self.get_jenis_data_display()} - {butir_label} - {self.tanggal_snapshot:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        # Auto-update total_records saat save
        if isinstance(self.data_json, list):
            self.total_records = len(self.data_json)
        super().save(*args, **kwargs)
