from django.urls import path

from .views import (
    AssessmentGenerateView,
    AssessmentLatestView,
    RiskAnalysisDetailView,
    RiskAnalysisListView,
    RiskAnalysisUploadView,
)

urlpatterns = [
    path("risk/upload/", RiskAnalysisUploadView.as_view(), name="risk_upload"),
    path("risk/analyses/", RiskAnalysisListView.as_view(), name="risk_analysis_list"),
    path("risk/analyses/<uuid:id>/", RiskAnalysisDetailView.as_view(), name="risk_analysis_detail"),
    path("risk/analyses/<uuid:id>/assessment/", AssessmentGenerateView.as_view(), name="risk_assessment_generate"),
    path("risk/analyses/<uuid:id>/assessment/latest/", AssessmentLatestView.as_view(), name="risk_assessment_latest"),
]
