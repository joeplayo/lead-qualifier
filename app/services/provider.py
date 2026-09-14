import json
import re
import httpx

from app.config import settings

class ProviderError(RuntimeError):
    pass

def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ProviderError("Model did not return JSON")
        return json.loads(match.group(0))

class GroqProvider:
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def complete_json(self, system: str, user: str) -> dict:
        if not settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is not configured")

        payload = {
            "model": settings.groq_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=settings.qualification_timeout_seconds) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"LLM provider request failed: {exc}") from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected LLM provider response") from exc
        return _extract_json(content)
