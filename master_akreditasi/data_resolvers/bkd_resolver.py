"""BKD Resolver — wrap logic existing untuk Beban Kerja Dosen.

Logic ini sebelumnya hard-coded di views_dtps_modal.py. Di-port ke resolver
class agar konsisten dengan jenis_data lain.

Source data: master.riwayat_bkd
Aggregate: Total SKS (pengajaran + penelitian + pkm + penunjang)
Dokumen: link_bkd (Google Drive URL) + file_bkd (path info)
"""
from django.db.models import Sum

from .base import BaseDataResolver, DosenSummary
from .factory import register_resolver


@register_resolver
class BKDResolver(BaseDataResolver):
    """Resolver untuk jenis_data='BKD' (Beban Kerja Dosen)."""

    jenis_data = 'BKD'
    title_prefix = 'Data Dosen DTPS'
    agg_column_label = 'Total SKS'

    modal_template = 'master_akreditasi/_modal_dtps_bkd.html'
    detail_template = 'master_akreditasi/_dosen_bkd_detail.html'

    def get_dosen_summary(self, sesi, dtps, mapping):
        """Hitung total SKS BKD untuk 1 dosen sesuai filter periode mapping."""
        # Lazy import untuk hindari circular dependency
        from master_akreditasi import simda_dosen as sd

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
                'total_pkm', 'total_penunjang',
            )
        )
        return DosenSummary(
            count=bkd_count,
            agg_label=self.agg_column_label,
            agg_value=total_sks,
            agg_value_formatted=f"{total_sks:.2f}" if total_sks else "—",
            extra={
                'bkd_agg': bkd_agg,
                'total_sks': total_sks,  # untuk backward compat dengan template existing
                'bkd_count': bkd_count,  # idem
            },
        )

    def get_detail_records(self, sesi, dtps, mapping):
        """Fetch BKD records untuk drill-down expand row."""
        from master_akreditasi import simda_dosen as sd

        return (
            sd.get_bkd_dosen_filter_periode(
                nidn=dtps.dosen_nidn,
                tahun_ts=str(sesi.tahun_ts),
                filter_periode=mapping.filter_periode,
            )
            .select_related('periode')
            .order_by('-periode__urutan')
        )