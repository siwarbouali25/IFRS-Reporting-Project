from rest_framework import serializers

from .models import IFRSAssetBundle, StyleAssetBundle


class IFRSAssetBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IFRSAssetBundle
        fields = [
            "id",
            "name",
            "version",
            "minio_prefix",
            "status",
            "created_at",
        ]


class StyleAssetBundleSerializer(serializers.ModelSerializer):
    bank_code = serializers.CharField(source="bank.code", read_only=True)

    class Meta:
        model = StyleAssetBundle
        fields = [
            "id",
            "name",
            "version",
            "bank",
            "bank_code",
            "minio_prefix",
            "status",
            "created_at",
        ]