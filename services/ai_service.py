"""OpenRouter / OpenAI-compatible AI generation with validation and retry."""
import json
import os
import re

import requests

from services.image_service import enrich_slides_with_images

ALLOWED_SLIDE_COUNTS = {5, 8, 10, 12}
ALLOWED_AUDIENCES = {"student", "teacher", "professional", "general"}
ALLOWED_TONES = {"educational", "formal", "persuasive", "casual", "inspiring"}
ALLOWED_THEMES = {"midnight", "aurora", "minimal", "corporate"}
ALLOWED_LAYOUTS = {
    "title", "intro", "content", "image-left", "image-right",
    "full-image", "comparison", "conclusion", "references",
}


class AIConfigError(Exception):
    """Raised when the server has no AI key configured."""


class AIResponseError(Exception):
    """Raised when the AI returns invalid or incomplete content."""


def _get_config():
    key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY") or "").strip()
    if not key:
        raise AIConfigError(
            "AI is not configured. Add OPENROUTER_API_KEY (or AI_API_KEY) to your "
            ".env file locally, or to Render environment variables, then restart."
        )
    base_url = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    default_model = os.getenv("AI_MODEL") or "google/gemini-2.5-flash"
    try:
        timeout = int(os.getenv("AI_TIMEOUT") or "60")
    except ValueError:
        timeout = 60
    return key, base_url, default_model, timeout


def _validate_input(payload: dict):
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("Please enter a presentation topic.")
    if len(topic) > 200:
        raise ValueError("Topic is too long. Keep it under 200 characters.")

    try:
        slide_count = int(payload.get("slides"))
    except (TypeError, ValueError):
        raise ValueError("Please choose a valid slide count.")

    if slide_count not in ALLOWED_SLIDE_COUNTS:
        allowed = ", ".join(str(n) for n in sorted(ALLOWED_SLIDE_COUNTS))
        raise ValueError(f"Slide count must be one of: {allowed}.")

    audience = str(payload.get("audience") or "general").strip().lower()
    tone = str(payload.get("tone") or "educational").strip().lower()
    theme = str(payload.get("theme") or "aurora").strip().lower()
    model = str(payload.get("model") or "").strip()

    return {
        "topic": topic,
        "slides": slide_count,
        "audience": audience,
        "tone": tone,
        "theme": theme,
        "model": model,
    }


def _build_prompt(topic: str, audience: str, tone: str, theme: str, slide_count: int) -> str:
    return f"""Create a presentation for a {audience} audience.

Topic: {topic}
Tone: {tone}
Visual theme: {theme}
Exact number of slides: {slide_count}

Requirements:
- Return exactly {slide_count} slides.
- Slide 1 must be a strong title/intro slide.
- The last slide must be a conclusion or call to action.
- Include an introduction, logically ordered main content, and conclusion.
- If the topic benefits from references, add a references slide at the end.
- Every slide needs a short, strong title.
- Every slide needs 3 to 5 short bullet points (max 6).
- Every slide needs 2 to 4 sentences of speaker notes, separate from visible slide text.
- Add a specific "image_query" for most slides. It must be a concrete Wikimedia
  Commons search phrase (e.g. "artificial intelligence robot laboratory"), not
  a generic word like "technology".
- For references slides, image_query must be an empty string.
- Use one of these layouts: title, intro, content, image-left, image-right,
  full-image, comparison, conclusion, references.
- Do not repeat the same content across slides. No filler.

Return ONLY valid JSON in this exact shape, with no markdown and no text outside the JSON:

{{
  "title": "Overall presentation title",
  "subtitle": "One-line subtitle",
  "slides": [
    {{
      "layout": "title",
      "title": "Slide title",
      "bullets": ["point 1", "point 2", "point 3"],
      "speaker_notes": "What the speaker says.",
      "image_query": "specific image search phrase"
    }}
  ]
}}
"""


def _extract_json(text: str) -> dict:
    if not text:
        raise AIResponseError("The AI returned an empty response.")

    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise AIResponseError("The AI returned content that is not valid JSON.")


def _validate_output(data: dict, expected_slides: int) -> dict:
    if not isinstance(data, dict):
        raise AIResponseError("The AI response was not a JSON object.")

    title = str(data.get("title") or "").strip()[:160]
    subtitle = str(data.get("subtitle") or "").strip()[:240]
    raw_slides = data.get("slides")

    if not title:
        raise AIResponseError("The AI response is missing the presentation title.")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise AIResponseError("The AI response is missing slides.")
    if len(raw_slides) != expected_slides:
        raise AIResponseError(
            f"The AI returned {len(raw_slides)} slide(s) but you asked for "
            f"{expected_slides}. Please try again."
        )

    slides = []
    for index, raw in enumerate(raw_slides, start=1):
        if not isinstance(raw, dict):
            continue

        slide_title = str(raw.get("title") or f"Slide {index}").strip()[:160]
        bullets_raw = raw.get("bullets") or []
        if not isinstance(bullets_raw, list):
            bullets_raw = [str(bullets_raw)]

        bullets = []
        for bullet in bullets_raw:
            text = str(bullet).strip()[:300]
            if text:
                bullets.append(text)
        if len(bullets) < 2:
            bullets.append("Key takeaway for this slide.")
        bullets = bullets[:6]

        notes = str(raw.get("speaker_notes") or "").strip()[:2400]
        if not notes:
            notes = "No speaker notes were generated for this slide."

        layout = str(raw.get("layout") or "content").strip().lower()
        if layout not in ALLOWED_LAYOUTS:
            layout = "content"

        image_query = str(raw.get("image_query") or "").strip()[:80]

        slides.append(
            {
                "layout": layout,
                "title": slide_title or f"Slide {index}",
                "bullets": bullets,
                "speaker_notes": notes,
                "image_query": image_query,
            }
        )

    if len(slides) != expected_slides:
        raise AIResponseError(
            f"Only {len(slides)} valid slide(s) were produced. Please try again."
        )

    return {"title": title, "subtitle": subtitle, "slides": slides}


def _call_ai(topic, audience, tone, theme, slide_count, model_name=None, strict=False):
    api_key, base_url, default_model, timeout = _get_config()
    active_model = model_name if model_name else default_model

    prompt = _build_prompt(topic, audience, tone, theme, slide_count)
    if strict:
        prompt += f"\n\nIMPORTANT: Return exactly {slide_count} slides. Count them before replying."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://slidewala.example"),
        "X-OpenRouter-Title": "SlideWala",
    }

    payload = {
        "model": active_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are SlideWala, a senior presentation designer. "
                    "You always answer with one valid JSON object and nothing else."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.65,
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,  # 🚨 FIXES THE 402 CREDIT ERROR
    }

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        raise AIResponseError("The AI service took too long to respond. Please try again.")
    except requests.ConnectionError:
        raise AIResponseError("Could not reach the AI service. Check your internet connection and AI_BASE_URL.")
    except requests.RequestException as exc:
        raise AIResponseError(f"Network error while contacting the AI: {exc}")

    # Some OpenRouter models reject response_format; retry without it
    if response.status_code == 400 and "response_format" in (response.text or ""):
        payload.pop("response_format", None)
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise AIResponseError(f"Network error while contacting the AI: {exc}")

    if response.status_code == 401:
        raise AIConfigError("The AI API key was rejected. Check OPENROUTER_API_KEY.")
    if response.status_code == 402:
        raise AIResponseError("Your OpenRouter account is out of credits. Please add funds or use a free model.")
    if response.status_code == 429:
        raise AIResponseError("The AI provider is rate-limiting requests. Wait a moment and try again.")
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = (response.text or "")[:200]
        raise AIResponseError(f"AI service error ({response.status_code}): {detail or 'Unknown error'}")

    try:
        body = response.json()
        choices = body.get("choices") or []
        
        if not choices:
            raise AIResponseError("OpenRouter returned an empty response. Please try again.")
            
        content = choices[0].get("message", {}).get("content")
        
        if not content or not str(content).strip():
            raise AIResponseError("OpenRouter returned empty text. The model might be overloaded. Please try again.")
            
    except AIResponseError:
        raise
    except (KeyError, IndexError, ValueError):
        raise AIResponseError("The AI service returned an unexpected response format.")

    return _extract_json(content)


def generate_presentation(payload: dict) -> dict:
    inputs = _validate_input(payload)
    last_error = None

    for attempt in range(2):
        try:
            raw = _call_ai(
                topic=inputs["topic"],
                audience=inputs["audience"],
                tone=inputs["tone"],
                theme=inputs["theme"],
                slide_count=inputs["slides"],
                model_name=inputs["model"],
                strict=(attempt == 1),
            )
            deck = _validate_output(raw, inputs["slides"])
            deck["audience"] = inputs["audience"]
            deck["tone"] = inputs["tone"]
            deck["theme"] = inputs["theme"]
            enrich_slides_with_images(deck)
            return deck
        except AIResponseError as exc:
            last_error = exc
            continue

    raise last_error or AIResponseError("The AI could not generate a valid presentation.")
