import os

from django.core.management.base import BaseCommand

from ifrs_assets.models import (
    IFRSAssetBundle,
    StyleAssetBundle,
)
from organizations.models import Bank


class Command(BaseCommand):
    help = (
        "Create or reactivate the default IFRS and style "
        "asset-bundle metadata after changing databases."
    )

    def handle(self, *args, **options):
        bank_code = os.getenv(
            "DEFAULT_REPORT_BANK_CODE",
            "BANK01",
        )
        bank_name = os.getenv(
            "DEFAULT_REPORT_BANK_NAME",
            "Eurolux Universal Bank AG",
        )

        ifrs_version = os.getenv(
            "DEFAULT_IFRS_ASSET_VERSION",
            "ifrs_s1_s2_2024",
        )
        ifrs_prefix = os.getenv(
            "DEFAULT_IFRS_ASSET_PREFIX",
            "ifrs-assets/IFRS-S1-S2/2024/",
        )

        style_version = os.getenv(
            "DEFAULT_STYLE_ASSET_VERSION",
            "bank01_style_v1",
        )
        style_prefix = os.getenv(
            "DEFAULT_STYLE_ASSET_PREFIX",
            "style-assets/BANK01/style-v1/",
        )

        bank, _ = Bank.objects.update_or_create(
            code=bank_code,
            defaults={
                "name": bank_name,
            },
        )

        ifrs_bundle, _ = (
            IFRSAssetBundle.objects.update_or_create(
                version=ifrs_version,
                defaults={
                    "name": "IFRS S1/S2 reporting assets",
                    "minio_prefix": ifrs_prefix,
                    "status": (
                        IFRSAssetBundle.Status.ACTIVE
                    ),
                },
            )
        )

        style_bundle, _ = (
            StyleAssetBundle.objects.update_or_create(
                version=style_version,
                defaults={
                    "name": (
                        f"{bank_code} report style"
                    ),
                    "bank": bank,
                    "minio_prefix": style_prefix,
                    "status": (
                        StyleAssetBundle.Status.ACTIVE
                    ),
                },
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Active asset metadata is ready."
            )
        )
        self.stdout.write(
            (
                f"IFRS: {ifrs_bundle.version} -> "
                f"{ifrs_bundle.minio_prefix}"
            )
        )
        self.stdout.write(
            (
                f"Style: {style_bundle.version} -> "
                f"{style_bundle.minio_prefix}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Confirm that both prefixes contain the "
                "corresponding files in MinIO."
            )
        )
