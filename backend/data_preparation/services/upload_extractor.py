import json
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from data_preparation.models import DataUploadBatch


def get_batch_base_folder(batch: DataUploadBatch) -> Path:
    return Path(settings.MEDIA_ROOT) / "data_preparation" / "batches" / str(batch.id)


def get_extracted_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "extracted"


def get_mapping_folder(batch: DataUploadBatch) -> Path:
    return get_batch_base_folder(batch) / "mapping"


def ensure_extraction_folders(batch: DataUploadBatch) -> Dict[str, Path]:
    base_folder = get_batch_base_folder(batch)
    raw_folder = base_folder / "raw"
    extracted_folder = base_folder / "extracted"
    mapping_folder = base_folder / "mapping"

    raw_folder.mkdir(parents=True, exist_ok=True)
    extracted_folder.mkdir(parents=True, exist_ok=True)
    mapping_folder.mkdir(parents=True, exist_ok=True)

    return {
        "base": base_folder,
        "raw": raw_folder,
        "extracted": extracted_folder,
        "mapping": mapping_folder,
    }


def clean_extracted_folder(extracted_folder: Path) -> None:
    if extracted_folder.exists():
        shutil.rmtree(extracted_folder)

    extracted_folder.mkdir(parents=True, exist_ok=True)


def safe_csv_filename(filename: str) -> str:
    name = Path(filename).name
    name = name.replace("\\", "_").replace("/", "_").strip()

    if not name.lower().endswith(".csv"):
        name = f"{name}.csv"

    return name


def unique_destination_path(folder: Path, filename: str) -> Path:
    filename = safe_csv_filename(filename)
    destination = folder / filename

    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix

    counter = 2
    while True:
        candidate = folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def copy_csv_to_extracted(source_path: Path, extracted_folder: Path, original_name: str) -> Dict:
    destination = unique_destination_path(extracted_folder, original_name)
    shutil.copy2(source_path, destination)

    return {
        "source_type": "csv",
        "source_name": original_name,
        "extracted_filename": destination.name,
        "extracted_path": str(destination),
        "size_bytes": destination.stat().st_size,
    }


def extract_zip_to_extracted(zip_path: Path, extracted_folder: Path, original_name: str) -> List[Dict]:
    extracted_files = []

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            member_name = Path(member.filename).name

            if not member_name:
                continue

            if member.is_dir():
                continue

            if member_name.startswith("."):
                continue

            if not member_name.lower().endswith(".csv"):
                continue

            destination = unique_destination_path(extracted_folder, member_name)

            with zip_ref.open(member, "r") as source, open(destination, "wb") as target:
                shutil.copyfileobj(source, target)

            extracted_files.append(
                {
                    "source_type": "zip",
                    "source_name": original_name,
                    "zip_member": member.filename,
                    "extracted_filename": destination.name,
                    "extracted_path": str(destination),
                    "size_bytes": destination.stat().st_size,
                }
            )

    return extracted_files


def extract_uploaded_sources(batch: DataUploadBatch) -> Dict:
    folders = ensure_extraction_folders(batch)
    extracted_folder = folders["extracted"]
    mapping_folder = folders["mapping"]

    clean_extracted_folder(extracted_folder)

    manifest = {
        "batch_id": str(batch.id),
        "extracted_folder": str(extracted_folder),
        "files": [],
        "errors": [],
    }

    uploaded_files = batch.uploaded_files.all()

    for uploaded in uploaded_files:
        try:
            source_path = Path(uploaded.file.path)
            original_name = uploaded.original_filename or source_path.name

            if uploaded.file_type == "csv":
                item = copy_csv_to_extracted(
                    source_path=source_path,
                    extracted_folder=extracted_folder,
                    original_name=original_name,
                )
                manifest["files"].append(item)

            elif uploaded.file_type == "zip":
                items = extract_zip_to_extracted(
                    zip_path=source_path,
                    extracted_folder=extracted_folder,
                    original_name=original_name,
                )
                manifest["files"].extend(items)

            else:
                manifest["errors"].append(
                    {
                        "source_name": original_name,
                        "error": "Unsupported file type. Only CSV and ZIP files are processed.",
                    }
                )

        except zipfile.BadZipFile:
            manifest["errors"].append(
                {
                    "source_name": uploaded.original_filename,
                    "error": "Invalid ZIP file.",
                }
            )

        except Exception as exc:
            manifest["errors"].append(
                {
                    "source_name": uploaded.original_filename,
                    "error": str(exc),
                }
            )

    manifest["total_extracted_csv_files"] = len(manifest["files"])

    manifest_path = mapping_folder / "extraction_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    manifest["manifest_path"] = str(manifest_path)

    return manifest