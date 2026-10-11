"""
Tautan dokumen Pustaka -> butir (DokumenTautanButir): aturan cakupan & hak akses.
Penghitungan di sesi/bundle/laporan ada di dokumen/sharing.py.

Cakupan (nilai form):
  ""            semua prodi        (butir Universitas/Biro, atau pilihan superadmin)
  "P:<prodi>"   hanya prodi itu    (butir Prodi)
  "F:<fak>"     hanya fakultas itu (butir Fakultas/UPPS)
"""
from django.db.models import Q

from .permissions import can_edit_dokumen, get_user_scopes, is_superadmin

BAGIAN_PUSTAKA = ("UNIVERSITAS", "BIRO", "FAKULTAS")


def opsi_cakupan(user, butir):
    """[(nilai, label)] cakupan yang boleh dipilih user untuk menautkan ke butir ini."""
    kat = butir.kategori_kepemilikan
    if kat in ("UNIVERSITAS", "BIRO"):
        return [("", "Semua prodi (butir level Universitas/Lembaga)")]
    if is_superadmin(user):
        hasil = [("", "Semua prodi")]
        if kat == "PRODI":
            from master_akreditasi.models import MappingProdiInstrumen
            for kode, nama in (MappingProdiInstrumen.objects
                               .filter(instrumen_id=butir.sub_standar.standar.instrumen_id, aktif=True)
                               .order_by("kode_prodi").values_list("kode_prodi", "nama_prodi")):
                hasil.append((f"P:{kode}", f"Hanya prodi {kode} — {nama}"))
        else:
            from .pustaka import nama_fakultas_map
            for kode, nama in sorted(nama_fakultas_map().items()):
                hasil.append((f"F:{kode}", f"Hanya fakultas {kode} — {nama}"))
        return hasil
    hasil = []
    for s in get_user_scopes(user):
        if s.role == "ASESOR":
            continue
        if kat == "PRODI" and s.level == "PRODI" and s.prodi_id:
            hasil.append((f"P:{s.prodi_id}", f"Prodi {s.prodi_id}"))
        elif kat == "FAKULTAS" and s.level in ("FAKULTAS", "PRODI") and s.fakultas_id:
            hasil.append((f"F:{s.fakultas_id}", f"Fakultas {s.fakultas_id}"))
    return list(dict.fromkeys(hasil))


def urai_cakupan(nilai):
    jenis, _, kode = (nilai or "").partition(":")
    if jenis == "P":
        return {"scope_kode_prodi": kode, "scope_kode_fakultas": ""}
    if jenis == "F":
        return {"scope_kode_prodi": "", "scope_kode_fakultas": kode}
    return {"scope_kode_prodi": "", "scope_kode_fakultas": ""}


def kandidat_dokumen(user, butir, q="", kategori=""):
    """Dokumen Pustaka (FINAL, level Universitas/Biro/Fakultas) yang bisa ditautkan ke butir."""
    from .models import Dokumen
    from .sharing import butir_groups

    grup = butir_groups([butir])[butir.pk]
    qs = (Dokumen.objects.filter(status="FINAL", kategori_pemilik__in=BAGIAN_PUSTAKA)
          .exclude(butir_dokumen_id__in=grup)
          .select_related("kategori", "butir_dokumen"))
    if not is_superadmin(user):
        fak = {s.fakultas_id for s in get_user_scopes(user) if s.fakultas_id}
        qs = qs.filter(~Q(kategori_pemilik="FAKULTAS") | Q(scope_kode_fakultas__in=fak))
    if q:
        qs = qs.filter(Q(judul__icontains=q) | Q(nomor_dokumen__icontains=q) | Q(penerbit__icontains=q)
                       | Q(deskripsi__icontains=q))
    if kategori:
        qs = qs.filter(kategori_id=kategori)
    return qs.order_by("kategori__urutan", "judul", "-tahun_akademik")


def bisa_lepas(user, tautan):
    if not user.is_authenticated:
        return False
    if is_superadmin(user) or tautan.dibuat_oleh_id == user.pk:
        return True
    return can_edit_dokumen(user, tautan.dokumen)[0]
