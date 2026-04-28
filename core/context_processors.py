"""
Context processor global — stats & info user tersedia di semua template internal.
"""
from master_akreditasi.models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    MappingProdiInstrumen,
)


def sidebar_stats(request):
    """Stats untuk sidebar & dashboard (cached sederhana via lazy query)."""
    if not request.user.is_authenticated:
        return {}

    return {
        "stat_instrumen_count": Instrumen.objects.filter(aktif=True).count(),
        "stat_standar_count": Standar.objects.filter(aktif=True).count(),
        "stat_substandar_count": SubStandar.objects.filter(aktif=True).count(),
        "stat_butir_count": ButirDokumen.objects.filter(aktif=True).count(),
        "stat_mapping_count": MappingProdiInstrumen.objects.filter(aktif=True).count(),
    }

def notifikasi_context(request):
    """Inject notifikasi recent + unread count ke semua template."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'notifikasi_recent': [], 'notifikasi_unread_count': 0}
    
    try:
        from core.models import Notifikasi
        qs = Notifikasi.objects.filter(penerima=user).order_by('-tanggal_dibuat')
        
        # Recent 5 untuk dropdown
        recent = list(qs[:5])
        
        # Total unread untuk badge
        unread_count = qs.filter(sudah_dibaca=False).count()
        
        return {
            'notifikasi_recent': recent,
            'notifikasi_unread_count': unread_count,
        }
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
