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

