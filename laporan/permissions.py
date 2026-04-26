"""Permission helpers untuk app laporan.

Access level laporan:
- Superuser / Admin: full access
- Scope UNIVERSITAS / REKTORAT / BIRO / LP3M / LP2M: full access
- Scope FAKULTAS (Dekan): filtered by fakultas-nya
- Scope PRODI (Kaprodi): filtered by prodi-nya (lihat data sendiri saja)
"""


def can_access_laporan(user):
    """Cek apakah user punya akses ke menu Laporan."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if not hasattr(user, 'scopes'):
        return False
    for scope in user.scopes.filter(aktif=True):
        level = (scope.level or '').upper()
        if level in (
            'UNIVERSITAS', 'REKTORAT', 'BIRO', 'LP3M', 'LP2M',
            'SUPER', 'ADMIN', 'FAKULTAS', 'PRODI',
        ):
            return True
    return False


def get_user_laporan_scope(user):
    """Return dict scope untuk filter data laporan.

    Return shape:
        {
            'is_admin': bool,        # full access (admin/lp3m/rektorat/biro)
            'fakultas_ids': list,    # kode fakultas yang Dekan bisa lihat
            'prodi_ids': list,       # kode prodi yang Kaprodi bisa lihat
            'is_kaprodi_only': bool, # True kalau user HANYA punya scope PRODI
        }
    """
    result = {
        'is_admin': False,
        'fakultas_ids': [],
        'prodi_ids': [],
        'is_kaprodi_only': False,
    }

    if not user or not user.is_authenticated:
        return result

    if user.is_superuser or user.is_staff:
        result['is_admin'] = True
        return result

    if not hasattr(user, 'scopes'):
        return result

    admin_levels = ('UNIVERSITAS', 'REKTORAT', 'BIRO', 'LP3M', 'LP2M', 'SUPER', 'ADMIN')

    has_any_admin = False
    has_any_fakultas = False
    has_any_prodi = False

    for scope in user.scopes.filter(aktif=True):
        level = (scope.level or '').upper()
        if level in admin_levels:
            result['is_admin'] = True
            has_any_admin = True
        elif level == 'FAKULTAS' and scope.fakultas_id:
            result['fakultas_ids'].append(str(scope.fakultas_id))
            has_any_fakultas = True
        elif level == 'PRODI' and scope.prodi_id:
            result['prodi_ids'].append(str(scope.prodi_id))
            has_any_prodi = True

    # Kalau admin scope ada, langsung return is_admin=True
    if has_any_admin:
        # Reset filter karena admin punya akses penuh
        result['fakultas_ids'] = []
        result['prodi_ids'] = []
        return result

    # Flag: user HANYA punya scope prodi (tidak punya fakultas/admin)
    if has_any_prodi and not has_any_fakultas:
        result['is_kaprodi_only'] = True

    return result