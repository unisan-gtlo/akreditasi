"""
Helper query untuk integrasi dosen SIMDA → SIAKRED.

Modul ini berisi fungsi-fungsi yang umum dipakai untuk fetch data dosen
dan riwayat dosen dari schema `master` (SIMDA), sudah termasuk logika
filter periode (TS, TS-1, TS-2, dll) dan resolusi DTPSDosenSesi.

PRINSIP:
  - Semua fungsi di sini adalah READ-ONLY ke SIMDA.
  - Caller bertanggung jawab untuk caching (kalau perlu) — file ini real-time.
  - Output umum berupa dict atau queryset, tidak pernah HTML.

CARA PAKAI dari view:
  >>> from master_akreditasi.simda_dosen import (
  ...     get_dosen_homebase_prodi,
  ...     get_dtps_aktif_sesi,
  ...     get_bkd_dosen_filter_periode,
  ... )
  >>> dosen_e11 = get_dosen_homebase_prodi('E11')
  >>> dtps = get_dtps_aktif_sesi(sesi)
  >>> bkd = get_bkd_dosen_filter_periode('0910097601', tahun_ts='2026', filter_periode='TS_TS_M1_TS_M2')
"""

from typing import Iterable

from django.db.models import Q


# ============================================================================
# 1. QUERY DOSEN
# ============================================================================

def get_dosen_homebase_prodi(kode_prodi: str, hanya_aktif: bool = True):
    """Ambil semua dosen yang homebase di prodi tertentu.

    Args:
        kode_prodi: Kode prodi (mis. 'E11', 'T31')
        hanya_aktif: Kalau True, filter is_active=True

    Returns:
        QuerySet[DataDosenRef]
    """
    from .models_simda_ref import DataDosenRef

    qs = DataDosenRef.objects.filter(kode_prodi=kode_prodi)
    if hanya_aktif:
        qs = qs.filter(is_active=True)
    return qs.select_related(
        'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
    ).order_by('nama_lengkap')


def get_dosen_by_nidn_list(nidn_list: Iterable[str]):
    """Ambil dosen berdasarkan list NIDN.

    Args:
        nidn_list: iterable NIDN string

    Returns:
        QuerySet[DataDosenRef] dengan select_related sudah dilakukan
    """
    from .models_simda_ref import DataDosenRef

    nidn_list = list(nidn_list)
    if not nidn_list:
        return DataDosenRef.objects.none()

    return DataDosenRef.objects.filter(
        nidn__in=nidn_list
    ).select_related(
        'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
    ).order_by('nama_lengkap')


def search_dosen(query: str, exclude_prodi: str | None = None, limit: int = 20):
    """Search dosen untuk autocomplete/picker UI.

    Args:
        query: kata kunci (NIDN, nama, atau bagian nama)
        exclude_prodi: kalau ada, exclude dosen homebase di prodi ini
                       (untuk filter "tampilkan dosen lintas prodi saja")
        limit: maksimal hasil yang dikembalikan

    Returns:
        QuerySet[DataDosenRef]
    """
    from .models_simda_ref import DataDosenRef

    if not query or len(query) < 2:
        return DataDosenRef.objects.none()

    qs = DataDosenRef.objects.filter(
        Q(nidn__icontains=query) |
        Q(nama_lengkap__icontains=query) |
        Q(nip__icontains=query) |
        Q(nuptk__icontains=query)
    ).filter(is_active=True)

    if exclude_prodi:
        qs = qs.exclude(kode_prodi=exclude_prodi)

    return qs.select_related(
        'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
    ).order_by('nama_lengkap')[:limit]


# ============================================================================
# 2. QUERY DTPS POOL PER SESI
# ============================================================================

def get_dtps_aktif_sesi(sesi):
    """Ambil semua dosen DTPS yang aktif untuk satu sesi (gabungan auto + manual).

    Args:
        sesi: instance SesiAkreditasi

    Returns:
        QuerySet[DTPSDosenSesi] yang aktif=True
    """
    from .models_dosen_link import DTPSDosenSesi
    return DTPSDosenSesi.objects.filter(
        sesi=sesi, aktif=True,
    ).order_by('sumber', 'dosen_nama_snapshot')


def get_dtps_nidn_list(sesi) -> list[str]:
    """Ambil list NIDN dosen DTPS aktif untuk sesi.

    Sering dipakai sebagai input untuk query DataDosenRef/RiwayatBKDRef.

    Args:
        sesi: instance SesiAkreditasi

    Returns:
        list[str]: NIDN string list
    """
    return list(
        get_dtps_aktif_sesi(sesi).values_list('dosen_nidn', flat=True)
    )


def get_dtps_full_data(sesi):
    """Ambil DTPS sesi lengkap dengan join ke data SIMDA.

    Returns list of dict dengan key:
      - dtps_id, sumber, peran, mk_diampu, alasan_inklusi, aktif
      - dosen: nidn, nama_lengkap, kode_prodi, nama_prodi, jabfung, jenis_kelamin, dst
      - snapshot_outdated (boolean)

    Useful untuk display table di UI atau export.
    """
    from .models_simda_ref import DataDosenRef

    dtps_list = list(get_dtps_aktif_sesi(sesi))
    nidn_list = [d.dosen_nidn for d in dtps_list]

    # Single query untuk semua data dosen
    dosen_map = {
        d.nidn: d for d in DataDosenRef.objects.filter(nidn__in=nidn_list).select_related(
            'kode_prodi', 'kode_fakultas', 'jabatan_fungsional',
        )
    }

    result = []
    for dtps in dtps_list:
        dosen = dosen_map.get(dtps.dosen_nidn)
        result.append({
            'dtps_id': dtps.id,
            'sumber': dtps.sumber,
            'sumber_display': dtps.get_sumber_display(),
            'peran': dtps.peran,
            'peran_display': dtps.get_peran_display(),
            'mk_diampu': dtps.mk_diampu,
            'alasan_inklusi': dtps.alasan_inklusi,
            'aktif': dtps.aktif,
            'snapshot_outdated': dtps.snapshot_outdated,
            'dosen': {
                'nidn': dtps.dosen_nidn,
                'nama_lengkap': dosen.nama_lengkap if dosen else dtps.dosen_nama_snapshot,
                'nama_dengan_gelar': dosen.nama_dengan_gelar if dosen else dtps.dosen_nama_snapshot,
                'kode_prodi': dosen.kode_prodi_id if dosen else dtps.dosen_homebase_prodi_snapshot,
                'nama_prodi': dosen.kode_prodi.nama_prodi if dosen else '',
                'kode_fakultas': dosen.kode_fakultas_id if dosen else dtps.dosen_homebase_fakultas_snapshot,
                'jabfung': dosen.jabatan_fungsional.nama if (dosen and dosen.jabatan_fungsional) else dtps.dosen_jabfung_snapshot,
                'pendidikan_terakhir': dosen.pendidikan_terakhir if dosen else '',
                'is_active': dosen.is_active if dosen else False,
                'data_simda_exists': dosen is not None,
            },
        })
    return result


# ============================================================================
# 3. QUERY RIWAYAT BKD DENGAN FILTER PERIODE
# ============================================================================

def _generate_periode_codes_from_ts(tahun_ts: str, filter_periode: str) -> list[str]:
    """Generate list kode periode dari tahun TS.

    Format kode periode di SIMDA: '20251' (Ganjil 2025/2026), '20252' (Genap 2025/2026)
    Asumsi: tahun_ts berupa string '2025' (artinya TS=2025/2026)

    Returns:
        list[str]: list kode tahun_akademik untuk query
    """
    try:
        ts = int(tahun_ts)
    except (TypeError, ValueError):
        return []

    def codes_for_year(year: int) -> list[str]:
        # Pattern: '{year}1' (Ganjil), '{year}2' (Genap)
        return [f"{year}1", f"{year}2"]

    if filter_periode == 'TS_ONLY':
        return codes_for_year(ts)
    elif filter_periode == 'TS_TS_M1':
        return codes_for_year(ts) + codes_for_year(ts - 1)
    elif filter_periode == 'TS_TS_M1_TS_M2':
        return codes_for_year(ts) + codes_for_year(ts - 1) + codes_for_year(ts - 2)
    elif filter_periode == 'TS_TS_M3':
        return (codes_for_year(ts) + codes_for_year(ts - 1)
                + codes_for_year(ts - 2) + codes_for_year(ts - 3))
    elif filter_periode in ('SEMUA', 'AKTIF_SAJA'):
        return []  # caller handle: empty list = no filter
    else:
        return []


def get_bkd_dosen_filter_periode(
    nidn: str,
    tahun_ts: str,
    filter_periode: str = 'TS_TS_M1_TS_M2',
):
    """Ambil riwayat BKD seorang dosen dengan filter periode.

    Args:
        nidn: NIDN dosen
        tahun_ts: tahun TS sebagai string ('2025', '2026', dst)
        filter_periode: salah satu FILTER_PERIODE_CHOICES

    Returns:
        QuerySet[RiwayatBKDRef] terurut dari periode terbaru
    """
    from .models_simda_ref import RiwayatBKDRef

    qs = RiwayatBKDRef.objects.filter(dosen__nidn=nidn).select_related(
        'dosen', 'periode',
    )

    periode_codes = _generate_periode_codes_from_ts(tahun_ts, filter_periode)

    if filter_periode == 'AKTIF_SAJA':
        qs = qs.filter(periode__is_aktif=True)
    elif periode_codes:
        qs = qs.filter(periode__tahun_akademik__in=periode_codes)
    # else SEMUA → tanpa filter

    return qs.order_by('-periode__urutan')


def get_bkd_dtps_sesi(sesi, filter_periode: str = 'TS_TS_M1_TS_M2'):
    """Ambil semua riwayat BKD untuk DTPS sesi tertentu.

    Args:
        sesi: instance SesiAkreditasi
        filter_periode: salah satu FILTER_PERIODE_CHOICES

    Returns:
        QuerySet[RiwayatBKDRef] untuk semua DTPS aktif di sesi
    """
    from .models_simda_ref import RiwayatBKDRef

    nidn_list = get_dtps_nidn_list(sesi)
    if not nidn_list:
        return RiwayatBKDRef.objects.none()

    qs = RiwayatBKDRef.objects.filter(dosen__nidn__in=nidn_list).select_related(
        'dosen', 'periode',
    )

    periode_codes = _generate_periode_codes_from_ts(sesi.tahun_ts, filter_periode)

    if filter_periode == 'AKTIF_SAJA':
        qs = qs.filter(periode__is_aktif=True)
    elif periode_codes:
        qs = qs.filter(periode__tahun_akademik__in=periode_codes)

    return qs.order_by('dosen__nama_lengkap', '-periode__urutan')


# ============================================================================
# 4. AUTO-POPULATE & SNAPSHOT HELPERS
# ============================================================================

def auto_populate_dtps_homebase(sesi, user=None) -> int:
    """Auto-populate DTPS pool sesi dengan dosen homebase prodi.

    Idempotent — bisa dipanggil ulang tanpa duplikasi (pakai
    update_or_create dengan unique_together (sesi, dosen_nidn)).

    Args:
        sesi: instance SesiAkreditasi
        user: User yang trigger (untuk audit; bisa None untuk signal)

    Returns:
        int: jumlah record DTPS yang dibuat (created, bukan total)
    """
    from .models_dosen_link import DTPSDosenSesi

    dosen_qs = get_dosen_homebase_prodi(sesi.kode_prodi, hanya_aktif=True)

    created_count = 0
    for dosen in dosen_qs:
        _, created = DTPSDosenSesi.objects.update_or_create(
            sesi=sesi,
            dosen_nidn=dosen.nidn,
            defaults={
                'sumber': 'AUTO_HOMEBASE',
                'peran': 'DTPS_HOMEBASE',
                'aktif': True,
                'dosen_nama_snapshot': dosen.nama_lengkap,
                'dosen_homebase_prodi_snapshot': dosen.kode_prodi_id,
                'dosen_homebase_fakultas_snapshot': dosen.kode_fakultas_id,
                'dosen_jabfung_snapshot': (
                    dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else ''
                ),
                'snapshot_outdated': False,
                'dibuat_oleh': user,
            },
        )
        if created:
            created_count += 1
    return created_count


def serialize_dosen_for_snapshot(dosen) -> dict:
    """Serialize DataDosenRef ke dict untuk disimpan di SnapshotDataSimda.data_json."""
    return {
        'nidn': dosen.nidn,
        'nip': dosen.nip,
        'nuptk': dosen.nuptk,
        'nama_lengkap': dosen.nama_lengkap,
        'gelar_depan': dosen.gelar_depan,
        'gelar_belakang': dosen.gelar_belakang,
        'jenis_kelamin': dosen.jenis_kelamin,
        'pendidikan_terakhir': dosen.pendidikan_terakhir,
        'kode_prodi': dosen.kode_prodi_id,
        'kode_fakultas': dosen.kode_fakultas_id,
        'jabfung': dosen.jabatan_fungsional.nama if dosen.jabatan_fungsional else '',
        'id_sinta': dosen.id_sinta,
        'id_scopus': dosen.id_scopus,
        'orcid': dosen.orcid,
        'h_index_sinta': dosen.h_index_sinta,
        'h_index_scopus': dosen.h_index_scopus,
        'is_active': dosen.is_active,
    }


def serialize_bkd_for_snapshot(bkd) -> dict:
    """Serialize RiwayatBKDRef ke dict untuk disimpan di SnapshotDataSimda.data_json."""
    return {
        'bkd_id': bkd.id,
        'dosen_nidn': bkd.dosen.nidn,
        'dosen_nama': bkd.dosen.nama_lengkap,
        'periode_kode': bkd.periode.tahun_akademik,
        'periode_label': bkd.periode.label_lengkap,
        'sks_pengajaran': str(bkd.sks_pengajaran) if bkd.sks_pengajaran else None,
        'sks_penelitian': str(bkd.sks_penelitian) if bkd.sks_penelitian else None,
        'sks_pkm': str(bkd.sks_pkm) if bkd.sks_pkm else None,
        'sks_penunjang': str(bkd.sks_penunjang) if bkd.sks_penunjang else None,
        'total_sks': str(bkd.total_sks),
        'file_bkd': bkd.file_bkd or '',
        'link_bkd': bkd.link_bkd or '',
        'status_pengesahan': bkd.status_pengesahan,
        'tgl_upload': bkd.tgl_upload.isoformat() if bkd.tgl_upload else None,
    }
