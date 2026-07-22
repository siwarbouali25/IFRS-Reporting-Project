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


def select_cited_evidence(
    assessment: str,
    evidence: list[dict],
) -> list[dict]:
    """
    Return only evidence referenced by the assessment, preserving the
    first-citation order and removing duplicate markers.
    """
    evidence_by_id = {
        str(item.get("id")): item
        for item in evidence
        if isinstance(item, dict)
        and item.get("id")
    }

    ordered_ids: list[str] = []
    seen: set[str] = set()

    for evidence_id in MARKER_PATTERN.findall(
        assessment or ""
    ):
        if (
            evidence_id in seen
            or evidence_id not in evidence_by_id
        ):
            continue

        seen.add(evidence_id)
        ordered_ids.append(evidence_id)

    return [
        evidence_by_id[evidence_id]
        for evidence_id in ordered_ids
    ]


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
            f"value={item['value']} | "
            f"meaning={item.get('detail', '')} | "
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
You are producing an executive climate-risk assessment for an internal audit
and review platform. The audience is an audit, risk, and sustainability team.

Institution: {bank.get("bank_name", "Reporting institution")}
Reporting year: {metadata.get("reporting_year", "not specified")}

Use ONLY the evidence catalogue below. Do not introduce an external
benchmark, peer comparison, unsupported methodology, invented cause, or
uncited factual claim. You may make a simple arithmetic comparison only when
it can be calculated directly from the cited evidence.

EVIDENCE:
{evidence_lines}

Allowed evidence ids: {allowed_ids}

Return one JSON object only, with exactly these keys:
{{
  "assessment": "one coherent executive assessment",
  "recommendations": [
    {{"title": "short action", "detail": "one evidence-grounded action sentence"}}
  ],
  "avoid": [
    {{"title": "short warning", "detail": "one evidence-grounded warning sentence"}}
  ]
}}

Assessment requirements:
1. Write 4-6 complete sentences and approximately 120-190 words.
2. Write a connected analytical narrative, not one isolated sentence per KPI.
3. Start with an overall conclusion about the institution's climate-risk
   profile using the strongest available evidence.
4. Combine related evidence where useful, especially transition exposure,
   risk-register severity, physical-risk concentration, scenario impact, and
   measurement uncertainty.
5. Explain the risk-management significance of the evidence without using
   external thresholds or unsupported assumptions.
6. Prioritise the most decision-relevant findings; do not attempt to mention
   every evidence item.
7. Where proxy, estimated, or schedule-based information exists, include one
   concise limitation statement.
8. End with the principal management implication supported by the evidence.
9. Every sentence must contain at least one allowed evidence marker. Put the
   marker immediately after the supported clause and before final punctuation,
   for example: "...is concentrated in flood exposure [E4]."
10. Avoid repetitive openings such as "Carbon intensity is", "Financed
    emissions total", and "The risk register contains".
11. Use professional, neutral audit and risk-management language. Do not use
    promotional, dramatic, or alarmist wording.

Action requirements:
12. Return 3-5 recommendations and 3-5 avoid items.
13. Recommendations must respond to the evidence and must not claim that an
    action has already been implemented.
14. Avoid items must highlight interpretation, traceability, measurement, or
    disclosure risks supported by the catalogue.
15. Do not mention synthetic peers, invented benchmarks, or unsupported
    sensitivity bands.
16. Do not wrap the JSON in markdown.
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

    assessment = assessment.strip()

    if assessment[-1] not in ".!?":
        raise ValueError(
            "Assessment appears incomplete or truncated."
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

    word_count = len(
        re.findall(
            r"\b[\w€%./-]+\b",
            assessment,
        )
    )

    if not 90 <= word_count <= 220:
        raise ValueError(
            "Assessment must contain between "
            "90 and 220 words."
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

        finish_reason = getattr(
            completion.choices[0],
            "finish_reason",
            None,
        )

        if finish_reason == "length":
            raise ValueError(
                "The model response was truncated."
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


def _evidence_by_key(
    evidence: list[dict],
) -> dict[str, dict]:
    return {
        str(item.get("key")): item
        for item in evidence
        if (
            isinstance(item, dict)
            and item.get("key")
            and item.get("id")
        )
    }


def _markers(
    *items: dict | None,
) -> str:
    ordered_ids: list[str] = []
    seen: set[str] = set()

    for item in items:
        if not item:
            continue

        evidence_id = str(
            item.get("id", "")
        ).strip()

        if (
            not evidence_id
            or evidence_id in seen
        ):
            continue

        seen.add(evidence_id)
        ordered_ids.append(
            evidence_id
        )

    return "".join(
        f"[{evidence_id}]"
        for evidence_id in ordered_ids
    )


def _supported_sentence(
    text: str,
    *items: dict | None,
) -> str:
    markers = _markers(*items)
    clean = text.strip().rstrip(".!?")

    if not markers:
        return f"{clean}."

    return f"{clean} {markers}."


def _generic_evidence_sentence(
    item: dict,
) -> str:
    label = str(
        item.get("label")
        or "Risk indicator"
    )
    value = str(
        item.get("value")
        or "not available"
    )

    return _supported_sentence(
        (
            f"The prepared information reports "
            f"{label.lower()} as {value}"
        ),
        item,
    )


def _fallback(
    bundle: dict,
) -> dict:
    """
    Produce a coherent executive assessment when live generation is not
    available. The fallback remains deterministic and uses only the prepared
    evidence catalogue.
    """
    evidence = [
        item
        for item in bundle.get(
            "evidence",
            [],
        )
        if isinstance(item, dict)
    ]
    by_key = _evidence_by_key(
        evidence
    )

    intensity = by_key.get(
        "carbon_intensity"
    )
    financed = by_key.get(
        "financed_emissions"
    )
    register = by_key.get(
        "risk_register"
    )
    physical = by_key.get(
        "physical_hazard"
    )
    scenario = by_key.get(
        "scenario_impact"
    )
    fossil = by_key.get(
        "fossil_fuel_exposure"
    )
    equity_proxy = by_key.get(
        "equity_proxy"
    )
    schedule_proxy = by_key.get(
        "schedule_proxy"
    )
    modeled_data = by_key.get(
        "modeled_data"
    )

    sentences: list[str] = []
    used_ids: set[str] = set()

    def remember(
        *items: dict | None,
    ) -> None:
        for item in items:
            if item and item.get("id"):
                used_ids.add(
                    str(item["id"])
                )

    opening_items = [
        item
        for item in (
            intensity,
            financed,
            fossil,
        )
        if item
    ]

    if intensity and financed:
        opening = (
            "The available evidence indicates a material "
            "transition-risk profile: lending-book carbon "
            f"intensity is {intensity['value']}, while "
            f"financed emissions are {financed['value']}"
        )

        if fossil:
            opening += (
                ", and fossil-fuel exposure is "
                f"{fossil['value']}"
            )

        sentences.append(
            _supported_sentence(
                opening,
                *opening_items,
            )
        )
        remember(*opening_items)
    elif opening_items:
        item = opening_items[0]
        sentences.append(
            _supported_sentence(
                (
                    "The available evidence indicates a "
                    "material climate-risk profile, with "
                    f"{item['label'].lower()} reported as "
                    f"{item['value']}"
                ),
                item,
            )
        )
        remember(item)

    if register:
        sentences.append(
            _supported_sentence(
                (
                    "Risk severity is concentrated at the "
                    "upper end of the assessment scale, with "
                    f"{register['value']}"
                ),
                register,
            )
        )
        remember(register)

    if physical:
        sentences.append(
            _supported_sentence(
                (
                    "Physical-risk exposure is most "
                    "concentrated in "
                    f"{physical['value']}"
                ),
                physical,
            )
        )
        remember(physical)

    if scenario:
        sentences.append(
            _supported_sentence(
                (
                    "Scenario analysis indicates potentially "
                    "material financial effects, with the "
                    "highest available impact reported as "
                    f"{scenario['value']}"
                ),
                scenario,
            )
        )
        remember(scenario)

    limitation_parts: list[str] = []
    limitation_items: list[dict] = []

    if modeled_data:
        limitation_parts.append(
            str(modeled_data["value"])
        )
        limitation_items.append(
            modeled_data
        )

    if equity_proxy:
        limitation_parts.append(
            str(equity_proxy["value"])
        )
        limitation_items.append(
            equity_proxy
        )

    if schedule_proxy:
        limitation_parts.append(
            str(schedule_proxy["value"])
        )
        limitation_items.append(
            schedule_proxy
        )

    if limitation_parts:
        sentences.append(
            _supported_sentence(
                (
                    "Interpretation should retain clear "
                    "visibility over measurement and progress "
                    "limitations, including "
                    + "; ".join(
                        limitation_parts
                    )
                ),
                *limitation_items,
            )
        )
        remember(*limitation_items)

    for item in evidence:
        evidence_id = str(
            item.get("id", "")
        )

        if (
            len(sentences) >= 4
            or evidence_id in used_ids
        ):
            continue

        sentences.append(
            _generic_evidence_sentence(
                item
            )
        )
        remember(item)

    implication_items = [
        item
        for item in (
            register,
            physical,
            scenario,
            intensity,
            fossil,
        )
        if item
    ][:3]

    if implication_items:
        sentences.append(
            _supported_sentence(
                (
                    "Taken together, the evidence supports "
                    "prioritising severe-risk ownership, "
                    "transition-exposure reduction, and the "
                    "integration of physical and scenario "
                    "effects into risk appetite and ongoing "
                    "monitoring"
                ),
                *implication_items,
            )
        )

    assessment = " ".join(
        sentences[:6]
    )

    evidence_keys = set(
        by_key
    )
    recommendations: list[dict] = []

    if {
        "carbon_intensity",
        "fossil_fuel_exposure",
    } & evidence_keys:
        recommendations.append(
            {
                "title": "Reduce transition concentration",
                "detail": (
                    "Review sector exposure limits, client "
                    "transition plans, and portfolio "
                    "decarbonisation actions against the "
                    "reported transition-risk indicators."
                ),
            }
        )

    if "risk_register" in evidence_keys:
        recommendations.append(
            {
                "title": "Escalate severe risks",
                "detail": (
                    "Assign accountable owners, monitoring "
                    "thresholds, and documented response plans "
                    "to the critical and high-rated risks."
                ),
            }
        )

    if "physical_hazard" in evidence_keys:
        recommendations.append(
            {
                "title": "Strengthen physical-risk controls",
                "detail": (
                    "Prioritise the largest hazard "
                    "concentration for exposure review, "
                    "collateral monitoring, and resilience "
                    "actions."
                ),
            }
        )

    if "scenario_impact" in evidence_keys:
        recommendations.append(
            {
                "title": "Integrate scenario impacts",
                "detail": (
                    "Connect material scenario results to risk "
                    "appetite, capital planning, portfolio "
                    "monitoring, and management escalation."
                ),
            }
        )

    if {
        "equity_proxy",
        "modeled_data",
    } & evidence_keys:
        recommendations.append(
            {
                "title": "Improve measurement quality",
                "detail": (
                    "Prioritise reported counterparty data and "
                    "document the methodology, source, and "
                    "quality of estimated or proxy values."
                ),
            }
        )

    default_recommendations = [
        {
            "title": "Maintain evidence traceability",
            "detail": (
                "Retain source, methodology, ownership, and "
                "review information for each material risk "
                "metric."
            ),
        },
        {
            "title": "Review material indicators",
            "detail": (
                "Use the prepared evidence catalogue to define "
                "monitoring thresholds and escalation criteria."
            ),
        },
        {
            "title": "Link analysis to decisions",
            "detail": (
                "Document how material risk findings inform "
                "risk appetite, portfolio monitoring, and "
                "management review."
            ),
        },
    ]

    for item in default_recommendations:
        if len(recommendations) >= 3:
            break
        recommendations.append(item)

    avoid = [
        {
            "title": "Avoid unsupported conclusions",
            "detail": (
                "Do not extend the assessment beyond the "
                "prepared evidence catalogue or present an "
                "inference as a reported fact."
            ),
        },
        {
            "title": "Do not invent benchmarks",
            "detail": (
                "Use peer or external threshold comparisons "
                "only when an approved and traceable source is "
                "available."
            ),
        },
    ]

    if {
        "equity_proxy",
        "modeled_data",
    } & evidence_keys:
        avoid.append(
            {
                "title": "Keep uncertainty visible",
                "detail": (
                    "Do not present estimated, proxy-based, or "
                    "unassured figures as directly reported or "
                    "fully verified values."
                ),
            }
        )

    if "schedule_proxy" in evidence_keys:
        avoid.append(
            {
                "title": "Separate time from progress",
                "detail": (
                    "Do not describe schedule elapsed as "
                    "evidence of an achieved emissions "
                    "reduction."
                ),
            }
        )

    if len(avoid) < 3:
        avoid.append(
            {
                "title": "Preserve source context",
                "detail": (
                    "Do not remove the scope, year, unit, or "
                    "methodology needed to interpret a material "
                    "metric."
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
            "deterministic-executive-assessment"
        ),
        "is_fallback": True,
    }
