"""
Context processor global — stats & info user tersedia di semua template internal.
"""
from django.core.cache import cache

from master_akreditasi.models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    MappingProdiInstrumen,
)

from .cache_utils import (
    NOTIF_TTL,
    SIDEBAR_STATS_KEY,
    SIDEBAR_STATS_TTL,
    notif_key,
)


def _compute_sidebar_stats():
    return {
        "stat_instrumen_count": Instrumen.objects.filter(aktif=True).count(),
        "stat_standar_count": Standar.objects.filter(aktif=True).count(),
        "stat_substandar_count": SubStandar.objects.filter(aktif=True).count(),
        "stat_butir_count": ButirDokumen.objects.filter(aktif=True).count(),
        "stat_mapping_count": MappingProdiInstrumen.objects.filter(aktif=True).count(),
    }


def sidebar_stats(request):
    """Stats untuk sidebar & dashboard.

    Data master jarang berubah -> di-cache 10 menit, dihapus otomatis
    lewat signal saat master diubah (core/signals.py).
    """
    if not request.user.is_authenticated:
        return {}

    return cache.get_or_set(SIDEBAR_STATS_KEY, _compute_sidebar_stats, SIDEBAR_STATS_TTL)

def notifikasi_context(request):
    """Inject notifikasi recent + unread count ke semua template."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'notifikasi_recent': [], 'notifikasi_unread_count': 0}

    try:
        key = notif_key(user.pk)
        data = cache.get(key)
        if data is None:
            from core.models import Notifikasi
            qs = Notifikasi.objects.filter(penerima=user).order_by('-tanggal_dibuat')

            data = {
                # Recent 5 untuk dropdown (dibuat_oleh ikut di-join untuk topbar)
                'notifikasi_recent': list(qs.select_related('dibuat_oleh')[:5]),
                # Total unread untuk badge
                'notifikasi_unread_count': qs.filter(sudah_dibaca=False).count(),
            }
            cache.set(key, data, NOTIF_TTL)
        return data
    except Exception:
        return {'notifikasi_recent': [], 'notifikasi_unread_count': 0}

def vmts_stats(request):
    """Inject statistik survei VMTS ke semua template."""
    if not request.user.is_authenticated:
        return {}
    try:
        from core.models import SurveiVMTS
        from django.db.models import Count
        total = SurveiVMTS.objects.count()
        return {'stats_vmts_total': total}
    except Exception:
        return {}
