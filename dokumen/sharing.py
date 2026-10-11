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

5. Tautan Pustaka (DokumenTautanButir): dokumen yang ditautkan ke butir dihitung seperti
   dokumen yang diunggah ke butir itu, bila (a) dokumennya lolos aturan scope & tahun
   sesi, dan (b) cakupan tautan cocok dengan prodi/fakultas sesi (kosong = semua prodi).
   Dokumen tautan ditandai `dok.dari_pustaka = True`.
"""
import copy

from django.db.models import Q

from master_akreditasi.models import ButirDokumen

from .models import Dokumen, DokumenTautanButir


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


def tahun_diterima(periode):
    """Nilai tahun_akademik yang dianggap masuk periode sesi.

    Selain format baku '2024/2025', diterima juga '2024-2025' dan tahun tunggal
    ('2025') yang berada di rentang periode (data lama yang diisi bebas).
    """
    nilai = set(periode)
    for p in periode:
        nilai.add(p.replace("/", "-"))
        nilai.update(bagian.strip() for bagian in p.split("/") if bagian.strip())
    return nilai


def sesi_tahun_q(sesi):
    periode = sesi.tahun_periode_list
    q = Q(tahun_akademik="") | Q(tahun_akademik__in=tahun_diterima(periode))
    for p in periode:  # mis. '2024/2025 Ganjil'
        q |= Q(tahun_akademik__startswith=p + " ")
    return q


def sesi_dokumen_qs(sesi, butir_ids):
    """Dokumen FINAL yang berlaku untuk sesi, pada butir_ids (sudah termasuk anggota grup)."""
    return (
        Dokumen.objects.filter(butir_dokumen_id__in=butir_ids, status="FINAL")
        .filter(sesi_tahun_q(sesi))
        .filter(scope_q(sesi.kode_prodi, sesi.kode_fakultas))
    )


def tautan_sesi(sesi, butir_ids):
    """[(butir_id, dokumen_id)] tautan Pustaka yang berlaku untuk sesi pada butir_ids."""
    dok_berlaku = (
        Dokumen.objects.filter(status="FINAL")
        .filter(sesi_tahun_q(sesi))
        .filter(scope_q(sesi.kode_prodi, sesi.kode_fakultas))
    )
    return list(
        DokumenTautanButir.objects.filter(butir_id__in=butir_ids, dokumen__in=dok_berlaku)
        .filter(scope_q(sesi.kode_prodi, sesi.kode_fakultas))
        .order_by()
        .values_list("butir_id", "dokumen_id")
        .distinct()
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

    # Tautan Pustaka -> butir
    tautan = tautan_sesi(sesi, all_ids(groups))
    tautan_by_butir = {}
    dok_tautan = {}
    if tautan:
        for bid, dok_id in tautan:
            tautan_by_butir.setdefault(bid, []).append(dok_id)
        dok_tautan = {
            d.pk: d for d in Dokumen.objects.filter(pk__in={dk for _, dk in tautan}).select_related("butir_dokumen")
        }

    result = {}
    for bid, ids in groups.items():
        if len(ids) == 1:
            result[bid] = by_butir.get(bid, [])
        else:
            result[bid] = [d for d in docs if d.butir_dokumen_id in ids]
        for d in result[bid]:
            d.dari_butir_lain = d.butir_dokumen_id != bid
        if tautan_by_butir:
            sudah = {d.pk for d in result[bid]}
            tambahan = []
            for gid in ids:
                for dok_id in tautan_by_butir.get(gid, []):
                    if dok_id in sudah or dok_id not in dok_tautan:
                        continue
                    salinan = copy.copy(dok_tautan[dok_id])  # objek terpisah per butir
                    salinan.dari_butir_lain = True
                    salinan.dari_pustaka = True
                    tambahan.append(salinan)
                    sudah.add(dok_id)
            if tambahan:
                result[bid] = list(result[bid]) + tambahan
    return result


def butir_terisi_for_sesi(sesi, butirs):
    """Set butir_id yang sudah punya minimal 1 dokumen (termasuk dokumen bersama)."""
    groups = butir_groups(butirs)
    punya_dokumen = set(
        sesi_dokumen_qs(sesi, all_ids(groups)).values_list("butir_dokumen_id", flat=True).distinct()
    )
    punya_dokumen |= {bid for bid, _ in tautan_sesi(sesi, all_ids(groups))}
    terisi = {bid for bid, ids in groups.items() if ids & punya_dokumen}
    # Butir ber-mapping data dosen SIMDA yang buktinya lengkap untuk semua DTPS
    from master_akreditasi.dosen_data import butir_terisi_simda
    return terisi | butir_terisi_simda(sesi, list(groups))


def dokumen_rows(butir_ids):
    """{butir_id: [(dokumen_id, scope_prodi, scope_fakultas), ...]} untuk dokumen FINAL,
    termasuk tautan Pustaka (scope efektif = cakupan tautan bila diisi, selain itu scope dokumen)."""
    rows = {}
    for pk, bid, sp, sf in Dokumen.objects.filter(
        butir_dokumen_id__in=butir_ids, status="FINAL"
    ).values_list("pk", "butir_dokumen_id", "scope_kode_prodi", "scope_kode_fakultas"):
        rows.setdefault(bid, []).append((pk, sp or "", sf or ""))
    for bid, pk, lp, lf, dp, df in DokumenTautanButir.objects.filter(
        butir_id__in=butir_ids, dokumen__status="FINAL"
    ).values_list("butir_id", "dokumen_id", "scope_kode_prodi", "scope_kode_fakultas",
                  "dokumen__scope_kode_prodi", "dokumen__scope_kode_fakultas"):
        sp, sf = (lp, lf) if (lp or lf) else (dp, df)
        rows.setdefault(bid, []).append((pk, sp or "", sf or ""))
    return rows
