"""
Login SSO -> akun & scope SIAKRED.

1. Akun dicocokkan dari username SSO (NIDN dosen / NIP tendik): username, nidn, nip,
   lalu email. Pejabat yang belum punya akun dibuatkan otomatis (SSO_BUAT_AKUN_PEJABAT).
2. Scope diturunkan dari jabatan struktural AKTIF di SIMDA (master.pejabat_struktural),
   dibaca langsung (dosen & tendik) -- bukan hanya dari jawaban SSO yang hanya dosen.
     lingkup universitas -> Pimpinan Rektorat (Universitas)
     lingkup fakultas    -> Pimpinan Fakultas (fakultasnya)
     lingkup prodi       -> Pimpinan Prodi (prodinya)
     lingkup unit        -> sesuai tabel PemetaanJabatanSSO (wajib dipetakan)
   Tanpa jabatan: cadangan dari role SSO (rektorat/dekan/wadek/kaprodi/sekprodi).
3. Scope bersumber SSO disinkron tiap login: yang tidak berlaku lagi dinonaktifkan.
   Scope MANUAL (operator, staf LPM, asesor, superadmin) tidak pernah diubah.
"""
import logging

from django.db import connection, transaction

from .models import PemetaanJabatanSSO, ScopeUser, User

logger = logging.getLogger("siakred.sso")

ROLE_CADANGAN = {
    "rektorat": ("UNIVERSITAS", None),
    "dekan": ("FAKULTAS", "kode_fakultas"),
    "wadek": ("FAKULTAS", "kode_fakultas"),
    "kaprodi": ("PRODI", "kode_prodi"),
    "sekprodi": ("PRODI", "kode_prodi"),
}
ROLE_LEVEL = {"UNIVERSITAS": "PIMP_REKTORAT", "FAKULTAS": "PIMP_FAKULTAS", "PRODI": "PIMP_PRODI"}


def _q(sql, params):
    try:
        with connection.cursor() as c:
            c.execute(sql, params)
            kolom = [d[0] for d in c.description]
            return [dict(zip(kolom, r)) for r in c.fetchall()]
    except Exception as e:  # SIMDA tak terjangkau: jangan gagalkan login
        logger.warning("Query SIMDA gagal: %s", e)
        return []


def jabatan_simda(username):
    """Jabatan struktural aktif milik NIDN (dosen) / NIP (tendik)."""
    if not username:
        return []
    return _q(
        """
        SELECT j.kode, j.nama, j.lingkup, j.level, ps.kode_fakultas, ps.kode_prodi
        FROM master.pejabat_struktural ps
        JOIN master.jabatan_struktural j ON j.id = ps.jabatan_id
        LEFT JOIN master.data_dosen d ON d.id = ps.dosen_id
        LEFT JOIN master.data_tendik t ON t.id = ps.tendik_id
        WHERE ps.is_aktif = TRUE
          AND (ps.tgl_selesai IS NULL OR ps.tgl_selesai >= CURRENT_DATE)
          AND (d.nidn = %s OR t.nip = %s)
        ORDER BY j.level
        """,
        [username, username],
    )


def _fakultas_prodi(kode_prodi):
    rows = _q("SELECT kode_fakultas FROM master.program_studi WHERE kode_prodi = %s", [kode_prodi])
    return (rows[0]["kode_fakultas"] or None) if rows else None


def target_scope(username, data_sso=None):
    """[(dict scope, keterangan)] yang seharusnya dimiliki user + daftar catatan jabatan dilewati."""
    pemetaan = {p.kode_jabatan.upper(): p for p in PemetaanJabatanSSO.objects.all()}
    target, catatan = [], []
    for j in jabatan_simda(username):
        kode = (j["kode"] or "").upper()
        p = pemetaan.get(kode)
        fak = (j.get("kode_fakultas") or "").strip() or None
        prodi = (j.get("kode_prodi") or "").strip() or None
        if p and p.abaikan:
            catatan.append(f"{kode}: diabaikan (pemetaan)")
            continue
        if p:
            role, level, unit = p.role, p.level, p.unit_kerja_id
        elif j["lingkup"] in ("universitas", "fakultas", "prodi"):
            level = {"universitas": "UNIVERSITAS", "fakultas": "FAKULTAS", "prodi": "PRODI"}[j["lingkup"]]
            role, unit = ROLE_LEVEL[level], None
        else:
            catatan.append(f"{kode} ({j['nama']}): jabatan unit belum dipetakan")
            continue
        if level == "PRODI" and prodi and not fak:
            fak = _fakultas_prodi(prodi)
        if level == "FAKULTAS" and not fak or level == "PRODI" and not prodi or level == "BIRO" and not unit:
            catatan.append(f"{kode}: data fakultas/prodi/unit kosong")
            continue
        target.append({
            "role": role, "level": level, "unit_kerja_id": unit,
            "fakultas_id": fak if level in ("FAKULTAS", "PRODI") else None,
            "prodi_id": prodi if level == "PRODI" else None,
            "kode_jabatan": kode[:20],
        })
    if not target and data_sso:  # cadangan: role SSO
        role_sso = (data_sso.get("role") or "").lower()
        profil = data_sso.get("profil") or {}
        if role_sso in ROLE_CADANGAN:
            level, kolom = ROLE_CADANGAN[role_sso]
            kode = (profil.get(kolom) or "").strip() if kolom else ""
            if not kolom or kode:
                fak = kode if level == "FAKULTAS" else (_fakultas_prodi(kode) if level == "PRODI" else None)
                target.append({
                    "role": ROLE_LEVEL[level], "level": level, "unit_kerja_id": None,
                    "fakultas_id": fak, "prodi_id": kode if level == "PRODI" else None,
                    "kode_jabatan": f"ROLE:{role_sso}"[:20],
                })
    # buang duplikat
    unik = {}
    for t in target:
        unik.setdefault((t["role"], t["unit_kerja_id"], t["fakultas_id"], t["prodi_id"]), t)
    return list(unik.values()), catatan


def _kunci(s):
    return (s.role, s.unit_kerja_id or None, (s.fakultas_id or None), (s.prodi_id or None))


@transaction.atomic
def sinkron_scope(user, target):
    """Terapkan target ke ScopeUser (hanya menyentuh scope bersumber SSO). Return ringkasan."""
    hasil = {"dibuat": 0, "diaktifkan": 0, "dinonaktifkan": 0, "manual_sudah_ada": 0}
    ada = {_kunci(s): s for s in ScopeUser.objects.select_for_update().filter(user=user)}
    kunci_target = set()
    for t in target:
        k = (t["role"], t["unit_kerja_id"], t["fakultas_id"], t["prodi_id"])
        kunci_target.add(k)
        s = ada.get(k)
        if s is None:
            ScopeUser.objects.create(user=user, sumber=ScopeUser.Sumber.SSO, is_pimpinan=True, aktif=True, **t)
            hasil["dibuat"] += 1
        elif s.sumber == ScopeUser.Sumber.SSO:
            if not s.aktif or s.level != t["level"] or s.kode_jabatan != t["kode_jabatan"]:
                s.aktif, s.level, s.kode_jabatan = True, t["level"], t["kode_jabatan"]
                s.save(update_fields=["aktif", "level", "kode_jabatan", "tanggal_diubah"])
                hasil["diaktifkan"] += 1
        else:
            hasil["manual_sudah_ada"] += 1
    for k, s in ada.items():
        if s.sumber == ScopeUser.Sumber.SSO and s.aktif and k not in kunci_target:
            s.aktif = False
            s.save(update_fields=["aktif", "tanggal_diubah"])
            hasil["dinonaktifkan"] += 1
    return hasil


def cocokkan_user(data):
    uname = (data.get("username") or "").strip()
    if not uname:
        return None
    for q in ({"username__iexact": uname}, {"nidn": uname}, {"nip": uname}):
        u = User.objects.filter(**q).first()
        if u:
            return u
    email = (data.get("email") or "").strip()
    if email:
        cocok = list(User.objects.filter(email__iexact=email)[:2])
        if len(cocok) == 1:
            return cocok[0]
    return None


def _isi_profil(user, data, baru=False):
    profil = data.get("profil") or {}
    ubah = []
    nama = (profil.get("nama_lengkap") or "").strip()
    if nama and (baru or not (user.first_name or user.last_name)):
        user.first_name, user.last_name = nama[:150], ""
        ubah += ["first_name", "last_name"]
    email = (data.get("email") or "").strip()
    if email and not user.email:
        user.email = email
        ubah.append("email")
    uname = data.get("username") or ""
    role_sso = (data.get("role") or "").lower()
    if role_sso == "tendik" and not user.nip:
        user.nip = uname
        ubah.append("nip")
    elif role_sso not in ("tendik", "mahasiswa", "alumni", "publik") and not user.nidn and uname.isdigit():
        user.nidn = uname
        ubah.append("nidn")
    return ubah


def masuk_sso(data):
    """Data user dari SSO -> (User | None, pesan, ringkasan_scope)."""
    from django.conf import settings

    uname = (data.get("username") or "").strip()
    target, catatan = target_scope(uname, data)
    user = cocokkan_user(data)
    if user is None:
        if not (target and getattr(settings, "SSO_BUAT_AKUN_PEJABAT", True)):
            return None, (f"Akun SSO {uname} belum terdaftar di SIAKRED. Hubungi admin SIAKRED "
                          f"untuk dibuatkan akses."), {}
        user = User(username=uname[:150])
        _isi_profil(user, data, baru=True)
        user.set_unusable_password()
        user.save()
        logger.info("SSO: akun SIAKRED dibuat otomatis untuk %s", uname)
    elif not user.is_active:
        return None, "Akun SIAKRED Anda nonaktif. Hubungi admin SIAKRED.", {}
    else:
        ubah = _isi_profil(user, data)
        if ubah:
            user.save(update_fields=ubah)
    ringkasan = sinkron_scope(user, target)
    ringkasan["catatan"] = catatan
    return user, "", ringkasan
