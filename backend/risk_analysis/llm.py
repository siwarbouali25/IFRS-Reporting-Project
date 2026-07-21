"""
Evidence-linked risk assessment generation.

The deterministic evidence catalogue is the only factual context sent to
the model. Any malformed response, unknown citation, uncited sentence, or
network/configuration error falls back to a deterministic narrative.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings
from openai import OpenAI


logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = (
    "https://integrate.api.nvidia.com/v1"
)
DEFAULT_MODEL = (
    "meta/llama-3.3-70b-instruct"
)

MARKER_PATTERN = re.compile(
    r"\[(E\d+)\]"
)


def _setting(
    name: str,
    fallback: str | None = None,
) -> str | None:
    value = getattr(
        settings,
        name,
        None,
    )

    if value in (
        None,
        "",
    ):
        return fallback

    return str(value)


def _provider_config() -> tuple[
    str | None,
    str,
    str,
]:
    """
    Prefer generic RISK_LLM_* settings so the project can use the same
    approved Azure/OpenAI-compatible infrastructure as Report Generation.

    NVIDIA settings remain a backwards-compatible fallback.
    """
    api_key = (
        _setting("RISK_LLM_API_KEY")
        or _setting("NVIDIA_API_KEY")
    )
    base_url = (
        _setting("RISK_LLM_BASE_URL")
        or DEFAULT_BASE_URL
    )
    model = (
        _setting("RISK_LLM_MODEL")
        or DEFAULT_MODEL
    )

    return api_key, base_url, model


def _build_prompt(
    bundle: dict,
) -> str:
    bank = bundle.get("bank", {})
    metadata = bundle.get(
        "metadata",
        {},
    )
    evidence = bundle.get(
        "evidence",
        [],
    )

    evidence_lines = "\n".join(
        (
            f"{item['id']} | "
            f"{item['label']} | "
            f"{item['value']} | "
            f"source={item['source']} | "
            f"reference={item['ifrs']}"
        )
        for item in evidence
    )

    allowed_ids = ", ".join(
        item["id"]
        for item in evidence
    )

    return f"""
You are producing an internal climate-risk assessment for an audit and
review platform.

Institution: {bank.get("bank_name", "Reporting institution")}
Reporting year: {metadata.get("reporting_year", "not specified")}

You may use ONLY the evidence below. Do not add a number, percentage, year,
methodology, benchmark, entity, or conclusion that is absent from the
evidence catalogue.

EVIDENCE:
{evidence_lines}

Allowed evidence ids: {allowed_ids}

Return one JSON object only, with exactly these keys:
{{
  "assessment": "4-6 factual sentences",
  "recommendations": [
    {{"title": "short action", "detail": "one factual sentence"}}
  ],
  "avoid": [
    {{"title": "short warning", "detail": "one factual sentence"}}
  ]
}}

Rules:
1. Every assessment sentence must end with at least one evidence marker,
   such as [E1].
2. Use only the allowed evidence ids.
3. Use 3-5 recommendations and 3-5 avoid items.
4. Do not mention synthetic peers, invented benchmarks, or unsupported
   sensitivity bands.
5. Do not wrap the JSON in markdown.
""".strip()


def _clean_json_text(
    text: str,
) -> dict:
    clean = (
        text.strip()
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    start = clean.find("{")
    end = clean.rfind("}")

    if start == -1 or end == -1:
        raise ValueError(
            "No JSON object was returned."
        )

    value = json.loads(
        clean[start:end + 1]
    )

    if not isinstance(value, dict):
        raise ValueError(
            "The model response is not an object."
        )

    return value


def _validate_actions(
    value: Any,
    field_name: str,
) -> list[dict]:
    if not (
        isinstance(value, list)
        and 3 <= len(value) <= 5
    ):
        raise ValueError(
            f"{field_name} must contain "
            "between 3 and 5 items."
        )

    cleaned: list[dict] = []

    for item in value:
        if not isinstance(item, dict):
            raise ValueError(
                f"{field_name} contains "
                "an invalid item."
            )

        title = item.get("title")
        detail = item.get("detail")

        if not (
            isinstance(title, str)
            and title.strip()
            and isinstance(detail, str)
            and detail.strip()
        ):
            raise ValueError(
                f"{field_name} items require "
                "title and detail strings."
            )

        cleaned.append(
            {
                "title": title.strip(),
                "detail": detail.strip(),
            }
        )

    return cleaned


def _validate_assessment(
    parsed: dict,
    bundle: dict,
) -> dict:
    required_keys = {
        "assessment",
        "recommendations",
        "avoid",
    }

    if set(parsed) != required_keys:
        raise ValueError(
            "The response has an unexpected JSON shape."
        )

    assessment = parsed.get(
        "assessment"
    )

    if not (
        isinstance(assessment, str)
        and assessment.strip()
    ):
        raise ValueError(
            "Assessment text is missing."
        )

    evidence = bundle.get(
        "evidence",
        [],
    )
    valid_ids = {
        item["id"]
        for item in evidence
    }
    cited_ids = set(
        MARKER_PATTERN.findall(
            assessment
        )
    )

    if not cited_ids:
        raise ValueError(
            "The assessment contains no evidence citations."
        )

    unknown_ids = (
        cited_ids - valid_ids
    )

    if unknown_ids:
        raise ValueError(
            "Unknown evidence ids: "
            + ", ".join(
                sorted(unknown_ids)
            )
        )

    # Every factual sentence must carry evidence. Splitting is deliberately
    # conservative and ignores empty fragments.
    sentences = [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+",
            assessment.strip(),
        )
        if sentence.strip()
    ]

    if not 4 <= len(sentences) <= 6:
        raise ValueError(
            "Assessment must contain 4-6 sentences."
        )

    for sentence in sentences:
        if not MARKER_PATTERN.search(
            sentence
        ):
            raise ValueError(
                "Every assessment sentence must "
                "contain an evidence citation."
            )

    return {
        "assessment": assessment.strip(),
        "recommendations": (
            _validate_actions(
                parsed.get("recommendations"),
                "recommendations",
            )
        ),
        "avoid": _validate_actions(
            parsed.get("avoid"),
            "avoid",
        ),
    }


def generate_assessment(
    bundle: dict,
) -> dict:
    """
    Never raises. Returns a validated live response or a deterministic
    evidence-based fallback.
    """
    evidence = bundle.get(
        "evidence",
        [],
    )

    if len(evidence) < 2:
        return _fallback(bundle)

    api_key, base_url, model = (
        _provider_config()
    )

    if not api_key:
        logger.warning(
            "Risk LLM credentials are not configured; "
            "using the deterministic fallback."
        )
        return _fallback(bundle)

    try:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        completion = (
            client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return strict JSON only. "
                            "Use only the supplied evidence."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            _build_prompt(bundle)
                        ),
                    },
                ],
                temperature=0.1,
                top_p=0.7,
                max_tokens=1200,
                stream=False,
            )
        )

        raw_text = (
            completion
            .choices[0]
            .message
            .content
            or ""
        )
        parsed = _clean_json_text(
            raw_text
        )
        validated = _validate_assessment(
            parsed,
            bundle,
        )

        return {
            **validated,
            "model_used": model,
            "is_fallback": False,
        }
    except Exception:
        logger.exception(
            "Risk assessment generation failed; "
            "using the deterministic fallback."
        )
        return _fallback(bundle)


def _sentence_for_evidence(
    item: dict,
) -> str:
    key = item.get("key")
    label = item.get(
        "label",
        "Risk indicator",
    )
    value = item.get(
        "value",
        "not available",
    )
    marker = f"[{item['id']}]"

    templates = {
        "carbon_intensity": (
            f"Carbon intensity is {value} {marker}."
        ),
        "financed_emissions": (
            f"Financed emissions total {value} {marker}."
        ),
        "risk_register": (
            f"The risk register contains {value} {marker}."
        ),
        "physical_hazard": (
            f"The largest physical-risk concentration is "
            f"{value} {marker}."
        ),
        "scenario_impact": (
            f"The highest available scenario impact is "
            f"{value} {marker}."
        ),
        "fossil_fuel_exposure": (
            f"Transition exposure includes "
            f"{value} {marker}."
        ),
        "green_loan_share": (
            f"The green-loan share is "
            f"{value} {marker}."
        ),
        "equity_proxy": (
            f"Equity-emissions measurement includes "
            f"{value} {marker}."
        ),
        "schedule_proxy": (
            f"Target tracking includes "
            f"{value} {marker}."
        ),
        "modeled_data": (
            f"Measurement uncertainty is material because "
            f"{value} {marker}."
        ),
    }

    return templates.get(
        key,
        f"{label} is reported as {value} {marker}.",
    )


def _fallback(
    bundle: dict,
) -> dict:
    evidence = bundle.get(
        "evidence",
        [],
    )

    selected = evidence[:6]

    if selected:
        assessment = " ".join(
            _sentence_for_evidence(item)
            for item in selected
        )
    else:
        assessment = (
            "The prepared information did not contain "
            "enough supported evidence for a populated "
            "risk narrative."
        )

    evidence_keys = {
        item.get("key")
        for item in evidence
    }

    recommendations = [
        {
            "title": "Prioritise severe risks",
            "detail": (
                "Assign owners and response plans to the "
                "highest-rated risks in the register."
            ),
        },
        {
            "title": "Strengthen source traceability",
            "detail": (
                "Retain source, methodology, and quality "
                "information for every material metric."
            ),
        },
        {
            "title": "Review scenario impacts",
            "detail": (
                "Link material scenario results to risk "
                "appetite, capital planning, and monitoring."
            ),
        },
    ]

    if "equity_proxy" in evidence_keys:
        recommendations.append(
            {
                "title": "Improve counterparty data",
                "detail": (
                    "Replace proxy emissions with reported "
                    "counterparty data when it becomes "
                    "available."
                ),
            }
        )

    avoid = [
        {
            "title": "Avoid unsupported conclusions",
            "detail": (
                "Do not extend conclusions beyond the "
                "prepared evidence catalogue."
            ),
        },
        {
            "title": "Do not hide uncertainty",
            "detail": (
                "Keep proxy, estimated, and unassured "
                "figures visibly identified."
            ),
        },
        {
            "title": "Do not invent benchmarks",
            "detail": (
                "Use peer comparisons only when an approved "
                "external benchmark source exists."
            ),
        },
    ]

    if "schedule_proxy" in evidence_keys:
        avoid.append(
            {
                "title": "Do not report schedule as progress",
                "detail": (
                    "Elapsed time is not evidence of an "
                    "achieved emissions reduction."
                ),
            }
        )

    return {
        "assessment": assessment,
        "recommendations": (
            recommendations[:5]
        ),
        "avoid": avoid[:5],
        "model_used": (
            "deterministic-evidence-template"
        ),
        "is_fallback": True,
    }
