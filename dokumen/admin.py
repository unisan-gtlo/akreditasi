"""Django Admin untuk modul Dokumen."""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Dokumen, DokumenRevisi, DokumenAccessLog


class DokumenRevisiInline(admin.TabularInline):
    model = DokumenRevisi
    extra = 0
    fields = ("nomor_revisi", "file", "file_size_kb", "aktif", "tanggal_upload", "uploaded_by")
    readonly_fields = ("file_size_kb", "tanggal_upload", "uploaded_by")
    ordering = ("-nomor_revisi",)


@admin.register(Dokumen)
class DokumenAdmin(admin.ModelAdmin):
    list_display = (
        "judul", "butir_dokumen", "kategori_pemilik",
        "scope_label_display", "status_akses_badge", "status_badge",
        "view_count", "download_count",
        "tanggal_diubah",
    )
    list_filter = (
        "status_akses", "status", "kategori_pemilik",
        "butir_dokumen__sub_standar__standar__instrumen",
    )
    search_fields = ("judul", "butir_dokumen__kode", "butir_dokumen__nama_dokumen")
    ordering = ("-tanggal_diubah",)
    date_hierarchy = "tanggal_diubah"

    fieldsets = (
        (_("Identitas"), {
            "fields": ("butir_dokumen", "judul", "deskripsi", "tahun_akademik"),
        }),
        (_("Pemilik & Scope"), {
            "fields": (
                "kategori_pemilik",
                "scope_kode_prodi", "scope_kode_fakultas", "scope_kode_unit_kerja",
            ),
        }),
        (_("Akses & Status"), {
            "fields": ("status_akses", "status"),
        }),
        (_("Counter"), {
            "fields": ("view_count", "download_count"),
            "classes": ("collapse",),
        }),
        (_("Audit"), {
            "fields": ("uploaded_by", "last_updated_by", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("view_count", "download_count", "tanggal_dibuat", "tanggal_diubah")
    autocomplete_fields = ["butir_dokumen"]

    inlines = [DokumenRevisiInline]

    @admin.display(description="Scope")
    def scope_label_display(self, obj):
        return obj.scope_label

    @admin.display(description="Akses")
    def status_akses_badge(self, obj):
        if obj.status_akses == "TERBUKA":
            return format_html('<span style="background:#10B981;color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">TERBUKA</span>')
        return format_html('<span style="background:#6B7280;color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">INTERNAL</span>')

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"DRAFT": "#F59E0B", "FINAL": "#10B981", "ARSIP": "#6B7280"}
        c = colors.get(obj.status, "#6B7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">{}</span>',
            c, obj.get_status_display()
        )


@admin.register(DokumenRevisi)
class DokumenRevisiAdmin(admin.ModelAdmin):
    list_display = (
        "dokumen", "nomor_revisi", "file_size_display",
        "extension", "aktif", "uploaded_by", "tanggal_upload",
    )
    list_filter = ("aktif", "extension", "tanggal_upload")
    search_fields = ("dokumen__judul", "original_filename")
    ordering = ("-tanggal_upload",)
    readonly_fields = ("file_hash", "file_size_kb", "mime_type", "extension", "tanggal_upload")


@admin.register(DokumenAccessLog)
class DokumenAccessLogAdmin(admin.ModelAdmin):
    list_display = ("waktu", "dokumen", "aksi", "user", "ip_address")
    list_filter = ("aksi", "waktu")
    search_fields = ("dokumen__judul", "user__username", "ip_address")
    ordering = ("-waktu",)
    readonly_fields = ("dokumen", "revisi", "aksi", "user", "ip_address", "user_agent", "waktu", "catatan")
    date_hierarchy = "waktu"

    def has_add_permission(self, request):
        return False