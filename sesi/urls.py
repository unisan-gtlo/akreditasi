"""URL routing untuk app sesi."""
from django.urls import path
from . import views

app_name = "sesi"

urlpatterns = [
    path("", views.sesi_list, name="sesi_list"),
    path("dashboard/", views.dashboard_sesi, name="dashboard_sesi"),
    path("baru/", views.sesi_create, name="sesi_create"),
    path("<int:pk>/", views.sesi_detail, name="sesi_detail"),
    path("<int:pk>/edit/", views.sesi_edit, name="sesi_edit"),
    path("<int:pk>/cancel/", views.sesi_cancel, name="sesi_cancel"),
    path("<int:pk>/delete/", views.sesi_delete, name="sesi_delete"),
    path("<int:pk>/timeline/", views.sesi_timeline, name="sesi_timeline"),

    # Milestone management
    path("<int:sesi_pk>/milestone/<int:ms_pk>/progress/", views.milestone_mark_progress, name="milestone_mark_progress"),
    path("<int:sesi_pk>/milestone/<int:ms_pk>/selesai/", views.milestone_mark_selesai, name="milestone_mark_selesai"),
    path("<int:sesi_pk>/milestone/<int:ms_pk>/reset/", views.milestone_reset, name="milestone_reset"),
    path("<int:sesi_pk>/milestone/<int:ms_pk>/edit/", views.milestone_edit, name="milestone_edit"),
]