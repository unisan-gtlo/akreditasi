"""Permission helpers untuk modul Sesi Akreditasi."""
from core.models import ScopeUser


def is_superadmin(user):
    return user.is_authenticated and user.is_superuser


def can_create_sesi(user):
    """
    Bisa buat sesi:
    - Super Admin Pustikom
    - User dengan scope UNIVERSITAS (rektorat)
    """
    if not user.is_authenticated:
        return False, "Anda harus login"

    if is_superadmin(user):
        return True, "Super Admin"

    # Cek scope UNIVERSITAS
    has_univ_scope = user.scopes.filter(
        level="UNIVERSITAS",
        aktif=True,
    ).exists()

    if has_univ_scope:
        return True, "Pimpinan Universitas"

    return False, "Hanya Super Admin atau Pimpinan Universitas yang bisa membuat sesi akreditasi"


def can_edit_sesi(user, sesi):
    """Bisa edit sesi: sama dengan can_create."""
    return can_create_sesi(user)


def can_view_sesi(user, sesi):
    """
    Bisa lihat sesi:
    - Semua user login bisa lihat (transparency)
    """
    if not user.is_authenticated:
        return False, "Login required"
    return True, "OK"
# =========================================================
# DASHBOARD ACCESS & SCOPE FILTERING
# =========================================================

def can_access_dashboard(user):
    """
    Bisa akses dashboard sesi:
    - Super Admin
    - User dengan scope UNIVERSITAS, BIRO, FAKULTAS, atau PRODI
    """
    if not user.is_authenticated:
        return False, "Login required"

    if is_superadmin(user):
        return True, "Super Admin"

    has_scope = user.scopes.filter(
        level__in=["UNIVERSITAS", "BIRO", "FAKULTAS", "PRODI"],
        aktif=True,
    ).exists()

    if has_scope:
        return True, "User dengan scope"

    return False, "Tidak memiliki scope akreditasi"


def get_visible_sesi_for_user(user, sesi_qs=None):
    """
    Filter queryset sesi berdasarkan scope user.
    Return: filtered queryset

    - Super Admin: semua sesi
    - UNIVERSITAS / BIRO scope (LP3M, Rektorat): semua sesi
    - FAKULTAS scope (Dekan): hanya sesi dengan kode_fakultas matching
    - PRODI scope (Kaprodi): hanya sesi dengan kode_prodi matching
    """
    from sesi.models import SesiAkreditasi

    if sesi_qs is None:
        sesi_qs = SesiAkreditasi.objects.all()

    if not user.is_authenticated:
        return sesi_qs.none()

    if is_superadmin(user):
        return sesi_qs

    user_scopes = user.scopes.filter(aktif=True)

    # Cek scope UNIVERSITAS atau BIRO -> semua sesi
    if user_scopes.filter(level__in=["UNIVERSITAS", "BIRO"]).exists():
        return sesi_qs

    # Cek FAKULTAS scope
    fakultas_codes = list(
        user_scopes.filter(level="FAKULTAS")
        .values_list("fakultas_id", flat=True)
    )
    fakultas_codes = [f for f in fakultas_codes if f]  # filter empty

    # Cek PRODI scope
    prodi_codes = list(
        user_scopes.filter(level="PRODI")
        .values_list("prodi_id", flat=True)
    )
    prodi_codes = [p for p in prodi_codes if p]

    if not fakultas_codes and not prodi_codes:
        return sesi_qs.none()

    # Build OR query
    from django.db.models import Q
    q = Q()
    if fakultas_codes:
        q |= Q(kode_fakultas__in=fakultas_codes)
    if prodi_codes:
        q |= Q(kode_prodi__in=prodi_codes)

    return sesi_qs.filter(q)
