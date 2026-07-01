from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminCreateUserView,
    LoginView,
    MFALoginVerifyView,
    MFASetupVerifyView,
    MFASetupView,
    MeView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("auth/mfa/setup/", MFASetupView.as_view(), name="mfa_setup"),
    path("auth/mfa/verify-setup/", MFASetupVerifyView.as_view(), name="mfa_verify_setup"),
    path("auth/mfa/verify-login/", MFALoginVerifyView.as_view(), name="mfa_verify_login"),

    path("accounts/me/", MeView.as_view(), name="me"),
    path("accounts/users/create/", AdminCreateUserView.as_view(), name="admin_create_user"),
]