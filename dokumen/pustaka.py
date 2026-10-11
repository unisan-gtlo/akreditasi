"""
Pustaka Dokumen Institusi: semua dokumen FINAL level Universitas/Rektorat,
Biro/Lembaga, dan Fakultas dalam satu halaman, tanpa harus masuk ke sesi.

- Akses lihat: superadmin + semua user dengan scope aktif selain Asesor
  (asesor tetap melihat dokumen lewat sesi yang ditugaskan).
- Dokumen bisa berasal dari butir instrumen atau diunggah langsung di Pustaka
  (Dokumen.butir_dokumen kosong).
- Dokumen dengan judul sama (tahun diabaikan) di unit yang sama = satu entri;
  versi tahun terbaru tampil, tahun lain bisa dibuka.
- Kategori: master KategoriDokumen (dikelola superadmin/LPM). Bila kosong, kategori
  ditebak dari kata kunci kategori yang cocok dengan judul (posisi paling awal, lalu terpanjang).
"""
import re

from django.core.cache import cache
from django.db import connection

BAGIAN = [
    ("UNIVERSITAS", "Universitas & Rektorat"),
    ("BIRO", "Biro & Lembaga"),
    ("FAKULTAS", "Fakultas"),
]

UKURAN_MAKS_MB = 50
EKSTENSI_DITERIMA = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                     ".jpg", ".jpeg", ".png", ".webp", ".zip", ".rar")


# =========================================================
# KATEGORI: tebakan otomatis
# =========================================================

def normal(teks):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (teks or "").lower()).split())


def cocokkan(teks, aturan):
    """aturan = [(pk, kode, urutan, [kata_kunci,...])]. Return pk kategori terbaik atau None."""
    t = f" {normal(teks)} "
    terbaik = None
    for pk, _kode, urutan, kunci in aturan:
        for kw in kunci:
            kw = normal(kw)
            pos = t.find(f" {kw} ") if kw else -1
            if pos >= 0:
                # Kata jenis biasanya di awal judul ("SK Rektor tentang Pedoman ..."):
                # posisi paling awal menang, lalu kata kunci terpanjang, lalu urutan kategori.
                skor = (-pos, len(kw), -urutan)
                if terbaik is None or skor > terbaik[0]:
                    terbaik = (skor, pk)
    return terbaik[1] if terbaik else None


def aturan_kategori():
    data = cache.get("pustaka_kategori_aturan")
    if data is None:
        from .models import KategoriDokumen
        data = [(k.pk, k.kode, k.urutan, k.kata_kunci_list())
                for k in KategoriDokumen.objects.filter(aktif=True)]
        cache.set("pustaka_kategori_aturan", data, 300)
    return data


def tebak_kategori_id(judul, nama_butir="", is_link=False):
    aturan = aturan_kategori()
    per_kode = {kode: pk for pk, kode, _u, _k in aturan}
    if is_link and "aplikasi" in per_kode:
        return per_kode["aplikasi"]
    return cocokkan(judul, aturan) or cocokkan(nama_butir, aturan) or per_kode.get("lainnya")


# =========================================================
# HAK AKSES
# =========================================================

def can_access_pustaka(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.scopes.filter(aktif=True).exclude(role="ASESOR").exists()


def can_kelola_kategori(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.scopes.filter(aktif=True, role="LPM").exists()


def pilihan_pemilik(user):
    """[(nilai, label)] pemilik yang boleh dipilih user saat menambah dokumen di Pustaka.
    nilai: 'UNIVERSITAS:' | 'BIRO:<unit_kerja_id>' | 'FAKULTAS:<kode>'."""
    if not user.is_authenticated:
        return []
    unit = nama_unit_map()
    fak = nama_fakultas_map()
    if user.is_superuser:
        hasil = [("UNIVERSITAS:", "Universitas & Rektorat")]
        hasil += [(f"BIRO:{k}", f"Biro/Lembaga — {v}") for k, v in sorted(unit.items(), key=lambda x: x[1].lower())]
        hasil += [(f"FAKULTAS:{k}", f"Fakultas — {v}") for k, v in sorted(fak.items(), key=lambda x: x[1].lower())]
        return hasil
    hasil = []
    for s in user.scopes.filter(aktif=True).exclude(role="ASESOR"):
        if s.level == "UNIVERSITAS":
            hasil.append(("UNIVERSITAS:", "Universitas & Rektorat"))
        elif s.level == "BIRO" and s.unit_kerja_id:
            k = str(s.unit_kerja_id)
            hasil.append((f"BIRO:{k}", f"Biro/Lembaga — {unit.get(k, 'Unit ' + k)}"))
        elif s.level == "FAKULTAS" and s.fakultas_id:
            hasil.append((f"FAKULTAS:{s.fakultas_id}", f"Fakultas — {fak.get(s.fakultas_id, s.fakultas_id)}"))
    return list(dict.fromkeys(hasil))


def urai_pemilik(nilai):
    """'BIRO:12' → dict field scope Dokumen."""
    kat, _, kode = (nilai or "").partition(":")
    return {
        "kategori_pemilik": kat,
        "scope_kode_prodi": "",
        "scope_kode_fakultas": kode if kat == "FAKULTAS" else "",
        "scope_kode_unit_kerja": kode if kat == "BIRO" else "",
    }


# =========================================================
# NAMA UNIT / FAKULTAS
# =========================================================

def nama_unit_map():
    """{str(unit_kerja.id): 'Nama Unit'} dari SIMDA (cache 10 menit). Kosong bila gagal."""
    data = cache.get("pustaka_unit_kerja")
    if data is not None:
        return data
    data = {}
    try:
        with connection.cursor() as c:
            c.execute("SELECT * FROM master.unit_kerja")
            kolom = [d[0] for d in c.description]
            nama_col = next((k for k in ("nama_unit_kerja", "nama_unit", "nama", "nama_lengkap") if k in kolom), None)
            for row in c.fetchall():
                r = dict(zip(kolom, row))
                nama = " ".join(str((r.get(nama_col) if nama_col else "") or r.get("kode") or r.get("id")).split())
                kode = r.get("kode")
                data[str(r.get("id"))] = f"{nama} ({kode})" if kode and nama_col and kode != nama else str(nama)
    except Exception:
        data = {}
    cache.set("pustaka_unit_kerja", data, 600)
    return data


def nama_fakultas_map():
    try:
        from core.views import _get_fakultas_list
        return {f["kode"]: f["nama"] for f in _get_fakultas_list()}
    except Exception:
        return {}


_TAHUN_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def kunci_judul(judul):
    """Judul dinormalisasi tanpa tahun → dokumen tahun berbeda dianggap satu entri."""
    t = _TAHUN_RE.sub(" ", (judul or "").lower())
    t = re.sub(r"\b(tahun|ta|t\.a\.?)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def tahun_urut(tahun_akademik):
    angka = [int(x) for x in _TAHUN_RE.findall(tahun_akademik or "")]
    return max(angka) if angka else 0


# =========================================================
# DAFTAR PUSTAKA
# =========================================================

def bangun_pustaka(params, user):
    """Susun entri Pustaka dari dokumen FINAL sesuai filter GET."""
    from django.db.models import Prefetch, Q

    from master_akreditasi.models import ButirDokumen
    from .models import Dokumen, DokumenRevisi, KategoriDokumen
    from .permissions import can_edit_dokumen, get_user_scopes

    f_bagian = params.get("bagian", "")
    f_kategori = params.get("kategori", "")
    f_unit = params.get("unit", "")
    f_tahun = params.get("tahun", "").strip()
    f_instrumen = params.get("instrumen", "")
    f_sumber = params.get("sumber", "")
    q = params.get("q", "").strip()

    qs = (
        Dokumen.objects.filter(status="FINAL", kategori_pemilik__in=[k for k, _ in BAGIAN])
        .select_related("butir_dokumen__sub_standar__standar__instrumen", "kategori")
        .prefetch_related(Prefetch(
            "revisi",
            queryset=DokumenRevisi.objects.filter(aktif=True).order_by("-nomor_revisi"),
            to_attr="rev_aktif",
        ))
    )
    if f_bagian:
        qs = qs.filter(kategori_pemilik=f_bagian)
    if f_unit:
        qs = qs.filter(Q(kategori_pemilik="BIRO", scope_kode_unit_kerja=f_unit)
                       | Q(kategori_pemilik="FAKULTAS", scope_kode_fakultas=f_unit))
    if f_instrumen:
        qs = qs.filter(butir_dokumen__sub_standar__standar__instrumen_id=f_instrumen)
    if f_sumber == "pustaka":
        qs = qs.filter(butir_dokumen__isnull=True)
    elif f_sumber == "butir":
        qs = qs.filter(butir_dokumen__isnull=False)
    if f_tahun:
        qs = qs.filter(Q(tahun_akademik__icontains=f_tahun) | Q(tanggal_dokumen__year=f_tahun if f_tahun.isdigit() else 0))
    if q:
        qs = qs.filter(Q(judul__icontains=q) | Q(butir_dokumen__nama_dokumen__icontains=q)
                       | Q(butir_dokumen__kode__icontains=q) | Q(deskripsi__icontains=q)
                       | Q(nomor_dokumen__icontains=q) | Q(penerbit__icontains=q))
    docs = list(qs)

    kategori_all = list(KategoriDokumen.objects.all())
    kat_by_pk = {k.pk: k for k in kategori_all}
    kat_by_kode = {k.kode: k for k in kategori_all}

    # Butir lain yang memakai dokumen bersama (kode_bersama)
    kb_set = {d.butir_dokumen.kode_bersama for d in docs if d.butir_dokumen_id and d.butir_dokumen.kode_bersama}
    kb_butir = {}
    for b in (ButirDokumen.objects.filter(kode_bersama__in=kb_set)
              .select_related("sub_standar__standar__instrumen")):
        kb_butir.setdefault(b.kode_bersama, []).append(b)

    # Butir yang memakai dokumen lewat tautan Pustaka
    from .models import DokumenTautanButir
    tautan_dok = {}
    for t in (DokumenTautanButir.objects.filter(dokumen_id__in=[d.pk for d in docs])
              .select_related("butir__sub_standar__standar__instrumen")):
        tautan_dok.setdefault(t.dokumen_id, []).append(t)

    unit_nama = nama_unit_map()
    fak_nama = nama_fakultas_map()
    scopes = get_user_scopes(user)

    def unit_dari(d):
        if d.kategori_pemilik == "BIRO":
            k = d.scope_kode_unit_kerja or ""
            return k, (unit_nama.get(k) or (f"Unit {k}" if k else "Biro/Lembaga (unit belum diisi)"))
        if d.kategori_pemilik == "FAKULTAS":
            k = d.scope_kode_fakultas or ""
            return k, (fak_nama.get(k) or k or "Fakultas (belum diisi)")
        return "", "Universitas & Rektorat"

    grup = {}
    for d in docs:
        rev = d.rev_aktif[0] if d.rev_aktif else None
        kat = d.kategori
        if rev and rev.is_link and (kat is None or kat.kode == "lainnya") and "aplikasi" in kat_by_kode:
            kat = kat_by_kode["aplikasi"]
        d.kat_tampil = kat
        d.rev = rev
        unit_kode, unit_label = unit_dari(d)
        key = (d.kategori_pemilik, unit_kode, kunci_judul(d.judul) or f"#{d.pk}")
        g = grup.setdefault(key, {"unit_kode": unit_kode, "unit_label": unit_label, "versi": [], "butir": {}})
        g["versi"].append(d)
        b = d.butir_dokumen
        if b is not None:
            anggota = kb_butir.get(b.kode_bersama, [b]) if b.kode_bersama else [b]
            for x in anggota:
                g["butir"][x.pk] = f"{x.kode} · {x.sub_standar.standar.instrumen.nama_singkat}"
        for t in tautan_dok.get(d.pk, []):
            x = t.butir
            g["butir"].setdefault(x.pk, f"{x.kode} · {x.sub_standar.standar.instrumen.nama_singkat} (tautan)")

    ringkasan = {}
    per_bagian = {k: {} for k, _ in BAGIAN}
    for (kat_pemilik, _u, _j), g in grup.items():
        g["versi"].sort(key=lambda d: (tahun_urut(d.tahun_akademik) or (d.tanggal_dokumen.year if d.tanggal_dokumen else 0),
                                       d.tanggal_dibuat), reverse=True)
        utama = g["versi"][0]
        kat = utama.kat_tampil
        kat_pk = kat.pk if kat else 0
        ringkasan[kat_pk] = ringkasan.get(kat_pk, 0) + 1
        if f_kategori and str(kat_pk) != f_kategori:
            continue
        entri = {
            "dok": utama,
            "kategori": kat,
            "versi_lain": g["versi"][1:],
            "butir": sorted(g["butir"].values()),
            "bisa_edit": can_edit_dokumen(user, utama, scopes=scopes)[0],
        }
        unit = per_bagian[kat_pemilik].setdefault(g["unit_kode"], {"label": g["unit_label"], "entri": []})
        unit["entri"].append(entri)

    hasil = []
    total = 0
    for kat_pemilik, label in BAGIAN:
        units = sorted(per_bagian[kat_pemilik].values(), key=lambda u: u["label"].lower())
        for u in units:
            u["entri"].sort(key=lambda e: ((e["kategori"].urutan, e["kategori"].nama) if e["kategori"] else (9999, ""),
                                           e["dok"].judul.lower()))
        n = sum(len(u["entri"]) for u in units)
        total += n
        if units:
            hasil.append({"kode": kat_pemilik, "label": label, "units": units, "jumlah": n})

    ringkasan_kat = [(k.pk, k.nama, ringkasan[k.pk]) for k in kategori_all if ringkasan.get(k.pk)]
    if ringkasan.get(0):
        ringkasan_kat.append((0, "Tanpa kategori", ringkasan[0]))

    # Opsi filter unit (semua unit yang punya dokumen, bukan hanya hasil filter)
    opsi_unit = set()
    for kode in (Dokumen.objects.filter(status="FINAL", kategori_pemilik="BIRO")
                 .exclude(scope_kode_unit_kerja="").values_list("scope_kode_unit_kerja", flat=True).distinct()):
        opsi_unit.add((kode, unit_nama.get(kode) or f"Unit {kode}"))
    for kode in (Dokumen.objects.filter(status="FINAL", kategori_pemilik="FAKULTAS")
                 .exclude(scope_kode_fakultas="").values_list("scope_kode_fakultas", flat=True).distinct()):
        opsi_unit.add((kode, fak_nama.get(kode) or kode))

    return {
        "bagian_list": hasil,
        "total_entri": total,
        "ringkasan_kategori": ringkasan_kat,
        "opsi_bagian": BAGIAN,
        "opsi_unit": sorted(opsi_unit, key=lambda x: x[1].lower()),
        "f": {"bagian": f_bagian, "kategori": f_kategori, "unit": f_unit, "tahun": f_tahun,
              "instrumen": f_instrumen, "sumber": f_sumber, "q": q},
        "ada_filter": any([f_bagian, f_kategori, f_unit, f_tahun, f_instrumen, f_sumber, q]),
    }
