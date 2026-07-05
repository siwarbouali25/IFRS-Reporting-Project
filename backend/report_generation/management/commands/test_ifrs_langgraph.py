import json

from django.conf import settings
from django.core.management.base import BaseCommand

from generation_engine.graph.workflow import run_ifrs_report_graph
from ifrs_assets.models import IFRSAssetBundle, StyleAssetBundle
from organizations.models import Bank
from payloads.models import PayloadManifest


class Command(BaseCommand):
    help = "Test the IFRS report generation LangGraph workflow."

    def add_arguments(self, parser):
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

        parser.add_argument(
            "--writer-mode",
            type=str,
            default="deterministic",
            choices=["deterministic", "llm"],
        )

    def handle(self, *args, **options):
        bank_code = options["bank"]
        reporting_year = options["year"]
        writer_mode = options["writer_mode"]

        self.stdout.write("Loading database records...")

        bank = Bank.objects.get(code=bank_code)

        payload_manifest = PayloadManifest.objects.filter(
            bank=bank,
            reporting_year=reporting_year,
        ).latest("created_at")

        ifrs_asset_bundle = IFRSAssetBundle.objects.latest("created_at")
        style_asset_bundle = StyleAssetBundle.objects.latest("created_at")

        initial_state = {
            "job_id": "manual-langgraph-test",
            "bank_code": bank.code,
            "bank_name": bank.name,
            "reporting_year": reporting_year,
            "input_root": settings.GENERATION_INPUT_ROOT,
            "payload_prefix": payload_manifest.minio_prefix,
            "ifrs_asset_prefix": ifrs_asset_bundle.minio_prefix,
            "style_asset_prefix": style_asset_bundle.minio_prefix,
            "writer_mode": writer_mode,
        }

        self.stdout.write("Running IFRS LangGraph workflow...")

        final_state = run_ifrs_report_graph(initial_state)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("LangGraph workflow completed."))
        self.stdout.write("")

        final_summary = final_state.get("final_summary", {})
        warnings = final_state.get("warnings", [])
        final_markdown = final_state.get("final_markdown", "")

        self.stdout.write("Final summary:")
        self.stdout.write(
            json.dumps(
                final_summary,
                indent=2,
                default=str,
                ensure_ascii=False,
            )
        )

        self.stdout.write("")
        self.stdout.write(f"Warnings count: {len(warnings)}")
        self.stdout.write("")

        self.stdout.write("=" * 100)
        self.stdout.write("Final Markdown Preview")
        self.stdout.write("=" * 100)
        self.stdout.write(final_markdown[:3000])
        self.stdout.write("=" * 100)