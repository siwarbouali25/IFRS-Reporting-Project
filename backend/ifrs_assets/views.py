from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import IFRSAssetBundle, StyleAssetBundle
from .serializers import IFRSAssetBundleSerializer, StyleAssetBundleSerializer


class IFRSAssetBundleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IFRSAssetBundleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IFRSAssetBundle.objects.filter(status="active").order_by("-created_at")


class StyleAssetBundleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StyleAssetBundleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = StyleAssetBundle.objects.select_related("bank").filter(status="active")

        bank_code = self.request.query_params.get("bank_code")
        if bank_code:
            queryset = queryset.filter(bank__code=bank_code)

        return queryset.order_by("-created_at")