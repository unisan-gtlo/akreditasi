"""URL routing utama SIAKRED."""
from django.contrib import admin
from django.urls import path, include
from sesi.views import sesi_bundle_public, sesi_bundle_zip_public
from django.conf import settings
from django.conf.urls.static import static

from dokumen import views as dokumen_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # PUBLIK shortcuts (no login)
    path("publik/", dokumen_views.dokumen_publik_list, name="dokumen_publik_list"),
    path("publik/<int:pk>/", dokumen_views.dokumen_publik_detail, name="dokumen_publik_detail"),
    path("publik/<int:pk>/preview/", dokumen_views.dokumen_publik_preview_serve, name="dokumen_publik_preview"),
    path("publik/<int:pk>/download/", dokumen_views.dokumen_publik_download, name="dokumen_publik_download"),

    # PUBLIC DOC LINK (untuk hyperlink di LED — UUID token, no login)
    path("d/<uuid:token>/", dokumen_views.public_dokumen, name="public_dokumen"),
    path("d/<uuid:token>/download/", dokumen_views.public_download, name="public_download"),

    # Internal apps
    path("master/", include("master_akreditasi.urls")),
    path("dokumen/", include("dokumen.urls")),
        path("laporan/", include("laporan.urls")),
    path("sesi/", include("sesi.urls")),     # ← TAMBAH BARIS INI

    # Core (landing, login, dashboard)
    path("", include("core.urls")),
    path('bundle/<str:token>/', sesi_bundle_public, name='bundle_public'),
    path('bundle/<str:token>/zip/', sesi_bundle_zip_public, name='bundle_public_zip'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)