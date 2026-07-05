from django.conf import settings
from django.core.management.base import BaseCommand

from generation_engine.evidence.evidence_mapper import build_evidence_maps
from generation_engine.loaders.payload_loader import load_payloads_from_prefix
from generation_engine.loaders.requirements_loader import load_requirements_from_prefix
from generation_engine.loaders.style_loader import load_style_assets_from_prefix
from generation_engine.planning.disclosure_plan_builder import build_disclosure_plans
from generation_engine.writing.llm_section_writer import build_llm_section_drafts
from generation_engine.writing.writer_context import build_writer_contexts

from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from organizations.models import Bank
from payloads.models import PayloadManifest


class Command(BaseCommand):
    help = "Test the LLM section writer on one IFRS report section."

    def add_arguments(self, parser):
        parser.add_argument(
            "--section",
            type=str,
            default="governance",
            help=(
                "Section key to generate. Example: governance, strategy, "
                "risk_management, metrics_targets, general_requirements"
            ),
        )

        parser.add_argument(
            "--bank",
            type=str,
            default="BANK01",
        )

        parser.add_argument(
            "--year",
            type=int,
            default=2024,
        )

    def handle(self, *args, **options):
        section_key = options["section"]
        bank_code = options["bank"]
        reporting_year = options["year"]

        self.stdout.write("Loading database records...")

        bank = Bank.objects.get(code=bank_code)

        payload_manifest = PayloadManifest.objects.filter(
            bank=bank,
            reporting_year=reporting_year,
        ).latest("created_at")

        ifrs_asset_bundle = IFRSAssetBundle.objects.latest("created_at")
        style_asset_bundle = StyleAssetBundle.objects.latest("created_at")

        input_root = settings.GENERATION_INPUT_ROOT

        self.stdout.write("Loading payloads...")
        payload_result = load_payloads_from_prefix(
            input_root=input_root,
            minio_prefix=payload_manifest.minio_prefix,
            bank_code=bank.code,
        )

        self.stdout.write("Loading IFRS requirements...")
        requirements_result = load_requirements_from_prefix(
            input_root=input_root,
            minio_prefix=ifrs_asset_bundle.minio_prefix,
        )

        self.stdout.write("Loading style assets...")
        style_result = load_style_assets_from_prefix(
            input_root=input_root,
            minio_prefix=style_asset_bundle.minio_prefix,
        )

        self.stdout.write("Building evidence maps...")
        evidence_result = build_evidence_maps(
            payload_result=payload_result,
            requirements_result=requirements_result,
        )

        self.stdout.write("Building disclosure plans...")
        disclosure_plan_result = build_disclosure_plans(
            evidence_result=evidence_result,
        )

        self.stdout.write("Building writer contexts...")
        writer_context_result = build_writer_contexts(
            disclosure_plan_result=disclosure_plan_result,
            style_result=style_result,
        )

        self.stdout.write(f"Generating LLM section: {section_key}...")

        section_result = build_llm_section_drafts(
            writer_context_result=writer_context_result,
            sections=[section_key],
        )

        if section_result.warnings:
            self.stdout.write(self.style.WARNING("Warnings:"))
            for warning in section_result.warnings:
                self.stdout.write(f"- {warning.warning_type}: {warning.message}")
                self.stdout.write(str(warning.details))

        draft = section_result.drafts.get(section_key)

        if not draft:
            self.stdout.write(
                self.style.ERROR(
                    f"No draft was generated for section: {section_key}"
                )
            )
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("LLM section generated successfully."))
        self.stdout.write("")
        self.stdout.write("=" * 100)
        self.stdout.write(draft["markdown"])
        self.stdout.write("=" * 100)