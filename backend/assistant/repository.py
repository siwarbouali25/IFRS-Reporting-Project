"""
Single source of truth for reading a bank's structured payload.

Tools never touch storage directly; they go through PayloadRepository so the
resolution order (DB first, disk fallback) lives in one place and is easy to
swap when payload storage moves fully to MinIO.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class PayloadNotFound(Exception):
    pass


def _from_risk_analysis(bank_code: str, year: int | None) -> dict | None:
    """Latest completed RiskAnalysis carries the full payload as JSON."""
    from risk_analysis.models import RiskAnalysis

    qs = RiskAnalysis.objects.filter(bank_id=bank_code)
    if year is not None:
        qs = qs.filter(reporting_year=year)
    obj = qs.order_by("-created_at").first()
    if obj and obj.raw_payload:
        return obj.raw_payload
    return None


def _from_manifest(bank_code: str, year: int | None) -> dict | None:
    """Fallback: a PayloadManifest points at an on-disk payload folder."""
    from payloads.models import PayloadManifest

    qs = PayloadManifest.objects.filter(bank__code=bank_code)
    if year is not None:
        qs = qs.filter(reporting_year=year)
    manifest = qs.order_by("-reporting_year", "-created_at").first()
    if not manifest or not manifest.local_folder:
        return None

    folder = Path(manifest.local_folder)
    if not folder.is_absolute():
        folder = Path(settings.MEDIA_ROOT) / folder

    for candidate in (
        folder / f"payload_{bank_code}.json",
        folder / "payloads" / f"payload_{bank_code}.json",
    ):
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as fh:
                return json.load(fh)
    return None


class PayloadRepository:
    """Loads and caches per-bank payloads for the current request."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int | None], dict] = {}

    def get(self, bank_code: str, year: int | None = None) -> dict[str, Any]:
        key = (bank_code, year)
        if key in self._cache:
            return self._cache[key]

        payload = _from_risk_analysis(bank_code, year) or _from_manifest(
            bank_code, year
        )
        if payload is None:
            raise PayloadNotFound(
                f"No payload found for bank_code={bank_code}"
                + (f", year={year}" if year else "")
            )
        self._cache[key] = payload
        return payload

    def available_banks(self) -> list[dict[str, Any]]:
        from organizations.models import Bank

        return [
            {"bank_code": b.code, "bank_name": b.name}
            for b in Bank.objects.all().order_by("code")
        ]
