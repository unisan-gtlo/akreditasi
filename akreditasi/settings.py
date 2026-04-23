"""
Django settings for akreditasi project (SIAKRED).
Multi-schema: akreditasi (own) + master (SIMDA read-only) + public (SSO read-only)
"""

from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(BASE_DIR / ".env")

# ==========================================
# SECURITY
# ==========================================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-unsafe-secret-key-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]

# ==========================================
# APPLICATIONS
# ==========================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes", 

    # SIAKRED apps
    "core",
    "master_akreditasi",
    "dokumen",
    "sesi",
    "asesor",
    "laporan",
]

# ==========================================
# AUTHENTICATION BACKENDS (django-axes)
# ==========================================
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "akreditasi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.sidebar_stats",
            ],
        },
    },
]

WSGI_APPLICATION = "akreditasi.wsgi.application"

# ==========================================
# DATABASE - Multi-schema PostgreSQL
# search_path: akreditasi (own tables) -> master (SIMDA) -> public (SSO)
# ==========================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "unisan_db"),
        "USER": os.getenv("DB_USER", "akreditasi_user"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "OPTIONS": {
             "options": "-c search_path=akreditasi"
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==========================================
# PASSWORD VALIDATION
# ==========================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==========================================
# I18N & TIME
# ==========================================
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "id")
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Makassar")
USE_I18N = True
USE_TZ = True

# ==========================================
# STATIC & MEDIA
# ==========================================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==========================================
# FILE UPLOAD
# ==========================================
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ==========================================
# SSO INTEGRATION
# ==========================================
SSO_BASE_URL = os.getenv("SSO_BASE_URL", "https://sso.unisan-g.id")
SSO_SECRET_KEY = os.getenv("SSO_SECRET_KEY", "")
SSO_COOKIE_DOMAIN = os.getenv("SSO_COOKIE_DOMAIN", ".unisan-g.id")

# ==========================================
# SITE
# ==========================================
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
SITE_NAME = os.getenv("SITE_NAME", "SIAKRED UNISAN")

# ==========================================
# LIBREOFFICE
# ==========================================
LIBREOFFICE_PATH = os.getenv("LIBREOFFICE_PATH", "")

# ==========================================
# LOGGING
# ==========================================
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "siakred.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["file", "console"],
        "level": "INFO",
    },
}

# ==========================================
# CUSTOM USER MODEL
# ==========================================
AUTH_USER_MODEL = "core.User"

# ==========================================
# LOGIN / LOGOUT
# ==========================================
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/app/"
LOGOUT_REDIRECT_URL = "/"

# ==========================================
# EMAIL CONFIGURATION (Gmail SMTP)
# ==========================================
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "SIAKRED UNISAN <noreply@unisan-g.id>")

# ==========================================
# DJANGO-AXES (Brute Force Protection)
# ==========================================
AXES_ENABLED = os.getenv("AXES_ENABLED", "True").lower() == "true"
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = float(os.getenv("AXES_COOLOFF_TIME", "0.25"))  # dalam jam (0.25 = 15 menit)
AXES_RESET_ON_SUCCESS = os.getenv("AXES_RESET_ON_SUCCESS", "True").lower() == "true"
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_LOCKOUT_TEMPLATE = "auth/locked.html"
AXES_VERBOSE = True

# ==========================================
# SECURITY HARDENING
# ==========================================
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Session inactivity timeout (30 menit)
SESSION_COOKIE_AGE = 60 * 30
SESSION_SAVE_EVERY_REQUEST = True
# ==========================================
# PRODUCTION HTTPS & PROXY SETTINGS
# ==========================================
# CSRF Trusted Origins (wajib untuk Django 4+ dengan HTTPS)
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
]

# HTTPS Settings (hanya aktif kalau DEBUG=False di production)
if not DEBUG:
    # Force redirect HTTP -> HTTPS
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"

    # Behind nginx reverse proxy (penting untuk SSL detection)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # HTTP Strict Transport Security (1 tahun)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Force HTTPS untuk cookies (sudah di-handle env var di atas, ini fallback)
    if not os.getenv("SESSION_COOKIE_SECURE"):
        SESSION_COOKIE_SECURE = True
    if not os.getenv("CSRF_COOKIE_SECURE"):
        CSRF_COOKIE_SECURE = True

# ==========================================
# LOGGING (production-friendly)
# ==========================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
