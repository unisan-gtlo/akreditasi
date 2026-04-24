"""
Django Admin registration untuk app core.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, ScopeUser, LoginAttempt, DeviceSession


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username", "nama_lengkap", "email", "nidn", "nip",
        "is_active", "is_staff", "date_joined",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email", "nidn", "nip")
    ordering = ("username",)

    fieldsets = (
        (_("Login"), {"fields": ("username", "password")}),
        (_("Informasi Pribadi"), {
            "fields": ("first_name", "last_name", "email", "no_telepon", "foto_profil")
        }),
        (_("Identitas SIMDA"), {
            "fields": ("nidn", "nip", "data_dosen_id", "data_tendik_id"),
            "classes": ("collapse",),
        }),
        (_("Permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        (_("Tanggal Penting"), {
            "fields": ("last_login", "date_joined", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )

    readonly_fields = ("date_joined", "last_login", "tanggal_dibuat", "tanggal_diubah")

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "email"),
        }),
    )


@admin.register(ScopeUser)
class ScopeUserAdmin(admin.ModelAdmin):
    list_display = (
        "user", "role", "level", "is_pimpinan",
        "unit_kerja_id", "fakultas_id", "prodi_id",
        "aktif",
    )
    list_filter = ("role", "level", "is_pimpinan", "aktif")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    ordering = ("user__username", "role")

    fieldsets = (
        (_("Pengguna & Role"), {
            "fields": ("user", "role", "level", "is_pimpinan", "aktif"),
        }),
        (_("Scope Organisasi"), {
            "fields": ("unit_kerja_id", "fakultas_id", "prodi_id"),
        }),
        (_("Masa Berlaku"), {
            "fields": ("tanggal_berakhir",),
        }),
    )

    readonly_fields = ("tanggal_mulai",)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "waktu", "username_attempted", "status",
        "ip_address", "user",
    )
    list_filter = ("status", "waktu")
    search_fields = ("username_attempted", "ip_address", "user__username")
    ordering = ("-waktu",)
    readonly_fields = (
        "username_attempted", "user", "status",
        "ip_address", "user_agent", "waktu",
    )
    date_hierarchy = "waktu"

    def has_add_permission(self, request):
        return False


@admin.register(DeviceSession)
class DeviceSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "browser_name", "os_name", "device_type",
        "ip_address", "last_seen", "is_trusted", "aktif",
    )
    list_filter = ("is_trusted", "aktif", "device_type", "browser_name", "os_name")
    search_fields = ("user__username", "ip_address")
    ordering = ("-last_seen",)
    readonly_fields = (
        "user", "device_fingerprint", "ip_address", "user_agent",
        "browser_name", "os_name", "device_type",
        "first_seen", "last_seen", "last_ip",
    )
    date_hierarchy = "last_seen"

    def has_add_permission(self, request):
        return False


# ============================================
# NOTIFIKASI ADMIN (Step 9H)
# ============================================

from .models import Notifikasi


@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    list_display = ['judul', 'penerima', 'tipe', 'sudah_dibaca', 'tanggal_dibuat']
    list_filter = ['tipe', 'sudah_dibaca', 'tanggal_dibuat']
    search_fields = ['judul', 'pesan', 'penerima__username', 'penerima__nama_lengkap']
    readonly_fields = ['tanggal_dibuat', 'tanggal_dibaca']
    date_hierarchy = 'tanggal_dibuat'
    
    fieldsets = (
        ('Penerima & Tipe', {'fields': ('penerima', 'tipe', 'dibuat_oleh')}),
        ('Konten', {'fields': ('judul', 'pesan', 'url_action')}),
        ('Object Terkait', {'fields': ('dokumen', 'verifikasi'), 'classes': ('collapse',)}),
        ('Status', {'fields': ('sudah_dibaca', 'tanggal_dibaca', 'tanggal_dibuat')}),
    )


# --- SiteProfile Admin ---
from .models import SiteProfile

@admin.register(SiteProfile)
class SiteProfileAdmin(admin.ModelAdmin):
    list_display = ("nama_institusi", "tagline", "nama_rektor", "foto_rektor_preview", "aktif")
    readonly_fields = ("foto_rektor_preview_large", "tanggal_dibuat", "tanggal_diubah")
    
    fieldsets = (
        ("Identitas Institusi", {
            "fields": ("nama_institusi", "nama_singkat", "tagline", "deskripsi_singkat", "tahun_berdiri"),
        }),
        ("Visi Misi & Tujuan", {
            "fields": ("visi", "misi", "tujuan"),
            "description": "Visi, misi, dan tujuan universitas. Untuk misi & tujuan, 1 poin per baris.",
        }),
        ("Akreditasi Institusi", {
            "fields": ("akreditasi_peringkat", "akreditasi_no_sk", "akreditasi_tanggal_sk", "akreditasi_berlaku_sampai", "akreditasi_lembaga"),
            "description": "Informasi akreditasi institusi (BAN-PT). Kalau sudah diisi di SIMDA, bisa mirror ke sini.",
        }),
        ("Profil Rektor", {
            "fields": ("nama_rektor", "periode_rektor", "foto_rektor", "foto_rektor_preview_large", "kata_sambutan"),
            "description": "Upload foto close-up Rektor + kata sambutan untuk halaman publik",
        }),
        ("Kontak & Alamat", {
            "fields": ("alamat", "telepon", "email", "website"),
        }),
        ("Media Sosial", {
            "fields": ("instagram", "facebook", "youtube", "twitter_x", "tiktok", "linkedin", "whatsapp_channel", "telegram"),
            "description": "URL lengkap (https://...). Kosongkan platform yang tidak digunakan.",
            "classes": ("collapse",),
        }),
        ("Meta", {
            "fields": ("aktif", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Foto Rektor")
    def foto_rektor_preview(self, obj):
        if obj.foto_rektor:
            return format_html(
                '<img src="{}" style="height:40px; width:40px; border-radius:50%; object-fit:cover;" />',
                obj.foto_rektor.url,
            )
        return mark_safe('<span style="color:#999;">- tidak ada -</span>')
    
    @admin.display(description="Preview Foto")
    def foto_rektor_preview_large(self, obj):
        if obj.foto_rektor:
            return format_html(
                '<img src="{}" style="max-height:250px; max-width:200px; border-radius:8px; border:1px solid #ddd;" />',
                obj.foto_rektor.url,
            )
        return mark_safe('<span style="color:#999;">Belum ada foto Rektor.</span>')
    
    def has_add_permission(self, request):
        if SiteProfile.objects.count() >= 1:
            return False
        return super().has_add_permission(request)
# ============================================================
# FakultasTheme Admin
# ============================================================

from .models import FakultasTheme


@admin.register(FakultasTheme)
class FakultasThemeAdmin(admin.ModelAdmin):
    list_display = ("kode_fakultas", "nama_fakultas", "color_preview", "urutan", "aktif")
    list_filter = ("aktif",)
    search_fields = ("kode_fakultas", "nama_fakultas")
    list_editable = ("urutan", "aktif")
    ordering = ("urutan", "kode_fakultas")
    
    fieldsets = (
        ("Identitas Fakultas", {
            "fields": ("kode_fakultas", "nama_fakultas"),
            "description": "Kode fakultas harus sync dengan SIMDA master.fakultas",
        }),
        ("Theme Warna", {
            "fields": ("warna_primary", "warna_light", "icon_nama"),
            "description": "Hex color dalam format #RRGGBB. Icon pakai nama Lucide (e.g. graduation-cap).",
        }),
        ("Display", {
            "fields": ("urutan", "aktif"),
        }),
    )
    
    def color_preview(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<div style="display:flex; gap:6px; align-items:center;">'
            '<span style="width:24px; height:24px; background:{}; border-radius:4px; border:1px solid #ccc;" title="{}"></span>'
            '<span style="width:24px; height:24px; background:{}; border-radius:4px; border:1px solid #ccc;" title="{}"></span>'
            '<code style="font-size:.75rem;">{}</code>'
            '</div>',
            obj.warna_primary, obj.warna_primary,
            obj.warna_light, obj.warna_light,
            obj.warna_primary,
        )
    color_preview.short_description = "Preview"

# ============================================================
# FakultasProfile + ProdiProfile Admin
# ============================================================

from .models import FakultasProfile, ProdiProfile
from django.utils.html import format_html
from django.utils.safestring import mark_safe


def _nama_fakultas_simda(kode):
    from django.db import connection
    try:
        with connection.cursor() as c:
            c.execute("SELECT nama_fakultas FROM master.fakultas WHERE kode_fakultas = %s", [kode])
            row = c.fetchone()
            return row[0] if row else kode
    except Exception:
        return kode


def _nama_prodi_simda(kode):
    from django.db import connection
    try:
        with connection.cursor() as c:
            c.execute("SELECT nama_prodi, kode_fakultas FROM master.program_studi WHERE kode_prodi = %s", [kode])
            row = c.fetchone()
            return row if row else (kode, "-")
    except Exception:
        return (kode, "-")


@admin.register(FakultasProfile)
class FakultasProfileAdmin(admin.ModelAdmin):
    list_display = ("kode_fakultas", "nama_fakultas_display", "nama_dekan", "foto_preview_small", "has_visi_misi", "aktif")
    list_filter = ("aktif",)
    search_fields = ("kode_fakultas", "nama_dekan")
    readonly_fields = ("foto_preview_large", "tanggal_dibuat", "tanggal_diubah")
    
    fieldsets = (
        ("Identitas Fakultas", {
            "fields": ("kode_fakultas",),
            "description": "Kode fakultas sync dengan SIMDA (FE, FH, FISIP, FK, FP, FT, S2)",
        }),
        ("Informasi Dekan", {
            "fields": ("nama_dekan", "periode_dekan", "foto_dekan", "foto_preview_large"),
            "description": "Upload foto close-up dekan (ratio 1:1 atau 3:4, min 400x400px)",
        }),
        ("Visi Misi", {
            "fields": ("visi", "misi", "tujuan"),
            "description": "Visi/Misi fakultas. Untuk misi, tulis satu poin per baris.",
        }),
        ("Meta", {
            "fields": ("aktif", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Nama Fakultas (SIMDA)")
    def nama_fakultas_display(self, obj):
        return _nama_fakultas_simda(obj.kode_fakultas)
    
    @admin.display(description="Foto")
    def foto_preview_small(self, obj):
        url = obj.get_foto_dekan_url()
        if url:
            return format_html(
                '<img src="{}" style="height:40px; width:40px; border-radius:50%; object-fit:cover;" />',
                url,
            )
        return mark_safe('<span style="color:#999;">- tidak ada -</span>')
    
    @admin.display(description="Preview Foto")
    def foto_preview_large(self, obj):
        url = obj.get_foto_dekan_url()
        if url:
            return format_html(
                '<img src="{}" style="max-height:250px; max-width:200px; border-radius:8px; border:1px solid #ddd;" />',
                url,
            )
        return mark_safe('<span style="color:#999;">Belum ada foto.</span>')
    
    @admin.display(description="Visi Misi")
    def has_visi_misi(self, obj):
        has_v = bool(obj.visi)
        has_m = bool(obj.misi)
        if has_v and has_m:
            return mark_safe('<span style="color:#059669;">&check; Lengkap</span>')
        if has_v or has_m:
            return mark_safe('<span style="color:#F59E0B;">&#9888; Sebagian</span>')
        return mark_safe('<span style="color:#DC2626;">&times; Kosong</span>')


@admin.register(ProdiProfile)
class ProdiProfileAdmin(admin.ModelAdmin):
    list_display = ("kode_prodi", "nama_prodi_display", "kode_fakultas_display", "nama_kaprodi", "foto_preview_small", "has_visi_misi", "aktif")
    list_filter = ("aktif",)
    search_fields = ("kode_prodi", "nama_kaprodi")
    readonly_fields = ("foto_preview_large", "tanggal_dibuat", "tanggal_diubah")
    
    fieldsets = (
        ("Identitas Prodi", {
            "fields": ("kode_prodi",),
            "description": "Kode prodi sync dengan SIMDA master.program_studi",
        }),
        ("Informasi Kaprodi", {
            "fields": ("nama_kaprodi", "periode_kaprodi", "foto_kaprodi", "foto_preview_large"),
            "description": "Upload foto close-up ketua program studi",
        }),
        ("Visi Misi", {
            "fields": ("visi", "misi", "tujuan", "profil_lulusan"),
            "description": "Untuk misi, tulis satu poin per baris.",
        }),
        ("Meta", {
            "fields": ("aktif", "tanggal_dibuat", "tanggal_diubah"),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Nama Prodi (SIMDA)")
    def nama_prodi_display(self, obj):
        nama, _ = _nama_prodi_simda(obj.kode_prodi)
        return nama
    
    @admin.display(description="Fakultas")
    def kode_fakultas_display(self, obj):
        _, kode_fak = _nama_prodi_simda(obj.kode_prodi)
        return kode_fak
    
    @admin.display(description="Foto")
    def foto_preview_small(self, obj):
        url = obj.get_foto_kaprodi_url()
        if url:
            return format_html(
                '<img src="{}" style="height:40px; width:40px; border-radius:50%; object-fit:cover;" />',
                url,
            )
        return mark_safe('<span style="color:#999;">- tidak ada -</span>')
    
    @admin.display(description="Preview Foto")
    def foto_preview_large(self, obj):
        url = obj.get_foto_kaprodi_url()
        if url:
            return format_html(
                '<img src="{}" style="max-height:250px; max-width:200px; border-radius:8px; border:1px solid #ddd;" />',
                url,
            )
        return mark_safe('<span style="color:#999;">Belum ada foto.</span>')
    
    @admin.display(description="Visi Misi")
    def has_visi_misi(self, obj):
        has_v = bool(obj.visi)
        has_m = bool(obj.misi)
        if has_v and has_m:
            return mark_safe('<span style="color:#059669;">&check; Lengkap</span>')
        if has_v or has_m:
            return mark_safe('<span style="color:#F59E0B;">&#9888; Sebagian</span>')
        return mark_safe('<span style="color:#DC2626;">&times; Kosong</span>')

