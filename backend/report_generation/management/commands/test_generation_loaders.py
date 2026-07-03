from django.conf import settings
from django.core.management.base import BaseCommand

from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from organizations.models import Bank
from payloads.models import PayloadManifest

from generation_engine.loaders.payload_loader import load_payloads_from_prefix
from generation_engine.loaders.requirements_loader import load_requirements_from_prefix
from generation_engine.loaders.style_loader import load_style_assets_from_prefix


class Command(BaseCommand):
    help = "Test generation engine loaders for BANK01."

    def handle(self, *args, **options):
        bank = Bank.objects.get(code="BANK01")

        payload_manifest = PayloadManifest.objects.get(
            bank=bank,
            reporting_year=2024,
            version="v1",
            status="available",
        )

        ifrs_bundle = IFRSAssetBundle.objects.get(
            version="ifrs_s1_s2_2024",
            status="active",
        )

        style_bundle = StyleAssetBundle.objects.get(
            version="bank01_style_v1",
            status="active",
        )

        input_root = settings.GENERATION_INPUT_ROOT

        payload_result = load_payloads_from_prefix(
            input_root=input_root,
            minio_prefix=payload_manifest.minio_prefix,
            bank_code=bank.code,
        )

        requirements_result = load_requirements_from_prefix(
            input_root=input_root,
            minio_prefix=ifrs_bundle.minio_prefix,
        )

        style_result = load_style_assets_from_prefix(
            input_root=input_root,
            minio_prefix=style_bundle.minio_prefix,
        )

        self.stdout.write(self.style.SUCCESS("Generation loaders test completed."))

        self.stdout.write("")
        self.stdout.write("Payloads:")
        self.stdout.write(f"  Loaded files: {len(payload_result.loaded_files)}")
        self.stdout.write(f"  Missing files: {len(payload_result.missing_files)}")
        self.stdout.write(f"  Warnings: {len(payload_result.warnings)}")

        self.stdout.write("")
        self.stdout.write("IFRS requirements:")
        self.stdout.write(f"  Loaded files: {len(requirements_result.loaded_files)}")
        self.stdout.write(f"  Missing files: {len(requirements_result.missing_files)}")
        self.stdout.write(f"  Warnings: {len(requirements_result.warnings)}")

        self.stdout.write("")
        self.stdout.write("Style assets:")
        self.stdout.write(f"  Loaded files: {len(style_result.loaded_files)}")
        self.stdout.write(f"  Missing files: {len(style_result.missing_files)}")
        self.stdout.write(f"  Warnings: {len(style_result.warnings)}")

        total_warnings = (
            len(payload_result.warnings)
            + len(requirements_result.warnings)
            + len(style_result.warnings)
        )

        if total_warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Warnings found:"))

            for warning in [
                *payload_result.warnings,
                *requirements_result.warnings,
                *style_result.warnings,
            ]:
                self.stdout.write(
                    f"  [{warning.stage}] {warning.warning_type}: {warning.message}"
                )