"""URL routing untuk master_akreditasi."""
from django.urls import path
from . import views

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

    # Import Excel
    path("import/", views.import_excel_home, name="import_home"),
    path("import/upload/", views.import_upload, name="import_upload"),
    path("import/preview/<int:pk>/", views.import_preview, name="import_preview"),
    path("import/commit/<int:pk>/", views.import_commit, name="import_commit"),
    path("import/cancel/<int:pk>/", views.import_cancel, name="import_cancel"),

    # Download Template
    path("import/template/", views.download_template_picker, name="template_picker"),
    path("import/template/<int:instrumen_id>/download/", views.download_template, name="template_download"),
]