"""
Core lead-qualification logic.
No Google Sheets or Streamlit code here — just takes lead info in,
returns a scored result. Reused by both the Streamlit app and the
original batch sheet-scanning script.
"""

import os
import json
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client_ai = Groq(api_key=GROQ_API_KEY)


def qualify_lead(name, company, source, notes):
    """
    Score a single lead using the LLM.
    Returns a dict: {score, status, next_action, reason}
    Raises on failure (caller decides how to handle/display the error).
    """
    prompt = f"""
You are a lead qualification assistant for a solar installation company.
Score the following lead from 1-10 and provide a next action.

Lead Info:
- Name: {name}
- Company: {company}
- Source: {source}
- Notes: {notes}

Respond in this exact JSON format:
{{
    "score": <number 1-10>,
    "status": "<Hot / Warm / Cold>",
    "next_action": "<one sentence recommended next action>",
    "reason": "<one sentence explanation of the score>"
}}

Respond with JSON only, no other text.
"""
    response = client_ai.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    json_string = response.choices[0].message.content
    result = json.loads(json_string)
    return result
