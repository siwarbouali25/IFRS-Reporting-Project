from rest_framework import serializers

from .models import Bank


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            "id",
            "code",
            "name",
            "country",
            "sector",
            "created_at",
        ]