"""
Klien SSO UNISAN (sso.unisan.ac.id / sso.unisan-g.id).

Alur: user login di SSO -> SSO memasang cookie `sso_token` untuk domain induk
(.unisan.ac.id / .unisan-g.id) dan/atau mengarahkan ke SIAKRED dengan ?sso_token=.
SIAKRED memverifikasi token server-ke-server (POST /api/verify-token/ + secret key
sistem SIAKRED), lalu login user (core/middleware_sso.py) dan menyinkronkan scope
dari jabatan SIMDA (core/sso_sinkron.py).

Aktif hanya bila SSO_ENABLED=True dan SSO_SECRET_KEY terisi di .env.
"""
import hashlib
import logging
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("siakred.sso")


def aktif():
    kunci = getattr(settings, "SSO_SECRET_KEY", "") or ""
    return bool(getattr(settings, "SSO_ENABLED", False) and kunci and not kunci.upper().startswith("GANTI"))


def _keluarga(host):
    host = (host or "").split(":")[0].lower()
    return "g.id" if host.endswith("unisan-g.id") else "ac.id"


def basis_sso(request):
    """Alamat SSO sekeluarga domain dengan SIAKRED yang sedang diakses (cookie tidak lintas keluarga)."""
    if _keluarga(request.get_host()) == "g.id":
        return settings.SSO_BASE_URL_G
    return settings.SSO_BASE_URL_AC


def url_login(request, next_path="/app/"):
    """URL login SSO yang kembali ke SIAKRED (SSO menambahkan ?sso_token=...)."""
    kembali = request.build_absolute_uri(next_path or "/app/")
    return f"{basis_sso(request)}/auth/login/?{urlencode({'next': kembali})}"


def url_logout(request):
    return f"{basis_sso(request)}/auth/logout/"


def _kunci(token):
    return "sso_verif:" + hashlib.sha256(token.encode()).hexdigest()[:40]


def verifikasi(token, pakai_cache=True):
    """Return (data_user | None, pesan_error | None, sementara: bool).

    `sementara` True bila SSO tidak bisa dihubungi/membatasi (jangan putuskan sesi karenanya).
    Hasil sukses di-cache singkat agar tidak melampaui batas 60 request/menit SSO.
    """
    if not token or not aktif():
        return None, "SSO belum dikonfigurasi", True
    kunci = _kunci(token)
    if pakai_cache:
        hit = cache.get(kunci)
        if hit is not None:
            return hit.get("user"), hit.get("error"), False
    try:
        r = requests.post(
            settings.SSO_VERIFY_URL,
            json={"token": token},
            headers={"Authorization": f"Bearer {settings.SSO_SECRET_KEY}"},
            timeout=getattr(settings, "SSO_TIMEOUT", 5),
        )
    except requests.RequestException as e:
        logger.warning("SSO tidak dapat dihubungi: %s", e.__class__.__name__)
        return None, "SSO tidak dapat dihubungi", True
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code == 200 and data.get("valid"):
        cache.set(kunci, {"user": data.get("user")}, 120)
        return data.get("user"), None, False
    if r.status_code in (429,) or r.status_code >= 500:
        return None, data.get("error") or f"SSO error {r.status_code}", True
    if r.status_code == 401 and "secret key" in (data.get("error") or "").lower():
        logger.error("SSO menolak secret key SIAKRED (periksa SSO_SECRET_KEY)")
        return None, "Konfigurasi SSO SIAKRED tidak valid", True
    err = data.get("error") or f"Token ditolak ({r.status_code})"
    cache.set(kunci, {"user": None, "error": err}, 600)
    return None, err, False
