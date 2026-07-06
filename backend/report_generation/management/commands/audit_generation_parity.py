import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from generation_engine.evidence.coverage import build_coverage_summary
from generation_engine.evidence.evidence_mapper import build_evidence_maps
from generation_engine.evidence.missing_register import build_missing_requirements_register
from generation_engine.loaders.payload_loader import load_payloads_from_prefix
from generation_engine.loaders.requirements_loader import load_requirements_from_prefix
from generation_engine.loaders.style_loader import load_style_assets_from_prefix
from generation_engine.planning.disclosure_plan_builder import build_disclosure_plans
from generation_engine.writing.writer_context import build_writer_contexts

from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from organizations.models import Bank
from payloads.models import PayloadManifest


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )


class Command(BaseCommand):
    help = "Audit Django generation pipeline parity against notebook logic."

    def add_arguments(self, parser):
        parser.add_argument("--bank", type=str, default="BANK01")
        parser.add_argument("--year", type=int, default=2024)

    def handle(self, *args, **options):
        bank_code = options["bank"]
        reporting_year = options["year"]

        output_dir = (
            Path(settings.BASE_DIR)
            / "debug_outputs"
            / "parity_audit"
            / bank_code
            / str(reporting_year)
        )

        self.stdout.write("Loading database records...")

        bank = Bank.objects.get(code=bank_code)

        payload_manifest = PayloadManifest.objects.filter(
            bank=bank,
            reporting_year=reporting_year,
        ).latest("created_at")

        ifrs_asset_bundle = IFRSAssetBundle.objects.latest("created_at")
        style_asset_bundle = StyleAssetBundle.objects.latest("created_at")

        input_root = settings.GENERATION_INPUT_ROOT

        self.stdout.write("1. Loading payloads...")

        payload_result = load_payloads_from_prefix(
            input_root=input_root,
            minio_prefix=payload_manifest.minio_prefix,
            bank_code=bank.code,
        )

        save_json(
            output_dir / "01_payload_loader_result.json",
            {
                "loaded_files": payload_result.loaded_files,
                "missing_files": payload_result.missing_files,
                "warnings": [
                    {
                        "stage": warning.stage,
                        "warning_type": warning.warning_type,
                        "message": warning.message,
                        "details": warning.details,
                    }
                    for warning in payload_result.warnings
                ],
                "payload_keys": list(payload_result.data.keys()),
                "payloads": payload_result.data,
            },
        )

        self.stdout.write("2. Loading IFRS requirements...")

        requirements_result = load_requirements_from_prefix(
            input_root=input_root,
            minio_prefix=ifrs_asset_bundle.minio_prefix,
        )

        save_json(
            output_dir / "02_requirements_loader_result.json",
            {
                "loaded_files": requirements_result.loaded_files,
                "missing_files": requirements_result.missing_files,
                "warnings": [
                    {
                        "stage": warning.stage,
                        "warning_type": warning.warning_type,
                        "message": warning.message,
                        "details": warning.details,
                    }
                    for warning in requirements_result.warnings
                ],
                "requirement_keys": list(requirements_result.data.keys()),
                "requirements": requirements_result.data,
            },
        )

        self.stdout.write("3. Loading style assets...")

        style_result = load_style_assets_from_prefix(
            input_root=input_root,
            minio_prefix=style_asset_bundle.minio_prefix,
        )

        save_json(
            output_dir / "03_style_loader_result.json",
            {
                "loaded_files": style_result.loaded_files,
                "missing_files": style_result.missing_files,
                "warnings": [
                    {
                        "stage": warning.stage,
                        "warning_type": warning.warning_type,
                        "message": warning.message,
                        "details": warning.details,
                    }
                    for warning in style_result.warnings
                ],
                "style_keys": list(style_result.data.keys()),
                "style_assets": style_result.data,
            },
        )

        self.stdout.write("4. Building evidence maps...")

        evidence_result = build_evidence_maps(
            payload_result=payload_result,
            requirements_result=requirements_result,
        )

        save_json(
            output_dir / "04_evidence_result_summary.json",
            evidence_result.summary,
        )

        save_json(
            output_dir / "04_evidence_maps_full.json",
            evidence_result.evidence_maps,
        )

        for section_key, section_map in evidence_result.evidence_maps["maps"].items():
            file_slug = evidence_result.evidence_maps["file_slugs"][section_key]

            save_json(
                output_dir / "evidence_maps" / f"evidence_map_{file_slug}.json",
                section_map,
            )

            save_json(
                output_dir
                / "evidence_maps"
                / f"evidence_map_summary_{file_slug}.json",
                evidence_result.evidence_maps["summaries"][section_key],
            )

        self.stdout.write("5. Building coverage summary...")

        coverage_result = build_coverage_summary(
            evidence_result=evidence_result,
        )

        save_json(
            output_dir / "05_coverage_summary.json",
            coverage_result.coverage_summary,
        )

        self.stdout.write("6. Building missing requirements register...")

        missing_result = build_missing_requirements_register(
            evidence_result=evidence_result,
        )

        save_json(
            output_dir / "06_missing_requirements_register.json",
            missing_result.missing_register,
        )

        self.stdout.write("7. Building disclosure plans...")

        disclosure_plan_result = build_disclosure_plans(
            evidence_result=evidence_result,
        )

        save_json(
            output_dir / "07_disclosure_plan_summary.json",
            disclosure_plan_result.summary,
        )

        for section_key, plan in disclosure_plan_result.plans.items():
            file_slug = plan["file_slug"]

            save_json(
                output_dir
                / "disclosure_plans"
                / f"disclosure_plan_{file_slug}.json",
                plan,
            )

        self.stdout.write("8. Building writer contexts...")

        writer_context_result = build_writer_contexts(
            disclosure_plan_result=disclosure_plan_result,
            style_result=style_result,
        )

        save_json(
            output_dir / "08_writer_context_summary.json",
            writer_context_result.summary,
        )

        for section_key, context in writer_context_result.contexts.items():
            file_slug = context["file_slug"]

            save_json(
                output_dir
                / "writer_contexts"
                / f"writer_context_{file_slug}.json",
                context,
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Parity audit completed."))
        self.stdout.write(f"Outputs saved to: {output_dir}")