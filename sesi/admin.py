"""Django Admin untuk Sesi Akreditasi."""
from django.contrib import admin, messages
from django.utils.html import format_html

from .models import SesiAkreditasi, MilestoneSesi, CatatanSesi


class MilestoneSesiInline(admin.TabularInline):
    model = MilestoneSesi
    extra = 0
    fields = ("urutan", "judul", "tanggal_target", "tanggal_aktual", "status")
    ordering = ("urutan",)


class CatatanSesiInline(admin.TabularInline):
    model = CatatanSesi
    extra = 0
    fields = ("tipe", "isi", "dibuat_oleh", "tanggal_dibuat")
    readonly_fields = ("dibuat_oleh", "tanggal_dibuat")


@admin.register(SesiAkreditasi)
class SesiAkreditasiAdmin(admin.ModelAdmin):
    list_display = (
        "judul", "instrumen", "kode_prodi", "tahun_ts",
        "status_badge", "tipe", "tanggal_mulai", "tanggal_target_selesai",
    )
    list_filter = ("status", "tipe", "instrumen")
    search_fields = ("judul", "nama_prodi_snapshot", "kode_prodi", "nomor_sk_akreditasi")
    ordering = ("-tanggal_mulai",)
    date_hierarchy = "tanggal_mulai"

    fieldsets = (
        ("Identitas", {
            "fields": ("judul", "deskripsi", "tipe"),
        }),
        ("Scope", {
            "fields": ("instrumen", "kode_prodi", "nama_prodi_snapshot", "kode_fakultas", "tahun_ts", "jumlah_tahun_evaluasi"),
        }),
        ("Timeline", {
            "fields": (
                "tanggal_mulai", "tanggal_target_selesai", "deadline_upload_dokumen",
                "tanggal_submit", "tanggal_visitasi_mulai", "tanggal_visitasi_selesai",
                "tanggal_sertifikat",
            ),
        }),
        ("Status", {
            "fields": ("status",),
        }),
        ("Hasil Akreditasi", {
            "fields": ("nilai_akhir", "nomor_sk_akreditasi", "berlaku_sampai"),
            "classes": ("collapse",),
        }),
        ("Audit", {
            "fields": ("dibuat_oleh", "terakhir_diupdate_oleh", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("tanggal_dibuat", "tanggal_diubah")
    autocomplete_fields = ["instrumen"]

    inlines = [MilestoneSesiInline, CatatanSesiInline]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "PERSIAPAN": "#3B82F6",
            "REVIEW_INTERNAL": "#F59E0B",
            "SUBMITTED": "#06B6D4",
            "VISITASI_AKTIF": "#A855F7",
            "MENUNGGU_HASIL": "#EAB308",
            "SELESAI": "#10B981",
            "DIBATALKAN": "#EF4444",
        }
        c = colors.get(obj.status, "#6B7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">{}</span>',
            c, obj.get_status_display()
        )

    @admin.action(description="🔄 Auto-populate DTPS dari homebase prodi")
    def action_auto_populate_dtps(self, request, queryset):
        """Bulk action: populate DTPS pool dengan dosen homebase prodi.

        Untuk tiap sesi terpilih, panggil helper auto_populate_dtps_homebase()
        yang ambil dosen dari master.data_dosen dengan kode_prodi yang sama.
        Sumber DTPS = AUTO_HOMEBASE, peran default = DTPS_HOMEBASE.

        Idempotent: dosen yang sudah ada di pool tidak akan duplikat.
        """
        from master_akreditasi.simda_dosen import auto_populate_dtps_homebase

        total_sesi = 0
        total_dtps_added = 0
        errors = []

        for sesi in queryset:
            try:
                created_count = auto_populate_dtps_homebase(sesi)
                count = created_count if isinstance(created_count, int) else 0
                total_dtps_added += count
                total_sesi += 1
                self.message_user(
                    request,
                    f"✓ {sesi.judul[:60]} ({sesi.kode_prodi}): {count} dosen homebase ditambahkan ke DTPS pool.",
                    level=messages.SUCCESS,
                )
            except Exception as e:
                errors.append(f"{sesi.judul[:40]}: {type(e).__name__}: {e}")
                self.message_user(
                    request,
                    f"✗ {sesi.judul[:60]}: {type(e).__name__}: {e}",
                    level=messages.ERROR,
                )

        # Summary
        if total_sesi > 0:
            self.message_user(
                request,
                f"Selesai: {total_dtps_added} dosen di-populate ke {total_sesi} sesi.",
                level=messages.INFO,
            )

    actions = ['action_auto_populate_dtps']

@admin.register(MilestoneSesi)
class MilestoneSesiAdmin(admin.ModelAdmin):
    list_display = ("sesi", "urutan", "judul", "tanggal_target", "tanggal_aktual", "status")
    list_filter = ("status", "sesi__instrumen")
    search_fields = ("judul", "sesi__judul")


@admin.register(CatatanSesi)
class CatatanSesiAdmin(admin.ModelAdmin):
    list_display = ("sesi", "tipe", "dibuat_oleh", "tanggal_dibuat")
    list_filter = ("tipe", "sesi__instrumen")
    search_fields = ("sesi__judul", "isi")

from .models import BundleShareToken


@admin.register(BundleShareToken)
class BundleShareTokenAdmin(admin.ModelAdmin):
    list_display = [
        'label', 'sesi', 'token_short', 'is_active',
        'expires_at', 'access_count', 'created_at',
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['label', 'token', 'sesi__judul']
    readonly_fields = ['token', 'created_at', 'last_accessed_at', 'access_count']
    
    def token_short(self, obj):
        return obj.token[:16] + '...' if len(obj.token) > 16 else obj.token
    token_short.short_description = 'Token'
    
    def save_model(self, request, obj, form, change):
        if not obj.token:
            obj.token = BundleShareToken.generate_token()
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)