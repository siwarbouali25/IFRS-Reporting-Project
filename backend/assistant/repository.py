"""
Single source of truth for reading a bank's structured payload.

Bank codes remain internal identifiers for database and payload lookup. The
assistant can accept either a bank name or a bank code, resolves it to the Bank
record, and returns both values so user-facing answers can use the real name.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)


class PayloadNotFound(Exception):
    pass


class BankNotFound(Exception):
    pass


@dataclass(frozen=True)
class BankIdentity:
    code: str
    name: str


def _from_risk_analysis(
    bank_code: str,
    year: int | None,
) -> dict | None:
    """Latest RiskAnalysis carries the full payload as JSON."""

    from risk_analysis.models import RiskAnalysis

    queryset = RiskAnalysis.objects.filter(
        bank_id=bank_code
    )

    if year is not None:
        queryset = queryset.filter(
            reporting_year=year
        )

    analysis = queryset.order_by(
        "-created_at"
    ).first()

    if analysis and analysis.raw_payload:
        return analysis.raw_payload

    return None


def _from_manifest(
    bank_code: str,
    year: int | None,
) -> dict | None:
    """Fallback: a PayloadManifest points at an on-disk payload folder."""

    from payloads.models import PayloadManifest

    queryset = PayloadManifest.objects.filter(
        bank__code=bank_code
    )

    if year is not None:
        queryset = queryset.filter(
            reporting_year=year
        )

    manifest = queryset.order_by(
        "-reporting_year",
        "-created_at",
    ).first()

    if (
        not manifest
        or not manifest.local_folder
    ):
        return None

    folder = Path(manifest.local_folder)

    if not folder.is_absolute():
        folder = (
            Path(settings.MEDIA_ROOT)
            / folder
        )

    for candidate in (
        folder / f"payload_{bank_code}.json",
        folder
        / "payloads"
        / f"payload_{bank_code}.json",
    ):
        if candidate.exists():
            with open(
                candidate,
                "r",
                encoding="utf-8",
            ) as file:
                return json.load(file)

    return None


class PayloadRepository:
    """
    Loads and caches payloads while resolving user-facing bank names to the
    internal bank code expected by the existing models and files.
    """

    def __init__(self) -> None:
        self._payload_cache: dict[
            tuple[str, int | None],
            dict,
        ] = {}
        self._bank_cache: dict[
            str,
            BankIdentity,
        ] = {}

    def resolve_bank(
        self,
        identifier: str,
    ) -> BankIdentity:
        """
        Resolve either:
        - the internal code, such as BANK01;
        - the full bank name;
        - a unique partial bank name.

        Exact matches are preferred. Ambiguous partial names are rejected.
        """

        cleaned = str(identifier or "").strip()

        if not cleaned:
            raise BankNotFound(
                "A bank name is required."
            )

        cache_key = cleaned.casefold()

        if cache_key in self._bank_cache:
            return self._bank_cache[
                cache_key
            ]

        from organizations.models import Bank

        exact = Bank.objects.filter(
            Q(code__iexact=cleaned)
            | Q(name__iexact=cleaned)
        ).first()

        if exact is not None:
            identity = BankIdentity(
                code=exact.code,
                name=exact.name,
            )
            self._cache_identity(
                cleaned,
                identity,
            )
            return identity

        partial_matches = list(
            Bank.objects.filter(
                name__icontains=cleaned
            ).order_by("name")[:3]
        )

        if len(partial_matches) == 1:
            bank = partial_matches[0]
            identity = BankIdentity(
                code=bank.code,
                name=bank.name,
            )
            self._cache_identity(
                cleaned,
                identity,
            )
            return identity

        if len(partial_matches) > 1:
            names = ", ".join(
                bank.name
                for bank in partial_matches
            )
            raise BankNotFound(
                f"Bank name '{cleaned}' is ambiguous. "
                f"Possible matches: {names}."
            )

        raise BankNotFound(
            f"No bank named '{cleaned}' was found."
        )

    def _cache_identity(
        self,
        original_identifier: str,
        identity: BankIdentity,
    ) -> None:
        for key in {
            original_identifier.casefold(),
            identity.code.casefold(),
            identity.name.casefold(),
        }:
            self._bank_cache[key] = identity

    def get(
        self,
        bank_identifier: str,
        year: int | None = None,
    ) -> dict[str, Any]:
        identity = self.resolve_bank(
            bank_identifier
        )
        key = (identity.code, year)

        if key in self._payload_cache:
            return self._payload_cache[key]

        payload = (
            _from_risk_analysis(
                identity.code,
                year,
            )
            or _from_manifest(
                identity.code,
                year,
            )
        )

        if payload is None:
            raise PayloadNotFound(
                f"No payload was found for "
                f"{identity.name}"
                + (
                    f" for {year}."
                    if year is not None
                    else "."
                )
            )

        self._payload_cache[key] = payload
        return payload

    def bank_details(
        self,
        bank_identifier: str,
    ) -> dict[str, str]:
        identity = self.resolve_bank(
            bank_identifier
        )
        return {
            "bank_code": identity.code,
            "bank_name": identity.name,
        }

    def available_banks(
        self,
    ) -> list[dict[str, Any]]:
        from organizations.models import Bank

        return [
            {
                "bank_code": bank.code,
                "bank_name": bank.name,
            }
            for bank in Bank.objects.all().order_by(
                "name"
            )
        ]
