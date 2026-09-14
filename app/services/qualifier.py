import json
import re
from typing import Any

from app.schemas import QualificationResult
from app.services.provider import GroqProvider

SYSTEM_PROMPT = """You are an intent-first lead qualification engine.
Evaluate only the information supplied by the business qualification profile and the incoming lead.
Never invent budget, location, authority, urgency, project details, or other missing facts.

CRITICAL SCORING PRINCIPLES:
- Missing information is UNKNOWN. Do not subtract score merely because a field or required question is unanswered.
- Required questions are discovery prompts, not score prerequisites, unless the business profile explicitly identifies an item as a hard disqualifier.
- Explicit buying intent outranks missing BANT-style metadata. A person can be highly qualified even when authority, budget, or timeline has not yet been captured.
- Score demonstrated intent and fit, not form completeness.
- Apply supplied disqualifiers only when the lead clearly matches one.

CALIBRATION:
10 = committed transaction behavior: wants to buy/pay/sign/start now, requests a contract/payment step, or equivalent immediate purchase action.
9 = explicit purchase intent or a concrete near-term buying action, such as wanting to start today/tomorrow, move forward, or obtain pricing/quote for an immediate decision.
8 = strong sales intent: asks to book/schedule a sales step, consultation, estimate, demo, inspection, proposal, or equivalent next action.
6-7 = relevant and interested, but no clear buying action yet.
4-5 = exploratory/researching/general interest with a plausible fit.
1-3 = clearly unrelated, spam, solicitation, explicit disqualifier, or no credible sales need.

If the lead explicitly says they are ready to buy, want to buy, want to move forward, or want to start now/very soon, the score should normally be 9-10 unless a supplied disqualifier clearly applies.

Return valid JSON with exactly these keys:
score: integer 1-10
status: Hot, Warm, or Cold
next_action: concise recommended action appropriate to the demonstrated intent
reason: concise evidence-based explanation
intent_level: one of transaction, high, medium, low, none
disqualified: boolean
disqualifier_reason: string, empty when not disqualified

Status mapping is fixed: 8-10 Hot, 4-7 Warm, 1-3 Cold."""

_NEGATED_BUYING_PATTERNS = [
    r"\bnot\s+ready\s+to\s+(?:buy|purchase|start|move\s+forward|proceed)\b",
    r"\b(?:do\s+not|don't|doesn't|does\s+not)\s+(?:want|plan)\s+to\s+(?:buy|purchase|start|move\s+forward|proceed)\b",
    r"\bnot\s+interested\b",
    r"\bjust\s+browsing\b",
    r"\bresearch(?:ing)?\s+only\b",
]

_TRANSACTION_PATTERNS = [
    r"\bready\s+to\s+(?:buy|purchase|sign|start|move\s+forward|proceed)\b",
    r"\b(?:want|wants|wanted)\s+to\s+(?:buy|purchase|start|move\s+forward|proceed)\b",
    r"\b(?:buy|purchase)\s+now\b",
    r"\b(?:start|begin)\s+(?:today|tomorrow|now|asap|immediately)\b",
    r"\b(?:send|ready\s+for)\s+(?:me\s+)?(?:the\s+)?(?:contract|agreement|invoice|payment\s+link)\b",
    r"\bhow\s+(?:do|can)\s+(?:i|we)\s+(?:pay|purchase|sign|start)\b",
]

_HIGH_INTENT_PATTERNS = [
    r"\b(?:book|schedule)\s+(?:(?:a|an|the)\s+)?(?:call|demo|consultation|appointment|inspection|estimate)\b",
    r"\b(?:need|want|request(?:ing)?)\s+(?:(?:a|an|the)\s+)?(?:quote|estimate|proposal|pricing)\b",
    r"\b(?:get|send)\s+(?:(?:me|us)\s+)?(?:(?:a|an|the)\s+)?(?:quote|estimate|proposal|pricing)\b",
]

_NEAR_TERM_WORDS = re.compile(
    r"\b(?:today|tomorrow|asap|immediately|right\s+away|this\s+week|now)\b",
    flags=re.I,
)
_COMMERCIAL_WORDS = re.compile(
    r"\b(?:pricing|price|quote|estimate|proposal|buy|purchase|start|book|schedule|sign|contract)\b",
    flags=re.I,
)


def build_prompt(profile: dict[str, Any], lead: dict[str, Any]) -> str:
    return "\n".join([
        "BUSINESS QUALIFICATION PROFILE",
        json.dumps(profile, ensure_ascii=False, indent=2),
        "",
        "INCOMING LEAD",
        json.dumps(lead, ensure_ascii=False, indent=2),
        "",
        "Remember: unanswered fields are unknown, not negative evidence.",
        "Return JSON only.",
    ])


def normalize_result(raw: dict[str, Any]) -> QualificationResult:
    score = int(raw.get("score", 0))
    score = max(1, min(10, score))
    expected = "Hot" if score >= 8 else "Warm" if score >= 4 else "Cold"
    return QualificationResult(
        score=score,
        status=expected,
        next_action=str(raw.get("next_action", "")).strip() or "Review the lead manually.",
        reason=str(raw.get("reason", "")).strip() or "No explanation returned.",
    )


def _lead_text(lead: dict[str, Any]) -> str:
    pieces = [
        str(lead.get("notes") or ""),
        str(lead.get("source") or ""),
    ]
    attributes = lead.get("attributes")
    if isinstance(attributes, dict):
        pieces.extend(str(v) for v in attributes.values() if isinstance(v, (str, int, float)))
    return " ".join(pieces).strip().lower()


def _has_pattern(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def _intent_floor(lead: dict[str, Any]) -> int | None:
    text = _lead_text(lead)
    if not text or _has_pattern(_NEGATED_BUYING_PATTERNS, text):
        return None
    if _has_pattern(_TRANSACTION_PATTERNS, text):
        return 9
    if _COMMERCIAL_WORDS.search(text) and _NEAR_TERM_WORDS.search(text):
        return 9
    if _has_pattern(_HIGH_INTENT_PATTERNS, text):
        return 8
    return None


def _apply_guardrails(
    raw: dict[str, Any],
    result: QualificationResult,
    lead: dict[str, Any],
) -> QualificationResult:
    disqualified = raw.get("disqualified") is True
    if disqualified:
        score = min(result.score, 3)
        reason_detail = str(raw.get("disqualifier_reason") or "").strip()
        reason = reason_detail or result.reason
        return QualificationResult(
            score=score,
            status="Cold",
            next_action=result.next_action,
            reason=reason,
        )

    floor = _intent_floor(lead)
    model_intent = str(raw.get("intent_level") or "").strip().lower()
    if model_intent == "transaction":
        floor = max(floor or 0, 9)
    elif model_intent == "high":
        floor = max(floor or 0, 8)

    if floor and result.score < floor:
        score = floor
        status = "Hot" if score >= 8 else "Warm"
        if score >= 9:
            next_action = "Contact promptly to complete the next buying step and confirm any remaining details."
            reason = (
                "Explicit buying intent or an immediate commercial next step was detected; "
                "missing fields are treated as unknown rather than negative evidence."
            )
        else:
            next_action = result.next_action
            reason = (
                "A concrete sales action was requested, which warrants Hot priority even though "
                "some discovery details are still unknown."
            )
        return QualificationResult(
            score=score,
            status=status,
            next_action=next_action,
            reason=reason,
        )

    return result


def qualify(profile: dict[str, Any], lead: dict[str, Any], provider=None) -> QualificationResult:
    provider = provider or GroqProvider()
    raw = provider.complete_json(SYSTEM_PROMPT, build_prompt(profile, lead))
    result = normalize_result(raw)
    return _apply_guardrails(raw, result, lead)
