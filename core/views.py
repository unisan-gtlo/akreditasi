"""
Views untuk app core (authentication & dashboard).
"""
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import never_cache

from .forms import LoginForm, MathCaptcha
from .models import LoginAttempt, DeviceSession


# ============================================
# HELPERS
# ============================================

def get_client_ip(request):
    """Ambil IP address asli client."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_user_agent(request):
    """Ambil user-agent string."""
    return request.META.get("HTTP_USER_AGENT", "")[:500]


def make_device_fingerprint(ip, user_agent):
    """Generate fingerprint dari IP prefix + user-agent."""
    ip_prefix = ".".join(ip.split(".")[:2]) if "." in ip else ip[:8]
    raw = f"{ip_prefix}|{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def parse_user_agent(ua):
    """Parse user-agent sederhana ke browser, OS, device type."""
    ua_lower = ua.lower()

    if "edg/" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "safari" in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower:
        browser = "Safari"
    elif "opera" in ua_lower or "opr/" in ua_lower:
        browser = "Opera"
    else:
        browser = "Lainnya"

    if "windows" in ua_lower:
        os_name = "Windows"
    elif "mac os" in ua_lower or "macintosh" in ua_lower:
        os_name = "macOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower or "ios" in ua_lower:
        os_name = "iOS"
    elif "linux" in ua_lower:
        os_name = "Linux"
    else:
        os_name = "Lainnya"

    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        device_type = "Mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device_type = "Tablet"
    else:
        device_type = "Desktop"

    return browser, os_name, device_type


def count_recent_failed_attempts(ip_address, minutes=15):
    """Hitung percobaan gagal dari IP dalam X menit terakhir."""
    since = timezone.now() - timezone.timedelta(minutes=minutes)
    return LoginAttempt.objects.filter(
        ip_address=ip_address,
        status__in=[
            LoginAttempt.Status.FAILED_PASSWORD,
            LoginAttempt.Status.FAILED_USERNAME,
            LoginAttempt.Status.FAILED_CAPTCHA,
        ],
        waktu__gte=since,
    ).count()


def clear_recent_failed_attempts(ip_address, minutes=15):
    """Hapus failed attempts dari IP setelah login berhasil."""
    since = timezone.now() - timezone.timedelta(minutes=minutes)
    LoginAttempt.objects.filter(
        ip_address=ip_address,
        status__in=[
            LoginAttempt.Status.FAILED_PASSWORD,
            LoginAttempt.Status.FAILED_USERNAME,
            LoginAttempt.Status.FAILED_CAPTCHA,
        ],
        waktu__gte=since,
    ).delete()


def record_attempt(username, user, status, request):
    """Simpan login attempt ke database."""
    LoginAttempt.objects.create(
        username_attempted=username[:200],
        user=user,
        status=status,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


def track_device_session(user, request):
    """Track device yang login. Return (session, is_new_device)."""
    ip = get_client_ip(request)
    ua = get_user_agent(request)
    fingerprint = make_device_fingerprint(ip, ua)
    browser, os_name, device_type = parse_user_agent(ua)

    session, created = DeviceSession.objects.update_or_create(
        user=user,
        device_fingerprint=fingerprint,
        defaults={
            "ip_address": ip,
            "user_agent": ua,
            "browser_name": browser,
            "os_name": os_name,
            "device_type": device_type,
            "last_ip": ip,
            "aktif": True,
        },
    )
    return session, created


def send_new_device_notification(user, device_session, request):
    """Kirim email notifikasi login dari device baru."""
    if not user.email:
        return
    if not settings.EMAIL_HOST_USER:
        return

    subject = "Login Baru Terdeteksi — SIAKRED UNISAN"
    message = f"""Halo {user.nama_lengkap},

Ada login baru ke akun Anda di SIAKRED UNISAN dari device yang belum pernah kami kenali sebelumnya.

Detail Login:
  Waktu    : {device_session.first_seen.strftime('%d %B %Y, %H:%M:%S')} WITA
  IP       : {device_session.ip_address}
  Browser  : {device_session.browser_name}
  OS       : {device_session.os_name}
  Device   : {device_session.device_type}

Jika ini BUKAN Anda, segera:
1. Ganti password Anda
2. Hubungi administrator Pustikom UNISAN

Jika ini Anda, abaikan pesan ini.

--
SIAKRED UNISAN
Sistem Informasi Arsip Akreditasi
https://akreditasi.unisan-g.id
"""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass


# ============================================
# LANDING PAGE PUBLIK
# ============================================

def landing_page(request):
    """Halaman landing publik SIAKRED."""
    context = {
        "page_title": "SIAKRED UNISAN — Arsip Akreditasi",
    }
    return render(request, "landing/index.html", context)


# ============================================
# LOGIN VIEW
# ============================================

@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    """Login dengan CAPTCHA, lockout, device tracking."""

    if request.user.is_authenticated:
        return redirect("core:dashboard")

    ip = get_client_ip(request)
    failed_count = count_recent_failed_attempts(ip, minutes=15)
    require_captcha = failed_count >= 2

    if failed_count >= 5:
        return render(
            request,
            "auth/locked.html",
            {
                "page_title": "Akun Dikunci Sementara",
                "wait_minutes": 15,
            },
            status=429,
        )

    if request.method == "POST":
        form = LoginForm(
            request.POST,
            request=request,
            require_captcha=require_captcha,
        )

        identifier = request.POST.get("identifier", "").strip()

        if form.is_valid():
            user = form.get_user()
            remember_me = form.cleaned_data.get("remember_me", False)

            if not remember_me:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(60 * 60 * 24 * 14)

            device_session, is_new_device = track_device_session(user, request)

            if is_new_device:
                send_new_device_notification(user, device_session, request)

            # Reset failed attempts saat login sukses
            clear_recent_failed_attempts(ip, minutes=15)

            login(request, user)
            record_attempt(identifier, user, LoginAttempt.Status.SUCCESS, request)

            messages.success(
                request,
                f"Selamat datang, {user.nama_lengkap}!"
            )
            return redirect("core:dashboard")
        else:
            error_codes = []
            for errs in form.errors.as_data().values():
                for e in errs:
                    error_codes.append(e.code)

            if "captcha_required" in error_codes or "captcha_invalid" in error_codes:
                status = LoginAttempt.Status.FAILED_CAPTCHA
            elif "inactive" in error_codes:
                status = LoginAttempt.Status.FAILED_INACTIVE
            else:
                status = LoginAttempt.Status.FAILED_PASSWORD

            record_attempt(identifier or "(kosong)", None, status, request)

            failed_count = count_recent_failed_attempts(ip, minutes=15)
            require_captcha = failed_count >= 2
    else:
        form = LoginForm(request=request, require_captcha=require_captcha)

    captcha_data = None
    if require_captcha:
        question, answer, token = MathCaptcha.generate()
        captcha_data = {
            "question": question,
            "token": token,
        }
        if "captcha_question" in form.fields:
            form.fields["captcha_question"].initial = question
            form.fields["captcha_token"].initial = token

    context = {
        "page_title": "Login — SIAKRED UNISAN",
        "form": form,
        "require_captcha": require_captcha,
        "captcha": captcha_data,
        "failed_count": failed_count,
    }
    return render(request, "auth/login.html", context)


# ============================================
# LOGOUT VIEW
# ============================================

@require_POST
def logout_view(request):
    """Logout & redirect ke landing."""
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, "Anda telah berhasil logout.")
    return redirect("core:landing")


# ============================================
# DASHBOARD
# ============================================

@login_required(login_url="/login/")
def dashboard_view(request):
    """Dashboard internal SIAKRED (placeholder)."""
    user = request.user
    scopes = user.scopes.filter(aktif=True) if hasattr(user, "scopes") else []

    current_fingerprint = make_device_fingerprint(
        get_client_ip(request), get_user_agent(request)
    )
    last_device = (
        DeviceSession.objects.filter(user=user)
        .exclude(device_fingerprint=current_fingerprint)
        .order_by("-last_seen")
        .first()
    )

    context = {
        "page_title": "Dashboard",
        "active_menu": "dashboard",
        "user": user,
        "scopes": scopes,
        "last_device": last_device,
    }
    return render(request, "dashboard/index.html", context)