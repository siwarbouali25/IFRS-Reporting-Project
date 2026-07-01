from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "email",
            "role",
            "department",
            "mfa_enabled",
            "is_active",
        )


class AdminCreateUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "email",
            "password",
            "role",
            "department",
            "mfa_enabled",
        )
        read_only_fields = ("id", "mfa_enabled")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["email"] = user.email
        token["role"] = user.role
        token["full_name"] = user.full_name

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = {
            "id": self.user.id,
            "full_name": self.user.full_name,
            "email": self.user.email,
            "role": self.user.role,
            "department": self.user.department,
            "mfa_enabled": self.user.mfa_enabled,
        }

        return data
    


class MFASetupVerifySerializer(serializers.Serializer):
        code = serializers.CharField(max_length=6)


class MFALoginVerifySerializer(serializers.Serializer):
        mfa_token = serializers.CharField()
        code = serializers.CharField(max_length=6)