"""
Middleware core SIAKRED.
"""
import time

from django.conf import settings


class SessionRefreshMiddleware:
    """Perpanjang session idle-timeout tanpa menulis ke DB di setiap request.

    Pengganti SESSION_SAVE_EVERY_REQUEST=True: session hanya ditandai
    `modified` kalau penyegaran terakhir sudah lewat SESSION_REFRESH_INTERVAL.
    Efeknya timeout tetap ~30 menit sejak aktivitas terakhir (selisih
    maks. sebesar interval), tapi tulis session turun dari tiap klik jadi
    paling banyak sekali per interval.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.interval = getattr(settings, "SESSION_REFRESH_INTERVAL", 300)

    def __call__(self, request):
        response = self.get_response(request)

        session = getattr(request, "session", None)
        # Pengunjung tanpa session (publik) dilewati supaya tidak dibuatkan session baru
        if session is None or not session.session_key:
            return response

        now = int(time.time())
        if now - session.get("_refreshed_at", 0) >= self.interval:
            session["_refreshed_at"] = now
        return response
