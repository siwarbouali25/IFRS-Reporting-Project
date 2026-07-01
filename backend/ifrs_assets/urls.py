from rest_framework.routers import DefaultRouter

from .views import IFRSAssetBundleViewSet, StyleAssetBundleViewSet

router = DefaultRouter()
router.register(r"ifrs-assets", IFRSAssetBundleViewSet, basename="ifrs-assets")
router.register(r"style-assets", StyleAssetBundleViewSet, basename="style-assets")

urlpatterns = router.urls