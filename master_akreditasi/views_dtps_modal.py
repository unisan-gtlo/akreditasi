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
    """Render modal body: daftar DTPS + data per butir akreditasi.

    URL : /master/sesi/<sesi_id>/butir/<butir_id>/dtps-bkd/
    Auth: Dual-mode (login OR token query param).

    Dispatch ke resolver yang sesuai berdasarkan mapping.jenis_data
    (BKD, PENDIDIKAN, JABFUNG, PROFIL). Setiap resolver tahu cara fetch
    data dan template mana yang harus dirender.

    Note: nama function tetap 'butir_dtps_bkd_modal' untuk backward
    compatibility dengan URL & template yang sudah live di production.
    """
    from master_akreditasi.data_resolvers import (
        get_resolver, UnsupportedJenisDataError,
    )

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

    # Dispatch ke resolver
    try:
        resolver = get_resolver(mapping.jenis_data)
    except UnsupportedJenisDataError as e:
        return HttpResponseForbidden(
            f'<div class="alert alert-warning m-3">'
            f'Jenis data <strong>{mapping.get_jenis_data_display()}</strong> '
            f'belum didukung. {e}</div>'
        )

    # Fetch DTPS aktif sesi
    dtps_aktif = DTPSDosenSesi.objects.filter(
        sesi=sesi, aktif=True
    ).order_by('dosen_nama_snapshot')

    # Build per-DTPS summary via resolver
    dtps_rows = []
    for dtps in dtps_aktif:
        summary = resolver.get_dosen_summary(sesi, dtps, mapping)
        # Untuk backward compat dengan template BKD existing,
        # extra dict di-merge ke row dict (template BKD baca total_sks, bkd_count, dst)
        row = {
            'dtps': dtps,
            'summary': summary,
            'count': summary.count,
            'agg_value': summary.agg_value,
            'agg_value_formatted': summary.agg_value_formatted,
        }
        row.update(summary.extra)  # inject extra fields (bkd_agg, total_sks, dll)
        dtps_rows.append(row)

    # Statistik ringkas
    total_dtps = len(dtps_rows)
    dtps_dengan_data = sum(1 for r in dtps_rows if r['count'] > 0)

    # Backward compat: template BKD existing pakai 'dtps_dengan_bkd'
    context = {
        'sesi': sesi,
        'butir': butir,
        'mapping': mapping,
        'resolver': resolver,
        'dtps_rows': dtps_rows,
        'total_dtps': total_dtps,
        'dtps_dengan_data': dtps_dengan_data,
        'dtps_dengan_bkd': dtps_dengan_data,  # alias untuk template BKD existing
        'is_public': is_public,
    }

    # Template ditentukan oleh resolver — masing-masing jenis_data render template berbeda
    return render(request, resolver.modal_template, context)

def dosen_bkd_detail(request, sesi_id, butir_id, nidn):
    """Render sub-tabel data per dosen (drill-down inline expand).

    URL : /master/sesi/<sesi_id>/butir/<butir_id>/dosen/<nidn>/bkd-detail/
    Auth: Dual-mode (login OR token query param) — sama dengan endpoint modal.

    Dispatch ke resolver yang sesuai berdasarkan mapping.jenis_data.
    Setiap resolver tahu cara fetch detail records & template-nya.

    Return HTML fragment <tr class="bkd-detail-row"> dengan colspan
    yang berisi sub-tabel detail (periode BKD, riwayat pendidikan, dst).

    Note: nama function tetap 'dosen_bkd_detail' untuk backward compat
    URL routing yang sudah live di production.
    """
    from master_akreditasi.data_resolvers import (
        get_resolver, UnsupportedJenisDataError,
    )

    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)
    butir = get_object_or_404(ButirDokumen, pk=butir_id)

    # Access check (reuse helper dari endpoint modal)
    is_allowed, is_public = _check_access(request, sesi)
    if not is_allowed:
        return HttpResponseForbidden(
            '<tr><td colspan="8" style="padding:1rem;color:#991B1B;">'
            'Anda tidak memiliki akses untuk melihat data ini.'
            '</td></tr>'
        )

    # Cari mapping aktif (untuk filter periode konsisten)
    try:
        mapping = ButirDataDosenMapping.objects.get(butir=butir, aktif=True)
    except ButirDataDosenMapping.DoesNotExist:
        return HttpResponseForbidden(
            '<tr><td colspan="8" style="padding:1rem;color:#991B1B;">'
            'Butir ini tidak punya mapping data dosen aktif.'
            '</td></tr>'
        )

    # Verify dosen termasuk DTPS aktif sesi
    try:
        dtps = DTPSDosenSesi.objects.get(
            sesi=sesi, dosen_nidn=nidn, aktif=True
        )
    except DTPSDosenSesi.DoesNotExist:
        return HttpResponseForbidden(
            '<tr><td colspan="8" style="padding:1rem;color:#991B1B;">'
            'Dosen tidak termasuk DTPS aktif sesi ini.'
            '</td></tr>'
        )

    # Dispatch ke resolver
    try:
        resolver = get_resolver(mapping.jenis_data)
    except UnsupportedJenisDataError as e:
        return HttpResponseForbidden(
            f'<tr><td colspan="8" style="padding:1rem;color:#991B1B;">'
            f'Jenis data {mapping.get_jenis_data_display()} belum didukung. {e}'
            f'</td></tr>'
        )

    # Fetch detail records via resolver
    detail_records = resolver.get_detail_records(sesi, dtps, mapping)

    context = {
        'sesi': sesi,
        'butir': butir,
        'mapping': mapping,
        'resolver': resolver,
        'dtps': dtps,
        # Backward compat: template BKD existing pakai 'bkd_records'
        'bkd_records': detail_records,
        # Generic name untuk template baru
        'detail_records': detail_records,
    }
    return render(request, resolver.detail_template, context)