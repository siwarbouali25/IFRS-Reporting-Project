"""
Evidence-linked risk assessment generation.

The deterministic evidence catalogue is the only factual context sent to the
model. Live model responses are accepted only when they are complete,
well-structured, evidence-linked, and analytically useful. Any configuration,
network, formatting, citation, or quality failure uses a deterministic
executive assessment built from the same evidence catalogue.
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
SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])\s+"
)
VAGUE_TERM_PATTERN = re.compile(
    r"\b(substantial|notable|considerable)\b",
    flags=re.IGNORECASE,
)
GENERIC_CONCLUSION_PATTERN = re.compile(
    (
        r"\bprioriti[sz]e climate-risk mitigation "
        r"and adaptation strategies\b"
    ),
    flags=re.IGNORECASE,
)

CORE_EVIDENCE_KEYS = {
    "carbon_intensity",
    "financed_emissions",
    "risk_register",
    "physical_hazard",
    "scenario_impact",
}
LIMITATION_EVIDENCE_KEYS = {
    "equity_proxy",
    "schedule_proxy",
    "modeled_data",
}


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
    approved OpenAI-compatible infrastructure as Report Generation.

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
            f"key={item.get('key', '')} | "
            f"label={item['label']} | "
            f"value={item['value']} | "
            f"detail={item.get('detail', '')} | "
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
You are producing an internal executive climate-risk assessment for an audit
and review platform.

Institution: {bank.get("bank_name", "Reporting institution")}
Reporting year: {metadata.get("reporting_year", "not specified")}

Use ONLY the evidence catalogue below. Do not add a number, percentage, year,
methodology, benchmark, entity, causal claim, materiality threshold, or
conclusion that is absent from or cannot be directly derived from the
catalogue.

EVIDENCE CATALOGUE:
{evidence_lines}

Allowed evidence ids: {allowed_ids}

Return one JSON object only, with exactly these keys:
{{
  "assessment": "one coherent executive assessment",
  "recommendations": [
    {{"title": "short action", "detail": "one concise action sentence"}}
  ],
  "avoid": [
    {{"title": "short warning", "detail": "one concise warning sentence"}}
  ]
}}

Assessment requirements:
1. Write 4-6 complete sentences and approximately 120-190 words.
2. Start with an overall evidence-based conclusion about the institution's
   climate-risk profile.
3. Do not write one isolated sentence for every evidence item. Combine related
   evidence into analytical statements.
4. Cover, when available:
   - transition exposure and target position;
   - financed emissions;
   - risk-register severity;
   - the quantified largest physical-risk concentration;
   - the named scenario, horizon, and quantified financial impact;
   - at least one measurement or target-progress limitation.
5. Interpret the evidence objectively. Prefer formulations such as:
   - "far above the stated target";
   - "all identified risks are high or critical";
   - "the largest concentration is...";
   Avoid unsupported adjectives such as "substantial", "notable", or
   "considerable".
6. Preserve useful quantities from the evidence. Do not replace a quantified
   physical-risk or scenario finding with a vague description.
7. End with a specific management implication connected to the cited
   transition, physical-risk, scenario, or measurement evidence. Do not use a
   generic conclusion such as "prioritise mitigation and adaptation
   strategies".
8. Every sentence must contain at least one evidence marker.
9. Put each marker immediately after the supported clause and before
   punctuation, for example: "across 30 exposure rows [E4]."
10. Use only allowed evidence ids. Cite 5-8 distinct evidence items when that
    many are available. Do not repeat the same marker twice in one sentence
    unless it supports separate, non-adjacent clauses.
11. Do not mention synthetic peers, invented benchmarks, unsupported
    sensitivity bands, or data that is not present.
12. Use 3-5 recommendations and 3-5 avoid items.
13. Do not wrap the JSON in markdown.
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


def _normalise_assessment_text(
    text: str,
) -> str:
    """
    Keep the model wording but normalise whitespace and citation punctuation.

    Examples:
      "value [E1] ." -> "value [E1]."
      "value [E1] ," -> "value [E1],"
    """
    clean = re.sub(
        r"\s+",
        " ",
        text.strip(),
    )
    clean = re.sub(
        r"\[(E\d+)\]\s+([,.;:!?])",
        r"[\1]\2",
        clean,
    )
    clean = re.sub(
        r"\s+([,.;:!?])",
        r"\1",
        clean,
    )

    return clean


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


def _evidence_index(
    bundle: dict,
) -> tuple[
    dict[str, dict],
    dict[str, str],
]:
    by_id: dict[str, dict] = {}
    id_by_key: dict[str, str] = {}

    for item in bundle.get(
        "evidence",
        [],
    ):
        if not isinstance(item, dict):
            continue

        evidence_id = item.get("id")
        key = item.get("key")

        if isinstance(evidence_id, str):
            by_id[evidence_id] = item

            if isinstance(key, str):
                id_by_key[key] = evidence_id

    return by_id, id_by_key


def _validate_required_coverage(
    cited_ids: set[str],
    id_by_key: dict[str, str],
) -> None:
    missing_core = [
        key
        for key in CORE_EVIDENCE_KEYS
        if (
            key in id_by_key
            and id_by_key[key] not in cited_ids
        )
    ]

    if missing_core:
        raise ValueError(
            "Assessment omitted core evidence: "
            + ", ".join(
                sorted(missing_core)
            )
        )

    available_limitations = {
        id_by_key[key]
        for key in LIMITATION_EVIDENCE_KEYS
        if key in id_by_key
    }

    if (
        available_limitations
        and not (
            cited_ids
            & available_limitations
        )
    ):
        raise ValueError(
            "Assessment omitted available measurement "
            "or target-progress limitations."
        )


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

    raw_assessment = parsed.get(
        "assessment"
    )

    if not (
        isinstance(raw_assessment, str)
        and raw_assessment.strip()
    ):
        raise ValueError(
            "Assessment text is missing."
        )

    assessment = (
        _normalise_assessment_text(
            raw_assessment
        )
    )

    if not assessment.endswith(
        (
            ".",
            "!",
            "?",
        )
    ):
        raise ValueError(
            "Assessment appears incomplete because "
            "it has no terminal punctuation."
        )

    evidence_by_id, id_by_key = (
        _evidence_index(bundle)
    )
    valid_ids = set(
        evidence_by_id
    )
    cited_sequence = (
        MARKER_PATTERN.findall(
            assessment
        )
    )
    cited_ids = set(
        cited_sequence
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

    minimum_distinct = min(
        5,
        len(valid_ids),
    )

    if len(cited_ids) < minimum_distinct:
        raise ValueError(
            "Assessment does not use enough distinct "
            "evidence items."
        )

    _validate_required_coverage(
        cited_ids,
        id_by_key,
    )

    sentences = [
        sentence.strip()
        for sentence in (
            SENTENCE_SPLIT_PATTERN.split(
                assessment
            )
        )
        if sentence.strip()
    ]

    if not 4 <= len(sentences) <= 6:
        raise ValueError(
            "Assessment must contain 4-6 sentences."
        )

    word_count = len(
        re.findall(
            r"\b[\w€%₂/.-]+\b",
            MARKER_PATTERN.sub(
                "",
                assessment,
            ),
        )
    )

    if not 90 <= word_count <= 220:
        raise ValueError(
            "Assessment must contain approximately "
            "90-220 words."
        )

    for sentence in sentences:
        if not MARKER_PATTERN.search(
            sentence
        ):
            raise ValueError(
                "Every assessment sentence must "
                "contain an evidence citation."
            )

        marker_ids = (
            MARKER_PATTERN.findall(
                sentence
            )
        )

        if len(marker_ids) != len(
            set(marker_ids)
        ):
            raise ValueError(
                "The same evidence marker is repeated "
                "within one sentence."
            )

    if VAGUE_TERM_PATTERN.search(
        assessment
    ):
        raise ValueError(
            "Assessment contains unsupported vague wording."
        )

    if GENERIC_CONCLUSION_PATTERN.search(
        sentences[-1]
    ):
        raise ValueError(
            "Assessment ends with a generic management "
            "conclusion."
        )

    if not MARKER_PATTERN.search(
        sentences[-1]
    ):
        raise ValueError(
            "The final management implication requires "
            "evidence."
        )

    return {
        "assessment": assessment,
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


def _finish_reason(
    completion: Any,
) -> str:
    try:
        return str(
            completion.choices[0].finish_reason
            or ""
        ).lower()
    except (
        AttributeError,
        IndexError,
        TypeError,
    ):
        return ""


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
                            "Use only supplied evidence. "
                            "Write a complete executive "
                            "risk assessment."
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
                max_tokens=1500,
                stream=False,
            )
        )

        finish_reason = (
            _finish_reason(completion)
        )

        if finish_reason in {
            "length",
            "content_filter",
        }:
            raise ValueError(
                "The model response was incomplete "
                f"(finish_reason={finish_reason})."
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
            "using the deterministic executive fallback."
        )
        return _fallback(bundle)


def _by_key(
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


def _marker(
    item: dict | None,
) -> str:
    if not item:
        return ""

    return f"[{item['id']}]"


def _sentence(
    text: str,
    *items: dict | None,
) -> str:
    markers = " ".join(
        _marker(item)
        for item in items
        if item
    )

    return (
        f"{text.rstrip('.')} {markers}."
        if markers
        else f"{text.rstrip('.')}."
    )


def _fallback(
    bundle: dict,
) -> dict:
    evidence = [
        item
        for item in bundle.get(
            "evidence",
            [],
        )
        if isinstance(item, dict)
    ]
    by_key = _by_key(
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
    proxy = by_key.get(
        "equity_proxy"
    )
    schedule = by_key.get(
        "schedule_proxy"
    )
    modeled = by_key.get(
        "modeled_data"
    )

    sentences: list[str] = []

    if intensity and financed:
        sentences.append(
            _sentence(
                (
                    "The available evidence indicates that "
                    "the institution's climate-risk profile "
                    "is led by transition exposure, with "
                    f"lending-book carbon intensity of "
                    f"{intensity['value']} and financed "
                    f"emissions of {financed['value']}"
                ),
                intensity,
                financed,
            )
        )
    elif intensity:
        sentences.append(
            _sentence(
                (
                    "The available evidence indicates that "
                    "transition exposure is a central part "
                    "of the institution's climate-risk "
                    "profile, with lending-book carbon "
                    f"intensity of {intensity['value']}"
                ),
                intensity,
            )
        )
    elif financed:
        sentences.append(
            _sentence(
                (
                    "The available evidence indicates that "
                    "transition exposure is a central part "
                    "of the institution's climate-risk "
                    "profile, with financed emissions of "
                    f"{financed['value']}"
                ),
                financed,
            )
        )

    if register:
        sentences.append(
            _sentence(
                (
                    "Risk severity is concentrated at the "
                    "upper end of the assessment scale: "
                    f"{register['value']}"
                ),
                register,
            )
        )

    if physical:
        sentences.append(
            _sentence(
                (
                    "The largest quantified physical-risk "
                    "concentration is "
                    f"{physical['value']}"
                ),
                physical,
            )
        )

    if scenario:
        sentences.append(
            _sentence(
                (
                    "Scenario analysis identifies the "
                    "highest available financial impact as "
                    f"{scenario['value']}"
                ),
                scenario,
            )
        )

    limitation_parts: list[str] = []
    limitation_items: list[dict] = []

    if proxy:
        limitation_parts.append(
            (
                "proxy-based equity-emissions "
                f"measurement ({proxy['value']})"
            )
        )
        limitation_items.append(
            proxy
        )

    if schedule:
        limitation_parts.append(
            (
                "target tracking based on elapsed "
                f"schedule time ({schedule['value']})"
            )
        )
        limitation_items.append(
            schedule
        )

    if modeled:
        limitation_parts.append(
            (
                "estimated or proxy-based emissions data "
                f"({modeled['value']})"
            )
        )
        limitation_items.append(
            modeled
        )

    if limitation_parts:
        sentences.append(
            _sentence(
                (
                    "Interpretation should retain clear "
                    "visibility over "
                    + "; ".join(
                        limitation_parts[:2]
                    )
                ),
                *limitation_items[:2],
            )
        )

    implication_items: list[dict] = []
    implication_parts: list[str] = []

    if fossil:
        implication_parts.append(
            (
                "portfolio transition controls for "
                f"{fossil['value']}"
            )
        )
        implication_items.append(
            fossil
        )

    if physical:
        implication_parts.append(
            "controls for the largest physical-risk concentration"
        )
        implication_items.append(
            physical
        )

    if scenario:
        implication_parts.append(
            "integration of scenario impacts into risk appetite and capital planning"
        )
        implication_items.append(
            scenario
        )

    if implication_parts:
        sentences.append(
            _sentence(
                (
                    "The principal management implication "
                    "is to assign accountable owners and "
                    "monitoring thresholds to "
                    + ", ".join(
                        implication_parts
                    )
                    + ", and to connect those controls to "
                    "decision processes"
                ),
                *implication_items,
            )
        )

    if not sentences:
        assessment = (
            "The prepared information did not contain "
            "enough supported evidence for a populated "
            "risk narrative."
        )
    else:
        assessment = " ".join(
            sentences[:6]
        )

    evidence_keys = set(
        by_key
    )

    recommendations = [
        {
            "title": "Prioritise severe risks",
            "detail": (
                "Assign accountable owners, monitoring "
                "thresholds, and response plans to all "
                "critical and high-rated risks."
            ),
        },
        {
            "title": "Integrate scenario impacts",
            "detail": (
                "Connect quantified scenario impacts to "
                "risk appetite, capital planning, and "
                "portfolio monitoring."
            ),
        },
        {
            "title": "Strengthen source traceability",
            "detail": (
                "Retain source, methodology, assurance, "
                "and quality information for every "
                "decision-relevant metric."
            ),
        },
    ]

    if (
        "fossil_fuel_exposure"
        in evidence_keys
    ):
        recommendations.append(
            {
                "title": "Review transition exposure",
                "detail": (
                    "Review sector limits and client "
                    "engagement for carbon-intensive "
                    "lending exposures."
                ),
            }
        )

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
            "title": "Keep uncertainty visible",
            "detail": (
                "Keep proxy, estimated, and unassured "
                "figures clearly identified."
            ),
        },
        {
            "title": "Do not invent benchmarks",
            "detail": (
                "Use peer comparisons only when an "
                "approved external benchmark source "
                "exists."
            ),
        },
    ]

    if "schedule_proxy" in evidence_keys:
        avoid.append(
            {
                "title": "Separate time from progress",
                "detail": (
                    "Do not present elapsed schedule time "
                    "as achieved emissions reduction."
                ),
            }
        )

    return {
        "assessment": (
            _normalise_assessment_text(
                assessment
            )
        ),
        "recommendations": (
            recommendations[:5]
        ),
        "avoid": avoid[:5],
        "model_used": (
            "deterministic-executive-assessment"
        ),
        "is_fallback": True,
    }
