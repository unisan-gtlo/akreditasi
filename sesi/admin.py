"""Django Admin untuk Sesi Akreditasi."""
from django.contrib import admin
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