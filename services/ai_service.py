
"""SlideWala AI service with automatic GPT/Claude routing through OpenRouter."""

import json
import os
import re
import requests

from services.image_service import enrich_slides_with_images


ALLOWED_SLIDE_COUNTS = {5, 8, 10, 12}

ALLOWED_AUDIENCES = {
    "student", "teacher", "professional", "general"
}

ALLOWED_TONES = {
    "educational", "formal", "persuasive", "casual", "inspiring"
}

ALLOWED_CONTENT_LENGTHS = {
    "short", "medium", "detailed"
}

CONTENT_LENGTH_GUIDES = {
    "short": (
        "Write exactly 2 to 3 concise bullet points per slide. "
        "Each point should communicate one useful idea clearly "
        "without unnecessary explanation."
    ),
    "medium": (
        "Write exactly 3 to 4 meaningful bullet points per slide. "
        "Explain each idea clearly with enough detail to be useful, "
        "but keep the slide easy to read."
    ),
    "detailed": (
        "Write exactly 4 to 5 informative bullet points per slide. "
        "Give each point a useful explanation, include relevant "
        "details or examples, and avoid unnecessary repetition."
    ),
}

THEME_DESCRIPTIONS = {
    "aurora": "soft purple, elegant gradients and light backgrounds",
    "midnight": "premium dark backgrounds with violet accents",
    "minimal": "clean white backgrounds and simple typography",
    "corporate": "professional blue, white and business styling",
    "ocean": "fresh teal, aqua and ocean-inspired colours",
    "sunset": "warm orange, peach and sunset-inspired colours",
    "forest": "natural green, earthy and calm colours",
    "rose": "soft pink, rose and elegant styling",
    "lavender": "light violet, lavender and elegant styling",
    "graphite": "modern dark grey, silver and neutral styling",
    "sand": "warm beige, cream and natural neutral colours",
    "cyberpunk": "dark futuristic backgrounds with neon pink accents",
}

ALLOWED_LAYOUTS = {
    "title", "intro", "content", "image-left",
    "image-right", "full-image", "comparison",
    "conclusion", "references",
}

DEFAULT_MODELS = {
    "chatgpt": "openai/gpt-4o-mini",
    "claude": "anthropic/claude-sonnet-4.6",
}


class AIConfigError(Exception):
    """Raised when OpenRouter configuration is missing."""


class AIResponseError(Exception):
    """Raised when the AI returns invalid content."""


def _get_config(provider):
    """Get OpenRouter configuration for the selected model."""

    api_key = (
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("AI_API_KEY")
        or ""
    ).strip()

    if not api_key:
        raise AIConfigError(
            "OpenRouter API key is missing. Add OPENROUTER_API_KEY "
            "to your Render environment variables."
        )

    base_url = (
        os.getenv("AI_BASE_URL")
        or "https://openrouter.ai/api/v1"
    ).rstrip("/")

    if provider == "chatgpt":
        model = (
            os.getenv("OPENAI_MODEL")
            or os.getenv("AI_MODEL")
            or DEFAULT_MODELS["chatgpt"]
        )
    else:
        model = (
            os.getenv("CLAUDE_MODEL")
            or os.getenv("AI_CLAUDE_MODEL")
            or DEFAULT_MODELS["claude"]
        )

    try:
        timeout = int(os.getenv("AI_TIMEOUT") or "90")
    except ValueError:
        timeout = 90

    return api_key, base_url, model, timeout


def _choose_provider(topic, theme):
    """
    Select an AI internally using topic and visual theme.

    This selection is never shown to the user.
    """

    text = f"{topic} {theme}".lower()

    claude_keywords = {
        "business", "finance", "marketing", "management",
        "leadership", "strategy", "branding", "storytelling",
        "creative writing", "literature", "history",
        "philosophy", "culture", "design thinking",
        "communication", "advertising", "entrepreneurship",
    }

    gpt_keywords = {
        "coding", "programming", "software", "python",
        "javascript", "artificial intelligence", "machine learning",
        "computer science", "technology", "engineering",
        "mathematics", "statistics", "data science",
        "cybersecurity", "database", "physics", "chemistry",
        "biology", "research", "algorithm",
    }

    claude_score = sum(
        1 for word in claude_keywords if word in text
    )

    gpt_score = sum(
        1 for word in gpt_keywords if word in text
    )

    if theme in {"rose", "lavender", "sand", "sunset"}:
        claude_score += 1

    if theme in {"cyberpunk", "graphite", "ocean"}:
        gpt_score += 1

    if theme == "corporate":
        claude_score += 1

    if claude_score > gpt_score:
        return "claude"

    return "chatgpt"


def _validate_input(payload):
    """Validate user presentation settings."""

    topic = str(payload.get("topic") or "").strip()

    if not topic:
        raise ValueError("Please enter a presentation topic.")

    if len(topic) > 200:
        raise ValueError(
            "Topic is too long. Keep it under 200 characters."
        )

    author_name = str(
        payload.get("author_name") or ""
    ).strip()

    if len(author_name) > 80:
        raise ValueError(
            "Your name is too long. Keep it under 80 characters."
        )

    try:
        slide_count = int(payload.get("slides"))
    except (TypeError, ValueError):
        raise ValueError("Please choose a valid slide count.")

    if slide_count not in ALLOWED_SLIDE_COUNTS:
        allowed = ", ".join(
            str(number) for number in sorted(ALLOWED_SLIDE_COUNTS)
        )
        raise ValueError(
            f"Slide count must be one of: {allowed}."
        )

    audience = str(
        payload.get("audience") or "general"
    ).strip().lower()

    if audience not in ALLOWED_AUDIENCES:
        raise ValueError("Please choose a valid audience.")

    tone = str(
        payload.get("tone") or "educational"
    ).strip().lower()

    if tone not in ALLOWED_TONES:
        raise ValueError("Please choose a valid presentation tone.")

    theme = str(
        payload.get("theme") or "aurora"
    ).strip().lower()

    if theme not in THEME_DESCRIPTIONS:
        raise ValueError("Please choose a valid design theme.")

    content_length = str(
        payload.get("content_length") or "medium"
    ).strip().lower()

    if content_length not in ALLOWED_CONTENT_LENGTHS:
        raise ValueError("Please choose a valid content length.")

    return {
        "topic": topic,
        "author_name": author_name,
        "slides": slide_count,
        "audience": audience,
        "tone": tone,
        "theme": theme,
        "content_length": content_length,
    }


def _build_prompt(
    topic,
    audience,
    tone,
    theme,
    slide_count,
    content_length="medium",
):
    """Build the presentation-generation prompt."""

    theme_description = THEME_DESCRIPTIONS.get(
        theme, THEME_DESCRIPTIONS["aurora"]
    )

    content_guide = CONTENT_LENGTH_GUIDES.get(
        content_length,
        CONTENT_LENGTH_GUIDES["medium"]
    )

    return f"""Create a professional PowerPoint presentation.

Topic: {topic}
Audience: {audience}
Tone: {tone}

Selected visual theme: {theme}
Visual theme description: {theme_description}

Exact number of slides: {slide_count}

Selected content length: {content_length}

CONTENT LENGTH INSTRUCTIONS:

{content_guide}

IMPORTANT:
- Follow the selected content length consistently.
- Do not use extremely short or meaningless bullet points.
- Do not turn bullet points into long paragraphs.
- Make every point informative and relevant.
- Use simple language appropriate for the audience.
- Do not add extra bullets just to fill space.
- Title and conclusion slides may naturally contain fewer points.
- References slides should contain only relevant references.

DESIGN REQUIREMENTS:

- Follow the selected visual theme consistently.
- Use the theme's colours, visual mood and design style.
- Make slide titles clear and visually interesting.
- Avoid unnecessarily long text.
- Keep slides readable and professionally designed.
- Balance text and images appropriately.

PRESENTATION REQUIREMENTS:

- Return exactly {slide_count} slides.
- Slide 1 must be a strong title slide about the topic.
- The last slide title must be exactly "Thank You".
- The last slide must have a conclusion layout.
- Include an introduction and logically ordered main content.
- Every other slide needs a short, strong title.
- Follow the selected content length instructions for bullet points.
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
- Do not add SlideWala branding, logos, promotional text or watermarks.
- Do not invent or include a presenter name.

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
    """Extract a JSON object from the model response."""

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
    """Validate and clean generated presentation content."""

    if not isinstance(data, dict):
        raise AIResponseError(
            "The AI response was not a JSON object."
        )

    title = str(data.get("title") or "").strip()[:160]
    subtitle = str(data.get("subtitle") or "").strip()[:240]
    raw_slides = data.get("slides")

    if not title:
        raise AIResponseError(
            "The AI response is missing the presentation title."
        )

    if not isinstance(raw_slides, list) or not raw_slides:
        raise AIResponseError(
            "The AI response is missing slides."
        )

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
            "bullets": bullets[:6],
            "speaker_notes": notes,
            "image_query": image_query,
        })

    if len(slides) != expected_slides:
        raise AIResponseError(
            f"Only {len(slides)} valid slide(s) were produced."
        )

    # Keep the opening slide in title layout.
    slides[0]["layout"] = "title"

    # Always make the final slide a clean Thank You slide.
    slides[-1]["layout"] = "conclusion"
    slides[-1]["title"] = "Thank You"

    return {
        "title": title,
        "subtitle": subtitle,
        "slides": slides,
    }


def _raise_api_error(response):
    """Convert OpenRouter errors into useful application errors."""

    if response.status_code in (401, 403):
        raise AIConfigError(
            "OpenRouter rejected your API key. "
            "Check OPENROUTER_API_KEY."
        )

    if response.status_code == 429:
        raise AIResponseError(
            "OpenRouter is rate-limiting requests. "
            "Check your credits and try again."
        )

    try:
        error_data = response.json()
        detail = error_data.get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = (response.text or "")[:250]

    raise AIResponseError(
        f"OpenRouter error ({response.status_code}): "
        f"{detail or 'Unknown error'}"
    )


def _call_ai(
    topic,
    audience,
    tone,
    theme,
    slide_count,
    provider,
    content_length="medium",
    strict=False
):
    """Call the internally selected model through OpenRouter."""

    api_key, base_url, model, timeout = _get_config(provider)

    prompt = _build_prompt(
        topic,
        audience,
        tone,
        theme,
        slide_count,
        content_length,
    )

    if strict:
        prompt += (
            f"\n\nIMPORTANT: Return exactly {slide_count} slides. "
            'The final slide title must be exactly "Thank You". '
            "Count the slides before replying. Return valid JSON only. "
            "Follow the selected content length instructions."
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

    request_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert presentation designer. "
                    "Create clean, professional presentations. "
                    "Return one valid JSON object and nothing else."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.65,
        "response_format": {"type": "json_object"},
    }

    url = f"{base_url}/chat/completions"

    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=timeout,
        )

        if (
            response.status_code == 400
            and "response_format" in (response.text or "")
        ):
            request_body.pop("response_format", None)

            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=timeout,
            )

        if not response.ok:
            _raise_api_error(response)

        try:
            body = response.json()
        except ValueError:
            raise AIResponseError(
                "OpenRouter returned an invalid response."
            )

    except requests.Timeout:
        raise AIResponseError(
            "The AI service took too long to respond. Please try again."
        )

    except requests.ConnectionError:
        raise AIResponseError(
            "Could not reach OpenRouter. Check your connection."
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


def generate_presentation(payload):
    """Choose a model, generate a deck and optionally enrich its images."""

    inputs = _validate_input(payload)

    preferred_provider = _choose_provider(
        inputs["topic"],
        inputs["theme"]
    )

    other_provider = (
        "claude" if preferred_provider == "chatgpt" else "chatgpt"
    )

    providers = [preferred_provider, other_provider]
    last_error = None
    deck = None

    for provider in providers:
        for attempt in range(2):
            try:
                raw = _call_ai(
                    topic=inputs["topic"],
                    audience=inputs["audience"],
                    tone=inputs["tone"],
                    theme=inputs["theme"],
                    slide_count=inputs["slides"],
                    content_length=inputs["content_length"],
                    provider=provider,
                    strict=(attempt == 1),
                )

                deck = _validate_output(
                    raw,
                    inputs["slides"]
                )
                break

            except AIConfigError:
                raise

            except AIResponseError as exc:
                last_error = exc

        if deck is not None:
            break

    if deck is None:
        raise last_error or AIResponseError(
            "Both AI models were unable to generate a presentation."
        )

    deck["author_name"] = inputs["author_name"]
    deck["audience"] = inputs["audience"]
    deck["tone"] = inputs["tone"]
    deck["theme"] = inputs["theme"]
    deck["content_length"] = inputs["content_length"]

    # Do not expose the internal AI provider in the response.

    if os.getenv(
        "ENABLE_WIKIMEDIA_IMAGES", "true"
    ).lower() in ("true", "1", "yes", "on"):

        try:
            enrich_slides_with_images(deck["slides"])
        except Exception:
            pass

    return deck
