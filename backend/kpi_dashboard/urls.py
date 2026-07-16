from django.urls import path

from .views import KPIDashboardView


urlpatterns = [
    path(
        "batches/<uuid:batch_id>/",
        KPIDashboardView.as_view(),
        name="kpi-dashboard",
    ),
]