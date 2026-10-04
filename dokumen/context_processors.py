"""Context processors untuk app dokumen.

Inject variable yang dibutuhkan oleh template global (sidebar, dll).
"""
from django.core.cache import cache
from django.db.models import Q

from core.cache_utils import VERIF_TTL, verif_key


VERIFY_LEVELS = {'BIRO', 'UNIVERSITAS', 'FAKULTAS', 'LP3M', 'LP2M', 'REKTORAT', 'SUPER', 'ADMIN'}
ALL_SCOPE_LEVELS = {'UNIVERSITAS', 'BIRO', 'LP3M', 'LP2M', 'REKTORAT', 'SUPER', 'ADMIN'}


def _compute_verifikasi(user):
    # Scope aktif cukup diambil sekali, dipakai untuk can_verify & filter
    if user.is_superuser or user.is_staff:
        can_verify = True
        scope_q = Q()  # all
    else:
        scopes = list(user.scopes.filter(aktif=True)) if hasattr(user, 'scopes') else []
        levels = [((s.level or '').upper(), s) for s in scopes]
        can_verify = any(level in VERIFY_LEVELS for level, _ in levels)

        scope_q = Q(pk__in=[])
        if any(level in ALL_SCOPE_LEVELS for level, _ in levels):
            scope_q = Q()
        else:
            fakultas_q = Q()
            has_any = False
            for level, scope in levels:
                if level == 'FAKULTAS' and scope.fakultas_id:
                    fakultas_q |= Q(scope_kode_fakultas=scope.fakultas_id)
                    has_any = True
            if has_any:
                scope_q = fakultas_q

    pending_count = 0
    if can_verify:
        # Lazy import untuk hindari circular
        try:
            from dokumen.models import VerifikasiDokumen, Dokumen

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


def verifikasi_context(request):
    """Inject can_verify dan verifikasi_pending_count ke semua template.

    Di-cache per user 60 detik; cache seluruh user ikut basi (naik versi)
    setiap ada perubahan verifikasi/dokumen (core/signals.py).
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'can_verify': False, 'verifikasi_pending_count': 0}

    return cache.get_or_set(verif_key(user.pk), lambda: _compute_verifikasi(user), VERIF_TTL)
