
"""SlideWala AI service with optimized GPT/Claude routing through OpenRouter."""

import json
import logging
import os
import re
import time

import requests

from services.image_service import enrich_slides_with_images


logger = logging.getLogger(__name__)

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

ALLOWED_DECK_TYPES = {
    "lecture", "pitch", "report", "story"
}

CONTENT_LENGTH_GUIDES = {
    "short": (
        "Write 2 to 3 concise but meaningful bullet points per slide. "
        "Use approximately 10 to 18 words per point. "
        "Keep the main information, not unnecessary explanations."
    ),
    "medium": (
        "Write 3 to 4 informative bullet points per slide. "
        "Use approximately 18 to 25 words per point. "
        "Explain the important ideas clearly and include useful examples "
        "where appropriate."
    ),
    "detailed": (
        "Write 4 to 5 informative bullet points per slide. "
        "Use approximately 22 to 35 words per point when the topic "
        "requires it. Explain concepts, include important details, "
        "practical examples, applications or evidence. "
        "Make the presentation genuinely informative, not repetitive."
    ),
}

DECK_TYPE_GUIDES = {
    "lecture": (
        "Create a structured educational lecture. Start with an engaging "
        "introduction and learning objectives. Explain the main concepts "
        "in a logical order. Include definitions, examples, applications, "
        "important facts and a useful recap."
    ),
    "pitch": (
        "Create a convincing business pitch. Explain the problem, target "
        "audience, proposed solution, how it works, value proposition, "
        "competitive advantages, business model where relevant, risks, "
        "roadmap and a clear call to action."
    ),
    "report": (
        "Create a professional report presentation. Cover background, "
        "objectives, methodology, important findings, analysis, evidence, "
        "challenges, conclusions and practical recommendations."
    ),
    "story": (
        "Create an engaging storytelling presentation. Establish a strong "
        "hook, setting and central challenge. Develop the story through "
        "meaningful events, turning points, consequences and resolution. "
        "Finish with a memorable lesson."
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

DATA_LAYOUTS = {"stats", "two-column", "timeline", "quote"}

ALLOWED_LAYOUTS = {
    "title", "intro", "content", "image-left",
    "image-right", "full-image", "comparison",
    "conclusion", "references", "section",
    "stats", "two-column", "timeline", "quote",
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
        timeout = max(20, int(os.getenv("AI_TIMEOUT") or "90"))
    except ValueError:
        timeout = 90

    return api_key, base_url, model, timeout


def _choose_provider(topic, deck_type="lecture", audience="general",
                     tone="educational"):
    """Choose a suitable model using the topic and presentation purpose."""

    text = f"{topic} {deck_type} {audience} {tone}".lower()

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

    claude_score = sum(1 for word in claude_keywords if word in text)
    gpt_score = sum(1 for word in gpt_keywords if word in text)

    if deck_type == "story":
        claude_score += 2

    if deck_type == "pitch":
        claude_score += 1

    if deck_type == "report":
        gpt_score += 1

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

    try:
        slide_count = int(payload.get("slides"))
    except (TypeError, ValueError):
        raise ValueError("Please choose a valid slide count.")

    if slide_count not in ALLOWED_SLIDE_COUNTS:
        allowed = ", ".join(
            str(number) for number in sorted(ALLOWED_SLIDE_COUNTS)
        )
        raise ValueError(f"Slide count must be one of: {allowed}.")

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

    deck_type = str(
        payload.get("deck_type") or "lecture"
    ).strip().lower()

    if deck_type not in ALLOWED_DECK_TYPES:
        raise ValueError("Please choose a valid presentation type.")

    return {
        "topic": topic,
        "slides": slide_count,
        "audience": audience,
        "tone": tone,
        "theme": theme,
        "content_length": content_length,
        "deck_type": deck_type,
    }


def _build_prompt(
    topic,
    audience,
    tone,
    theme,
    slide_count,
    content_length="medium",
    deck_type="lecture",
):
    """Build a detailed but efficient presentation prompt."""

    theme_description = THEME_DESCRIPTIONS.get(
        theme, THEME_DESCRIPTIONS["aurora"]
    )

    content_guide = CONTENT_LENGTH_GUIDES.get(
        content_length, CONTENT_LENGTH_GUIDES["medium"]
    )

    type_guide = DECK_TYPE_GUIDES.get(
        deck_type, DECK_TYPE_GUIDES["lecture"]
    )

    return f"""Create a high-quality, informative PowerPoint presentation.

TOPIC: {topic}
AUDIENCE: {audience}
TONE: {tone}
PRESENTATION TYPE: {deck_type}

PRESENTATION STRUCTURE:
{type_guide}

VISUAL DESIGN:
Theme: {theme}
Style: {theme_description}

SLIDE COUNT:
Exactly {slide_count} slides.

CONTENT LENGTH:
{content_length}

{content_guide}

CONTENT QUALITY RULES:

- Prioritize the most important and useful information about the topic.
- Explain what concepts mean, why they matter and how they work.
- Include relevant examples, applications and practical insights.
- Use accurate facts and meaningful comparisons.
- Explain technical terms in language appropriate for the audience.
- Avoid generic statements, repeated ideas and unnecessary filler.
- Do not make every slide sound like an introduction.
- Organize information in a logical learning or storytelling sequence.
- Give each slide a clear purpose.
- Do not sacrifice important information just to make slides shorter.
- Do not turn slides into large paragraphs.

FACTUAL ACCURACY:

- Never invent statistics, percentages, research findings or quotations.
- Use figures only when they are reliable and confidently known.
- If an exact figure is uncertain, explain the finding qualitatively.
- Never invent a source, research paper, author or reference URL.
- Use genuine, relevant references only when confidently known.
- Do not present estimates as verified facts.

SLIDE REQUIREMENTS:

- Slide 1 must be a strong title slide.
- Introduce the topic before explaining its main concepts.
- Cover the most important aspects of the topic.
- The final slide title must be exactly "Thank You".
- The final slide must use the conclusion layout.
- Avoid repeating the same information on multiple slides.
- Include 2 to 4 useful sentences in speaker notes for each slide.
- Speaker notes should explain and expand on the slide content.
- Add specific image_query descriptions to most suitable content slides.
- Do not add SlideWala branding, logos, advertisements or watermarks.
- Do not add a presenter name.

LAYOUT VARIETY:

Allowed layouts:
title, intro, content, image-left, image-right, full-image,
comparison, conclusion, references, section, stats,
two-column, timeline, quote.

- Use at least 3 different layouts where appropriate.
- Do not repeat the same layout more than twice consecutively.
- Use image-left and image-right to create visual variety.
- Use full-image only when a relevant image can carry the slide.
- Use stats only when reliable numerical data is available.
- Stats require 2 to 4 items:
  "stats": [{{"value": "72%", "label": "Short label"}}]
- Two-column requires exactly 2 columns with 2 to 3 bullets each:
  "columns": [
    {{"heading": "First", "bullets": ["Point 1", "Point 2"]}},
    {{"heading": "Second", "bullets": ["Point 1", "Point 2"]}}
  ]
- Timeline requires 3 to 5 steps:
  "steps": [
    {{"label": "Step name", "text": "Short explanation"}}
  ]
- Quote requires a genuine quotation:
  "quote": "Actual quotation",
  "quote_author": "Actual author"
- Use at most one quote slide.
- If reliable data for a special layout is unavailable, use a normal content layout.
- Section slides should only be used for presentations with 10 or more slides.
- Special layout slides must also contain useful summary bullets.

JSON OUTPUT:

Return ONLY one valid JSON object.
Do not include Markdown fences or explanations.

Use exactly this structure:

{{
  "title": "Presentation title",
  "subtitle": "One-line subtitle",
  "slides": [
    {{
      "layout": "title",
      "title": "Slide title",
      "bullets": ["Point 1", "Point 2"],
      "speaker_notes": "Detailed explanation of the slide.",
      "image_query": "Specific image search phrase",
      "stats": [],
      "columns": [],
      "steps": [],
      "quote": "",
      "quote_author": ""
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
        re.DOTALL | re.IGNORECASE,
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


def _clean_text(value, limit):
    """Return a trimmed string limited to a maximum length."""

    return str(value or "").strip()[:limit]


def _clean_bullets(value, limit=6, max_len=420):
    """Return a clean list of bullet strings."""

    if not isinstance(value, list):
        value = [value] if value else []

    result = []

    for item in value:
        text = _clean_text(item, max_len)

        if text:
            result.append(text)

    return result[:limit]


def _clean_extras(raw):
    """Clean additional data used by special layouts."""

    stats = []

    raw_stats = raw.get("stats")

    if isinstance(raw_stats, list):
        for item in raw_stats[:4]:
            if isinstance(item, dict):
                value = _clean_text(item.get("value"), 20)
                label = _clean_text(item.get("label"), 60)

                if value and label:
                    stats.append({
                        "value": value,
                        "label": label,
                    })

    columns = []

    raw_columns = raw.get("columns")

    if isinstance(raw_columns, list):
        for item in raw_columns[:2]:
            if isinstance(item, dict):
                heading = _clean_text(item.get("heading"), 60)

                bullets = _clean_bullets(
                    item.get("bullets"),
                    limit=4,
                    max_len=180,
                )

                if heading and bullets:
                    columns.append({
                        "heading": heading,
                        "bullets": bullets,
                    })

    steps = []

    raw_steps = raw.get("steps")

    if isinstance(raw_steps, list):
        for item in raw_steps[:5]:
            if isinstance(item, dict):
                label = _clean_text(item.get("label"), 40)
                text = _clean_text(item.get("text"), 150)

                if label and text:
                    steps.append({
                        "label": label,
                        "text": text,
                    })

    return {
        "stats": stats,
        "columns": columns,
        "steps": steps,
        "quote": _clean_text(raw.get("quote"), 260),
        "quote_author": _clean_text(raw.get("quote_author"), 80),
    }


def _has_layout_data(layout, extras):
    """Check whether a special layout has its required information."""

    if layout == "stats":
        return len(extras["stats"]) >= 2

    if layout == "two-column":
        return len(extras["columns"]) == 2

    if layout == "timeline":
        return len(extras["steps"]) >= 3

    if layout == "quote":
        return bool(extras["quote"])

    return True


def _validate_output(data, expected_slides):
    """Validate and clean generated presentation content."""

    if not isinstance(data, dict):
        raise AIResponseError(
            "The AI response was not a JSON object."
        )

    title = _clean_text(data.get("title"), 160)
    subtitle = _clean_text(data.get("subtitle"), 240)

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

        slide_title = _clean_text(
            raw.get("title") or f"Slide {index}",
            160,
        )

        bullets = _clean_bullets(raw.get("bullets"))

        layout = _clean_text(
            raw.get("layout") or "content",
            30,
        ).lower()

        if layout not in ALLOWED_LAYOUTS:
            layout = "content"

        extras = _clean_extras(raw)

        if layout in DATA_LAYOUTS and not _has_layout_data(
            layout, extras
        ):
            layout = "content"

        notes = _clean_text(raw.get("speaker_notes"), 2400)

        if not notes:
            notes = "No speaker notes were generated for this slide."

        slide = {
            "layout": layout,
            "title": slide_title or f"Slide {index}",
            "bullets": bullets,
            "speaker_notes": notes,
            "image_query": _clean_text(
                raw.get("image_query"),
                160,
            ),
        }

        if layout == "stats":
            slide["stats"] = extras["stats"]

        elif layout == "two-column":
            slide["columns"] = extras["columns"]

        elif layout == "timeline":
            slide["steps"] = extras["steps"]

        elif layout == "quote":
            slide["quote"] = extras["quote"]
            slide["quote_author"] = extras["quote_author"]

        if layout in DATA_LAYOUTS | {"section", "references"}:
            slide["image_query"] = ""

        slides.append(slide)

    if len(slides) != expected_slides:
        raise AIResponseError(
            f"Only {len(slides)} valid slide(s) were produced."
        )

    for position in (0, -1):
        for key in (
            "stats", "columns", "steps",
            "quote", "quote_author",
        ):
            slides[position].pop(key, None)

    slides[0]["layout"] = "title"
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


def _get_max_tokens(slide_count, content_length):
    """Set enough output tokens without excessively large responses."""

    tokens_per_slide = {
        "short": 280,
        "medium": 420,
        "detailed": 620,
    }

    return 800 + (
        slide_count * tokens_per_slide.get(content_length, 420)
    )


def _call_ai(
    topic,
    audience,
    tone,
    theme,
    slide_count,
    provider,
    content_length="medium",
    deck_type="lecture",
    strict=False,
):
    """Call the selected model through OpenRouter."""

    api_key, base_url, model, timeout = _get_config(provider)

    prompt = _build_prompt(
        topic,
        audience,
        tone,
        theme,
        slide_count,
        content_length,
        deck_type,
    )

    if strict:
        prompt += (
            f"\n\nFINAL CHECK: Return exactly {slide_count} slides. "
            'The final title must be exactly "Thank You". '
            "Return valid JSON only. Ensure every slide has a title, "
            "useful bullets and speaker notes. Do not invent facts."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv(
            "OPENROUTER_SITE_URL",
            "https://slidewala.onrender.com",
        ),
        "X-OpenRouter-Title": "SlideWala",
    }

    request_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert presentation researcher and "
                    "PowerPoint designer. Create informative, accurate, "
                    "well-structured presentations. Return one valid "
                    "JSON object and nothing else."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.55,
        "max_tokens": _get_max_tokens(
            slide_count,
            content_length,
        ),
        "response_format": {
            "type": "json_object",
        },
    }

    url = f"{base_url}/chat/completions"

    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=(10, timeout),
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
                timeout=(10, timeout),
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

    if isinstance(content, list):
        content = "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        )

    return _extract_json(content)


def generate_presentation(payload):
    """Generate a deck with automatic model fallback and image enrichment."""

    total_start = time.perf_counter()

    inputs = _validate_input(payload)

    preferred_provider = _choose_provider(
        inputs["topic"],
        inputs["deck_type"],
        inputs["audience"],
        inputs["tone"],
    )

    other_provider = (
        "claude"
        if preferred_provider == "chatgpt"
        else "chatgpt"
    )

    providers = [
        (preferred_provider, False),
        (other_provider, True),
    ]

    last_error = None
    deck = None

    for attempt_number, (provider, strict) in enumerate(
        providers,
        start=1,
    ):
        attempt_start = time.perf_counter()

        try:
            raw = _call_ai(
                topic=inputs["topic"],
                audience=inputs["audience"],
                tone=inputs["tone"],
                theme=inputs["theme"],
                slide_count=inputs["slides"],
                content_length=inputs["content_length"],
                deck_type=inputs["deck_type"],
                provider=provider,
                strict=strict,
            )

            deck = _validate_output(
                raw,
                inputs["slides"],
            )

            logger.info(
                "SlideWala AI attempt %s (%s) completed in %.2f seconds.",
                attempt_number,
                provider,
                time.perf_counter() - attempt_start,
            )

            break

        except AIConfigError:
            raise

        except AIResponseError as exc:
            last_error = exc

            logger.warning(
                "SlideWala AI attempt %s (%s) failed after %.2f seconds: %s",
                attempt_number,
                provider,
                time.perf_counter() - attempt_start,
                str(exc),
            )

    if deck is None:
        logger.error(
            "SlideWala generation failed after %.2f seconds.",
            time.perf_counter() - total_start,
        )

        raise last_error or AIResponseError(
            "Both AI models were unable to generate a presentation."
        )

    deck["audience"] = inputs["audience"]
    deck["tone"] = inputs["tone"]
    deck["theme"] = inputs["theme"]
    deck["content_length"] = inputs["content_length"]
    deck["deck_type"] = inputs["deck_type"]

    if os.getenv(
        "ENABLE_WIKIMEDIA_IMAGES", "true"
    ).lower() in ("true", "1", "yes", "on"):

        image_start = time.perf_counter()

        try:
            enrich_slides_with_images(deck["slides"])

            logger.info(
                "SlideWala image enrichment completed in %.2f seconds.",
                time.perf_counter() - image_start,
            )

        except Exception:
            logger.exception(
                "SlideWala image enrichment failed; continuing without images."
            )

    else:
        logger.info(
            "SlideWala image enrichment is disabled."
        )

    logger.info(
        "SlideWala total generation time: %.2f seconds.",
        time.perf_counter() - total_start,
    )

    return deck
