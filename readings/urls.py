from django.urls import path

from . import views

app_name = "readings"

urlpatterns = [
    path("", views.reading_grid, name="grid"),
    path("grilla-anual/", views.annual_grid, name="annual_grid"),
    path("calendario/eventos/", views.calendar_events, name="calendar_events"),
]
