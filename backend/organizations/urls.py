from rest_framework.routers import DefaultRouter

from .views import BankViewSet

router = DefaultRouter()
router.register(r"banks", BankViewSet, basename="banks")

urlpatterns = router.urls