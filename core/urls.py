"""URL routing untuk app core."""
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing_page, name="landing"),
    # Landing publik detail pages (Sub-Batch 12A)
    path("fakultas/", views.fakultas_list, name="fakultas_list"),
    path("fakultas/<str:kode>/", views.fakultas_detail, name="fakultas_detail"),
    path("prodi/<str:kode>/", views.prodi_detail, name="prodi_detail"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("app/", views.dashboard_view, name="dashboard"),
    # Notifikasi (Step 9H)
    path("notifikasi/", views.notifikasi_list, name="notifikasi_list"),
    path("notifikasi/<int:notif_id>/read/", views.notifikasi_read, name="notifikasi_read"),
    path("notifikasi/mark-all-read/", views.notifikasi_mark_all_read, name="notifikasi_mark_all_read"),
    # Help Center (User Manual)
    path("bantuan/", views.help_index, name="help_index"),
    path("bantuan/<str:section>/", views.help_section, name="help_section"),
]