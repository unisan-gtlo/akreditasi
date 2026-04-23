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