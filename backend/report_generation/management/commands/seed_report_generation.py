from django.core.management.base import BaseCommand

from organizations.models import Bank
from payloads.models import PayloadManifest
from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle


class Command(BaseCommand):
    help = "Seed initial report generation data for BANK01."

    def handle(self, *args, **options):
        bank, _ = Bank.objects.update_or_create(
            code="BANK01",
            defaults={
                "name": "Eurolux Universal Bank AG",
                "country": "Luxembourg",
                "sector": "Banking",
            },
        )

        PayloadManifest.objects.update_or_create(
            bank=bank,
            reporting_year=2024,
            version="v1",
            defaults={
                "minio_prefix": "payloads/BANK01/2024/v1/",
                "status": "available",
            },
        )

        IFRSAssetBundle.objects.update_or_create(
            version="ifrs_s1_s2_2024",
            defaults={
                "name": "IFRS S1/S2 Requirements",
                "minio_prefix": "ifrs-assets/IFRS-S1-S2/2024/",
                "status": "active",
            },
        )

        StyleAssetBundle.objects.update_or_create(
            version="bank01_style_v1",
            defaults={
                "name": "BANK01 Style Assets",
                "bank": bank,
                "minio_prefix": "style-assets/BANK01/style-v1/",
                "status": "active",
            },
        )

        self.stdout.write(
            self.style.SUCCESS("Seeded BANK01 report generation data successfully.")
        )