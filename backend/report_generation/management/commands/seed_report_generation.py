from django.conf import settings
from django.core.management.base import BaseCommand

from ifrs_assets.models import (
    IFRSAssetBundle,
    StyleAssetBundle,
)
from organizations.models import Bank
from payloads.models import PayloadManifest


class Command(BaseCommand):
    help = (
        "Seed initial report-generation data for "
        "BANK01."
    )

    def handle(self, *args, **options):
        bank, _ = Bank.objects.update_or_create(
            code="BANK01",
            defaults={
                "name": (
                    "Eurolux Universal Bank AG"
                ),
                "country": "DE",
                "sector": "Banking",
            },
        )

        static_payload_folder = (
            settings.GENERATION_INPUT_ROOT
            / "payloads"
            / "BANK01"
            / "2024"
            / "v1"
        )

        PayloadManifest.objects.update_or_create(
            bank=bank,
            reporting_year=2024,
            version="v1",
            defaults={
                "source_batch": None,
                "storage_backend": (
                    PayloadManifest.StorageBackend.LOCAL
                ),
                "local_folder": str(
                    static_payload_folder.resolve()
                ),
                "minio_prefix": (
                    "payloads/BANK01/2024/v1/"
                ),
                "source_manifest_path": "",
                "status": (
                    PayloadManifest.Status.AVAILABLE
                ),
            },
        )

        IFRSAssetBundle.objects.update_or_create(
            version="ifrs_s1_s2_2024",
            defaults={
                "name": "IFRS S1/S2 Requirements",
                "minio_prefix": (
                    "ifrs-assets/IFRS-S1-S2/2024/"
                ),
                "status": (
                    IFRSAssetBundle.Status.ACTIVE
                ),
            },
        )

        StyleAssetBundle.objects.update_or_create(
            version="bank01_style_v1",
            defaults={
                "name": "BANK01 Style Assets",
                "bank": bank,
                "minio_prefix": (
                    "style-assets/BANK01/style-v1/"
                ),
                "status": (
                    StyleAssetBundle.Status.ACTIVE
                ),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded BANK01 report-generation "
                "data successfully."
            )
        )