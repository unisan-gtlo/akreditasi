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

COOKIE_KELUAR = "siakred_sso_keluar"
AWALAN_INTERNAL = ("/app", "/dokumen", "/sesi", "/master", "/laporan", "/login")


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
        if not sso.aktif():
            return self.get_response(request)

        token_url = request.GET.get("sso_token", "").strip()
        if token_url and request.method == "GET":
            masuk_dengan_token(request, token_url)
            resp = redirect(_tanpa_token(request) if request.user.is_authenticated else "core:login")
            resp.delete_cookie(COOKIE_KELUAR)
            return resp

        if request.user.is_authenticated:
            resp = self._cek_ulang(request)
            if resp is not None:
                return resp
        elif request.path.startswith(AWALAN_INTERNAL) and not request.COOKIES.get(COOKIE_KELUAR):
            token = request.COOKIES.get(settings.SSO_COOKIE_NAME, "")
            if token and masuk_dengan_token(request, token, diam=True) and request.path.startswith("/login"):
                return redirect(_next_aman(request.GET.get("next", "")) or "core:dashboard")
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
