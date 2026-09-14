# LeadLift v0.6.2 — scoring calibration hotfix

- Reworked qualification to be intent-first instead of BANT-completeness-first.
- Missing/unknown fields no longer lower a lead's intent/fit score by themselves.
- Explicit buying intent such as ready to buy, buy now, move forward, or start immediately sets a Hot score floor unless a real disqualifier applies.
- Pricing/quote plus near-term timing receives Hot priority.
- Direct booking/scheduling/estimate/demo requests receive a Hot score floor.
- Explicit negation such as not ready to buy or just browsing prevents the deterministic buying-intent floor.
- Confirmed disqualifiers cap a lead in Cold territory.
- Updated the Custom preset wording so required discovery questions are not treated as score prerequisites.
- Updated the default/example Groq model to openai/gpt-oss-20b for the currently configured account.
- Added regression tests for explicit buying intent, near-term pricing, booking requests, negation, and disqualifier precedence.
