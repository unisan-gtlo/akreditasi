"""Permission helpers untuk app laporan.

Access level laporan:
- Superuser / Admin: full access
- Scope UNIVERSITAS / REKTORAT / BIRO / LP3M / LP2M: full access
- Scope FAKULTAS (Dekan): filtered by fakultas-nya
- Scope PRODI (Kaprodi): TIDAK PUNYA AKSES
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
        if level in ('UNIVERSITAS', 'REKTORAT', 'BIRO', 'LP3M', 'LP2M', 'SUPER', 'ADMIN', 'FAKULTAS'):
            return True
    return False


def get_user_laporan_scope(user):
    """Return dict scope untuk filter data laporan."""
    result = {'is_admin': False, 'fakultas_ids': []}
    
    if not user or not user.is_authenticated:
        return result
    
    if user.is_superuser or user.is_staff:
        result['is_admin'] = True
        return result
    
    if not hasattr(user, 'scopes'):
        return result
    
    admin_levels = ('UNIVERSITAS', 'REKTORAT', 'BIRO', 'LP3M', 'LP2M', 'SUPER', 'ADMIN')
    
    for scope in user.scopes.filter(aktif=True):
        level = (scope.level or '').upper()
        if level in admin_levels:
            result['is_admin'] = True
            return result
        if level == 'FAKULTAS' and scope.fakultas_id:
            result['fakultas_ids'].append(str(scope.fakultas_id))
    
    return result
