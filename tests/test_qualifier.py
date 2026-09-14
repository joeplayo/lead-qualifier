from app.services.qualifier import build_prompt, normalize_result, qualify

class FakeProvider:
    def complete_json(self, system, user):
        return {
            "score": 9,
            "status": "warm",
            "next_action": "Call within 10 minutes.",
            "reason": "The lead requested an estimate this week.",
        }

def test_status_is_consistent_with_score():
    result = normalize_result({
        "score": 9,
        "status": "cold",
        "next_action": "Call",
        "reason": "High intent",
    })
    assert result.status == "Hot"

def test_prompt_contains_profile_and_lead_without_vertical_hardcoding():
    prompt = build_prompt({"name": "Custom Agency"}, {"notes": "Need PPC help"})
    assert "Custom Agency" in prompt
    assert "Need PPC help" in prompt
    assert "solar installation company" not in prompt.lower()

def test_qualify_accepts_swappable_provider():
    result = qualify({"name": "Roofing"}, {"notes": "Leak"}, provider=FakeProvider())
    assert result.score == 9
    assert result.status == "Hot"


class LowBallProvider:
    def __init__(self, raw=None):
        self.raw = raw or {
            "score": 6,
            "status": "Warm",
            "next_action": "Ask discovery questions.",
            "reason": "Authority and timeline are unknown.",
            "intent_level": "medium",
            "disqualified": False,
            "disqualifier_reason": "",
        }

    def complete_json(self, system, user):
        return self.raw


def test_explicit_ready_to_buy_cannot_be_lowballed_by_missing_bant_fields():
    result = qualify(
        {"name": "Custom", "required_questions": ["Decision-maker", "Timeline"]},
        {"notes": "They're ready to buy", "email": "buyer@example.com"},
        provider=LowBallProvider(),
    )
    assert result.score >= 9
    assert result.status == "Hot"
    assert "missing fields" in result.reason.lower()


def test_pricing_plus_tomorrow_is_hot_even_if_model_returns_warm():
    result = qualify(
        {"name": "Custom"},
        {"notes": "Asked for pricing and wants to start tomorrow"},
        provider=LowBallProvider(),
    )
    assert result.score >= 9
    assert result.status == "Hot"


def test_direct_booking_request_is_at_least_hot():
    result = qualify(
        {"name": "Custom"},
        {"notes": "I want to schedule a consultation"},
        provider=LowBallProvider(),
    )
    assert result.score >= 8
    assert result.status == "Hot"


def test_negated_buying_intent_does_not_force_hot():
    result = qualify(
        {"name": "Custom"},
        {"notes": "I'm not ready to buy, just browsing"},
        provider=LowBallProvider(),
    )
    assert result.score == 6
    assert result.status == "Warm"


def test_clear_disqualifier_caps_score_even_with_transaction_language():
    provider = LowBallProvider({
        "score": 9,
        "status": "Hot",
        "next_action": "Do not pursue.",
        "reason": "Vendor solicitation.",
        "intent_level": "transaction",
        "disqualified": True,
        "disqualifier_reason": "Vendor solicitation matches the supplied disqualifier.",
    })
    result = qualify(
        {"name": "Custom", "disqualifiers": ["Vendor solicitation"]},
        {"notes": "Vendor wants to start tomorrow and sell us software"},
        provider=provider,
    )
    assert result.score <= 3
    assert result.status == "Cold"


def test_prompt_explicitly_says_missing_fields_are_not_negative():
    from app.services.qualifier import SYSTEM_PROMPT
    text = SYSTEM_PROMPT.lower()
    assert "missing information is unknown" in text
    assert "do not subtract score" in text
