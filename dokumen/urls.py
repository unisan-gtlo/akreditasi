"""URL routing untuk app dokumen."""
from django.urls import path
from . import views, views_pustaka

app_name = "dokumen"

urlpatterns = [
    # =========================================
    # PUBLIK (alias di bawah /dokumen/publik/ untuk backward compat)
    # =========================================
    path("publik/", views.dokumen_publik_list, name="alias_publik_list"), 

    # =========================================
    # INTERNAL (login required)
    # =========================================
    # Butir
    path("", views.butir_saya, name="butir_saya"),
    path("pustaka/", views_pustaka.pustaka_dokumen, name="pustaka"),
    path("pustaka/tambah/", views_pustaka.pustaka_tambah, name="pustaka_tambah"),
    path("pustaka/kategori/", views_pustaka.kategori_kelola, name="kategori_kelola"),
    path("pustaka/kategori/<int:pk>/", views_pustaka.kategori_kelola, name="kategori_ubah"),
    path("pustaka/kategori/<int:pk>/hapus/", views_pustaka.kategori_hapus, name="kategori_hapus"),
    path("butir/<int:butir_id>/", views.butir_detail, name="butir_detail"),

    # Upload baru (untuk butir)
    path("butir/<int:butir_id>/upload/", views.dokumen_upload, name="dokumen_upload"),
    path("butir/<int:butir_id>/penciri/", views.pilih_penciri, name="pilih_penciri"),

    # Detail dokumen (preview inline)
    path("dokumen/<int:pk>/", views.dokumen_detail, name="dokumen_detail"),

    # Preview serve (untuk iframe)
    path("dokumen/<int:pk>/preview/", views.dokumen_preview_serve, name="dokumen_preview_serve"),

    # Download
    path("dokumen/<int:pk>/download/", views.dokumen_download, name="dokumen_download"),

    # Upload revisi
    path("dokumen/<int:pk>/revisi/", views.dokumen_upload_revisi, name="dokumen_upload_revisi"),

    # Edit metadata
    path("dokumen/<int:pk>/edit/", views.dokumen_edit, name="dokumen_edit"),

    # Access log (K7)
    path("dokumen/<int:pk>/log/", views.dokumen_access_log, name="dokumen_access_log"),
    # Dashboard Verifikasi (Step 9)
    path('verifikasi/', views.verifikasi_dashboard, name='verifikasi_dashboard'),
    path('verifikasi/<int:verifikasi_id>/review/', views.verifikasi_review, name='verifikasi_review'),
    path("verifikasi/bulk-action/", views.verifikasi_bulk_action, name="verifikasi_bulk_action"),
]