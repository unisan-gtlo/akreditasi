"""
Dokumen bersama + aturan scope dokumen untuk sesi/laporan (satu sumber kebenaran).

1. Dokumen bersama
   Butir dengan `kode_bersama` sama (lintas instrumen / lintas standar) adalah
   satu "grup". Dokumen yang diunggah ke salah satu butir grup dihitung untuk
   semua butir di grup tersebut -> dokumen Universitas/Lembaga cukup diunggah sekali.

2. Scope dokumen untuk satu prodi
   Dokumen dihitung untuk prodi P (fakultas F) kalau:
     - scope prodi = P                          (dokumen PRODI milik P)
     - scope prodi kosong & scope fakultas = F  (dokumen FAKULTAS/UPPS milik F)
     - scope prodi & fakultas kosong            (dokumen UNIVERSITAS/BIRO)
   Dokumen PRODI milik prodi lain di fakultas yang sama TIDAK ikut.

3. Tahun (khusus sesi): tahun_akademik dalam periode evaluasi sesi, atau kosong
   (dokumen yang berlaku umum).

4. Data dosen SIMDA: butir ber-ButirDataDosenMapping juga terhitung terisi kalau
   bukti semua DTPS lengkap (master_akreditasi/dosen_data.py).
"""
from django.db.models import Q

from master_akreditasi.models import ButirDokumen

from .models import Dokumen


# =========================================================
# GRUP KODE BERSAMA
# =========================================================

def butir_groups(butirs):
    """Return {butir_id: set(butir_id satu grup, termasuk dirinya)}.

    `butirs`: iterable objek ButirDokumen (cukup field id & kode_bersama).
    """
    butirs = list(butirs)
    kodes = {b.kode_bersama for b in butirs if b.kode_bersama}
    members = {}
    if kodes:
        for bid, kode in ButirDokumen.objects.filter(kode_bersama__in=kodes).values_list("id", "kode_bersama"):
            members.setdefault(kode, set()).add(bid)
    return {
        b.id: (members.get(b.kode_bersama, set()) | {b.id}) if b.kode_bersama else {b.id}
        for b in butirs
    }


def all_ids(groups):
    ids = set()
    for g in groups.values():
        ids |= g
    return ids


# =========================================================
# SCOPE & TAHUN
# =========================================================

def scope_q(kode_prodi, kode_fakultas):
    """Filter Dokumen yang berlaku untuk satu prodi (lihat aturan di docstring modul)."""
    q = Q(scope_kode_prodi="", scope_kode_fakultas="")
    if kode_prodi:
        q |= Q(scope_kode_prodi=kode_prodi)
    if kode_fakultas:
        q |= Q(scope_kode_prodi="", scope_kode_fakultas=kode_fakultas)
    return q


def scope_match(row_prodi, row_fakultas, kode_prodi, kode_fakultas):
    """Versi Python dari scope_q untuk baris hasil values_list."""
    row_prodi = row_prodi or ""
    row_fakultas = row_fakultas or ""
    if not row_prodi and not row_fakultas:
        return True
    if kode_prodi and row_prodi == kode_prodi:
        return True
    return bool(kode_fakultas) and not row_prodi and row_fakultas == kode_fakultas


def sesi_tahun_q(sesi):
    return Q(tahun_akademik__in=sesi.tahun_periode_list) | Q(tahun_akademik="")


def sesi_dokumen_qs(sesi, butir_ids):
    """Dokumen FINAL yang berlaku untuk sesi, pada butir_ids (sudah termasuk anggota grup)."""
    return (
        Dokumen.objects.filter(butir_dokumen_id__in=butir_ids, status="FINAL")
        .filter(sesi_tahun_q(sesi))
        .filter(scope_q(sesi.kode_prodi, sesi.kode_fakultas))
    )


# =========================================================
# API UNTUK VIEW
# =========================================================

def dokumen_per_butir_for_sesi(sesi, butirs, order_by=("tahun_akademik", "-tanggal_dibuat")):
    """Return {butir_id: [Dokumen, ...]} termasuk dokumen bersama dari butir lain di grupnya.

    Dokumen yang berasal dari butir lain bisa dikenali lewat
    `dok.butir_dokumen_id != butir.id` (dan atribut `dok.dari_butir_lain`).
    """
    groups = butir_groups(butirs)
    docs = list(
        sesi_dokumen_qs(sesi, all_ids(groups))
        .select_related("butir_dokumen")
        .distinct()
        .order_by(*order_by)
    )
    by_butir = {}
    for d in docs:
        by_butir.setdefault(d.butir_dokumen_id, []).append(d)

    result = {}
    for bid, ids in groups.items():
        if len(ids) == 1:
            result[bid] = by_butir.get(bid, [])
        else:
            result[bid] = [d for d in docs if d.butir_dokumen_id in ids]
        for d in result[bid]:
            d.dari_butir_lain = d.butir_dokumen_id != bid
    return result


def butir_terisi_for_sesi(sesi, butirs):
    """Set butir_id yang sudah punya minimal 1 dokumen (termasuk dokumen bersama)."""
    groups = butir_groups(butirs)
    punya_dokumen = set(
        sesi_dokumen_qs(sesi, all_ids(groups)).values_list("butir_dokumen_id", flat=True).distinct()
    )
    terisi = {bid for bid, ids in groups.items() if ids & punya_dokumen}
    # Butir ber-mapping data dosen SIMDA yang buktinya lengkap untuk semua DTPS
    from master_akreditasi.dosen_data import butir_terisi_simda
    return terisi | butir_terisi_simda(sesi, list(groups))


def dokumen_rows(butir_ids):
    """{butir_id: [(dokumen_id, scope_prodi, scope_fakultas), ...]} untuk dokumen FINAL."""
    rows = {}
    for pk, bid, sp, sf in Dokumen.objects.filter(
        butir_dokumen_id__in=butir_ids, status="FINAL"
    ).values_list("pk", "butir_dokumen_id", "scope_kode_prodi", "scope_kode_fakultas"):
        rows.setdefault(bid, []).append((pk, sp or "", sf or ""))
    return rows
