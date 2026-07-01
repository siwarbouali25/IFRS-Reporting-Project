import base64
from io import BytesIO

import qrcode
from django.contrib.auth import authenticate, get_user_model
from django.core import signing
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsAdminRole
from .serializers import (
    AdminCreateUserSerializer,
    MFALoginVerifySerializer,
    MFASetupVerifySerializer,
    UserSerializer,
)

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    refresh["email"] = user.email
    refresh["role"] = user.role
    refresh["full_name"] = user.full_name

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def get_user_payload(user):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "mfa_enabled": user.mfa_enabled,
    }


def make_qr_code_data_url(config_url):
    qr = qrcode.make(config_url)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{image_base64}"


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, email=email, password=password)

        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.mfa_enabled:
            mfa_token = signing.dumps(
                {"user_id": user.id},
                salt="mfa-login",
            )

            return Response(
                {
                    "mfa_required": True,
                    "mfa_token": mfa_token,
                    "detail": "MFA verification required.",
                }
            )

        tokens = get_tokens_for_user(user)

        return Response(
            {
                **tokens,
                "mfa_required": False,
                "mfa_setup_required": True,
                "user": get_user_payload(user),
            }
        )


class MFALoginVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MFALoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mfa_token = serializer.validated_data["mfa_token"]
        code = serializer.validated_data["code"]

        try:
            payload = signing.loads(
                mfa_token,
                salt="mfa-login",
                max_age=300,
            )
        except signing.SignatureExpired:
            return Response(
                {"detail": "MFA login token expired. Please login again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Invalid MFA login token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            user = User.objects.get(id=payload["user_id"], is_active=True)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        device = TOTPDevice.objects.filter(
            user=user,
            confirmed=True,
        ).first()

        if not device:
            return Response(
                {"detail": "No confirmed MFA device found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed, data = device.verify_is_allowed()

        if not allowed:
            return Response(
                {
                    "detail": "Too many failed attempts. Please wait before trying again.",
                    "reason": data,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not device.verify_token(code):
            return Response(
                {"detail": "Invalid MFA code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tokens = get_tokens_for_user(user)

        return Response(
            {
                **tokens,
                "mfa_required": False,
                "user": get_user_payload(user),
            }
        )


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.mfa_enabled:
            return Response(
                {"detail": "MFA is already enabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device, created = TOTPDevice.objects.get_or_create(
            user=user,
            name="default",
            confirmed=False,
        )

        config_url = device.config_url
        qr_code = make_qr_code_data_url(config_url)

        return Response(
            {
                "qr_code": qr_code,
                "config_url": config_url,
                "detail": "Scan the QR code with an authenticator app.",
            }
        )


class MFASetupVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFASetupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        user = request.user

        device = TOTPDevice.objects.filter(
            user=user,
            confirmed=False,
            name="default",
        ).first()

        if not device:
            return Response(
                {"detail": "No MFA setup device found. Generate QR code first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed, data = device.verify_is_allowed()

        if not allowed:
            return Response(
                {
                    "detail": "Too many failed attempts. Please wait before trying again.",
                    "reason": data,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not device.verify_token(code):
            return Response(
                {"detail": "Invalid MFA code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device.confirmed = True
        device.save()

        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])

        return Response(
            {
                "detail": "MFA enabled successfully.",
                "user": get_user_payload(user),
            }
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class AdminCreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = AdminCreateUserSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]