"""URL routing untuk master_akreditasi."""
from django.urls import path
from . import views, views_dtps_modal

app_name = "master_akreditasi"

urlpatterns = [
    # Instrumen
    path("instrumen/", views.instrumen_list, name="instrumen_list"),
    path("instrumen/<int:pk>/", views.instrumen_detail, name="instrumen_detail"),

    # Standar
    path("standar/", views.standar_list, name="standar_list"),
    path("standar/<int:pk>/", views.standar_detail, name="standar_detail"),

    # Mapping Prodi
    path("mapping-prodi/", views.mapping_list, name="mapping_list"),
    path("mapping-prodi/create/", views.mapping_create, name="mapping_create"),
    path("mapping-prodi/<int:pk>/edit/", views.mapping_edit, name="mapping_edit"),
    path("mapping-prodi/<int:pk>/delete/", views.mapping_delete, name="mapping_delete"),

    # Import Excel
    path("import/", views.import_excel_home, name="import_home"),
    path("import/upload/", views.import_upload, name="import_upload"),
    path("import/preview/<int:pk>/", views.import_preview, name="import_preview"),
    path("import/commit/<int:pk>/", views.import_commit, name="import_commit"),
    path("import/cancel/<int:pk>/", views.import_cancel, name="import_cancel"),

    # Download Template
    path("import/template/", views.download_template_picker, name="template_picker"),
    path("import/template/<int:instrumen_id>/download/", views.download_template, name="template_download"),

    # Mode Cepat — Manage Butir Dokumen
    path("butir/quick/", views.butir_quick_manage, name="butir_quick_manage"),
    path("butir/quick/save/", views.butir_quick_save, name="butir_quick_save"),
    path("butir/quick/<int:pk>/delete/", views.butir_quick_delete, name="butir_quick_delete"),
    # Modal AJAX: Data DTPS + BKD per butir (dipanggil dari halaman bundle)
    path(
        "sesi/<int:sesi_id>/butir/<int:butir_id>/dtps-bkd/",
        views_dtps_modal.butir_dtps_bkd_modal,
        name="butir_dtps_bkd_modal",
    ),
    # AJAX drill-down: detail BKD per dosen (inline expand di modal)
    path(
        "sesi/<int:sesi_id>/butir/<int:butir_id>/dosen/<str:nidn>/bkd-detail/",
        views_dtps_modal.dosen_bkd_detail,
        name="dosen_bkd_detail",
    ),
]