"""
Django Admin untuk Master Akreditasi.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    MappingProdiInstrumen,
    ImportLog,
    ImportLogItem,
)


# ============================================
# INLINES
# ============================================

class StandarInline(admin.TabularInline):
    model = Standar
    extra = 0
    fields = ("urutan", "nomor", "nama", "bobot", "aktif")
    ordering = ("urutan", "nomor")


class SubStandarInline(admin.TabularInline):
    model = SubStandar
    extra = 0
    fields = ("urutan", "nomor", "nama", "parent", "aktif")
    ordering = ("urutan", "nomor")
    fk_name = "standar"


class ButirDokumenInline(admin.TabularInline):
    model = ButirDokumen
    extra = 0
    fields = ("urutan", "kode", "nama_dokumen", "kategori_kepemilikan", "wajib", "aktif")
    ordering = ("urutan", "kode")


# ============================================
# INSTRUMEN
# ============================================

@admin.register(Instrumen)
class InstrumenAdmin(admin.ModelAdmin):
    list_display = (
        "kode", "nama_singkat", "lembaga", "versi",
        "jumlah_standar_display", "jumlah_butir_display",
        "aktif", "urutan",
    )
    list_filter = ("lembaga", "aktif")
    search_fields = ("kode", "nama_resmi", "nama_singkat", "lembaga")
    ordering = ("urutan", "kode")
    list_editable = ("urutan", "aktif")

    fieldsets = (
        (_("Identitas Instrumen"), {
            "fields": ("kode", "nama_resmi", "nama_singkat", "versi", "lembaga"),
        }),
        (_("Label Dinamis"), {
            "fields": ("label_standar", "label_substandar", "label_butir"),
            "description": _(
                "Istilah bisa beda per instrumen. Contoh: BAN-PT pakai 'Kriteria', "
                "LAM lain mungkin 'Standar'."
            ),
        }),
        (_("Informasi"), {
            "fields": ("deskripsi", "tahun_berlaku", "url_referensi", "logo"),
            "classes": ("collapse",),
        }),
        (_("Status"), {
            "fields": ("urutan", "aktif"),
        }),
    )

    inlines = [StandarInline]

    @admin.display(description="Jml Standar")
    def jumlah_standar_display(self, obj):
        return obj.jumlah_standar

    @admin.display(description="Jml Butir")
    def jumlah_butir_display(self, obj):
        return obj.jumlah_butir


# ============================================
# STANDAR
# ============================================

@admin.register(Standar)
class StandarAdmin(admin.ModelAdmin):
    list_display = (
        "instrumen", "nomor", "nama", "bobot",
        "jumlah_substandar_display", "jumlah_butir_display",
        "aktif", "urutan",
    )
    list_filter = ("instrumen", "aktif")
    search_fields = ("nomor", "nama", "deskripsi")
    ordering = ("instrumen", "urutan", "nomor")
    list_editable = ("urutan", "aktif")
    autocomplete_fields = ["instrumen"]

    fieldsets = (
        (None, {
            "fields": ("instrumen", "nomor", "nama"),
        }),
        (_("Deskripsi"), {
            "fields": ("deskripsi", "bobot"),
        }),
        (_("Status"), {
            "fields": ("urutan", "aktif"),
        }),
    )

    inlines = [SubStandarInline]

    @admin.display(description="Jml Sub-Std")
    def jumlah_substandar_display(self, obj):
        return obj.jumlah_substandar

    @admin.display(description="Jml Butir")
    def jumlah_butir_display(self, obj):
        return obj.jumlah_butir


# ============================================
# SUB-STANDAR
# ============================================

@admin.register(SubStandar)
class SubStandarAdmin(admin.ModelAdmin):
    list_display = (
        "path_display", "nama", "level_display",
        "jumlah_butir_langsung_display", "aktif", "urutan",
    )
    list_filter = ("standar__instrumen", "standar", "aktif")
    search_fields = ("nomor", "nama", "deskripsi")
    ordering = ("standar", "urutan", "nomor")
    list_editable = ("urutan", "aktif")
    autocomplete_fields = ["standar", "parent"]

    fieldsets = (
        (None, {
            "fields": ("standar", "parent", "nomor", "nama"),
        }),
        (_("Deskripsi"), {
            "fields": ("deskripsi", "panduan"),
        }),
        (_("Status"), {
            "fields": ("urutan", "aktif"),
        }),
    )

    inlines = [ButirDokumenInline]

    @admin.display(description="Path")
    def path_display(self, obj):
        return obj.path

    @admin.display(description="Level")
    def level_display(self, obj):
        return f"L{obj.level}"

    @admin.display(description="Jml Butir")
    def jumlah_butir_langsung_display(self, obj):
        return obj.jumlah_butir_langsung


# ============================================
# BUTIR DOKUMEN
# ============================================

@admin.register(ButirDokumen)
class ButirDokumenAdmin(admin.ModelAdmin):
    list_display = (
        "kode", "nama_dokumen", "sub_standar",
        "kategori_display", "wajib", "format_diterima",
        "status_akses_default", "aktif",
    )
    list_filter = (
        "sub_standar__standar__instrumen",
        "kategori_kepemilikan",
        "wajib",
        "format_diterima",
        "status_akses_default",
        "aktif",
    )
    search_fields = ("kode", "nama_dokumen", "deskripsi")
    ordering = ("sub_standar", "urutan", "kode")
    list_editable = ("wajib", "aktif")
    autocomplete_fields = ["sub_standar"]

    fieldsets = (
        (None, {
            "fields": ("sub_standar", "kode", "nama_dokumen"),
        }),
        (_("Deskripsi"), {
            "fields": ("deskripsi", "panduan_dokumen"),
        }),
        (_("Aturan Dokumen"), {
            "fields": (
                "kategori_kepemilikan", "wajib",
                "format_diterima", "ukuran_max_mb",
                "status_akses_default",
            ),
        }),
        (_("Status"), {
            "fields": ("urutan", "aktif"),
        }),
    )

    @admin.display(description="Kategori")
    def kategori_display(self, obj):
        colors = {
            "UNIVERSITAS": "#2563EB",
            "BIRO": "#06B6D4",
            "FAKULTAS": "#F59E0B",
            "PRODI": "#10B981",
        }
        color = colors.get(obj.kategori_kepemilikan, "#64748B")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">{}</span>',
            color,
            obj.get_kategori_kepemilikan_display(),
        )


# ============================================
# MAPPING PRODI - INSTRUMEN
# ============================================

@admin.register(MappingProdiInstrumen)
class MappingProdiInstrumenAdmin(admin.ModelAdmin):
    list_display = (
        "kode_prodi", "nama_prodi", "instrumen", "aktif",
    )
    list_filter = ("instrumen", "aktif")
    search_fields = ("kode_prodi", "nama_prodi")
    ordering = ("kode_prodi",)
    autocomplete_fields = ["instrumen"]

# ============================================
# IMPORT LOG ADMIN
# ============================================

class ImportLogItemInline(admin.TabularInline):
    model = ImportLogItem
    extra = 0
    fields = ("sheet", "row_number", "status", "error_detail")
    readonly_fields = fields
    can_delete = False
    show_change_link = False


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = (
        "waktu_upload", "file_name", "instrumen", "mode",
        "total_rows", "valid_rows", "error_rows",
        "status", "uploaded_by",
    )
    list_filter = ("status", "mode", "instrumen", "waktu_upload")
    search_fields = ("file_name", "uploaded_by__username")
    ordering = ("-waktu_upload",)
    date_hierarchy = "waktu_upload"
    readonly_fields = (
        "file_name", "file_size_kb", "file",
        "instrumen", "mode",
        "total_rows", "valid_rows", "error_rows",
        "substandar_created", "substandar_updated",
        "butir_created", "butir_updated",
        "status", "error_message",
        "uploaded_by", "waktu_upload", "waktu_commit",
    )

    inlines = [ImportLogItemInline]

    def has_add_permission(self, request):
        return False


@admin.register(ImportLogItem)
class ImportLogItemAdmin(admin.ModelAdmin):
    list_display = ("import_log", "sheet", "row_number", "status")
    list_filter = ("sheet", "status")
    search_fields = ("import_log__file_name",)
    readonly_fields = (
        "import_log", "sheet", "row_number", "raw_data",
        "status", "error_detail", "substandar", "butir",
    )

    def has_add_permission(self, request):
        return False