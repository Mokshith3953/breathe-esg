from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me_view),

    # Dashboard
    path("dashboard/stats/", views.dashboard_stats),

    # Ingestion
    path("ingest/sap/", views.IngestSAPView.as_view()),
    path("ingest/utility/", views.IngestUtilityView.as_view()),
    path("ingest/travel/", views.IngestTravelView.as_view()),
    path("ingestion-runs/", views.ingestion_runs),

    # Records
    path("records/", views.records_list),
    path("records/bulk-approve/", views.record_bulk_approve),
    path("records/<int:pk>/", views.record_detail),
    path("records/<int:pk>/approve/", views.record_approve),
    path("records/<int:pk>/reject/", views.record_reject),
    path("records/<int:pk>/flag/", views.record_flag),
    path("records/<int:pk>/note/", views.record_note),

    # Anomalies
    path("anomalies/", views.anomalies_list),
    path("anomalies/<int:pk>/resolve/", views.anomaly_resolve),
]
