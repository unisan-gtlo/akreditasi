"""
Diagnosis integrasi SSO UNISAN.

    manage.py cek_sso                 # konfigurasi + daftar jabatan SIMDA & status pemetaannya
    manage.py cek_sso --uji 0912...   # simulasi login SSO untuk NIDN/NIP (tanpa mengubah data)
    manage.py cek_sso --token <tok>   # uji verifikasi token ke SSO (butuh SSO aktif)
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core import sso
from core.models import PemetaanJabatanSSO, ScopeUser
from core.sso_sinkron import _q, cocokkan_user, jabatan_simda, sinkron_scope, target_scope


class Command(BaseCommand):
    help = "Diagnosis integrasi SSO UNISAN (konfigurasi, pemetaan jabatan, simulasi login)."

    def add_arguments(self, parser):
        parser.add_argument("--uji", default="", help="NIDN/NIP untuk simulasi login (dry-run)")
        parser.add_argument("--token", default="", help="Token SSO untuk uji verifikasi")

    def handle(self, *args, uji="", token="", **kw):
        w = self.stdout.write
        w("=== Konfigurasi ===")
        w(f"SSO_ENABLED={settings.SSO_ENABLED} | secret key terisi={bool(settings.SSO_SECRET_KEY)} | aktif={sso.aktif()}")
        w(f"VERIFY_URL={settings.SSO_VERIFY_URL} | cek ulang tiap {settings.SSO_CEK_ULANG_DETIK} dtk")

        w("\n=== Jabatan struktural SIMDA (aktif) ===")
        peta = {p.kode_jabatan.upper(): p for p in PemetaanJabatanSSO.objects.all()}
        rows = _q("""
            SELECT j.kode, j.nama, j.lingkup, j.level, COUNT(ps.id) AS pejabat
            FROM master.jabatan_struktural j
            LEFT JOIN master.pejabat_struktural ps ON ps.jabatan_id = j.id AND ps.is_aktif = TRUE
            WHERE j.status = TRUE
            GROUP BY j.kode, j.nama, j.lingkup, j.level ORDER BY j.level, j.kode
        """, [])
        if not rows:
            w("  (tidak terbaca -- periksa izin SELECT master.jabatan_struktural / pejabat_struktural)")
        for r in rows:
            p = peta.get((r["kode"] or "").upper())
            if p:
                aturan = "DIABAIKAN" if p.abaikan else f"pemetaan -> {p.role}/{p.level}" + (f" unit {p.unit_kerja_id}" if p.unit_kerja_id else "") + (f" fakultas {p.fakultas_tetap}" if p.fakultas_tetap else "")
            elif r["lingkup"] in ("universitas", "fakultas", "prodi"):
                aturan = f"bawaan -> {r['lingkup']}"
            else:
                aturan = "!! BELUM DIPETAKAN (jabatan unit)"
            w(f"  {r['kode']:<12} {r['nama'][:40]:<40} lingkup={r['lingkup']:<11} pejabat aktif={r['pejabat']:<3} {aturan}")

        if uji:
            w(f"\n=== Simulasi login SSO untuk {uji} (tidak disimpan) ===")
            w(f"Jabatan SIMDA: {[(j['kode'], j['lingkup'], j['kode_fakultas'], j['kode_prodi']) for j in jabatan_simda(uji)]}")
            target, catatan = target_scope(uji, {"username": uji})
            w(f"Scope target: {[(t['role'], t['level'], t['fakultas_id'], t['prodi_id'], t['unit_kerja_id']) for t in target]}")
            for c in catatan:
                w(f"  catatan: {c}")
            user = cocokkan_user({"username": uji})
            w(f"Akun SIAKRED: {user.username if user else '(belum ada -- akan dibuat otomatis bila punya jabatan)'}")
            if user:
                with transaction.atomic():
                    w(f"Sinkron scope: {sinkron_scope(user, target)}")
                    for s in ScopeUser.objects.filter(user=user).order_by("-aktif"):
                        w(f"  {'AKTIF ' if s.aktif else 'nonaktif'} {s.sumber:<6} {s.role}/{s.level} fak={s.fakultas_id} prodi={s.prodi_id} unit={s.unit_kerja_id}")
                    transaction.set_rollback(True)

        if token:
            w("\n=== Uji verifikasi token ===")
            data, err, sementara = sso.verifikasi(token, pakai_cache=False)
            w(f"valid={bool(data)} error={err} sementara={sementara}")
            if data:
                w(f"user={data.get('username')} role={data.get('role')} jabatan={data.get('jabatan_struktural')}")
