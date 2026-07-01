from rest_framework.routers import DefaultRouter

from .views import ReportGenerationJobViewSet, ReportVersionViewSet

router = DefaultRouter()
router.register(r"report-generation/jobs", ReportGenerationJobViewSet, basename="report-generation-jobs")
router.register(r"reports", ReportVersionViewSet, basename="reports")

urlpatterns = router.urls