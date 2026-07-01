"""
llm.py — server-side call to NVIDIA's NIM-hosted Llama 3.3 70B (via the
OpenAI-compatible client) to generate the risk assessment paragraph +
recommendations + avoid list. The API key lives only in this process
(settings.NVIDIA_API_KEY, from the environment) and is never sent to the
browser. The frontend calls our /api/risk/analysis/<id>/assessment/
endpoint, which calls this module.

The model is given ONLY the evidence catalogue already computed by
services.process_payload() and asked to cite by id (e.g. [E3]). It cannot
invent a figure that isn't already in the evidence list, because every
number the frontend renders in a hover panel is looked up by id, not parsed
out of free text. Output is validated as strict JSON with citations
checked against the real evidence ids before being trusted; any failure
(bad JSON, hallucinated id, network error, missing key) falls back to the
deterministic template below rather than surfacing a broken response.
"""

from __future__ import annotations

import json
import logging
import re

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "meta/llama-3.3-70b-instruct"


def _build_prompt(bundle):
    bank = bundle.get("bank", {})
    metadata = bundle.get("metadata", {})
    evidence = bundle.get("evidence", [])
    kpis = bundle.get("kpis", [])

    facts = {
        "bank": bank.get("bank_name"),
        "country": bank.get("country"),
        "reporting_year": metadata.get("reporting_year"),
        "kpis": kpis,
        "data_gaps": [g.get("field") for g in metadata.get("data_gaps", [])],
    }

    ev_lines = "\n".join(f"{e['id']}: {e['label']} \u2014 {e['value']}" for e in evidence)
    allowed_ids = ", ".join(e["id"] for e in evidence)

    return f"""You are a climate-risk analyst writing one IFRS S2 risk-assessment paragraph for a bank's internal dashboard.

FACTS (JSON):
{json.dumps(facts, indent=2, default=str)}

EVIDENCE you may cite (use ONLY these exact ids in square brackets, e.g. [E1]; you may not invent new ids or numbers not listed here):
{ev_lines}

Allowed ids: {allowed_ids}

Respond with STRICT JSON only. No markdown fences, no commentary before or after the JSON object. The JSON must have exactly this shape:
{{
  "assessment": "4-6 sentence paragraph. Embed evidence markers like [E1] right after the clause they support. Plain, factual, no hype. Cite 5-8 distinct ids.",
  "recommendations": [ {{"title": "short imperative", "detail": "one sentence"}} ],
  "avoid": [ {{"title": "short imperative", "detail": "one sentence"}} ]
}}

recommendations: 3-5 concrete actions for the bank's risk team.
avoid: 3-5 concrete disclosure/reporting pitfalls to avoid, grounded in the evidence (e.g. proxy data, unassured figures, schedule-based progress)."""


def generate_assessment(bundle):
    """
    Returns {"assessment": str, "recommendations": [...], "avoid": [...],
    "model_used": str, "is_fallback": bool}. Never raises — on any failure
    (no API key, network error, malformed JSON back from the model) it
    returns a deterministic fallback built from the same evidence catalogue,
    so the dashboard never blocks on this call.
    """
    api_key = getattr(settings, "NVIDIA_API_KEY", None)
    if not api_key:
        logger.warning("NVIDIA_API_KEY not configured; returning fallback assessment.")
        return _fallback(bundle)

    try:
        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
        prompt = _build_prompt(bundle)
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You respond with strict JSON only. Never wrap the JSON in markdown code fences. Never add commentary before or after the JSON object.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            top_p=0.7,
            max_tokens=1024,
            stream=False,
        )
        text = completion.choices[0].message.content or ""
        clean = text.strip()
        if "```" in clean:
            clean = clean.replace("```json", "").replace("```", "")
        start, end = clean.find("{"), clean.rfind("}")
        if start == -1 or end == -1:
            logger.warning("No JSON object found in model output; using fallback. Raw: %s", clean[:300])
            return _fallback(bundle)
        parsed = json.loads(clean[start:end + 1])

        valid_ids = {e["id"] for e in bundle.get("evidence", [])}
        assessment_text = parsed.get("assessment", "")
        cited = set(re.findall(r"\[(E\d+)\]", assessment_text))
        if cited and not cited.issubset(valid_ids):
            logger.warning("Model cited unknown evidence ids %s; using fallback.", cited - valid_ids)
            return _fallback(bundle)

        return {
            "assessment": assessment_text,
            "recommendations": parsed.get("recommendations", []),
            "avoid": parsed.get("avoid", []),
            "model_used": MODEL,
            "is_fallback": False,
        }
    except Exception:
        logger.exception("LLM assessment generation failed; returning fallback.")
        return _fallback(bundle)


def _fallback(bundle):
    """
    Deterministic, template-based assessment built directly from the
    evidence catalogue — used whenever the live API call is unavailable or
    fails, so the analyst is never blocked, just told it's an offline draft.
    """
    ev = {e["id"]: e for e in bundle.get("evidence", [])}
    bank_name = bundle.get("bank", {}).get("bank_name", "This bank")

    parts = []
    if "E2" in ev and "E1" in ev:
        parts.append(f"{bank_name}'s climate risk is concentrated in the lending book, with financed emissions [E2] far exceeding the operational footprint and carbon intensity above target [E1].")
    if "E3" in ev:
        parts.append("The risk register shows material concentration in the highest-severity bands [E3].")
    if "E6" in ev or "E7" in ev:
        parts.append("Transition exposure is structural, reflecting material fossil-fuel lending [E6] against a small green-loan share [E7].")
    if "E4" in ev or "E5" in ev:
        parts.append("Physical risk adds an acute layer [E4], and scenario analysis shows meaningful revenue at risk under adverse conditions [E5].")
    if "E13" in ev or "E14" in ev:
        parts.append("Confidence should stay measured: assurance is narrow [E13] and much of the underlying emissions data is modelled or proxy-based [E14].")
    if "E9" in ev or "E8" in ev:
        parts.append("Two reporting caveats matter: target progress reflects schedule, not measured reduction [E9], and proxy-based figures should not be presented as verified [E8].")

    assessment = " ".join(parts) or "Insufficient evidence was available to generate a populated assessment for this upload."

    recommendations = [
        {"title": "Extend assurance scope", "detail": "Bring financed emissions and physical-risk figures into the audit scope."},
        {"title": "Set sector decarbonisation pathways", "detail": "Translate intensity targets into per-sector glide-paths for high-carbon exposure."},
        {"title": "Close counterparty data gaps", "detail": "Populate counterparty_id across investment holdings to enable concentration analysis."},
    ]
    avoid = [
        {"title": "Don't report schedule as progress", "detail": "Schedule-elapsed percentages are not a measured reduction."},
        {"title": "Don't present proxy data as verified", "detail": "Flag PCAF proxy-based figures with their data-quality score and confidence level."},
        {"title": "Don't cite synthetic benchmarks externally", "detail": "Any peer/sector comparison generated by this tool is illustrative only."},
    ]
    return {
        "assessment": assessment, "recommendations": recommendations, "avoid": avoid,
        "model_used": "fallback-template", "is_fallback": True,
    }
