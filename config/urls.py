from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from readings.views import protected_photo

urlpatterns = [
    path("media/<path:path>", protected_photo, name="protected_photo"),
    path("admin/", admin.site.urls),
    path(
        "cuentas/ingresar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("cuentas/salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("readings.urls")),
]
