"""
Deterministic security and scope guardrails for the data assistant.

The checks in this module run before Azure receives a user message. They are
not model-based, so instructions such as "ignore previous instructions" cannot
persuade the guard itself.

The same module also:
- prevents blocked turns from being replayed into later conversations;
- validates completed model output before it is shown to the user;
- enforces tool-grounding for project-data answers;
- removes internal bank codes from user-facing text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

MAX_USER_INPUT_CHARS = 4000
MAX_ASSISTANT_OUTPUT_CHARS = 12000

OUT_OF_SCOPE_RESPONSE = (
    "I can only help with this platform's ESG and IFRS S1/S2 reporting and "
    "risk-analysis data. You can ask about emissions, reporting KPIs, climate "
    "targets, governance, climate risks, scenarios, exposures, data gaps, "
    "comparisons, and generated report content."
)

INJECTION_RESPONSE = (
    "I cannot follow requests that try to change, reveal, bypass, or override "
    "the assistant's protected instructions. Please ask a question about the "
    "platform's ESG reporting or risk-analysis data."
)

SENSITIVE_RESPONSE = (
    "I cannot provide credentials, environment variables, hidden prompts, "
    "internal instructions, or other protected system information."
)

UNVERIFIED_RESPONSE = (
    "I could not retrieve verified project data for that request. Please ask "
    "about available emissions, KPIs, climate targets, governance, climate "
    "risks, data gaps, or generated report content."
)


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    category: str
    reason: str
    response: str = ""
    requires_grounding: bool = False


@dataclass(frozen=True)
class OutputDecision:
    text: str
    accepted: bool
    reason: str = ""


def _normalise(text: str) -> str:
    value = unicodedata.normalize(
        "NFKC",
        str(text or ""),
    )
    value = value.replace("\x00", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _compile(patterns: Iterable[str]) -> tuple[re.Pattern, ...]:
    return tuple(
        re.compile(pattern, re.IGNORECASE | re.DOTALL)
        for pattern in patterns
    )


_INJECTION_PATTERNS = _compile(
    [
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above|earlier|system|developer)\s+(?:instructions?|rules?|messages?|prompts?)\b",
        r"\b(?:disregard|forget|override|bypass|disable|remove)\b.{0,80}\b(?:instructions?|rules?|guardrails?|policy|policies|system prompt|developer message|security)\b",
        r"\b(?:reveal|show|print|repeat|dump|expose|display|return)\b.{0,80}\b(?:system prompt|developer message|hidden instructions?|internal prompt|chain of thought|tool schemas?|guardrails?)\b",
        r"\b(?:jailbreak|dan mode|developer mode|unrestricted mode|god mode)\b",
        r"\bact\s+as\b.{0,60}\b(?:unrestricted|uncensored|developer|system|administrator|root)\b",
        r"\bpretend\b.{0,80}\b(?:no rules|no restrictions|you are not bound|instructions do not apply)\b",
        r"\bnew\s+(?:system\s+)?instructions?\s*:",
        r"\b(?:do not|don't)\s+use\s+(?:the\s+)?tools?\b",
        r"\banswer\s+(?:only\s+)?from\s+(?:your|general|outside)\s+knowledge\b",
        r"\b(?:ignore|change|escape)\s+(?:the\s+)?bank\s+scope\b",
        r"\bBEGIN\s+(?:SYSTEM|DEVELOPER|HIDDEN)\b",
        r"\b(?:role|channel)\s*:\s*(?:system|developer)\b",
    ]
)

_SENSITIVE_PATTERNS = _compile(
    [
        r"\b(?:api|secret|private)\s*key\b",
        r"\bAZURE_OPENAI_API_KEY\b",
        r"\bSECRET_KEY\b",
        r"\b(?:access|refresh|bearer|authentication)\s+token\b",
        r"\b(?:passwords?|credentials?|secrets?)\b",
        r"(?:^|\s)\.env(?:\s|$)",
        r"\benvironment\s+variables?\b",
        r"\binternal\s+(?:source\s+code|configuration|endpoint)\b",
    ]
)

_CREATIVE_OR_CONTROL_PATTERNS = _compile(
    [
        r"\b(?:write|compose|generate)\b.{0,30}\b(?:poem|song|story|joke|rap|fiction)\b",
        r"\brole[- ]?play\b",
        r"\bpretend\s+to\s+be\b",
        r"\bchange\s+your\s+(?:personality|identity|role|style)\b",
    ]
)

_EXPLICIT_OFF_TOPIC_PATTERNS = _compile(
    [
        r"\b(?:weather|forecast|temperature)\b",
        r"\b(?:football|soccer|basketball|tennis|sports?|match score)\b",
        r"\b(?:recipe|cooking|restaurant|food)\b",
        r"\b(?:movie|film|series|celebrity|music|song lyrics?)\b",
        r"\b(?:president|election|politics|political party)\b",
        r"\b(?:travel|flight|hotel|visa|tourism)\b",
        r"\b(?:skincare|retinal|acne|medical diagnosis|medicine)\b",
        r"\b(?:homework|algebra|geometry|calculus)\b",
        r"\b(?:write|debug|fix)\b.{0,30}\b(?:python|javascript|typescript|java|c\+\+|sql|code)\b",
        r"\b(?:cryptocurrency|bitcoin|stock price|forex)\b",
    ]
)

_STRONG_PROJECT_PATTERNS = _compile(
    [
        r"\bIFRS\s*S[12]\b",
        r"\bESG\b",
        r"\bsustainability\b",
        r"\bclimate\b",
        r"\bgreenhouse\s+gas(?:es)?\b",
        r"\bGHG\b",
        r"\bemissions?\b",
        r"\bscope\s*[123]\b",
        r"\bfinanced\s+emissions?\b",
        r"\bcarbon\s+(?:intensity|price|footprint)\b",
        r"\bPCAF\b",
        r"\bclimate\s+(?:risk|scenario|target|opportunity)\b",
        r"\btransition\s+risk\b",
        r"\bphysical\s+risk\b",
        r"\bdata\s+gaps?\b",
        r"\breporting\s+KPIs?\b",
        r"\bmateriality\b",
        r"\bdisclosures?\b",
        r"\brisk\s+(?:register|analysis|assessment|rating|matrix)\b",
        r"\bgovernance\b",
        r"\btargets?\b",
        r"\bexposures?\b",
        r"\bgenerated\s+report\b",
        r"\breport\s+(?:section|content|version|status)\b",
    ]
)

_WEAK_PROJECT_PATTERNS = _compile(
    [
        r"\bKPIs?\b",
        r"\bmetrics?\b",
        r"\brisks?\b",
        r"\breports?\b",
        r"\baudit\b",
        r"\bbanks?\b",
        r"\bscenarios?\b",
        r"\bportfolio\b",
        r"\bassets?\b",
        r"\byear[- ]on[- ]year\b",
        r"\bcompar(?:e|ison)\b",
    ]
)

_CAPABILITY_PATTERNS = _compile(
    [
        r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))\b",
        r"\bwhat\s+can\s+you\s+do\b",
        r"\bhow\s+can\s+you\s+help\b",
        r"\bwhat\s+(?:data|questions?)\s+(?:can|do)\s+you\b",
        r"\bwhich\s+banks?\s+(?:are|can|do)\b",
        r"\blist\s+(?:the\s+)?available\s+banks?\b",
        r"\bhelp\b.{0,30}\b(?:assistant|questions?|data)\b",
    ]
)

_FOLLOW_UP_PATTERNS = _compile(
    [
        r"^(?:and|also|then|so)\b",
        r"^(?:what|how)\s+about\b",
        r"^(?:why|how|when|where)\??$",
        r"^(?:compare|explain|summarise|summarize|show|list)\b",
        r"\b(?:it|its|that|those|this|these|them|same bank|previous year|last year)\b",
    ]
)

_CLARIFICATION_OR_NO_DATA_PATTERNS = _compile(
    [
        r"\bwhich\s+bank\b",
        r"\bselect\s+(?:a|the)\s+bank\b",
        r"\bprovide\s+(?:a|the)\s+bank\b",
        r"\bbank\s+name\b",
        r"\bnot\s+available\b",
        r"\bno\s+(?:verified\s+)?data\b",
        r"\bcould\s+not\s+retrieve\b",
        r"\bunable\s+to\s+retrieve\b",
        r"\bout\s+of\s+scope\b",
    ]
)

_OUTPUT_LEAK_PATTERNS = _compile(
    [
        r"\bAZURE_OPENAI_API_KEY\b",
        r"\bSECRET_KEY\s*=",
        r"\bBEGIN\s+(?:SYSTEM|DEVELOPER|HIDDEN)\b",
        r"\bthe\s+system\s+prompt\s+(?:is|says|contains)\b",
        r"\bdeveloper\s+message\s+(?:is|says|contains)\b",
        r"\bhidden\s+instructions?\s+(?:are|say|contain)\b",
        r"\bchain\s+of\s+thought\b",
        r"\btool\s+schema\b",
        r"\binternal\s+guardrails?\b",
    ]
)


def _matches_any(
    text: str,
    patterns: tuple[re.Pattern, ...],
) -> bool:
    return any(
        pattern.search(text)
        for pattern in patterns
    )


def evaluate_user_input(
    text: str,
    *,
    has_project_context: bool = False,
) -> GuardrailDecision:
    """
    Classify a user message before it is persisted or sent to Azure.
    """

    clean = _normalise(text)

    if not clean:
        return GuardrailDecision(
            allowed=False,
            category="empty",
            reason="empty_message",
            response=OUT_OF_SCOPE_RESPONSE,
        )

    if len(clean) > MAX_USER_INPUT_CHARS:
        return GuardrailDecision(
            allowed=False,
            category="too_long",
            reason="input_length_limit",
            response=(
                "Your question is too long for the data assistant. "
                "Please ask one concise ESG reporting or risk-analysis "
                "question at a time."
            ),
        )

    if _matches_any(
        clean,
        _INJECTION_PATTERNS,
    ):
        return GuardrailDecision(
            allowed=False,
            category="prompt_injection",
            reason="instruction_override_attempt",
            response=INJECTION_RESPONSE,
        )

    if _matches_any(
        clean,
        _SENSITIVE_PATTERNS,
    ):
        return GuardrailDecision(
            allowed=False,
            category="protected_information",
            reason="sensitive_information_request",
            response=SENSITIVE_RESPONSE,
        )

    if _matches_any(
        clean,
        _CREATIVE_OR_CONTROL_PATTERNS,
    ):
        return GuardrailDecision(
            allowed=False,
            category="out_of_scope",
            reason="creative_or_role_control_request",
            response=OUT_OF_SCOPE_RESPONSE,
        )

    strong_project_match = _matches_any(
        clean,
        _STRONG_PROJECT_PATTERNS,
    )
    weak_project_score = sum(
        1
        for pattern in _WEAK_PROJECT_PATTERNS
        if pattern.search(clean)
    )

    if (
        _matches_any(
            clean,
            _EXPLICIT_OFF_TOPIC_PATTERNS,
        )
        and not strong_project_match
    ):
        return GuardrailDecision(
            allowed=False,
            category="out_of_scope",
            reason="explicit_off_topic_request",
            response=OUT_OF_SCOPE_RESPONSE,
        )

    if _matches_any(
        clean,
        _CAPABILITY_PATTERNS,
    ):
        return GuardrailDecision(
            allowed=True,
            category="assistant_capability",
            reason="allowed_capability_request",
            requires_grounding=False,
        )

    if strong_project_match:
        return GuardrailDecision(
            allowed=True,
            category="project_data",
            reason="strong_project_scope_match",
            requires_grounding=True,
        )

    if weak_project_score >= 2:
        return GuardrailDecision(
            allowed=True,
            category="project_data",
            reason="multiple_project_scope_matches",
            requires_grounding=True,
        )

    if (
        has_project_context
        and weak_project_score >= 1
    ):
        return GuardrailDecision(
            allowed=True,
            category="project_follow_up",
            reason="project_term_with_conversation_context",
            requires_grounding=True,
        )

    if (
        has_project_context
        and len(clean) <= 240
        and _matches_any(
            clean,
            _FOLLOW_UP_PATTERNS,
        )
    ):
        return GuardrailDecision(
            allowed=True,
            category="project_follow_up",
            reason="contextual_follow_up",
            requires_grounding=True,
        )

    return GuardrailDecision(
        allowed=False,
        category="out_of_scope",
        reason="no_project_scope_match",
        response=OUT_OF_SCOPE_RESPONSE,
    )


def guardrail_metadata(
    decision: GuardrailDecision,
) -> list[dict]:
    return [
        {
            "type": "guardrail",
            "blocked": not decision.allowed,
            "category": decision.category,
            "reason": decision.reason,
        }
    ]


def is_guardrail_message(message) -> bool:
    for item in getattr(
        message,
        "tool_calls",
        None,
    ) or []:
        if (
            isinstance(item, dict)
            and item.get("type") == "guardrail"
        ):
            return True
    return False


def conversation_has_project_context(
    conversation,
) -> bool:
    if getattr(
        conversation,
        "bank_id",
        None,
    ):
        return True

    try:
        recent_messages = (
            conversation.messages
            .order_by("-created_at")[:8]
        )
    except Exception:
        return False

    for message in recent_messages:
        if is_guardrail_message(message):
            continue

        if (
            getattr(message, "role", "")
            == "assistant"
            and bool(
                getattr(
                    message,
                    "citations",
                    None,
                )
            )
        ):
            return True

    return False


def history_message_is_safe(
    message,
    *,
    has_project_context: bool,
) -> bool:
    if is_guardrail_message(message):
        return False

    content = getattr(
        message,
        "content",
        "",
    )

    if getattr(message, "role", "") == "user":
        decision = evaluate_user_input(
            content,
            has_project_context=has_project_context,
        )
        return decision.allowed

    if getattr(message, "role", "") == "assistant":
        clean = _normalise(content)
        return not _matches_any(
            clean,
            _OUTPUT_LEAK_PATTERNS,
        )

    return False


def validate_assistant_output(
    text: str,
    *,
    citations: list[dict] | None,
    input_decision: GuardrailDecision,
    bank_code: str | None = None,
    bank_name: str | None = None,
) -> OutputDecision:
    """
    Validate a completed answer before it is sent to the browser.

    For project-data questions, a factual answer must have at least one tool
    citation. A clarification or explicit no-data answer is allowed without a
    citation.
    """

    clean = str(text or "").strip()

    if not clean:
        return OutputDecision(
            text=UNVERIFIED_RESPONSE,
            accepted=False,
            reason="empty_model_output",
        )

    if len(clean) > MAX_ASSISTANT_OUTPUT_CHARS:
        clean = clean[
            :MAX_ASSISTANT_OUTPUT_CHARS
        ].rstrip() + "…"

    if _matches_any(
        _normalise(clean),
        _OUTPUT_LEAK_PATTERNS,
    ):
        return OutputDecision(
            text=SENSITIVE_RESPONSE,
            accepted=False,
            reason="protected_output_pattern",
        )

    if (
        input_decision.requires_grounding
        and not citations
        and not _matches_any(
            clean,
            _CLARIFICATION_OR_NO_DATA_PATTERNS,
        )
    ):
        return OutputDecision(
            text=UNVERIFIED_RESPONSE,
            accepted=False,
            reason="ungrounded_project_answer",
        )

    if (
        bank_code
        and bank_name
    ):
        clean = re.sub(
            rf"\b{re.escape(bank_code)}\b",
            bank_name,
            clean,
            flags=re.IGNORECASE,
        )

    return OutputDecision(
        text=clean,
        accepted=True,
    )
