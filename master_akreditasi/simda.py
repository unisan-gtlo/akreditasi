"""Helper untuk cross-schema query ke SIMDA (master.program_studi + master.fakultas).

SIMDA dan SIAKRED berada di database yang sama (unisan_db) dengan schema berbeda.
SIAKRED akses read-only ke schema master.
"""
from django.db import connection


def get_prodi_dari_simda(only_aktif=True):
    """Ambil daftar prodi dari master.program_studi + join fakultas."""
    sql = """
        SELECT 
            p.kode_prodi,
            p.nama_prodi,
            p.jenjang,
            p.kode_fakultas,
            COALESCE(f.nama_fakultas, p.kode_fakultas) AS nama_fakultas,
            COALESCE(f.nama_singkat, p.kode_fakultas) AS nama_singkat_fakultas,
            p.akreditasi,
            p.status,
            p.urutan
        FROM master.program_studi p
        LEFT JOIN master.fakultas f ON f.kode_fakultas = p.kode_fakultas
    """
    if only_aktif:
        sql += " WHERE LOWER(p.status) = 'aktif'"
    sql += " ORDER BY f.urutan NULLS LAST, p.kode_fakultas, p.urutan, p.kode_prodi"
    
    with connection.cursor() as cursor:
        cursor.execute(sql)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def get_fakultas_dari_simda(only_aktif=True):
    """Ambil daftar fakultas dari master.fakultas."""
    sql = """
        SELECT kode_fakultas, nama_fakultas, nama_singkat, urutan, status
        FROM master.fakultas
    """
    if only_aktif:
        sql += " WHERE LOWER(status) = 'aktif'"
    sql += " ORDER BY urutan NULLS LAST, kode_fakultas"
    
    with connection.cursor() as cursor:
        cursor.execute(sql)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def get_prodi_grouped_by_fakultas():
    """Prodi grouped by fakultas, untuk dropdown optgroup."""
    prodi_list = get_prodi_dari_simda(only_aktif=True)
    grouped = {}
    for p in prodi_list:
        kode_fak = p['kode_fakultas']
        if kode_fak not in grouped:
            grouped[kode_fak] = {
                'kode_fakultas': kode_fak,
                'nama_fakultas': p['nama_fakultas'],
                'prodi_list': [],
            }
        grouped[kode_fak]['prodi_list'].append(p)
    return list(grouped.values())


def get_prodi_detail_from_simda(kode_prodi):
    """Ambil detail lengkap 1 prodi dari SIMDA, join dengan fakultas.
    
    Returns dict atau None kalau tidak ditemukan.
    """
    sql = """
        SELECT 
            p.kode_prodi,
            p.kode_prodi_dikti,
            p.nama_prodi,
            p.jenjang,
            p.akreditasi,
            p.no_sk_akreditasi,
            p.tgl_sk_akreditasi,
            p.berlaku_sampai_akreditasi,
            p.no_sk_pendirian,
            p.total_sks_lulus,
            p.lama_studi_normal,
            p.lama_studi_maks,
            p.email_prodi,
            p.status,
            p.kode_fakultas,
            COALESCE(f.nama_fakultas, p.kode_fakultas) AS nama_fakultas,
            COALESCE(f.nama_singkat, p.kode_fakultas) AS nama_singkat_fakultas,
            p.visi,
            p.misi,
            p.tujuan,
            p.profil_lulusan
        FROM master.program_studi p
        LEFT JOIN master.fakultas f ON f.kode_fakultas = p.kode_fakultas
        WHERE UPPER(p.kode_prodi) = UPPER(%s)
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [kode_prodi])
        row = cursor.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))


def get_institusi_from_simda():
    """Ambil data institusi (UNISAN) dari SIMDA master.institusi."""
    sql = """
        SELECT kode, nama_resmi, nama_singkat, npsn, alamat, kabupaten, provinsi,
               kode_pos, telepon, email, website, akreditasi, no_sk_akreditasi,
               tgl_sk_akreditasi, berlaku_sampai, tgl_berdiri, logo,
               visi, misi, tujuan, sasaran_strategis
        FROM master.institusi
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))

