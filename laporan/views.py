"""Views untuk app laporan.

Sub-batch 11B: Dashboard Index dengan global stats + 4 kartu laporan.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import render

from .permissions import can_access_laporan, get_user_laporan_scope

# Mapping prefix kode_prodi -> (kode_fakultas, nama_fakultas)
_FAKULTAS_MAP = {
    'T': ('FT', 'Fakultas Teknik'),
    'E': ('FE', 'Fakultas Ekonomi'),
    'H': ('FH', 'Fakultas Hukum'),
    'K': ('FT', 'Fakultas Teknik'),  # K11 Sistem Informasi masuk FT
    'P': ('FP', 'Fakultas Pertanian'),
    'S': ('FS', 'Fakultas Ilmu Sosial dan Politik'),
}


def _derive_fakultas(kode_prodi):
    """Derive fakultas dari kode_prodi (huruf pertama)."""
    if not kode_prodi:
        return ('—', '—')
    prefix = kode_prodi[0].upper()
    return _FAKULTAS_MAP.get(prefix, ('—', '—'))



def _check_permission(request):
    if not can_access_laporan(request.user):
        return HttpResponseForbidden(
            '<h2>Akses Ditolak</h2>'
            '<p>Anda tidak memiliki akses ke menu Laporan. '
            'Laporan hanya untuk LP3M, Rektorat, Dekan, dan Admin.</p>'
        )
    return None


def _get_global_stats(scope_info):
    """Query global stats untuk dashboard laporan, filtered by scope."""
    from sesi.models import SesiAkreditasi
    from dokumen.models import Dokumen, DokumenRevisi, VerifikasiDokumen
    
    # Base querysets
    sesi_qs = SesiAkreditasi.objects.exclude(status__in=['SELESAI', 'DIBATALKAN'])
    dokumen_qs = Dokumen.objects.all()
    verifikasi_qs = VerifikasiDokumen.objects.all()
    
    # Apply fakultas filter untuk Dekan
    if not scope_info.get('is_admin') and scope_info.get('fakultas_ids'):
        fakultas_ids = scope_info['fakultas_ids']
        sesi_qs = sesi_qs.filter(kode_fakultas__in=fakultas_ids)
        dokumen_qs = dokumen_qs.filter(scope_kode_fakultas__in=fakultas_ids)
        verifikasi_qs = verifikasi_qs.filter(
            revisi__dokumen__scope_kode_fakultas__in=fakultas_ids
        )
    
    # Hitung stats
    sesi_aktif_count = sesi_qs.count()
    total_dokumen = dokumen_qs.count()
    total_verifikasi = verifikasi_qs.count()
    approved_count = verifikasi_qs.filter(status='APPROVED').count()
    pending_count = verifikasi_qs.filter(status='PENDING').count()
    rejected_count = verifikasi_qs.filter(status='REJECTED').count()
    revision_count = verifikasi_qs.filter(status='NEED_REVISION').count()
    
    # Completion rate (approved / total verifikasi)
    approved_pct = round((approved_count / total_verifikasi * 100), 1) if total_verifikasi > 0 else 0
    
    # Progress rata-rata sesi (butir_terisi / total_butir per sesi)
    # Simplified: pakai % approved dari total dokumen sebagai proxy
    progress_avg = approved_pct
    
    # Sesi aktif dengan shortcut
    sesi_aktif_list = list(
        sesi_qs.order_by('-tanggal_mulai')[:5]
        .values('id', 'judul', 'status', 'kode_prodi', 'nama_prodi_snapshot', 'tahun_ts')
    )
    
    return {
        'sesi_aktif_count': sesi_aktif_count,
        'total_dokumen': total_dokumen,
        'total_verifikasi': total_verifikasi,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'rejected_count': rejected_count,
        'revision_count': revision_count,
        'approved_pct': approved_pct,
        'progress_avg': progress_avg,
        'sesi_aktif_list': sesi_aktif_list,
    }


@login_required(login_url='/login/')
def laporan_index(request):
    """Dashboard index laporan dengan global stats + 4 kartu."""
    denied = _check_permission(request)
    if denied:
        return denied
    
    scope_info = get_user_laporan_scope(request.user)
    stats = _get_global_stats(scope_info)
    
    context = {
        'page_title': 'Dashboard Laporan',
        'active_menu': 'laporan',
        'scope_info': scope_info,
        **stats,
    }
    return render(request, 'laporan/laporan_index.html', context)


# ============================================
# SUB-BATCH 11C: LAPORAN PROGRESS PER SESI
# ============================================

def _get_sesi_progress_data(sesi):
    """Hitung data progress lengkap untuk 1 sesi akreditasi.
    
    Returns:
        dict dengan: butir_list, stats, butir_by_standar
    """
    from master_akreditasi.models import ButirDokumen, Standar, SubStandar
    from dokumen.models import Dokumen, DokumenRevisi, VerifikasiDokumen
    
    # 1. Ambil semua butir untuk instrumen sesi ini
    butir_qs = ButirDokumen.objects.filter(
        sub_standar__standar__instrumen=sesi.instrumen,
        aktif=True,
    ).select_related('sub_standar', 'sub_standar__standar').order_by(
        'sub_standar__standar__nomor',
        'sub_standar__nomor',
        'kode',
    )
    
    # 2. Ambil semua dokumen untuk sesi ini (by periode evaluasi + scope)
    # Pakai property tahun_periode_list dari sesi
    try:
        periode_list = sesi.tahun_periode_list
    except Exception:
        periode_list = [sesi.tahun_ts] if sesi.tahun_ts else []
    
    dokumen_qs = Dokumen.objects.filter(
        tahun_akademik__in=periode_list,
    )
    
    # Filter scope: prodi-specific atau universitas-level
    if sesi.kode_prodi:
        dokumen_qs = dokumen_qs.filter(
            Q(scope_kode_prodi=sesi.kode_prodi) |
            Q(scope_kode_fakultas=sesi.kode_fakultas) |
            (Q(scope_kode_prodi__isnull=True) & Q(scope_kode_fakultas__isnull=True))
        )
    
    # 3. Map butir_id → dokumen (ambil terbaru)
    dokumen_by_butir = {}
    for d in dokumen_qs.select_related('butir_dokumen').order_by('-tanggal_dibuat'):
        if d.butir_dokumen_id not in dokumen_by_butir:
            dokumen_by_butir[d.butir_dokumen_id] = d
    
    # 4. Build butir_list dengan status
    butir_list = []
    stats = {
        'total_butir': 0,
        'butir_terisi': 0,
        'butir_kosong': 0,
        'status_approved': 0,
        'status_pending': 0,
        'status_rejected': 0,
        'status_revision': 0,
    }
    
    for butir in butir_qs:
        stats['total_butir'] += 1
        
        dokumen = dokumen_by_butir.get(butir.pk)
        status = 'KOSONG'
        dokumen_info = None
        verifikator = None
        tanggal_verifikasi = None
        
        if dokumen:
            stats['butir_terisi'] += 1
            dokumen_info = {
                'id': dokumen.pk,
                'judul': dokumen.judul,
            }
            # Ambil verifikasi dari revisi terbaru
            latest_rev = dokumen.revisi.order_by('-nomor_revisi').first()
            if latest_rev:
                try:
                    verif = latest_rev.verifikasi
                    status = verif.status
                    if verif.verifikator:
                        verifikator = verif.verifikator.get_full_name() or verif.verifikator.username
                    tanggal_verifikasi = verif.tanggal_verifikasi
                except Exception:
                    status = 'PENDING'
            
            # Update stats status
            if status == 'APPROVED':
                stats['status_approved'] += 1
            elif status == 'PENDING':
                stats['status_pending'] += 1
            elif status == 'REJECTED':
                stats['status_rejected'] += 1
            elif status == 'NEED_REVISION':
                stats['status_revision'] += 1
        else:
            stats['butir_kosong'] += 1
        
        butir_list.append({
            'butir': butir,
            'kode': butir.kode,
            'nama': butir.nama_dokumen,
            'standar_nomor': butir.sub_standar.standar.nomor if butir.sub_standar else '',
            'standar_nama': (getattr(butir.sub_standar.standar, 'nama', None) or getattr(butir.sub_standar.standar, 'judul', None) or getattr(butir.sub_standar.standar, 'deskripsi', '')) if butir.sub_standar else '',
            'substandar_nomor': butir.sub_standar.nomor if butir.sub_standar else '',
            'dokumen': dokumen_info,
            'status': status,
            'verifikator': verifikator,
            'tanggal_verifikasi': tanggal_verifikasi,
        })
    
    # Progress percentage
    if stats['total_butir'] > 0:
        stats['progress_pct'] = round((stats['butir_terisi'] / stats['total_butir']) * 100, 1)
        stats['approved_pct'] = round((stats['status_approved'] / stats['total_butir']) * 100, 1)
    else:
        stats['progress_pct'] = 0
        stats['approved_pct'] = 0
    
    # Group by standar untuk tampilan
    butir_by_standar = {}
    for item in butir_list:
        key = (item['standar_nomor'], item['standar_nama'])
        if key not in butir_by_standar:
            butir_by_standar[key] = []
        butir_by_standar[key].append(item)
    
    # Convert ke list of dict untuk template
    standar_groups = [
        {
            'nomor': k[0],
            'nama': k[1],
            'butir_list': v,
            'total': len(v),
            'terisi': sum(1 for b in v if b['status'] != 'KOSONG'),
        }
        for k, v in sorted(butir_by_standar.items(), key=lambda x: x[0][0])
    ]
    
    return {
        'butir_list': butir_list,
        'stats': stats,
        'standar_groups': standar_groups,
    }


@login_required(login_url='/login/')
def laporan_sesi_detail(request, sesi_id):
    """Laporan Progress per Sesi (11C)."""
    from django.shortcuts import get_object_or_404
    from sesi.models import SesiAkreditasi
    
    denied = _check_permission(request)
    if denied:
        return denied
    
    sesi = get_object_or_404(
        SesiAkreditasi.objects.select_related('instrumen'),
        pk=sesi_id,
    )
    
    # Permission fakultas-level check
    scope_info = get_user_laporan_scope(request.user)
    if not scope_info['is_admin'] and scope_info['fakultas_ids']:
        if sesi.kode_fakultas and str(sesi.kode_fakultas) not in scope_info['fakultas_ids']:
            return HttpResponseForbidden('<h2>Akses Ditolak</h2><p>Sesi ini di luar fakultas Anda.</p>')
    
    data = _get_sesi_progress_data(sesi)
    
    # Export handling
    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'pdf':
        from .exports import export_sesi_pdf
        return export_sesi_pdf(sesi, data)
    elif export_fmt == 'excel':
        from .exports import export_sesi_excel
        return export_sesi_excel(sesi, data)
    
    context = {
        'page_title': f'Laporan Progress: {sesi.judul}',
        'active_menu': 'laporan',
        'sesi': sesi,
        'scope_info': scope_info,
        **data,
    }
    return render(request, 'laporan/laporan_sesi_detail.html', context)


# ============================================
# SUB-BATCH 11D: COMPLETENESS PER PRODI
# ============================================

def _get_prodi_completeness_data(scope_info, fakultas_filter=None):
    """Hitung completeness per prodi berdasarkan mapping prodi → instrumen.
    
    Returns: list of dict dengan data prodi + stats kelengkapan
    """
    from master_akreditasi.models import MappingProdiInstrumen, ButirDokumen
    from dokumen.models import Dokumen, VerifikasiDokumen
    
    # Ambil semua mapping prodi → instrumen
    mapping_qs = MappingProdiInstrumen.objects.filter(
        aktif=True,
    ).select_related('instrumen').order_by('kode_prodi')
    
    # Filter by fakultas di Python (karena MappingProdiInstrumen tidak punya field kode_fakultas)
    # Fakultas di-derive dari huruf pertama kode_prodi
    
    result = []
    
    for mapping in mapping_qs:
        # Hitung total butir untuk instrumen ini
        total_butir = ButirDokumen.objects.filter(
            sub_standar__standar__instrumen=mapping.instrumen,
            aktif=True,
        ).count()
        
        # Hitung dokumen untuk prodi ini
        dokumen_qs = Dokumen.objects.filter(
            scope_kode_prodi=mapping.kode_prodi,
        )
        
        # Unique butir yang sudah ada dokumennya
        butir_terisi = dokumen_qs.values('butir_dokumen').distinct().count()
        
        # Count status verifikasi per status (revisi terbaru per dokumen)
        approved_count = 0
        pending_count = 0
        rejected_count = 0
        revision_count = 0
        
        for d in dokumen_qs.prefetch_related('revisi'):
            latest_rev = d.revisi.order_by('-nomor_revisi').first()
            if latest_rev:
                try:
                    status = latest_rev.verifikasi.status
                    if status == 'APPROVED':
                        approved_count += 1
                    elif status == 'PENDING':
                        pending_count += 1
                    elif status == 'REJECTED':
                        rejected_count += 1
                    elif status == 'NEED_REVISION':
                        revision_count += 1
                except Exception:
                    pending_count += 1
        
        progress_pct = round((butir_terisi / total_butir * 100), 1) if total_butir > 0 else 0
        approved_pct = round((approved_count / total_butir * 100), 1) if total_butir > 0 else 0
        
        # Tier untuk color coding
        if progress_pct >= 70:
            tier = 'high'
        elif progress_pct >= 40:
            tier = 'mid'
        else:
            tier = 'low'
        
        kode_fakultas, nama_fakultas = _derive_fakultas(mapping.kode_prodi)
        
        # Apply filter fakultas di sini (Python-side)
        if not scope_info.get('is_admin') and scope_info.get('fakultas_ids'):
            if kode_fakultas not in scope_info['fakultas_ids']:
                continue
        if fakultas_filter and kode_fakultas != fakultas_filter:
            continue
        
        result.append({
            'kode_prodi': mapping.kode_prodi,
            'nama_prodi': mapping.nama_prodi,
            'kode_fakultas': kode_fakultas,
            'nama_fakultas': nama_fakultas,
            'instrumen_nama': getattr(mapping.instrumen, 'nama', None) or getattr(mapping.instrumen, 'judul', None) or getattr(mapping.instrumen, 'kode', None) or str(mapping.instrumen),
            'total_butir': total_butir,
            'butir_terisi': butir_terisi,
            'butir_kosong': total_butir - butir_terisi,
            'approved_count': approved_count,
            'pending_count': pending_count,
            'rejected_count': rejected_count,
            'revision_count': revision_count,
            'progress_pct': progress_pct,
            'approved_pct': approved_pct,
            'tier': tier,
        })
    
    # Sort default: progress desc
    result.sort(key=lambda x: -x['progress_pct'])
    
    return result


@login_required(login_url='/login/')
def laporan_prodi_list(request):
    """Laporan Completeness per Prodi (11D)."""
    denied = _check_permission(request)
    if denied:
        return denied
    
    scope_info = get_user_laporan_scope(request.user)
    
    fakultas_filter = request.GET.get('fakultas', '').strip() or None
    prodi_list = _get_prodi_completeness_data(scope_info, fakultas_filter=fakultas_filter)
    
    # Daftar fakultas unik untuk dropdown filter (kode + nama)
    fakultas_options_dict = {}
    for p in prodi_list:
        k = p.get('kode_fakultas')
        if k and k != '—' and k not in fakultas_options_dict:
            fakultas_options_dict[k] = p.get('nama_fakultas') or k
    fakultas_options = sorted(fakultas_options_dict.items(), key=lambda x: x[0])
    
    # Aggregate stats
    agg = {
        'total_prodi': len(prodi_list),
        'total_butir': sum(p['total_butir'] for p in prodi_list),
        'total_terisi': sum(p['butir_terisi'] for p in prodi_list),
        'total_approved': sum(p['approved_count'] for p in prodi_list),
    }
    if agg['total_butir'] > 0:
        agg['overall_progress'] = round((agg['total_terisi'] / agg['total_butir']) * 100, 1)
    else:
        agg['overall_progress'] = 0
    
    # Top 10 untuk bar chart
    top10 = prodi_list[:10]
    
    # Derive nama fakultas untuk filter yang aktif
    fakultas_filter_nama = None
    if fakultas_filter:
        for kode, nama in fakultas_options:
            if kode == fakultas_filter:
                fakultas_filter_nama = nama
                break
    
    # Export handling
    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'excel':
        from .exports import export_prodi_excel
        return export_prodi_excel(prodi_list, agg, fakultas_filter_nama)
    
    context = {
        'page_title': 'Completeness per Prodi',
        'active_menu': 'laporan',
        'scope_info': scope_info,
        'prodi_list': prodi_list,
        'top10': top10,
        'fakultas_options': fakultas_options,
        'fakultas_filter': fakultas_filter,
        'fakultas_filter_nama': fakultas_filter_nama,
        'agg': agg,
    }
    return render(request, 'laporan/laporan_prodi_list.html', context)


# ============================================
# SUB-BATCH 11E: HEATMAP VERIFIKASI
# ============================================

def _get_heatmap_data(instrumen, scope_info, fakultas_filter=None):
    """Build matrix data: rows=Standar, cols=Prodi, cells=aggregate status.
    
    Returns:
        dict dengan: standar_list, prodi_list, matrix (dict of dict),
                     insights (list of str)
    """
    from master_akreditasi.models import Standar, SubStandar, ButirDokumen, MappingProdiInstrumen
    from dokumen.models import Dokumen
    
    # 1. Ambil semua Standar untuk instrumen ini
    standar_qs = Standar.objects.filter(
        instrumen=instrumen,
        aktif=True,
    ).order_by('nomor')
    
    standar_list = []
    butir_per_standar = {}  # standar_id -> [butir_ids]
    
    for s in standar_qs:
        # Ambil semua butir untuk standar ini
        butir_ids = list(
            ButirDokumen.objects.filter(
                sub_standar__standar=s,
                aktif=True,
            ).values_list('id', flat=True)
        )
        
        standar_list.append({
            'id': s.id,
            'nomor': s.nomor,
            'nama': getattr(s, 'nama', None) or getattr(s, 'judul', None) or getattr(s, 'deskripsi', '') or f'Standar {s.nomor}',
            'total_butir': len(butir_ids),
        })
        butir_per_standar[s.id] = set(butir_ids)
    
    # 2. Ambil prodi yang mapped ke instrumen ini
    mapping_qs = MappingProdiInstrumen.objects.filter(
        instrumen=instrumen,
        aktif=True,
    ).order_by('kode_prodi')
    
    prodi_list = []
    for m in mapping_qs:
        kode_fakultas, nama_fakultas = _derive_fakultas(m.kode_prodi)
        
        # Filter scope
        if not scope_info.get('is_admin') and scope_info.get('fakultas_ids'):
            if kode_fakultas not in scope_info['fakultas_ids']:
                continue
        if fakultas_filter and kode_fakultas != fakultas_filter:
            continue
        
        prodi_list.append({
            'kode_prodi': m.kode_prodi,
            'nama_prodi': m.nama_prodi,
            'kode_fakultas': kode_fakultas,
            'nama_fakultas': nama_fakultas,
        })
    
    # 3. Ambil semua dokumen untuk prodi-prodi ini
    prodi_codes = [p['kode_prodi'] for p in prodi_list]
    dokumen_qs = Dokumen.objects.filter(
        scope_kode_prodi__in=prodi_codes,
    ).prefetch_related('revisi').select_related('butir_dokumen')
    
    # 4. Build index: (standar_id, kode_prodi) -> list of (butir_id, status)
    cells_data = {}  # (s_id, prodi_code) -> list of status
    
    for d in dokumen_qs:
        if not d.butir_dokumen_id:
            continue
        
        # Cari standar yang match butir ini
        s_id = None
        for sid, butir_set in butir_per_standar.items():
            if d.butir_dokumen_id in butir_set:
                s_id = sid
                break
        
        if s_id is None:
            continue
        
        # Ambil status dari revisi terbaru
        latest_rev = d.revisi.order_by('-nomor_revisi').first()
        status = 'KOSONG'
        if latest_rev:
            try:
                status = latest_rev.verifikasi.status
            except Exception:
                status = 'PENDING'
        
        key = (s_id, d.scope_kode_prodi)
        if key not in cells_data:
            cells_data[key] = []
        cells_data[key].append(status)
    
    # 5. Compute cell classification per (standar, prodi)
    matrix = {}  # s_id -> prodi_code -> cell_info
    
    for s in standar_list:
        matrix[s['id']] = {}
        for p in prodi_list:
            cell_statuses = cells_data.get((s['id'], p['kode_prodi']), [])
            total_butir = s['total_butir']
            
            # Count per status
            counts = {
                'APPROVED': cell_statuses.count('APPROVED'),
                'PENDING': cell_statuses.count('PENDING'),
                'REJECTED': cell_statuses.count('REJECTED'),
                'NEED_REVISION': cell_statuses.count('NEED_REVISION'),
            }
            terisi = sum(counts.values())
            
            # Classify cell color
            if terisi == 0:
                color = 'empty'
                label = 'Belum diisi'
            elif counts['REJECTED'] > 0:
                color = 'red'
                label = f'{counts["REJECTED"]} ditolak'
            elif counts['NEED_REVISION'] > 0:
                color = 'orange'
                label = f'{counts["NEED_REVISION"]} revisi'
            elif counts['APPROVED'] == total_butir:
                color = 'green'
                label = 'Semua approved'
            elif counts['APPROVED'] > 0 and counts['PENDING'] == 0:
                color = 'yellow'
                label = f'{counts["APPROVED"]}/{total_butir} approved'
            else:
                color = 'blue'
                label = f'{counts["PENDING"]} pending'
            
            matrix[s['id']][p['kode_prodi']] = {
                'color': color,
                'label': label,
                'terisi': terisi,
                'total': total_butir,
                'counts': counts,
            }
    
    # 6. Generate insights
    insights = []
    
    # Insight: Standar dengan paling banyak prodi bermasalah (revision/rejected)
    for s in standar_list:
        problem_count = 0
        for p in prodi_list:
            cell = matrix[s['id']].get(p['kode_prodi'], {})
            if cell.get('color') in ('red', 'orange'):
                problem_count += 1
        if problem_count >= 2:
            insights.append(f'Standar {s["nomor"]} ({s["nama"][:40]}): {problem_count} prodi butuh perhatian')
    
    # Insight: Prodi dengan paling banyak standar kosong
    for p in prodi_list:
        empty_count = 0
        for s in standar_list:
            cell = matrix[s['id']].get(p['kode_prodi'], {})
            if cell.get('color') == 'empty':
                empty_count += 1
        if empty_count >= len(standar_list) * 0.5 and empty_count > 0:
            insights.append(f'Prodi {p["kode_prodi"]} ({p["nama_prodi"][:30]}): {empty_count} dari {len(standar_list)} standar belum diisi')
    
    return {
        'standar_list': standar_list,
        'prodi_list': prodi_list,
        'matrix': matrix,
        'insights': insights[:5],  # Top 5 insights
    }


@login_required(login_url='/login/')
def laporan_heatmap(request):
    """Laporan Heatmap Verifikasi (11E)."""
    from master_akreditasi.models import Instrumen
    
    denied = _check_permission(request)
    if denied:
        return denied
    
    scope_info = get_user_laporan_scope(request.user)
    
    # Default: instrumen pertama yang aktif
    instrumen_id = request.GET.get('instrumen')
    fakultas_filter = request.GET.get('fakultas', '').strip() or None
    
    instrumen_options = list(Instrumen.objects.filter(aktif=True).order_by('kode'))
    
    selected_instrumen = None
    if instrumen_id:
        selected_instrumen = next((i for i in instrumen_options if str(i.id) == instrumen_id), None)
    if not selected_instrumen and instrumen_options:
        selected_instrumen = instrumen_options[0]
    
    heatmap_data = {'standar_list': [], 'prodi_list': [], 'matrix': {}, 'insights': []}
    if selected_instrumen:
        heatmap_data = _get_heatmap_data(selected_instrumen, scope_info, fakultas_filter)
    
    # Daftar fakultas untuk filter
    fakultas_options_dict = {}
    for p in heatmap_data['prodi_list']:
        k = p.get('kode_fakultas')
        if k and k != '—' and k not in fakultas_options_dict:
            fakultas_options_dict[k] = p.get('nama_fakultas') or k
    fakultas_options = sorted(fakultas_options_dict.items(), key=lambda x: x[0])
    
    # Export handling
    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'pdf':
        from .exports import export_heatmap_pdf
        return export_heatmap_pdf(
            selected_instrumen,
            heatmap_data['standar_list'],
            heatmap_data['prodi_list'],
            heatmap_data['matrix'],
            heatmap_data['insights'],
        )
    
    context = {
        'page_title': 'Heatmap Verifikasi',
        'active_menu': 'laporan',
        'scope_info': scope_info,
        'instrumen_options': instrumen_options,
        'selected_instrumen': selected_instrumen,
        'fakultas_options': fakultas_options,
        'fakultas_filter': fakultas_filter,
        **heatmap_data,
    }
    return render(request, 'laporan/laporan_heatmap.html', context)


# ============================================
# SUB-BATCH 11F: AUDIT TRAIL
# ============================================

def _get_audit_trail_data(scope_info, filters):
    """Query VerifikasiLog dengan filter."""
    from dokumen.models import VerifikasiLog
    from datetime import datetime
    
    qs = VerifikasiLog.objects.select_related(
        'verifikasi',
        'verifikasi__revisi',
        'verifikasi__revisi__dokumen',
        'verifikasi__revisi__dokumen__butir_dokumen',
        'dilakukan_oleh',
    ).order_by('-tanggal')
    
    # Filter scope fakultas
    if not scope_info.get('is_admin') and scope_info.get('fakultas_ids'):
        qs = qs.filter(
            verifikasi__revisi__dokumen__scope_kode_fakultas__in=scope_info['fakultas_ids']
        )
    
    # Filter date range
    if filters.get('date_from'):
        try:
            dt = datetime.strptime(filters['date_from'], '%Y-%m-%d')
            qs = qs.filter(tanggal__gte=dt)
        except ValueError:
            pass
    
    if filters.get('date_to'):
        try:
            dt = datetime.strptime(filters['date_to'], '%Y-%m-%d')
            # Include seluruh hari
            dt_end = dt.replace(hour=23, minute=59, second=59)
            qs = qs.filter(tanggal__lte=dt_end)
        except ValueError:
            pass
    
    # Filter aksi
    if filters.get('aksi'):
        qs = qs.filter(aksi=filters['aksi'])
    
    # Filter verifikator
    if filters.get('verifikator_id'):
        try:
            qs = qs.filter(dilakukan_oleh_id=int(filters['verifikator_id']))
        except (ValueError, TypeError):
            pass
    
    # Filter search (judul dokumen atau catatan)
    search = filters.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(verifikasi__revisi__dokumen__judul__icontains=search) |
            Q(catatan__icontains=search)
        )
    
    return qs


@login_required(login_url='/login/')
def laporan_audit_trail(request):
    """Laporan Audit Trail Verifikasi (11F)."""
    from django.core.paginator import Paginator
    from django.contrib.auth import get_user_model
    from dokumen.models import VerifikasiLog
    from datetime import datetime, timedelta
    
    denied = _check_permission(request)
    if denied:
        return denied
    
    scope_info = get_user_laporan_scope(request.user)
    User = get_user_model()
    
    # Default date range: 30 hari terakhir
    today = datetime.now().date()
    default_from = today - timedelta(days=30)
    
    filters = {
        'date_from': request.GET.get('date_from', default_from.strftime('%Y-%m-%d')),
        'date_to': request.GET.get('date_to', today.strftime('%Y-%m-%d')),
        'aksi': request.GET.get('aksi', '').strip(),
        'verifikator_id': request.GET.get('verifikator_id', '').strip(),
        'search': request.GET.get('search', '').strip(),
    }
    
    qs = _get_audit_trail_data(scope_info, filters)
    
    # Stats summary
    stats = {
        'total': qs.count(),
        'approved': qs.filter(aksi='APPROVED').count(),
        'rejected': qs.filter(aksi='REJECTED').count(),
        'revision': qs.filter(aksi='NEED_REVISION').count(),
        'reset': qs.filter(aksi='RESET').count(),
    }
    
    # Export handling (sebelum pagination, pakai full queryset)
    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'excel':
        from .exports import export_audit_excel
        return export_audit_excel(qs[:5000], stats, filters)
    
    # Pagination 30/page
    paginator = Paginator(qs, 30)
    page_num = request.GET.get('page', 1)
    page = paginator.get_page(page_num)
    
    # Verifikator options (user yang pernah melakukan verifikasi)
    verifikator_ids = VerifikasiLog.objects.values_list('dilakukan_oleh', flat=True).distinct()
    verifikator_options = list(
        User.objects.filter(id__in=verifikator_ids).order_by('username')
    )
    
    # Aksi options
    aksi_options = [
        ('APPROVED', 'Approved (Disetujui)'),
        ('REJECTED', 'Rejected (Ditolak)'),
        ('NEED_REVISION', 'Need Revision (Perlu Revisi)'),
        ('RESET', 'Reset ke Pending'),
    ]
    
    context = {
        'page_title': 'Audit Trail Verifikasi',
        'active_menu': 'laporan',
        'scope_info': scope_info,
        'page': page,
        'stats': stats,
        'filters': filters,
        'verifikator_options': verifikator_options,
        'aksi_options': aksi_options,
    }
    return render(request, 'laporan/laporan_audit_trail.html', context)

