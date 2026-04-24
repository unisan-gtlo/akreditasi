"""URL routing untuk app laporan."""
from django.urls import path
from . import views

app_name = "laporan"

urlpatterns = [
    path("", views.laporan_index, name="laporan_index"),
    path("sesi/<int:sesi_id>/", views.laporan_sesi_detail, name="laporan_sesi_detail"),
    path("prodi/", views.laporan_prodi_list, name="laporan_prodi_list"),
    path("heatmap/", views.laporan_heatmap, name="laporan_heatmap"),
    path("audit/", views.laporan_audit_trail, name="laporan_audit_trail"),
]
