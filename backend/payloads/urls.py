from rest_framework.routers import DefaultRouter

from .views import PayloadManifestViewSet

router = DefaultRouter()
router.register(r"payload-manifests", PayloadManifestViewSet, basename="payload-manifests")

urlpatterns = router.urls