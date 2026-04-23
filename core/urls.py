"""URL routing untuk app core."""
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("app/", views.dashboard_view, name="dashboard"),
]