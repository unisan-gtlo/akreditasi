"""Pendidikan Resolver — Riwayat Pendidikan / Ijazah dosen.

Source data: master.riwayat_pendidikan_dosen
Aggregate: Jenjang tertinggi (S1 → S2 → S3, ambil yang paling tinggi)
Dokumen: file_ijazah, file_transkrip (path file di SIMDA storage)
        Diakses lewat https://master.unisan-g.id/media/<path>
"""
from .base import BaseDataResolver, DosenSummary
from .factory import register_resolver


# Mapping jenjang ke level numerik untuk urutan
# Higher = lebih tinggi
JENJANG_LEVEL = {
    'D3': 1, 'D4': 2,
    'S1': 3,
    'PROFESI': 4, 'SP1': 4,
    'S2': 5, 'SP2': 5,
    'S3': 6,
}

JENJANG_LABEL = {
    'D3': 'Diploma 3',
    'D4': 'Diploma 4',
    'S1': 'Sarjana (S1)',
    'PROFESI': 'Profesi',
    'SP1': 'Spesialis 1',
    'S2': 'Magister (S2)',
    'SP2': 'Spesialis 2',
    'S3': 'Doktor (S3)',
}


@register_resolver
class PendidikanResolver(BaseDataResolver):
    """Resolver untuk jenis_data='PENDIDIKAN' (Riwayat Pendidikan / Ijazah)."""

    jenis_data = 'PENDIDIKAN'
    title_prefix = 'Riwayat Pendidikan Dosen DTPS'
    agg_column_label = 'Jenjang Tertinggi'

    modal_template = 'master_akreditasi/_modal_dtps_pendidikan.html'
    detail_template = 'master_akreditasi/_dosen_pendidikan_detail.html'

    def _get_records_qs(self, dtps):
        """Helper internal: ambil QuerySet pendidikan untuk 1 dosen.

        Filter periode TIDAK dipakai untuk PENDIDIKAN karena pendidikan
        adalah data lifetime, bukan temporal. Mapping filter_periode='SEMUA'
        adalah konvensi yang benar.

        Note: model unmanaged tidak punya FK Django ke perguruan_tinggi,
        hanya kolom raw pt_asal_id. Untuk display nama PT, butuh manual
        join atau template-side resolution.
        """
        from master_akreditasi.models_simda_ref import RiwayatPendidikanDosenRef

        return (
            RiwayatPendidikanDosenRef.objects
            .filter(dosen__nidn=dtps.dosen_nidn)
            .select_related('dosen')
            .order_by('tahun_lulus')
        )

    def get_dosen_summary(self, sesi, dtps, mapping):
        """Compute jenjang tertinggi + count untuk 1 dosen."""
        records = list(self._get_records_qs(dtps))
        count = len(records)

        if not records:
            return DosenSummary(
                count=0,
                agg_label=self.agg_column_label,
                agg_value=None,
                agg_value_formatted="—",
                extra={'jenjang_tertinggi': None},
            )

        # Cari jenjang tertinggi
        jenjang_tertinggi = max(
            records,
            key=lambda r: JENJANG_LEVEL.get(r.jenjang, 0),
        )
        jenjang_code = jenjang_tertinggi.jenjang
        jenjang_label = JENJANG_LABEL.get(jenjang_code, jenjang_code)

        return DosenSummary(
            count=count,
            agg_label=self.agg_column_label,
            agg_value=jenjang_code,
            agg_value_formatted=jenjang_code,
            extra={
                'jenjang_tertinggi': jenjang_tertinggi,
                'jenjang_label': jenjang_label,
                'records': records,  # cache untuk hindari double-query di detail
            },
        )

    def get_detail_records(self, sesi, dtps, mapping):
        """Fetch semua riwayat pendidikan dosen, diurutkan dari S1 ke atas."""
        return self._get_records_qs(dtps)