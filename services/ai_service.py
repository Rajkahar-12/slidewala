"""OpenRouter / OpenAI-compatible AI generation with validation and retry."""
import json
import os
import re

import requests

from services.image_service import enrich_slides_with_images

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
    default_model = os.getenv("AI_MODEL") or "openai/gpt-4o-mini"
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

    audience = str(payload.get("audience") or "general").strip().lower()
    tone = str(payload.get("tone") or "educational").strip().lower()
    theme = str(payload.get("theme") or "aurora").strip().lower()
    model = str(payload.get("model") or "").strip()
    style = str(payload.get("style") or "normal").strip().lower()
    content_length = str(payload.get("content_length") or "medium").strip().lower()

    return {
        "topic": topic,
        "audience": audience,
        "tone": tone,
        "theme": theme,
        "model": model,
        "style": style,
        "content_length": content_length,
    }


def _build_prompt(topic: str, audience: str, tone: str, theme: str, style: str, content_length: str, strict: bool = False) -> str:
    
    # Set the tone for the content based on the user's choice
    if style == "normal":
        content_style = "Write like a clear, educational textbook or a university lecture. Use structured bullet points, definitions, and logical steps."
    else:
        content_style = "Write like a high-impact Apple keynote or TED Talk. Use short, punchy phrases, strong action verbs, and minimal text."

    # Set the length
    length_rule = ""
    if content_length == "short":
        length_rule = "Keep bullet points to 1 short sentence."
    elif content_length == "detailed":
        length_rule = "Provide detailed explanations. Bullet points should be 2-3 sentences long, explaining the 'how' and 'why'."
    else:
        length_rule = "Provide balanced explanations. Bullet points should be 1-2 clear sentences."

    prompt = f"""You are an expert educator and presentation designer. Create a presentation for a {audience} audience.

Topic: {topic}
Tone: {tone}
Style: {content_style}
Length Rule: {length_rule}

STRUCTURAL RULES:
- Start with a strong Title slide.
- End with a Conclusion / Thank You slide.
- Organize the middle slides logically (e.g., Introduction, Key Concepts, Step-by-Step Process, Examples, Analysis). Do not repeat content.
- If the user's topic explicitly asks for a specific number of slides (e.g., "5 slides"), generate exactly that many.
- If no number is specified, generate exactly 8 slides.

IMAGE GENERATION RULES (CRITICAL):
- The "image_query" will be sent to an AI image generator (Pollinations AI).
- It must be a highly descriptive, safe, educational visual prompt.
- Example: "A 3D educational diagram of the human sperm cell, labeled with acrosome, head, midpiece, and tail, clean white background, scientific illustration."
- NEVER use abstract words. Describe exactly what should be drawn.
- Keep it strictly safe: no nudity, no violence, no gore.

Return ONLY valid JSON in this exact shape:

{{
  "title": "Overall presentation title",
  "subtitle": "One-line subtitle",
  "slides": [
    {{
      "layout": "image-left",
      "title": "Slide title",
      "subtopic": "Subtopic (only for Normal style, else empty string)",
      "bullets": ["point 1", "point 2", "point 3"],
      "speaker_notes": "What the speaker says.",
      "image_query": "A highly descriptive visual prompt for the AI image generator"
    }}
  ]
}}
"""
    if strict:
        prompt += "\n\nIMPORTANT: You MUST follow the slide count rules strictly. Output exactly the number requested or 8 slides."
    return prompt


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


def _validate_output(data: dict) -> dict:
    if not isinstance(data, dict):
        raise AIResponseError("The AI response was not a JSON object.")

    title = str(data.get("title") or "").strip()[:160]
    subtitle = str(data.get("subtitle") or "").strip()[:240]
    raw_slides = data.get("slides")

    if not title:
        raise AIResponseError("The AI response is missing the presentation title.")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise AIResponseError("The AI response is missing slides.")
    
    if len(raw_slides) < 3 or len(raw_slides) > 30:
        raise AIResponseError(f"The AI returned an invalid number of slides ({len(raw_slides)}). Please try again.")

    slides = []
    for index, raw in enumerate(raw_slides, start=1):
        if not isinstance(raw, dict):
            continue

        slide_title = str(raw.get("title") or f"Slide {index}").strip()[:160]
        subtopic = str(raw.get("subtopic") or "").strip()[:200]
        
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

        image_query = str(raw.get("image_query") or "").strip()[:300]

        slides.append(
            {
                "layout": layout,
                "title": slide_title or f"Slide {index}",
                "subtopic": subtopic,
                "bullets": bullets,
                "speaker_notes": notes,
                "image_query": image_query,
            }
        )

    return {"title": title, "subtitle": subtitle, "slides": slides}


def _call_ai(topic, audience, tone, theme, style, content_length, model_name=None, strict=False):
    api_key, base_url, default_model, timeout = _get_config()
    active_model = model_name if model_name else default_model

    prompt = _build_prompt(topic, audience, tone, theme, style, content_length, strict)

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
                    "You are SlideWala, a senior academic presentation designer. "
                    "You always answer with one valid JSON object and nothing else. "
                    "You are strictly prohibited from generating explicit, NSFW, or unsafe image prompts."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6, # Balanced creativity and structure
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
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
                style=inputs["style"],
                content_length=inputs["content_length"],
                model_name=inputs["model"],
                strict=(attempt == 1),
            )
            deck = _validate_output(raw)
            deck["audience"] = inputs["audience"]
            deck["tone"] = inputs["tone"]
            deck["theme"] = inputs["theme"]
            
            enrich_slides_with_images(deck)
            
            return deck
        except AIResponseError as exc:
            last_error = exc
            continue

    raise last_error or AIResponseError("The AI could not generate a valid presentation.")
