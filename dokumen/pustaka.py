"""
Pustaka Dokumen Institusi: semua dokumen FINAL level Universitas/Rektorat,
Biro/Lembaga, dan Fakultas dalam satu halaman, tanpa harus masuk ke sesi.

- Akses: superadmin + semua user dengan scope aktif selain Asesor
  (asesor tetap melihat dokumen lewat sesi yang ditugaskan).
- Dokumen dengan judul sama (tahun diabaikan) di unit yang sama = satu entri;
  versi tahun terbaru tampil, tahun lain bisa dibuka.
- Jenis dokumen: kolom Dokumen.jenis_dokumen, otomatis ditebak dari judul/nama butir
  bila kosong; bisa dikoreksi di Edit Dokumen.
"""
import re

from django.core.cache import cache
from django.db import connection

BAGIAN = [
    ("UNIVERSITAS", "Universitas & Rektorat"),
    ("BIRO", "Biro & Lembaga"),
    ("FAKULTAS", "Fakultas"),
]

# Urutan dicek dari atas: aturan pertama yang cocok menang.
_ATURAN_JENIS = [
    ("SOP", [r"\bsop\b", r"standar operasional", r"prosedur"]),
    ("SK", [r"\bsk\b", r"surat keputusan", r"keputusan (rektor|dekan|ketua|yayasan|senat)"]),
    ("RENCANA", [r"renstra", r"renop", r"rencana", r"\brip\b", r"roadmap", r"road map", r"peta jalan", r"\brkat\b"]),
    ("KEBIJAKAN", [r"kebijakan", r"statuta", r"peraturan", r"kode etik"]),
    ("PEDOMAN", [r"pedoman", r"manual", r"panduan", r"buku saku", r"petunjuk", r"\bstandar\b"]),
    ("FORMULIR", [r"formulir", r"\bform\b", r"borang", r"template", r"kuesioner"]),
    ("LAPORAN", [r"laporan", r"evaluasi", r"audit", r"\bami\b", r"\brtm\b", r"tinjauan manajemen", r"survei",
                 r"survey", r"notulen", r"rekap", r"analisis", r"hasil", r"bukti", r"\blkps\b", r"\bled\b"]),
    ("FORMULIR", [r"instrumen"]),
]


def _tebak(teks):
    t = (teks or "").lower()
    for jenis, pola in _ATURAN_JENIS:
        if any(re.search(p, t) for p in pola):
            return jenis
    return ""


def tebak_jenis(judul, nama_butir="", is_link=False):
    """Tebak Dokumen.JenisDokumen dari judul (lalu nama butir)."""
    if is_link:
        return "APLIKASI"
    return _tebak(judul) or _tebak(nama_butir) or "LAINNYA"


def can_access_pustaka(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.scopes.filter(aktif=True).exclude(role="ASESOR").exists()


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
                nama = (r.get(nama_col) if nama_col else "") or r.get("kode") or r.get("id")
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


def bangun_pustaka(params):
    """Susun entri Pustaka dari dokumen FINAL sesuai filter GET.

    Return dict: bagian (list section → unit → entri), ringkasan jenis, opsi filter.
    """
    from django.db.models import Prefetch, Q

    from master_akreditasi.models import ButirDokumen
    from .models import Dokumen, DokumenRevisi

    f_bagian = params.get("bagian", "")
    f_jenis = params.get("jenis", "")
    f_unit = params.get("unit", "")
    f_tahun = params.get("tahun", "").strip()
    f_instrumen = params.get("instrumen", "")
    q = params.get("q", "").strip()

    qs = (
        Dokumen.objects.filter(status="FINAL", kategori_pemilik__in=[k for k, _ in BAGIAN])
        .select_related("butir_dokumen__sub_standar__standar__instrumen")
        .prefetch_related(Prefetch(
            "revisi",
            queryset=DokumenRevisi.objects.filter(aktif=True).order_by("-nomor_revisi"),
            to_attr="rev_aktif",
        ))
    )
    if f_bagian:
        qs = qs.filter(kategori_pemilik=f_bagian)
    if f_unit:
        qs = qs.filter(Q(scope_kode_unit_kerja=f_unit) | Q(scope_kode_fakultas=f_unit))
    if f_instrumen:
        qs = qs.filter(butir_dokumen__sub_standar__standar__instrumen_id=f_instrumen)
    if f_tahun:
        qs = qs.filter(tahun_akademik__icontains=f_tahun)
    if q:
        qs = qs.filter(Q(judul__icontains=q) | Q(butir_dokumen__nama_dokumen__icontains=q)
                       | Q(butir_dokumen__kode__icontains=q) | Q(deskripsi__icontains=q))
    docs = list(qs)

    # Butir lain yang memakai dokumen bersama (kode_bersama)
    kb_set = {d.butir_dokumen.kode_bersama for d in docs if d.butir_dokumen.kode_bersama}
    kb_butir = {}
    for b in (ButirDokumen.objects.filter(kode_bersama__in=kb_set)
              .select_related("sub_standar__standar__instrumen")):
        kb_butir.setdefault(b.kode_bersama, []).append(b)

    unit_nama = nama_unit_map()
    fak_nama = nama_fakultas_map()
    label_jenis = dict(Dokumen.JenisDokumen.choices)

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
        jenis = d.jenis_dokumen or "LAINNYA"
        if rev and rev.is_link and jenis == "LAINNYA":
            jenis = "APLIKASI"
        d.jenis_tampil = jenis
        d.rev = rev
        unit_kode, unit_label = unit_dari(d)
        key = (d.kategori_pemilik, unit_kode, kunci_judul(d.judul) or f"#{d.pk}")
        g = grup.setdefault(key, {"unit_kode": unit_kode, "unit_label": unit_label, "versi": [], "butir": {}})
        g["versi"].append(d)
        b = d.butir_dokumen
        anggota = kb_butir.get(b.kode_bersama, [b]) if b.kode_bersama else [b]
        for x in anggota:
            g["butir"][x.pk] = f"{x.kode} · {x.sub_standar.standar.instrumen.nama_singkat}"

    ringkasan = {}
    per_bagian = {k: {} for k, _ in BAGIAN}
    for (kat, _u, _j), g in grup.items():
        g["versi"].sort(key=lambda d: (tahun_urut(d.tahun_akademik), d.tanggal_dibuat), reverse=True)
        utama = g["versi"][0]
        jenis = utama.jenis_tampil
        ringkasan[jenis] = ringkasan.get(jenis, 0) + 1
        if f_jenis and jenis != f_jenis:
            continue
        entri = {
            "dok": utama,
            "jenis": jenis,
            "jenis_label": label_jenis.get(jenis, jenis),
            "versi_lain": g["versi"][1:],
            "butir": sorted(g["butir"].values()),
        }
        unit = per_bagian[kat].setdefault(g["unit_kode"], {"label": g["unit_label"], "entri": []})
        unit["entri"].append(entri)

    urutan_jenis = [k for k, _ in Dokumen.JenisDokumen.choices]
    hasil = []
    total = 0
    for kat, label in BAGIAN:
        units = sorted(per_bagian[kat].values(), key=lambda u: u["label"].lower())
        for u in units:
            u["entri"].sort(key=lambda e: (urutan_jenis.index(e["jenis"]) if e["jenis"] in urutan_jenis else 99,
                                           e["dok"].judul.lower()))
        n = sum(len(u["entri"]) for u in units)
        total += n
        if units:
            hasil.append({"kode": kat, "label": label, "units": units, "jumlah": n})

    # Opsi filter unit (semua unit yang punya dokumen, bukan hanya hasil filter)
    opsi_unit = []
    for kat, kode in (Dokumen.objects.filter(status="FINAL", kategori_pemilik__in=["BIRO", "FAKULTAS"])
                      .values_list("kategori_pemilik", "scope_kode_unit_kerja").distinct()):
        if kat == "BIRO" and kode:
            opsi_unit.append((kode, unit_nama.get(kode) or f"Unit {kode}"))
    for kode in (Dokumen.objects.filter(status="FINAL", kategori_pemilik="FAKULTAS")
                 .exclude(scope_kode_fakultas="").values_list("scope_kode_fakultas", flat=True).distinct()):
        opsi_unit.append((kode, fak_nama.get(kode) or kode))
    opsi_unit = sorted(set(opsi_unit), key=lambda x: x[1].lower())

    return {
        "bagian_list": hasil,
        "total_entri": total,
        "ringkasan_jenis": [(k, label_jenis[k], ringkasan[k]) for k in urutan_jenis if ringkasan.get(k)],
        "opsi_bagian": BAGIAN,
        "opsi_jenis": Dokumen.JenisDokumen.choices,
        "opsi_unit": opsi_unit,
        "f": {"bagian": f_bagian, "jenis": f_jenis, "unit": f_unit, "tahun": f_tahun,
              "instrumen": f_instrumen, "q": q},
        "ada_filter": any([f_bagian, f_jenis, f_unit, f_tahun, f_instrumen, q]),
    }
