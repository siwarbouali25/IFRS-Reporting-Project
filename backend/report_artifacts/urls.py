from rest_framework.routers import DefaultRouter

from .views import ReportArtifactViewSet

router = DefaultRouter()
router.register(r"artifacts", ReportArtifactViewSet, basename="artifacts")

urlpatterns = router.urls