import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from django.db import transaction

from data_preparation.models import DataUploadBatch
from organizations.models import Bank
from payloads.models import PayloadManifest


SECTION_FILENAMES = {
    "full": "payload_{bank_code}.json",
    "general_requirements": (
        "payload_{bank_code}_general_requirements.json"
    ),
    "governance": "payload_{bank_code}_governance.json",
    "strategy": "payload_{bank_code}_strategy.json",
    "risk_management": (
        "payload_{bank_code}_risk_management.json"
    ),
    "metrics_targets": (
        "payload_{bank_code}_metrics_targets.json"
    ),
}

FULL_PAYLOAD_PATTERN = re.compile(
    r"^payload_(BANK\d+)\.json$",
    re.IGNORECASE,
)

VERSION_PATTERN = re.compile(r"^v(\d+)$", re.IGNORECASE)


class PayloadBundleError(Exception):
    """Raised when a report-generation payload bundle is invalid."""


def resolve_payload_folder(batch: DataUploadBatch) -> Path:
    folder_value = getattr(batch, "payload_folder", None)

    if not folder_value:
        raise PayloadBundleError(
            f"Batch {batch.id} does not have a payload folder."
        )

    payload_folder = Path(folder_value).resolve()

    if not payload_folder.exists():
        raise PayloadBundleError(
            f"Payload folder does not exist: {payload_folder}"
        )

    if not payload_folder.is_dir():
        raise PayloadBundleError(
            f"Payload path is not a directory: {payload_folder}"
        )

    return payload_folder


def build_payload_bundle(
    batch: DataUploadBatch,
    bank_code: str,
    reporting_year: int,
) -> Dict[str, Any]:
    normalized_bank_code = bank_code.strip().upper()

    if not normalized_bank_code:
        raise PayloadBundleError("A bank code is required.")

    payload_folder = resolve_payload_folder(batch)

    payloads: Dict[str, str] = {}
    missing_files: List[str] = []

    for section, filename_template in SECTION_FILENAMES.items():
        filename = filename_template.format(
            bank_code=normalized_bank_code
        )
        file_path = payload_folder / filename

        if not file_path.is_file():
            missing_files.append(filename)
            continue

        payloads[section] = str(file_path.resolve())

    if missing_files:
        raise PayloadBundleError(
            "The report-generation payload bundle is incomplete. "
            f"Missing files: {', '.join(missing_files)}"
        )

    return {
        "batch_id": str(batch.id),
        "bank_code": normalized_bank_code,
        "reporting_year": int(reporting_year),
        "storage_backend": (
            PayloadManifest.StorageBackend.LOCAL
        ),
        "payload_folder": str(payload_folder),
        "payloads": payloads,
    }


def discover_generated_bank_codes(
    payload_folder: Path,
) -> List[str]:
    bank_codes: List[str] = []

    for file_path in payload_folder.glob("payload_BANK*.json"):
        match = FULL_PAYLOAD_PATTERN.match(file_path.name)

        if match:
            bank_codes.append(match.group(1).upper())

    return sorted(set(bank_codes))


def read_payload_identity(
    full_payload_path: Path,
    fallback_bank_code: str,
) -> Dict[str, Any]:
    try:
        with full_payload_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise PayloadBundleError(
            f"Could not read payload identity from "
            f"{full_payload_path}: {exc}"
        ) from exc

    metadata = payload.get("metadata") or {}
    bank_data = payload.get("bank") or {}
    general_context = (
        payload.get("general_requirements_context") or {}
    )

    bank_code = (
        metadata.get("bank_id")
        or bank_data.get("bank_id")
        or general_context.get("bank_id")
        or fallback_bank_code
    )

    reporting_year = (
        metadata.get("reporting_year")
        or general_context.get("reporting_year")
    )

    if reporting_year in (None, ""):
        raise PayloadBundleError(
            f"No reporting year was found in {full_payload_path.name}."
        )

    bank_name = (
        bank_data.get("bank_name")
        or general_context.get("reporting_entity")
        or bank_code
    )

    return {
        "bank_code": str(bank_code).strip().upper(),
        "bank_name": str(bank_name).strip(),
        "reporting_year": int(reporting_year),
        "country": str(
            bank_data.get("country") or ""
        ).strip(),
    }


def calculate_bundle_checksum(
    payload_paths: Dict[str, str],
) -> str:
    digest = hashlib.sha256()

    for section_name in sorted(payload_paths):
        file_path = Path(payload_paths[section_name])

        digest.update(section_name.encode("utf-8"))
        digest.update(b"\0")

        with file_path.open("rb") as file:
            for chunk in iter(
                lambda: file.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

    return digest.hexdigest()


def get_next_manifest_version(
    bank: Bank,
    reporting_year: int,
) -> str:
    highest_version = 0

    versions = PayloadManifest.objects.filter(
        bank=bank,
        reporting_year=reporting_year,
    ).values_list("version", flat=True)

    for version in versions:
        match = VERSION_PATTERN.match(version or "")

        if match:
            highest_version = max(
                highest_version,
                int(match.group(1)),
            )

    return f"v{highest_version + 1}"


@transaction.atomic
def register_payload_manifests_for_batch(
    *,
    batch: DataUploadBatch,
    created_by,
    source_manifest_path: str = "",
) -> List[PayloadManifest]:
    payload_folder = resolve_payload_folder(batch)
    bank_codes = discover_generated_bank_codes(payload_folder)

    if not bank_codes:
        raise PayloadBundleError(
            "No complete bank payload bundles were found in "
            f"{payload_folder}."
        )

    registered_manifests: List[PayloadManifest] = []

    for discovered_bank_code in bank_codes:
        full_payload_path = (
            payload_folder
            / f"payload_{discovered_bank_code}.json"
        )

        identity = read_payload_identity(
            full_payload_path,
            fallback_bank_code=discovered_bank_code,
        )

        bundle = build_payload_bundle(
            batch=batch,
            bank_code=identity["bank_code"],
            reporting_year=identity["reporting_year"],
        )

        bank_defaults = {
            "name": identity["bank_name"],
        }

        if identity["country"]:
            bank_defaults["country"] = identity["country"]

        bank, _ = Bank.objects.update_or_create(
            code=identity["bank_code"],
            defaults=bank_defaults,
        )

        checksum = calculate_bundle_checksum(
            bundle["payloads"]
        )

        existing_manifest = (
            PayloadManifest.objects
            .filter(
                source_batch=batch,
                bank=bank,
                reporting_year=identity["reporting_year"],
            )
            .order_by("-created_at")
            .first()
        )

        if existing_manifest is not None:
            existing_manifest.storage_backend = (
                PayloadManifest.StorageBackend.LOCAL
            )
            existing_manifest.local_folder = (
                bundle["payload_folder"]
            )
            existing_manifest.minio_prefix = ""
            existing_manifest.source_manifest_path = (
                source_manifest_path or ""
            )
            existing_manifest.status = (
                PayloadManifest.Status.AVAILABLE
            )
            existing_manifest.checksum = checksum
            existing_manifest.created_by = created_by

            existing_manifest.save(
                update_fields=[
                    "storage_backend",
                    "local_folder",
                    "minio_prefix",
                    "source_manifest_path",
                    "status",
                    "checksum",
                    "created_by",
                ]
            )

            registered_manifests.append(
                existing_manifest
            )
            continue

        manifest = PayloadManifest.objects.create(
            bank=bank,
            source_batch=batch,
            reporting_year=identity["reporting_year"],
            version=get_next_manifest_version(
                bank,
                identity["reporting_year"],
            ),
            storage_backend=(
                PayloadManifest.StorageBackend.LOCAL
            ),
            local_folder=bundle["payload_folder"],
            minio_prefix="",
            source_manifest_path=(
                source_manifest_path or ""
            ),
            status=PayloadManifest.Status.AVAILABLE,
            checksum=checksum,
            created_by=created_by,
        )

        registered_manifests.append(manifest)

    return registered_manifests