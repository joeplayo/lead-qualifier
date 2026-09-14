PRESETS = {
    "roofing": {
        "name": "Roofing",
        "business_context": "Residential or commercial roofing contractor qualifying inbound project leads.",
        "high_intent_signals": [
            "Active leak or storm damage",
            "Property owner or authorized decision-maker",
            "Requests inspection, estimate, repair, or replacement",
            "Project is inside the contractor service area",
            "Near-term project timing",
        ],
        "medium_intent_signals": [
            "Researching roof age, materials, or replacement timing",
            "Interested but project timing is not yet clear",
        ],
        "disqualifiers": [
            "Clearly outside service area",
            "Vendor solicitation or job applicant",
            "No roofing-related need",
        ],
        "required_questions": [
            "Property location",
            "Repair, replacement, inspection, or other need",
            "Urgency or desired project timing",
            "Whether the contact can authorize the work",
        ],
        "custom_instructions": "Prioritize urgent damage and clear estimate or inspection requests. Do not infer insurance coverage, property ownership, budget, or location when absent.",
    },
    "solar": {
        "name": "Solar",
        "business_context": "Solar installer qualifying prospective residential or commercial customers.",
        "high_intent_signals": [
            "Requests solar quote or consultation",
            "Decision-maker for the property",
            "Near-term purchase intent",
            "Provides property or energy-use details",
        ],
        "medium_intent_signals": [
            "General savings or equipment questions",
            "Exploring solar without a defined timeline",
        ],
        "disqualifiers": [
            "Vendor solicitation or employment inquiry",
            "No solar-related need",
        ],
        "required_questions": [
            "Property location",
            "Property type",
            "Decision-making authority",
            "Desired timeline",
        ],
        "custom_instructions": "Do not infer utility bill, financing eligibility, tax credit eligibility, or property ownership when absent.",
    },
    "agency": {
        "name": "Agency",
        "business_context": "Professional services or marketing agency qualifying prospective clients.",
        "high_intent_signals": [
            "Specific business problem and desired outcome",
            "Decision-maker involvement",
            "Defined project timing",
            "Requests proposal, consultation, or scope discussion",
        ],
        "medium_intent_signals": [
            "Has a relevant need but lacks scope or timing",
            "Early research into services",
        ],
        "disqualifiers": [
            "Vendor solicitation",
            "Job applicant",
            "Request unrelated to offered services",
        ],
        "required_questions": [
            "Primary objective",
            "Desired timeline",
            "Decision-maker",
            "Current approach or provider",
        ],
        "custom_instructions": "Do not fabricate budget, company size, authority, or purchasing urgency.",
    },
    "custom": {
        "name": "Custom",
        "business_context": "General inbound sales qualification.",
        "high_intent_signals": ["Clear need", "Decision-making authority", "Near-term timing", "Specific request to buy, book, or speak with sales"],
        "medium_intent_signals": ["Relevant interest but incomplete buying context"],
        "disqualifiers": ["Spam", "Vendor solicitation", "Clearly unrelated inquiry"],
        "required_questions": ["Need", "Timing", "Decision-making authority"],
        "custom_instructions": "Base the score only on supplied information. Missing information is unknown and must not lower intent/fit by itself. Prioritize explicit requests to buy, book, quote, schedule, or start.",
    },
}
