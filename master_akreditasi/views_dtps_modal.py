"""View AJAX untuk modal Data DTPS + BKD per butir akreditasi.

Dipanggil dari halaman Bundle (admin & public) saat asesor klik butir
yang punya ButirDataDosenMapping. Return HTML fragment untuk modal body.

Dual-mode auth:
  - User login → cek permission via _check_sesi_permission
  - Anonymous + token query param → cek BundleShareToken valid
"""
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.db.models import Sum

from sesi.models import SesiAkreditasi, BundleShareToken
from master_akreditasi.models import ButirDokumen
from master_akreditasi.models_dosen_link import (
    ButirDataDosenMapping,
    DTPSDosenSesi,
)
from master_akreditasi.models_simda_ref import RiwayatBKDRef
from master_akreditasi import simda_dosen as sd


def _check_access(request, sesi):
    """Dual-mode access check.

    Return tuple (is_allowed: bool, is_public: bool).
    is_public True kalau akses lewat token (untuk approved_only filter).
    """
    # Mode 1: User login + permission check
    if request.user.is_authenticated:
        # Lazy import untuk hindari circular
        from sesi.views import _check_sesi_permission
        if _check_sesi_permission(request.user, sesi):
            return True, False

    # Mode 2: Token via query param (?token=<uuid>)
    token = request.GET.get('token', '').strip()
    if token:
        try:
            share = BundleShareToken.objects.get(token=token, sesi=sesi)
            if share.is_valid():
                return True, True
        except BundleShareToken.DoesNotExist:
            pass

    return False, False


def butir_dtps_bkd_modal(request, sesi_id, butir_id):
    """Render modal body: daftar DTPS + agregat BKD per butir.

    URL : /master-akreditasi/sesi/<sesi_id>/butir/<butir_id>/dtps-bkd/
    Auth: Dual-mode (login OR token query param).
    """
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)
    butir = get_object_or_404(ButirDokumen, pk=butir_id)

    # Access check
    is_allowed, is_public = _check_access(request, sesi)
    if not is_allowed:
        return HttpResponseForbidden(
            '<div class="alert alert-danger m-3">'
            'Anda tidak memiliki akses untuk melihat data ini.'
            '</div>'
        )

    # Cari mapping untuk butir ini
    try:
        mapping = ButirDataDosenMapping.objects.select_related('butir').get(
            butir=butir, aktif=True
        )
    except ButirDataDosenMapping.DoesNotExist:
        return render(
            request,
            'master_akreditasi/_modal_dtps_bkd_empty.html',
            {'butir': butir, 'sesi': sesi},
        )

    # Fetch DTPS aktif sesi
    dtps_aktif = DTPSDosenSesi.objects.filter(
        sesi=sesi, aktif=True
    ).order_by('dosen_nama_snapshot')

    # Build per-DTPS BKD aggregate
    dtps_rows = []
    for dtps in dtps_aktif:
        # BKD per dosen sesuai filter periode mapping
        bkd_qs = sd.get_bkd_dosen_filter_periode(
            nidn=dtps.dosen_nidn,
            tahun_ts=str(sesi.tahun_ts),
            filter_periode=mapping.filter_periode,
        )
        bkd_count = bkd_qs.count()
        bkd_agg = bkd_qs.aggregate(
            total_pengajaran=Sum('sks_pengajaran'),
            total_penelitian=Sum('sks_penelitian'),
            total_pkm=Sum('sks_pkm'),
            total_penunjang=Sum('sks_penunjang'),
        )
        total_sks = sum(
            (bkd_agg.get(k) or 0) for k in (
                'total_pengajaran', 'total_penelitian',
                'total_pkm', 'total_penunjang'
            )
        )
        dtps_rows.append({
            'dtps': dtps,
            'bkd_count': bkd_count,
            'bkd_agg': bkd_agg,
            'total_sks': total_sks,
        })

    # Statistik ringkas
    total_dtps = len(dtps_rows)
    dtps_dengan_bkd = sum(1 for r in dtps_rows if r['bkd_count'] > 0)

    context = {
        'sesi': sesi,
        'butir': butir,
        'mapping': mapping,
        'dtps_rows': dtps_rows,
        'total_dtps': total_dtps,
        'dtps_dengan_bkd': dtps_dengan_bkd,
        'is_public': is_public,
    }
    return render(
        request,
        'master_akreditasi/_modal_dtps_bkd.html',
        context,
    )