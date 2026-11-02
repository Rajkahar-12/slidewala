
"""SlideWala AI service using one OpenRouter API key."""

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

DEFAULT_MODELS = {
    "chatgpt": "openai/gpt-4o-mini",
    "openai": "openai/gpt-4o-mini",
    "claude": "anthropic/claude-sonnet-4.6",
    "anthropic": "anthropic/claude-sonnet-4.6",
}


class AIConfigError(Exception):
    """Raised when OpenRouter configuration is missing."""


class AIResponseError(Exception):
    """Raised when the AI returns invalid content."""


def _get_config(provider="chatgpt"):
    """Get OpenRouter configuration and selected model."""

    api_key = (
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("AI_API_KEY")
        or ""
    ).strip()

    if not api_key:
        raise AIConfigError(
            "OpenRouter API key is missing. Add OPENROUTER_API_KEY "
            "to your .env file or Render environment variables."
        )

    base_url = (
        os.getenv("AI_BASE_URL")
        or "https://openrouter.ai/api/v1"
    ).rstrip("/")

    provider = str(provider or "chatgpt").strip().lower()

    if provider not in DEFAULT_MODELS:
        raise ValueError("Please select ChatGPT or Claude.")

    # Model IDs are selected through OpenRouter.
    if provider in ("chatgpt", "openai"):
        model = (
            os.getenv("OPENAI_MODEL")
            or os.getenv("AI_MODEL")
            or DEFAULT_MODELS[provider]
        )
    else:
        model = (
            os.getenv("CLAUDE_MODEL")
            or os.getenv("AI_CLAUDE_MODEL")
            or DEFAULT_MODELS[provider]
        )

    try:
        timeout = int(os.getenv("AI_TIMEOUT") or "90")
    except ValueError:
        timeout = 90

    return api_key, base_url, model, timeout


def _validate_input(payload):
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

    audience = str(
        payload.get("audience") or "general"
    ).strip().lower()

    if audience not in ALLOWED_AUDIENCES:
        raise ValueError(
            "Audience must be student, teacher, professional, or general."
        )

    tone = str(
        payload.get("tone") or "educational"
    ).strip().lower()

    if tone not in ALLOWED_TONES:
        raise ValueError(
            "Tone must be educational, formal, persuasive, casual, or inspiring."
        )

    theme = str(
        payload.get("theme") or "aurora"
    ).strip().lower()

    if theme not in ALLOWED_THEMES:
        raise ValueError(
            "Theme must be midnight, aurora, minimal, or corporate."
        )

    provider = str(
        payload.get("provider")
        or os.getenv("AI_PROVIDER")
        or "chatgpt"
    ).strip().lower()

    if provider not in DEFAULT_MODELS:
        raise ValueError("AI provider must be ChatGPT or Claude.")

    return {
        "topic": topic,
        "slides": slide_count,
        "audience": audience,
        "tone": tone,
        "theme": theme,
        "provider": provider,
    }


def _build_prompt(topic, audience, tone, theme, slide_count):
    return f"""Create a professional PowerPoint presentation.

Topic: {topic}
Audience: {audience}
Tone: {tone}
Visual theme: {theme}
Exact number of slides: {slide_count}

Requirements:

- Return exactly {slide_count} slides.
- Slide 1 must be a strong title or introduction slide.
- The last slide must be a conclusion or call to action.
- Include an introduction and logically ordered main content.
- Every slide needs a short, strong title.
- Every slide needs 3 to 5 useful bullet points.
- Keep bullet points short and easy to understand.
- Every slide needs 2 to 4 sentences of speaker notes.
- Speaker notes must explain the slide in more detail.
- Add a specific image_query for most slides.
- Use descriptive image search phrases, not generic words.
- For references slides, image_query must be empty.
- Use only these layouts:
  title, intro, content, image-left, image-right,
  full-image, comparison, conclusion, references.
- Do not repeat information across slides.
- Do not add filler content.
- Make the presentation informative and engaging.

Return ONLY valid JSON in this exact structure.
Do not include Markdown or explanations outside the JSON.

{{
    "title": "Overall presentation title",
    "subtitle": "One-line subtitle",
    "slides": [
        {{
            "layout": "title",
            "title": "Slide title",
            "bullets": [
                "Point 1",
                "Point 2",
                "Point 3"
            ],
            "speaker_notes": "Detailed speaker explanation.",
            "image_query": "specific image search phrase"
        }}
    ]
}}
"""


def _extract_json(text):
    if not text:
        raise AIResponseError("The AI returned an empty response.")

    cleaned = text.strip()

    fence = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$",
        cleaned,
        re.DOTALL | re.IGNORECASE
    )

    if fence:
        cleaned = fence.group(1).strip()

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass

    raise AIResponseError(
        "The AI returned content that is not valid JSON."
    )


def _validate_output(data, expected_slides):
    if not isinstance(data, dict):
        raise AIResponseError("The AI response was not a JSON object.")

    title = str(data.get("title") or "").strip()[:160]
    subtitle = str(data.get("subtitle") or "").strip()[:240]

    raw_slides = data.get("slides")

    if not title:
        raise AIResponseError(
            "The AI response is missing the presentation title."
        )

    if not isinstance(raw_slides, list) or not raw_slides:
        raise AIResponseError("The AI response is missing slides.")

    if len(raw_slides) != expected_slides:
        raise AIResponseError(
            f"The AI returned {len(raw_slides)} slide(s), "
            f"but you requested {expected_slides}."
        )

    slides = []

    for index, raw in enumerate(raw_slides, start=1):
        if not isinstance(raw, dict):
            continue

        slide_title = str(
            raw.get("title") or f"Slide {index}"
        ).strip()[:160]

        bullets_raw = raw.get("bullets") or []

        if not isinstance(bullets_raw, list):
            bullets_raw = [str(bullets_raw)]

        bullets = []

        for bullet in bullets_raw:
            bullet_text = str(bullet).strip()[:300]

            if bullet_text:
                bullets.append(bullet_text)

        if len(bullets) < 2:
            bullets.append("Key takeaway for this slide.")

        bullets = bullets[:6]

        notes = str(
            raw.get("speaker_notes") or ""
        ).strip()[:2400]

        if not notes:
            notes = "No speaker notes were generated for this slide."

        layout = str(
            raw.get("layout") or "content"
        ).strip().lower()

        if layout not in ALLOWED_LAYOUTS:
            layout = "content"

        image_query = str(
            raw.get("image_query") or ""
        ).strip()[:120]

        slides.append({
            "layout": layout,
            "title": slide_title or f"Slide {index}",
            "bullets": bullets,
            "speaker_notes": notes,
            "image_query": image_query,
        })

    if len(slides) != expected_slides:
        raise AIResponseError(
            f"Only {len(slides)} valid slide(s) were produced."
        )

    return {
        "title": title,
        "subtitle": subtitle,
        "slides": slides,
    }


def _call_ai(topic, audience, tone, theme, slide_count,
             provider, strict=False):
    """Send the request to GPT or Claude through OpenRouter."""

    api_key, base_url, model, timeout = _get_config(provider)

    prompt = _build_prompt(
        topic, audience, tone, theme, slide_count
    )

    if strict:
        prompt += (
            f"\n\nIMPORTANT: Return exactly {slide_count} slides. "
            "Count them before replying. Return valid JSON only."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv(
            "OPENROUTER_SITE_URL",
            "https://slidewala.onrender.com"
        ),
        "X-OpenRouter-Title": "SlideWala",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are SlideWala, an expert presentation designer. "
                    "Return one valid JSON object and nothing else."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.65,
        "response_format": {"type": "json_object"},
    }

    url = f"{base_url}/chat/completions"

    try:
        with requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        ) as response:

            # Retry without response_format if the model
            # does not support JSON mode.
            if (
                response.status_code == 400
                and "response_format" in (response.text or "")
            ):
                payload.pop("response_format", None)

                with requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                ) as retry_response:
                    body = retry_response.json() if retry_response.ok else None

                    if not retry_response.ok:
                        _raise_api_error(retry_response)

            else:
                body = response.json() if response.ok else None

                if not response.ok:
                    _raise_api_error(response)

    except requests.Timeout:
        raise AIResponseError(
            "The AI service took too long to respond. Please try again."
        )

    except requests.ConnectionError:
        raise AIResponseError(
            "Could not reach OpenRouter. Check your internet connection."
        )

    except requests.RequestException as exc:
        raise AIResponseError(
            f"Network error while contacting OpenRouter: {exc}"
        )

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIResponseError(
            "OpenRouter returned an unexpected response format."
        )

    return _extract_json(content)


def _raise_api_error(response):
    if response.status_code in (401, 403):
        raise AIConfigError(
            "OpenRouter rejected your API key. Check OPENROUTER_API_KEY."
        )

    if response.status_code == 429:
        raise AIResponseError(
            "OpenRouter is rate-limiting requests. "
            "Check your credits and try again."
        )

    try:
        detail = response.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = (response.text or "")[:250]

    raise AIResponseError(
        f"OpenRouter error ({response.status_code}): "
        f"{detail or 'Unknown error'}"
    )


def generate_presentation(payload):
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
                provider=inputs["provider"],
                strict=(attempt == 1),
            )

            deck = _validate_output(
                raw,
                inputs["slides"]
            )

            deck["audience"] = inputs["audience"]
            deck["tone"] = inputs["tone"]
            deck["theme"] = inputs["theme"]
            deck["provider"] = inputs["provider"]

            # Optional Wikimedia images.
            # If image search fails, the presentation still works.
            if os.getenv(
                "ENABLE_WIKIMEDIA_IMAGES", "true"
            ).lower() in ("true", "1", "yes", "on"):

                try:
                    enrich_slides_with_images(deck["slides"])
                except Exception:
                    pass

            return deck

        except AIResponseError as exc:
            last_error = exc

    raise last_error or AIResponseError(
        "The AI could not generate a valid presentation."
    )
