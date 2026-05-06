"""
Django admin UI untuk model integrasi dosen-akreditasi.

Berisi 3 admin utama + 1 inline:

  1. ButirDataDosenMappingAdmin — setup mapping butir → jenis data SIMDA
  2. DTPSDosenSesiAdmin — manage DTPS pool per sesi (auto + manual)
  3. SnapshotDataSimdaAdmin — view audit trail snapshot (read-only)
  4. DTPSDosenSesiInline — tampil di SesiAkreditasiAdmin sebagai tab

Mengikuti pattern admin existing di SIAKRED:
  - @admin.register decorator
  - @admin.display untuk custom column
  - Plain Django admin (tanpa Jazzmin/Select2)
"""

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models_dosen_link import (
    ButirDataDosenMapping,
    DTPSDosenSesi,
    SnapshotDataSimda,
)


# ============================================================================
# 1. BUTIR ↔ DATA DOSEN MAPPING
# ============================================================================

@admin.register(ButirDataDosenMapping)
class ButirDataDosenMappingAdmin(admin.ModelAdmin):
    """Admin untuk setup mapping butir akreditasi → jenis data SIMDA.

    Di-pakai sekali per butir oleh admin LP3M. Setelah di-setup,
    sesi-sesi akreditasi yang menggunakan butir ini akan otomatis
    fetch data dosen sesuai konfigurasi.
    """

    list_display = (
        'butir_kode_display',
        'butir_nama_display',
        'jenis_data',
        'filter_periode',
        'aktif',
        'tanggal_diubah',
    )
    list_filter = (
        'jenis_data',
        'filter_periode',
        'aktif',
        'butir__sub_standar__standar__instrumen',
    )
    search_fields = (
        'butir__kode',
        'butir__nama_dokumen',
        'deskripsi_filter',
    )
    autocomplete_fields = ('butir',)
    readonly_fields = ('tanggal_dibuat', 'tanggal_diubah', 'dibuat_oleh')

    fieldsets = (
        ('Butir Akreditasi', {
            'fields': ('butir',),
        }),
        ('Konfigurasi Data SIMDA', {
            'fields': ('jenis_data', 'filter_periode', 'deskripsi_filter'),
        }),
        ('Status', {
            'fields': ('aktif',),
        }),
        ('Audit', {
            'fields': ('dibuat_oleh', 'tanggal_dibuat', 'tanggal_diubah'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Kode Butir', ordering='butir__kode')
    def butir_kode_display(self, obj):
        return obj.butir.kode

    @admin.display(description='Nama Butir')
    def butir_nama_display(self, obj):
        return obj.butir.nama_dokumen[:80]

    def save_model(self, request, obj, form, change):
        if not change and not obj.dibuat_oleh:
            obj.dibuat_oleh = request.user
        super().save_model(request, obj, form, change)


# ============================================================================
# 2. DTPS POOL PER SESI
# ============================================================================

@admin.register(DTPSDosenSesi)
class DTPSDosenSesiAdmin(admin.ModelAdmin):
    """Admin untuk manage DTPS pool per sesi akreditasi.

    Operator bisa: tambah dosen lintas prodi (MANUAL_TAMBAHAN),
    soft-delete dosen homebase (aktif=False), refresh snapshot.
    """

    list_display = (
        'sesi_display',
        'dosen_nidn',
        'dosen_nama_snapshot',
        'homebase_display',
        'sumber_display',
        'peran',
        'aktif_display',
        'snapshot_status_display',
        'tanggal_diubah',
    )
    list_filter = (
        'sumber',
        'peran',
        'aktif',
        'snapshot_outdated',
        'sesi__instrumen',
        'sesi__kode_prodi',
        'sesi__tahun_ts',
    )
    search_fields = (
        'dosen_nidn',
        'dosen_nama_snapshot',
        'sesi__kode_prodi',
        'sesi__nama_prodi_snapshot',
        'mk_diampu',
        'alasan_inklusi',
    )
    autocomplete_fields = ('sesi',)
    readonly_fields = (
        'snapshot_at', 'snapshot_outdated',
        'dosen_nama_snapshot',
        'dosen_homebase_prodi_snapshot',
        'dosen_homebase_fakultas_snapshot',
        'dosen_jabfung_snapshot',
        'tanggal_dibuat', 'tanggal_diubah', 'dibuat_oleh',
    )
    list_per_page = 50

    fieldsets = (
        ('Sesi & Dosen', {
            'fields': ('sesi', 'dosen_nidn'),
            'description': 'NIDN harus match dengan data_dosen di SIMDA. '
                           'Untuk dosen homebase, biasanya auto-populated saat sesi dibuat.',
        }),
        ('Peran sebagai DTPS', {
            'fields': ('sumber', 'peran', 'mk_diampu', 'alasan_inklusi'),
        }),
        ('Status', {
            'fields': ('aktif',),
            'description': 'Uncheck untuk soft-disable: record tetap ada untuk audit '
                           'tapi tidak muncul di butir akreditasi.',
        }),
        ('Snapshot Data SIMDA (read-only)', {
            'fields': (
                'dosen_nama_snapshot',
                'dosen_homebase_prodi_snapshot',
                'dosen_homebase_fakultas_snapshot',
                'dosen_jabfung_snapshot',
                'snapshot_at',
                'snapshot_outdated',
            ),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('dibuat_oleh', 'tanggal_dibuat', 'tanggal_diubah'),
            'classes': ('collapse',),
        }),
    )

    actions = ['action_soft_disable', 'action_restore', 'action_refresh_snapshot']

    # ---- Custom display methods ----

    @admin.display(description='Sesi', ordering='sesi__id')
    def sesi_display(self, obj):
        s = obj.sesi
        return f"{s.kode_prodi} - {s.tahun_ts} ({s.instrumen.kode})"

    @admin.display(description='Homebase')
    def homebase_display(self, obj):
        prodi = obj.dosen_homebase_prodi_snapshot or '?'
        fak = obj.dosen_homebase_fakultas_snapshot or '?'
        # Highlight kalau dosen lintas prodi (homebase ≠ sesi.kode_prodi)
        if obj.sesi and prodi != obj.sesi.kode_prodi:
            return format_html(
                '<span style="background:#fff3cd;padding:2px 6px;border-radius:3px;">'
                '🔄 {}</span>', f"{prodi} ({fak})"
            )
        return f"{prodi} ({fak})"

    @admin.display(description='Sumber', ordering='sumber')
    def sumber_display(self, obj):
        if obj.sumber == 'AUTO_HOMEBASE':
            color = '#0d6efd'  # biru
            label = 'Auto'
        else:
            color = '#198754'  # hijau
            label = 'Manual'
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            color, label,
        )

    @admin.display(description='Aktif', ordering='aktif', boolean=False)
    def aktif_display(self, obj):
        if obj.aktif:
            return mark_safe('<span style="color:#198754;">✓ Aktif</span>')
        return mark_safe(
            '<span style="color:#6c757d;text-decoration:line-through;">✗ Disabled</span>'
        )

    @admin.display(description='Snapshot')
    def snapshot_status_display(self, obj):
        if obj.snapshot_outdated:
            return mark_safe(
                '<span style="background:#dc3545;color:white;padding:2px 6px;'
                'border-radius:3px;font-size:11px;" title="Data SIMDA berubah, '
                'klik action Refresh untuk update.">⚠ Outdated</span>'
            )
        return mark_safe('<span style="color:#198754;font-size:11px;">✓ Synced</span>')

    # ---- Bulk actions ----

    @admin.action(description='Soft-disable (set aktif=False)')
    def action_soft_disable(self, request, queryset):
        n = queryset.update(aktif=False)
        self.message_user(
            request,
            f"{n} record DTPS di-soft-disable (record tetap ada untuk audit).",
            messages.SUCCESS,
        )

    @admin.action(description='Restore (set aktif=True)')
    def action_restore(self, request, queryset):
        n = queryset.update(aktif=True)
        self.message_user(
            request,
            f"{n} record DTPS di-restore.",
            messages.SUCCESS,
        )

    @admin.action(description='Refresh snapshot dari SIMDA')
    def action_refresh_snapshot(self, request, queryset):
        ok = 0
        fail = 0
        for dtps in queryset:
            if dtps.refresh_snapshot_from_simda():
                ok += 1
            else:
                fail += 1
        msg = f"Snapshot direfresh: {ok} sukses"
        if fail:
            msg += f", {fail} gagal (NIDN tidak ditemukan di SIMDA)"
        self.message_user(
            request, msg,
            messages.SUCCESS if fail == 0 else messages.WARNING,
        )

    # ---- Override save untuk auto-populate snapshot saat manual add ----

    def save_model(self, request, obj, form, change):
        if not change and not obj.dibuat_oleh:
            obj.dibuat_oleh = request.user

        # Kalau MANUAL_TAMBAHAN dan snapshot kosong, fetch dari SIMDA
        if not change and obj.sumber == 'MANUAL_TAMBAHAN' and not obj.dosen_nama_snapshot:
            from .models_simda_ref import DataDosenRef
            try:
                dosen = DataDosenRef.objects.select_related(
                    'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
                ).get(nidn=obj.dosen_nidn)
                obj.dosen_nama_snapshot = dosen.nama_lengkap
                obj.dosen_homebase_prodi_snapshot = dosen.kode_prodi_id
                obj.dosen_homebase_fakultas_snapshot = dosen.kode_fakultas_id
                obj.dosen_jabfung_snapshot = (
                    dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else ''
                )
            except DataDosenRef.DoesNotExist:
                messages.warning(
                    request,
                    f"NIDN {obj.dosen_nidn} tidak ditemukan di SIMDA. "
                    f"Snapshot tidak dapat di-populate otomatis."
                )

        super().save_model(request, obj, form, change)


# ============================================================================
# 3. SNAPSHOT DATA SIMDA (READ-ONLY)
# ============================================================================

@admin.register(SnapshotDataSimda)
class SnapshotDataSimdaAdmin(admin.ModelAdmin):
    """Admin read-only untuk audit trail snapshot data SIMDA.

    Snapshot di-trigger otomatis saat sesi finalize. User tidak boleh
    edit/delete via admin (bisa via shell kalau benar-benar perlu).
    """

    list_display = (
        'tanggal_snapshot',
        'sesi_display',
        'butir_display',
        'jenis_data',
        'total_records',
        'dibuat_oleh',
    )
    list_filter = (
        'jenis_data',
        'sesi__instrumen',
        'sesi__kode_prodi',
        'tanggal_snapshot',
    )
    search_fields = (
        'sesi__kode_prodi',
        'sesi__nama_prodi_snapshot',
        'butir__kode',
        'keterangan',
    )
    readonly_fields = (
        'sesi', 'butir', 'jenis_data',
        'data_json_preview', 'total_records',
        'keterangan', 'tanggal_snapshot', 'dibuat_oleh',
    )
    exclude = ('data_json',)
    list_per_page = 50
    date_hierarchy = 'tanggal_snapshot'

    @admin.display(description='Sesi', ordering='sesi__id')
    def sesi_display(self, obj):
        s = obj.sesi
        return f"{s.kode_prodi} - {s.tahun_ts}"

    @admin.display(description='Butir')
    def butir_display(self, obj):
        return obj.butir.kode if obj.butir else '(sesi-wide)'

    @admin.display(description='Data JSON Preview')
    def data_json_preview(self, obj):
        """Render JSON pretty di admin (truncated)."""
        import json
        try:
            preview = json.dumps(obj.data_json[:3] if isinstance(obj.data_json, list) else obj.data_json, indent=2)
        except (TypeError, ValueError):
            preview = str(obj.data_json)[:500]

        truncated = ''
        if isinstance(obj.data_json, list) and len(obj.data_json) > 3:
            truncated = f"\n... dan {len(obj.data_json) - 3} record lainnya"

        return format_html(
            '<pre style="background:#f8f9fa;padding:10px;border-radius:4px;'
            'max-height:400px;overflow:auto;font-size:11px;">{}{}</pre>',
            preview, truncated,
        )

    def has_add_permission(self, request):
        return False  # Snapshot dibuat otomatis, bukan via admin

    def has_change_permission(self, request, obj=None):
        return False  # Read-only

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Hanya superuser yang bisa delete


# ============================================================================
# 4. INLINE: DTPS DI SESIAKREDITASI ADMIN
# ============================================================================

class DTPSDosenSesiInline(admin.TabularInline):
    """Inline untuk tampil di SesiAkreditasiAdmin.

    Operator bisa lihat & manage DTPS pool langsung dari halaman sesi
    tanpa harus pindah ke menu DTPS terpisah.
    """

    model = DTPSDosenSesi
    extra = 0
    fields = (
        'dosen_nidn',
        'dosen_nama_snapshot',
        'sumber',
        'peran',
        'mk_diampu',
        'aktif',
    )
    readonly_fields = ('dosen_nama_snapshot',)
    show_change_link = True
    classes = ('collapse',)
    verbose_name = 'DTPS Dosen'
    verbose_name_plural = 'Pool DTPS untuk Sesi Ini'

    def get_queryset(self, request):
        # Default tampilkan yang aktif aja, biar tidak penuh
        qs = super().get_queryset(request)
        return qs.order_by('-aktif', 'sumber', 'dosen_nama_snapshot')
