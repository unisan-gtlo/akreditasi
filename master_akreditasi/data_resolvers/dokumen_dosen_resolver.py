"""Resolver dokumen dosen dari SIMDA: JABFUNG, SERDOS, SK_PENGANGKATAN, PROFIL.

Semua memakai template generik (_modal_dtps_generic.html & _dosen_generic_detail.html).
Detail record dikembalikan sebagai list dict:
    {"cells": [teks, ...], "files": [(label, kind, record_pk), ...]}
`kind` dipakai endpoint dosen_file (SIAKRED menyajikan file SIMDA dengan cek akses).

Status kelengkapan per dosen (status_dosen):
    "lengkap" -> bukti ada (dengan file bila jenis ini butuh file)
    "kurang"  -> seharusnya ada tapi belum lengkap di SIMDA
    "na"      -> tidak berlaku untuk dosen ini (mis. belum punya jabfung/serdos)
"""
from .base import BaseDataResolver, DosenSummary
from .factory import register_resolver


def _dosen(dtps):
    from master_akreditasi.models_simda_ref import DataDosenRef
    return (
        DataDosenRef.objects.select_related("jabatan_fungsional", "kode_prodi")
        .filter(nidn=dtps.dosen_nidn).first()
    )


def _tgl(d):
    return d.strftime("%d-%m-%Y") if d else "—"


class _GenericResolver(BaseDataResolver):
    modal_template = "master_akreditasi/_modal_dtps_generic.html"
    detail_template = "master_akreditasi/_dosen_generic_detail.html"
    detail_headers = []

    def status_dosen(self, sesi, dtps, mapping):  # pragma: no cover - di-override
        raise NotImplementedError


@register_resolver
class JabfungResolver(_GenericResolver):
    jenis_data = "JABFUNG"
    title_prefix = "SK Jabatan Akademik Dosen DTPS"
    agg_column_label = "Jabatan Saat Ini"
    detail_headers = ["Jabatan", "No. SK", "Tgl SK", "TMT", "Angka Kredit"]

    def _records(self, dtps):
        from master_akreditasi.models_simda_ref import RiwayatJabfungRef
        return list(
            RiwayatJabfungRef.objects.filter(dosen__nidn=dtps.dosen_nidn)
            .select_related("jabatan_fungsional").order_by("-tmt")
        )

    def get_dosen_summary(self, sesi, dtps, mapping):
        recs = self._records(dtps)
        terkini = recs[0].jabatan_fungsional.nama if recs else (dtps.dosen_jabfung_snapshot or "—")
        return DosenSummary(count=len(recs), agg_label=self.agg_column_label,
                            agg_value=terkini, agg_value_formatted=terkini)

    def get_detail_records(self, sesi, dtps, mapping):
        return [
            {
                "cells": [r.jabatan_fungsional.nama, r.no_sk or "—", _tgl(r.tgl_sk), _tgl(r.tmt),
                          r.angka_kredit if r.angka_kredit is not None else "—"],
                "files": [("SK Jabfung", "jabfung_sk", r.pk)] if r.file_sk else [],
            }
            for r in self._records(dtps)
        ]

    def status_dosen(self, sesi, dtps, mapping):
        recs = self._records(dtps)
        if not recs:
            d = _dosen(dtps)
            # Dosen tanpa jabatan akademik: SK jabfung tidak berlaku
            return "kurang" if (d and d.jabatan_fungsional_id) else "na"
        return "lengkap" if any(r.file_sk for r in recs) else "kurang"


@register_resolver
class SerdosResolver(_GenericResolver):
    jenis_data = "SERDOS"
    title_prefix = "Sertifikat Pendidik Dosen DTPS"
    agg_column_label = "ID Serdos"
    detail_headers = ["ID / No. Sertifikat Pendidik"]

    def get_dosen_summary(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        ada = bool(d and d.id_serdos)
        return DosenSummary(count=1 if ada else 0, agg_label=self.agg_column_label,
                            agg_value=d.id_serdos if ada else None,
                            agg_value_formatted=d.id_serdos if ada else "Belum serdos")

    def get_detail_records(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        if not d or not (d.id_serdos or d.file_serdos):
            return []
        return [{"cells": [d.id_serdos or "—"],
                 "files": [("Sertifikat Pendidik", "serdos", d.pk)] if d.file_serdos else []}]

    def status_dosen(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        if not d or not d.id_serdos:
            return "na"  # belum tersertifikasi: tidak berlaku
        return "lengkap" if d.file_serdos else "kurang"


@register_resolver
class SKPengangkatanResolver(_GenericResolver):
    jenis_data = "SK_PENGANGKATAN"
    title_prefix = "SK Pengangkatan Dosen Tetap DTPS"
    agg_column_label = "No. SK Pengangkatan"
    detail_headers = ["No. SK", "Tgl SK", "Mulai Kerja"]

    def get_dosen_summary(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        ada = bool(d and (d.no_sk_pengangkatan or d.file_sk_pengangkatan))
        return DosenSummary(count=1 if ada else 0, agg_label=self.agg_column_label,
                            agg_value=d.no_sk_pengangkatan if ada else None,
                            agg_value_formatted=(d.no_sk_pengangkatan or "File ada") if ada else "—")

    def get_detail_records(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        if not d or not (d.no_sk_pengangkatan or d.file_sk_pengangkatan):
            return []
        return [{"cells": [d.no_sk_pengangkatan or "—", _tgl(d.tgl_sk_pengangkatan), _tgl(d.tgl_mulai_kerja)],
                 "files": [("SK Pengangkatan", "sk_pengangkatan", d.pk)] if d.file_sk_pengangkatan else []}]

    def status_dosen(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        return "lengkap" if (d and d.file_sk_pengangkatan) else "kurang"


@register_resolver
class ProfilResolver(_GenericResolver):
    jenis_data = "PROFIL"
    title_prefix = "Profil & Homebase Dosen DTPS"
    agg_column_label = "Homebase"
    detail_headers = ["NIDN", "Homebase", "Jabatan", "Pendidikan", "SINTA", "Scopus", "Google Scholar"]

    def get_dosen_summary(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        hb = d.kode_prodi_id if d else "—"
        return DosenSummary(count=1 if d else 0, agg_label=self.agg_column_label,
                            agg_value=hb, agg_value_formatted=hb)

    def get_detail_records(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        if not d:
            return []
        return [{"cells": [d.nidn, d.kode_prodi_id or "—",
                           d.jabatan_fungsional.nama if d.jabatan_fungsional_id else "—",
                           d.pendidikan_terakhir or "—", d.id_sinta or "—", d.id_scopus or "—",
                           d.id_google_scholar or "—"],
                 "files": []}]

    def status_dosen(self, sesi, dtps, mapping):
        d = _dosen(dtps)
        return "lengkap" if (d and d.is_active) else "kurang"
