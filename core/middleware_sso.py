"""
Login otomatis lewat SSO UNISAN (lihat core/sso.py & core/sso_sinkron.py).

- ?sso_token=... di URL (dari portal SSO / setelah login SSO): verifikasi, login,
  lalu redirect ke URL yang sama tanpa token (token tidak tertinggal di riwayat).
- Cookie sso_token (domain induk .unisan.ac.id / .unisan-g.id): pengguna yang sudah
  login di SSO langsung masuk saat membuka halaman internal SIAKRED.
- Sesi hasil SSO dicek ulang berkala; bila token dicabut (logout SSO) sesi SIAKRED berakhir.
  SSO tidak terjangkau -> sesi dibiarkan (tidak memutus pengguna karena gangguan jaringan).
- Setelah logout SIAKRED, cookie `siakred_sso_keluar` mencegah login otomatis lagi
  sampai pengguna menekan "Masuk dengan SSO".
"""
import hashlib
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.cache import cache
from django.shortcuts import redirect

from . import sso

COOKIE_KELUAR = "siakred_sso_keluar"      # berisi sidik token yang di-logout (bukan tokennya)
COOKIE_PAKAI_SSO = "siakred_pakai_sso"     # browser ini biasa masuk lewat SSO (1 tahun)
COOKIE_COBA = "siakred_sso_coba"           # penahan putaran redirect ke SSO (60 detik)
AWALAN_INTERNAL = ("/app", "/dokumen", "/sesi", "/master", "/laporan", "/login")


def _sidik(token):
    return hashlib.sha256((token or "").encode()).hexdigest()[:24] if token else "x"


def _tandai_pakai_sso(resp, request):
    resp.set_cookie(COOKIE_PAKAI_SSO, "1", max_age=365 * 24 * 3600, httponly=True, samesite="Lax",
                    secure=request.is_secure())
    resp.delete_cookie(COOKIE_COBA)


def _tanpa_token(request):
    q = request.GET.copy()
    q.pop("sso_token", None)
    return request.path + (("?" + q.urlencode()) if q else "")


def _kunci_tolak(token):
    return "sso_tolak:" + hashlib.sha256(token.encode()).hexdigest()[:40]


def _next_aman(nilai):
    return nilai if nilai and nilai.startswith("/") and not nilai.startswith("//") else ""


def masuk_dengan_token(request, token, diam=False):
    """Verifikasi token & login. Return True bila berhasil."""
    from .models import LoginAttempt
    from .sso_sinkron import masuk_sso
    from .views import record_attempt, track_device_session

    if diam and cache.get(_kunci_tolak(token)):
        return False
    data, err, sementara = sso.verifikasi(token)
    if not data:
        if not diam:
            messages.error(request, f"Login SSO gagal: {err}")
        return False
    if request.user.is_authenticated and request.user.username.lower() == (data.get("username") or "").lower():
        request.session["sso_token"], request.session["sso_cek"] = token, int(time.time())
        return True
    user, pesan, ringkasan = masuk_sso(data)
    if not user:
        cache.set(_kunci_tolak(token), 1, 600)
        if not diam:
            messages.error(request, pesan)
        return False
    if request.user.is_authenticated:
        logout(request)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["sso_token"] = token
    request.session["sso_cek"] = int(time.time())
    record_attempt(f"SSO:{user.username}", user, LoginAttempt.Status.SUCCESS, request)
    track_device_session(user, request)
    messages.success(request, f"Selamat datang, {user.nama_lengkap}! (masuk lewat SSO UNISAN)")
    return True


class SSOMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Subrequest nginx auth_request per berkas: jangan sentuh sesi/redirect di sini
        if not sso.aktif() or request.path == "/media-akses/":
            return self.get_response(request)

        token_url = request.GET.get("sso_token", "").strip()
        if token_url and request.method == "GET":
            berhasil = masuk_dengan_token(request, token_url)
            resp = redirect(_tanpa_token(request) if request.user.is_authenticated else "core:login")
            resp.delete_cookie(COOKIE_KELUAR)
            if berhasil:
                _tandai_pakai_sso(resp, request)
            else:
                resp.delete_cookie(COOKIE_PAKAI_SSO)  # cegah putaran redirect ke SSO
            return resp

        if request.user.is_authenticated:
            resp = self._cek_ulang(request)
            if resp is not None:
                return resp
        elif request.path.startswith(AWALAN_INTERNAL) or request.path == "/":
            keluar = request.COOKIES.get(COOKIE_KELUAR, "")
            token = request.COOKIES.get(settings.SSO_COOKIE_NAME, "")
            # 1) Cookie SSO sekeluarga domain: login senyap (kecuali token yang sama baru saja di-logout)
            if token and keluar != _sidik(token) and masuk_dengan_token(request, token, diam=True):
                if request.path.startswith("/login"):
                    resp = redirect(_next_aman(request.GET.get("next", "")) or "core:dashboard")
                else:
                    resp = self.get_response(request)
                _tandai_pakai_sso(resp, request)
                resp.delete_cookie(COOKIE_KELUAR)
                return resp
            # 2) Pernah masuk lewat SSO di browser ini tapi cookie SSO ada di domain lain
            #    (mis. login di sso.unisan.ac.id, membuka siakred.unisan-g.id): minta token ke SSO.
            #    SSO langsung mengembalikan token bila sudah login (jembatan lintas domain SSO).
            if (request.method == "GET" and request.path != "/" and request.COOKIES.get(COOKIE_PAKAI_SSO) and not keluar
                    and not request.COOKIES.get(COOKIE_COBA) and request.GET.get("lokal") != "1"):
                tujuan = (_next_aman(request.GET.get("next", "")) or "/app/") if request.path.startswith("/login") \
                    else request.get_full_path()
                resp = redirect(sso.url_login(request, tujuan))
                resp.set_cookie(COOKIE_COBA, "1", max_age=60, httponly=True, samesite="Lax", secure=request.is_secure())
                return resp
        return self.get_response(request)

    def _cek_ulang(self, request):
        token = request.session.get("sso_token")
        if not token:
            return None  # login lokal (password)
        sekarang = int(time.time())
        if sekarang - request.session.get("sso_cek", 0) < getattr(settings, "SSO_CEK_ULANG_DETIK", 300):
            return None
        data, err, sementara = sso.verifikasi(token)
        if data or sementara:
            request.session["sso_cek"] = sekarang
            return None
        # Token lama tak berlaku: pakai token baru di cookie bila user login ulang di SSO
        baru = request.COOKIES.get(settings.SSO_COOKIE_NAME, "")
        if baru and baru != token:
            data2, _e, _s = sso.verifikasi(baru)
            if data2 and (data2.get("username") or "").lower() == request.user.username.lower():
                request.session["sso_token"], request.session["sso_cek"] = baru, sekarang
                return None
        logout(request)
        messages.info(request, "Sesi SSO Anda telah berakhir. Silakan masuk kembali.")
        tujuan = request.get_full_path() if request.method == "GET" else "/app/"
        return redirect(f"/login/?{urlencode({'next': tujuan})}")
