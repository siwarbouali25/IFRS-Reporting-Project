import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from generation_engine.notebook_port.evidence_bridge import (
    run_notebook_evidence_stage,
)
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
    help = "Run exact notebook evidence-mapping logic from Django."

    def add_arguments(self, parser):
        parser.add_argument("--bank", type=str, default="BANK01")
        parser.add_argument("--year", type=int, default=2024)

    def handle(self, *args, **options):
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

        output_dir = (
            Path(settings.BASE_DIR)
            / "debug_outputs"
            / "notebook_bridge"
            / bank_code
            / str(reporting_year)
        )

        self.stdout.write("Running notebook evidence bridge...")

        result = run_notebook_evidence_stage(
            notebook_path=settings.IFRS_NOTEBOOK_PATH,
            input_root=settings.GENERATION_INPUT_ROOT,
            payload_prefix=payload_manifest.minio_prefix,
            ifrs_asset_prefix=ifrs_asset_bundle.minio_prefix,
            style_asset_prefix=style_asset_bundle.minio_prefix,
            output_dir=output_dir,
        )

        evidence_maps = result["evidence_maps_by_section"]
        evidence_summaries = result["evidence_map_summaries"]
        coverage_by_section = result["coverage_by_section"]
        missing_registers = result["missing_registers_by_section"]
        section_slugs = result["section_slugs"]

        bridge_output_dir = output_dir / "exported_from_bridge"

        for section_name, evidence_map in evidence_maps.items():
            slug = section_slugs[section_name]

            save_json(
                bridge_output_dir / "evidence_maps" / f"evidence_map_{slug}.json",
                evidence_map,
            )

            save_json(
                bridge_output_dir
                / "evidence_maps"
                / f"evidence_map_summary_{slug}.json",
                evidence_summaries[section_name],
            )

            save_json(
                bridge_output_dir / "coverage" / f"coverage_matrix_{slug}.json",
                coverage_by_section[section_name],
            )

            save_json(
                bridge_output_dir
                / "missing_requirements"
                / f"missing_requirements_{slug}.json",
                missing_registers[section_name],
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Notebook evidence bridge completed."))
        self.stdout.write(f"Outputs saved to: {bridge_output_dir}")
        self.stdout.write("")

        for section_name, summary in evidence_summaries.items():
            self.stdout.write(
                f"{section_name}: "
                f"{summary.get('requirements_with_candidates')} / "
                f"{summary.get('requirements_total')} with candidates"
            )