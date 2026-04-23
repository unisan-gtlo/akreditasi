"""Context processors untuk app dokumen.

Inject variable yang dibutuhkan oleh template global (sidebar, dll).
"""
from django.db.models import Q


def verifikasi_context(request):
    """Inject can_verify dan verifikasi_pending_count ke semua template."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'can_verify': False, 'verifikasi_pending_count': 0}

    # Cek apakah user bisa verifikasi
    can_verify = False
    if user.is_superuser or user.is_staff:
        can_verify = True
    elif hasattr(user, 'scopes'):
        allowed_levels = {'BIRO', 'UNIVERSITAS', 'FAKULTAS', 'LP3M', 'LP2M', 'REKTORAT', 'SUPER', 'ADMIN'}
        for scope in user.scopes.filter(aktif=True):
            if (scope.level or '').upper() in allowed_levels:
                can_verify = True
                break

    pending_count = 0
    if can_verify:
        # Lazy import untuk hindari circular
        try:
            from dokumen.models import VerifikasiDokumen, Dokumen
            
            # Build scope filter
            scope_q = Q()
            if user.is_superuser or user.is_staff:
                scope_q = Q()  # all
            else:
                has_any = False
                for scope in user.scopes.filter(aktif=True):
                    level = (scope.level or '').upper()
                    if level in ('UNIVERSITAS', 'BIRO', 'LP3M', 'LP2M', 'REKTORAT', 'SUPER', 'ADMIN'):
                        scope_q = Q()
                        has_any = True
                        break
                    if level == 'FAKULTAS' and scope.fakultas_id:
                        scope_q |= Q(scope_kode_fakultas=scope.fakultas_id)
                        has_any = True
                if not has_any:
                    scope_q = Q(pk__in=[])

            pending_count = VerifikasiDokumen.objects.filter(
                status='PENDING',
                revisi__aktif=True,
                revisi__dokumen__in=Dokumen.objects.filter(scope_q),
            ).count()
        except Exception:
            pending_count = 0

    return {
        'can_verify': can_verify,
        'verifikasi_pending_count': pending_count,
    }
