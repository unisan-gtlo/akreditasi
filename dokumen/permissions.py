"""
Permission & Scope management untuk modul Dokumen.

Aturan akses:
  - VIEW (internal): semua user login bisa lihat SEMUA dokumen
    (biro/lembaga terbuka untuk semua role)
  - VIEW (publik/terbuka): non-login user bisa akses dokumen status_akses=TERBUKA
  - EDIT/DELETE: hanya pemilik (scope sama) yang bisa
  - UPLOAD: user harus punya scope yang cocok dengan butir.kategori_kepemilikan
"""
from django.core.exceptions import PermissionDenied

from core.models import ScopeUser


# =========================================================
# SCOPE RESOLVER
# =========================================================

def get_user_scopes(user):
    """Return list scope aktif user. Return [] kalau tidak ada."""
    if not user.is_authenticated:
        return []
    return list(user.scopes.filter(aktif=True))


def is_superadmin(user):
    """Super admin Pustikom bisa semuanya."""
    return user.is_authenticated and user.is_superuser


# =========================================================
# UPLOAD PERMISSION
# =========================================================

def can_upload_to_butir(user, butir):
    """
    Cek apakah user boleh upload dokumen ke butir tertentu.
    Return (boolean, message).
    """
    if not user.is_authenticated:
        return False, "Anda harus login terlebih dahulu"

    if is_superadmin(user):
        return True, "Super admin bisa upload ke semua butir"

    # Cek scope user cocok dengan kategori butir
    scopes = get_user_scopes(user)
    if not scopes:
        return False, "Anda belum memiliki scope (role). Hubungi admin Pustikom."

    kategori = butir.kategori_kepemilikan

    for scope in scopes:
        # UNIVERSITAS: pimpinan/operator universitas bisa upload
        if kategori == "UNIVERSITAS":
            if scope.level == "UNIVERSITAS":
                return True, f"OK - Scope Universitas ({scope.get_role_display()})"

        # BIRO: user biro/lembaga bisa upload ke butir kategori BIRO
        elif kategori == "BIRO":
            if scope.level == "BIRO":
                return True, f"OK - Scope Biro ({scope.get_role_display()})"

        # FAKULTAS: user fakultas bisa upload ke butir kategori FAKULTAS
        elif kategori == "FAKULTAS":
            if scope.level in ["FAKULTAS", "PRODI"]:
                return True, f"OK - Scope Fakultas/Prodi ({scope.get_role_display()})"

        # PRODI: user prodi bisa upload ke butir kategori PRODI
        elif kategori == "PRODI":
            if scope.level == "PRODI":
                return True, f"OK - Scope Prodi ({scope.get_role_display()})"

    return False, (
        f"Butir ini kategori {kategori}. "
        f"Anda belum punya scope yang sesuai untuk upload."
    )


# =========================================================
# EDIT/DELETE PERMISSION  (lateral lock)
# =========================================================

def can_edit_dokumen(user, dokumen):
    """
    Cek apakah user boleh edit/delete dokumen ini.
    LATERAL LOCK: fakultas A tidak boleh edit dokumen fakultas B.
    """
    if not user.is_authenticated:
        return False, "Anda harus login"

    if is_superadmin(user):
        return True, "Super admin"

    scopes = get_user_scopes(user)
    if not scopes:
        return False, "Tidak punya scope"

    kat = dokumen.kategori_pemilik

    for scope in scopes:
        # UNIVERSITAS: siapa saja yang scope UNIVERSITAS bisa edit
        if kat == "UNIVERSITAS" and scope.level == "UNIVERSITAS":
            return True, "OK - Scope Universitas"

        # BIRO: harus unit_kerja_id cocok
        elif kat == "BIRO" and scope.level == "BIRO":
            # Simple check: unit_kerja_id di scope vs scope_kode_unit_kerja di dokumen
            # Di Phase 1 kita relax: semua scope BIRO bisa edit semua dokumen BIRO
            return True, "OK - Scope Biro"

        # FAKULTAS: harus fakultas_id cocok
        elif kat == "FAKULTAS" and scope.level == "FAKULTAS":
            if scope.fakultas_id and str(scope.fakultas_id) == dokumen.scope_kode_fakultas:
                return True, "OK - Scope Fakultas sama"

        # PRODI: harus prodi_id cocok
        elif kat == "PRODI" and scope.level == "PRODI":
            if scope.prodi_id == dokumen.scope_kode_prodi:
                return True, "OK - Scope Prodi sama"

    return False, f"Tidak punya akses edit untuk dokumen {kat} ini (lateral lock)"


# =========================================================
# VIEW PERMISSION
# =========================================================

def can_view_dokumen(user, dokumen):
    """
    Cek apakah user boleh LIHAT dokumen.
    Aturan: semua user internal bisa view semua dokumen.
            Publik hanya bisa view dokumen TERBUKA.
    """
    if dokumen.status_akses == "TERBUKA":
        return True, "Dokumen terbuka untuk publik"

    if user.is_authenticated:
        return True, "User login bisa lihat semua internal"

    return False, "Dokumen internal, harus login"


# =========================================================
# SCOPE SUGGESTIONS
# =========================================================

def get_uploadable_butir_for_user(user):
    """
    Return queryset butir yang user BOLEH upload.
    Berguna untuk list butir yang relevan di UI.
    """
    from master_akreditasi.models import ButirDokumen

    if is_superadmin(user):
        return ButirDokumen.objects.filter(aktif=True)

    scopes = get_user_scopes(user)
    if not scopes:
        return ButirDokumen.objects.none()

    # Build kategori set based on scopes
    kategori_allowed = set()
    for scope in scopes:
        if scope.level == "UNIVERSITAS":
            kategori_allowed.add("UNIVERSITAS")
        elif scope.level == "BIRO":
            kategori_allowed.add("BIRO")
        elif scope.level == "FAKULTAS":
            kategori_allowed.update(["FAKULTAS"])  # Fakultas tidak auto include prodi
        elif scope.level == "PRODI":
            kategori_allowed.update(["FAKULTAS", "PRODI"])  # Prodi boleh akses fakultas juga (?)

    return ButirDokumen.objects.filter(
        aktif=True,
        kategori_kepemilikan__in=kategori_allowed,
    )