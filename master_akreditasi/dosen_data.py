"""
Data dosen SIMDA untuk butir akreditasi: file dosen & kelengkapan per sesi.

File dosen (ijazah, SK jabfung, serdos, SK pengangkatan, BKD) tersimpan di media
SIMDA (SIMDA_MEDIA_ROOT, server yang sama). SIAKRED menyajikannya lewat endpoint
ber-cek-akses (bukan tautan langsung ke media SIMDA), dan memasukkannya ke Export ZIP.

Kelengkapan: butir yang punya ButirDataDosenMapping aktif dihitung TERISI kalau
semua dosen DTPS aktif yang "wajib" (status != 'na') berstatus 'lengkap'.
"""
import hashlib
import os

from django.conf import settings
from django.core.cache import cache

# kind -> (path model, field file, cara ambil NIDN dari record)
FILE_KINDS = {
    "ijazah": ("RiwayatPendidikanDosenRef", "file_ijazah", "dosen__nidn"),
    "transkrip": ("RiwayatPendidikanDosenRef", "file_transkrip", "dosen__nidn"),
    "jabfung_sk": ("RiwayatJabfungRef", "file_sk", "dosen__nidn"),
    "bkd": ("RiwayatBKDRef", "file_bkd", "dosen__nidn"),
    "serdos": ("DataDosenRef", "file_serdos", "nidn"),
    "sk_pengangkatan": ("DataDosenRef", "file_sk_pengangkatan", "nidn"),
}

# Jenis data mapping -> kind file yang boleh disajikan untuk butir tsb
JENIS_KINDS = {
    "PENDIDIKAN": {"ijazah", "transkrip"},
    "BKD": {"bkd"},
    "JABFUNG": {"jabfung_sk"},
    "SERDOS": {"serdos"},
    "SK_PENGANGKATAN": {"sk_pengangkatan"},
    "PROFIL": set(),
    "ID_AKADEMIK": set(),
}

KELENGKAPAN_TTL = 60 * 10


def media_root():
    return getattr(settings, "SIMDA_MEDIA_ROOT", "/var/www/simda/media")


def resolve_file(kind, pk):
    """Return (nidn, path absolut) file SIMDA, atau (None, None) kalau tidak ada / tidak aman."""
    from master_akreditasi import models_simda_ref

    spec = FILE_KINDS.get(kind)
    if not spec:
        return None, None
    model_name, field, nidn_lookup = spec
    model = getattr(models_simda_ref, model_name)
    row = model.objects.filter(pk=pk).values(field, nidn_lookup).first()
    if not row or not row[field]:
        return None, None
    root = os.path.realpath(media_root())
    path = os.path.realpath(os.path.join(root, row[field]))
    # Cegah path traversal: file wajib berada di dalam media SIMDA
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        return row[nidn_lookup], None
    return row[nidn_lookup], path


# =========================================================
# KELENGKAPAN PER SESI
# =========================================================

def _mappings_for(butir_ids):
    from master_akreditasi.models_dosen_link import ButirDataDosenMapping
    return {
        m.butir_id: m
        for m in ButirDataDosenMapping.objects.filter(butir_id__in=butir_ids, aktif=True)
    }


def kelengkapan_sesi(sesi, butir_ids):
    """{butir_id: {jenis, lengkap, wajib, kurang:[nama], terisi}} untuk butir ber-mapping aktif.

    Di-cache 10 menit per (sesi, DTPS, mapping) -- data SIMDA tidak punya sinyal
    perubahan, jadi TTL yang menentukan seberapa cepat perubahan SIMDA terlihat.
    """
    from master_akreditasi.data_resolvers import UnsupportedJenisDataError, get_resolver
    from master_akreditasi.models_dosen_link import DTPSDosenSesi

    mappings = _mappings_for(butir_ids)
    if not mappings:
        return {}
    dtps_list = list(DTPSDosenSesi.objects.filter(sesi=sesi, aktif=True).order_by("dosen_nama_snapshot"))
    sig = hashlib.sha1(repr((
        sorted(d.dosen_nidn for d in dtps_list),
        sorted((m.butir_id, m.jenis_data, m.filter_periode) for m in mappings.values()),
        str(sesi.tahun_ts),
    )).encode()).hexdigest()[:16]
    key = f"simda_kelengkapan:{sesi.pk}:{sig}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    hasil = {}
    for butir_id, mapping in mappings.items():
        try:
            resolver = get_resolver(mapping.jenis_data)
        except UnsupportedJenisDataError:
            continue
        lengkap, wajib, kurang = 0, 0, []
        for dtps in dtps_list:
            try:
                status = resolver.status_dosen(sesi, dtps, mapping)
            except Exception:
                status = "kurang"
            if status == "na":
                continue
            wajib += 1
            if status == "lengkap":
                lengkap += 1
            else:
                kurang.append(dtps.dosen_nama_snapshot or dtps.dosen_nidn)
        hasil[butir_id] = {
            "jenis": mapping.get_jenis_data_display(),
            "lengkap": lengkap,
            "wajib": wajib,
            "kurang": kurang,
            "terisi": wajib > 0 and lengkap == wajib,
        }
    cache.set(key, hasil, KELENGKAPAN_TTL)
    return hasil


def butir_terisi_simda(sesi, butir_ids):
    return {bid for bid, info in kelengkapan_sesi(sesi, butir_ids).items() if info["terisi"]}


# =========================================================
# EXPORT ZIP
# =========================================================

def zip_data_dosen(sesi, butir):
    """Isi folder DATA_SIMDA untuk 1 butir ber-mapping.

    Return (jenis_data, csv_text, files) dengan files = [(nama_relatif, path_absolut, label, nidn)],
    atau None kalau butir tidak punya mapping aktif / resolver.
    """
    import csv
    import io
    import re

    from master_akreditasi.data_resolvers import UnsupportedJenisDataError, get_resolver
    from master_akreditasi.models_dosen_link import ButirDataDosenMapping, DTPSDosenSesi

    mapping = ButirDataDosenMapping.objects.filter(butir=butir, aktif=True).first()
    if mapping is None:
        return None
    try:
        resolver = get_resolver(mapping.jenis_data)
    except UnsupportedJenisDataError:
        return None

    def aman(teks, n=50):
        return re.sub(r"[^A-Za-z0-9._-]+", "_", str(teks or "")).strip("_")[:n] or "x"

    buf = io.StringIO()
    w = csv.writer(buf)
    # Resolver boleh menambah kolom CSV (mis. URL profil akademik) lewat csv_extra()
    csv_extra = getattr(resolver, "csv_extra", None)
    dtps_list = list(DTPSDosenSesi.objects.filter(sesi=sesi, aktif=True).order_by("dosen_nama_snapshot"))
    extra_cols = list(csv_extra(sesi, dtps_list[0], mapping)) if (csv_extra and dtps_list) else []
    w.writerow(["No", "NIDN", "Nama", "Homebase", "Jabfung", "Status Bukti",
                resolver.agg_column_label, "Jumlah File"] + extra_cols)
    label_status = {"lengkap": "Lengkap", "kurang": "Belum lengkap", "na": "Tidak berlaku"}
    files = []
    for no, dtps in enumerate(dtps_list, start=1):
        summary = resolver.get_dosen_summary(sesi, dtps, mapping)
        status = resolver.status_dosen(sesi, dtps, mapping)
        dosen_files = []
        for label, kind, pk in resolver.files_for_dosen(sesi, dtps, mapping):
            _nidn, path = resolve_file(kind, pk)
            if path:
                ext = os.path.splitext(path)[1]
                folder = f"{aman(dtps.dosen_nidn, 20)}_{aman(dtps.dosen_nama_snapshot, 40)}"
                dosen_files.append((f"{folder}/{aman(label, 40)}{ext}", path, label, dtps.dosen_nidn))
        files.extend(dosen_files)
        extra = csv_extra(sesi, dtps, mapping) if extra_cols else {}
        w.writerow([no, dtps.dosen_nidn, dtps.dosen_nama_snapshot, dtps.dosen_homebase_prodi_snapshot,
                    dtps.dosen_jabfung_snapshot, label_status.get(status, status),
                    summary.agg_value_formatted, len(dosen_files)] + [extra.get(c, "") for c in extra_cols])
    return mapping.jenis_data, buf.getvalue(), files
