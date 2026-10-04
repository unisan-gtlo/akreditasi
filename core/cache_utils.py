"""
Helper cache SIAKRED: key terpusat + invalidasi berbasis versi.

Pola versi: key data memuat nomor versi, jadi "hapus semua cache X"
cukup dengan menaikkan nomor versi (tanpa perlu tahu key per-user).
"""
from django.core.cache import cache

SIDEBAR_STATS_KEY = "sidebar_stats"
SIDEBAR_STATS_TTL = 60 * 10

PUBLIK_TTL = 60 * 5

NOTIF_TTL = 60
VERIF_TTL = 60
VERIF_VERSION_KEY = "verif_version"


def get_version(key):
    version = cache.get(key)
    if version is None:
        version = 1
        cache.set(key, version, None)
    return version


def bump_version(key):
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, None)


def notif_key(user_id):
    return f"notif_ctx:{user_id}"


def verif_key(user_id):
    return f"verif_ctx:{user_id}:v{get_version(VERIF_VERSION_KEY)}"


def invalidate_notif(user_id):
    cache.delete(notif_key(user_id))


def invalidate_verif():
    bump_version(VERIF_VERSION_KEY)


def invalidate_sidebar_stats():
    cache.delete(SIDEBAR_STATS_KEY)


def invalidate_publik():
    cache.delete_many(["publik_stats", "publik_fakultas_list", "publik_institusi_simda"])
