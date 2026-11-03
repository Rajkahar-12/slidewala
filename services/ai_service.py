"""SlideWala AI service with automatic GPT/Claude routing through OpenRouter."""

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

DECK_TYPE_GUIDES = {
    "lecture": (
        "A classroom lecture. Flow: introduction, learning objectives, "
        "key concepts one by one, real examples, a comparison or "
        "timeline where useful, then a recap."
    ),
    "pitch": (
        "A business pitch. Flow: hook, problem, solution, how it works, "
        "market size (stats), traction or benefits (stats), a comparison "
        "with alternatives, roadmap (timeline), then a clear call to action."
    ),
    "report": (
        "A report or project presentation. Flow: background, objectives, "
        "method, findings (stats), analysis, a comparison, "
        "conclusions and recommendations."
    ),
    "story": (
        "A storytelling presentation. Flow: strong hook, setting, the "
        "challenge, turning points (timeline), a memorable quote, "
        "the resolution and the key lesson."
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

# Layouts that need extra data besides bullets.
DATA_LAYOUTS = {"stats", "two-column", "timeline", "quote"}

ALLOWED_LAYOUTS = {
    "title", "intro", "content", "image-left",
    "image-right", "full-image", "comparison",
    "conclusion", "references",
    "section", "stats", "two-column", "timeline", "quote",
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
    """Select an AI internally using topic and visual theme."""

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

    claude_score = sum(1 for word in claude_keywords if word in text)
    gpt_score = sum(1 for word in gpt_keywords if word in text)

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

    author_name = str(payload.get("author_name") or "").strip()

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
        raise ValueError(f"Slide count must be one of: {allowed}.")

    audience = str(payload.get("audience") or "general").strip().lower()

    if audience not in ALLOWED_AUDIENCES:
        raise ValueError("Please choose a valid audience.")

    tone = str(payload.get("tone") or "educational").strip().lower()

    if tone not in ALLOWED_TONES:
        raise ValueError("Please choose a valid presentation tone.")

    theme = str(payload.get("theme") or "aurora").strip().lower()

    if theme not in THEME_DESCRIPTIONS:
        raise ValueError("Please choose a valid design theme.")

    content_length = str(
        payload.get("content_length") or "medium"
    ).strip().lower()

    if content_length not in ALLOWED_CONTENT_LENGTHS:
        raise ValueError("Please choose a valid content length.")

    deck_type = str(payload.get("deck_type") or "lecture").strip().lower()

    if deck_type not in ALLOWED_DECK_TYPES:
        raise ValueError("Please choose a valid presentation type.")

    return {
        "topic": topic,
        "author_name": author_name,
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
    """Build the presentation-generation prompt."""

    theme_description = THEME_DESCRIPTIONS.get(
        theme, THEME_DESCRIPTIONS["aurora"]
    )

    content_guide = CONTENT_LENGTH_GUIDES.get(
        content_length, CONTENT_LENGTH_GUIDES["medium"]
    )

    type_guide = DECK_TYPE_GUIDES.get(deck_type, DECK_TYPE_GUIDES["lecture"])

    return f"""Create a professional PowerPoint presentation.

Topic: {topic}
Audience: {audience}
Tone: {tone}
Presentation type: {deck_type}

PRESENTATION TYPE GUIDE:
{type_guide}

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
- Keep every bullet under 20 words.
- Make every point informative and relevant.
- Use simple language appropriate for the audience.
- Do not add extra bullets just to fill space.
- Title and conclusion slides may naturally contain fewer points.
- References slides should contain only relevant references.

DESIGN REQUIREMENTS:

- Follow the selected visual theme consistently.
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
- Every slide needs 2 to 4 sentences of speaker notes.
- Speaker notes must explain the slide in more detail.
- Add a specific image_query for most slides.
- Use descriptive image search phrases, not generic words.
- For references, stats, timeline and quote slides, image_query may be empty.
- Do not repeat information across slides.
- Do not add filler content.
- Do not add SlideWala branding, logos, promotional text or watermarks.
- Do not invent or include a presenter name.

LAYOUT RULES (this makes the deck look varied and professional):

- Allowed layouts: title, intro, content, image-left, image-right,
  full-image, comparison, conclusion, references,
  section, stats, two-column, timeline, quote.
- Do not use the same layout more than twice in a row.
- Alternate image-left and image-right for image slides.
- Use at least 3 different layouts in the deck (more for 8+ slides).
- "stats": only for real, believable figures. Add
  "stats": [{{"value": "72%", "label": "short label"}}] with 2 to 4 items.
  Do not invent exact statistics you are unsure about; prefer
  well-known figures or clearly rounded numbers.
- "two-column": add
  "columns": [{{"heading": "A", "bullets": ["..."]}},
  {{"heading": "B", "bullets": ["..."]}}] with exactly 2 columns and
  2 to 3 bullets each. Use it for comparisons, pros and cons, before and after.
- "timeline": add "steps": [{{"label": "Step name", "text": "one short line"}}]
  with 3 to 5 items. Use it for processes, history or roadmaps.
- "quote": add "quote": "a short real or well-known quote" and
  "quote_author": "Name". Use at most one quote slide, and only if the
  quote is genuine. Otherwise use another layout.
- "section": a divider slide with a one-line subtitle in bullets.
  Use it only for decks of 10 or more slides.
- Slides using these layouts must still include bullets (1 to 3 short
  summary points) and speaker notes.

Return ONLY valid JSON in this exact structure.
Do not include Markdown or explanations outside the JSON.

{{
    "title": "Overall presentation title",
    "subtitle": "One-line subtitle",
    "slides": [
        {{
            "layout": "title",
            "title": "Slide title",
            "bullets": ["Point 1", "Point 2"],
            "speaker_notes": "Detailed speaker explanation.",
            "image_query": "specific image search phrase",
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


def _clean_text(value, limit):
    """Return a trimmed string limited to a maximum length."""

    return str(value or "").strip()[:limit]


def _clean_bullets(value, limit=6, max_len=300):
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
    """Clean the extra data used by stats, columns, timeline and quote."""

    stats = []

    for item in (raw.get("stats") or [])[:4] if isinstance(
        raw.get("stats"), list
    ) else []:
        if isinstance(item, dict):
            value = _clean_text(item.get("value"), 20)
            label = _clean_text(item.get("label"), 60)
            if value and label:
                stats.append({"value": value, "label": label})

    columns = []

    for item in (raw.get("columns") or [])[:2] if isinstance(
        raw.get("columns"), list
    ) else []:
        if isinstance(item, dict):
            heading = _clean_text(item.get("heading"), 60)
            bullets = _clean_bullets(item.get("bullets"), limit=4, max_len=140)
            if heading and bullets:
                columns.append({"heading": heading, "bullets": bullets})

    steps = []

    for item in (raw.get("steps") or [])[:5] if isinstance(
        raw.get("steps"), list
    ) else []:
        if isinstance(item, dict):
            label = _clean_text(item.get("label"), 40)
            text = _clean_text(item.get("text"), 110)
            if label and text:
                steps.append({"label": label, "text": text})

    return {
        "stats": stats,
        "columns": columns,
        "steps": steps,
        "quote": _clean_text(raw.get("quote"), 260),
        "quote_author": _clean_text(raw.get("quote_author"), 80),
    }


def _has_layout_data(layout, extras):
    """Check that a data layout really has the data it needs."""

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
        raise AIResponseError("The AI response was not a JSON object.")

    title = _clean_text(data.get("title"), 160)
    subtitle = _clean_text(data.get("subtitle"), 240)
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

        slide_title = _clean_text(raw.get("title") or f"Slide {index}", 160)
        bullets = _clean_bullets(raw.get("bullets"))

        layout = _clean_text(raw.get("layout") or "content", 30).lower()

        if layout not in ALLOWED_LAYOUTS:
            layout = "content"

        extras = _clean_extras(raw)

        # Fall back to a normal slide if the data layout is incomplete.
        if layout in DATA_LAYOUTS and not _has_layout_data(layout, extras):
            layout = "content"

        if len(bullets) < 2 and layout not in DATA_LAYOUTS | {"section"}:
            bullets.append("Key takeaway for this slide.")

        notes = _clean_text(raw.get("speaker_notes"), 2400)

        if not notes:
            notes = "No speaker notes were generated for this slide."

        slide = {
            "layout": layout,
            "title": slide_title or f"Slide {index}",
            "bullets": bullets,
            "speaker_notes": notes,
            "image_query": _clean_text(raw.get("image_query"), 120),
        }

        # Only keep the extra data that the layout actually uses.
        if layout == "stats":
            slide["stats"] = extras["stats"]
        elif layout == "two-column":
            slide["columns"] = extras["columns"]
        elif layout == "timeline":
            slide["steps"] = extras["steps"]
        elif layout == "quote":
            slide["quote"] = extras["quote"]
            slide["quote_author"] = extras["quote_author"]

        # These layouts do not show a picture.
        if layout in DATA_LAYOUTS | {"section", "references"}:
            slide["image_query"] = ""

        slides.append(slide)

    if len(slides) != expected_slides:
        raise AIResponseError(
            f"Only {len(slides)} valid slide(s) were produced."
        )

    # First and last slides are always plain title / thank-you slides.
    for position in (0, -1):
        for key in ("stats", "columns", "steps", "quote", "quote_author"):
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


def _call_ai(
    topic,
    audience,
    tone,
    theme,
    slide_count,
    provider,
    content_length="medium",
    deck_type="lecture",
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
        deck_type,
    )

    if strict:
        prompt += (
            f"\n\nIMPORTANT: Return exactly {slide_count} slides. "
            'The final slide title must be exactly "Thank You". '
            "Count the slides before replying. Return valid JSON only. "
            "Follow the selected content length instructions. "
            "Every stats, two-column, timeline or quote slide must "
            "include its required data fields."
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

        # Retry the same request only if the provider does not
        # support OpenRouter's JSON response format.
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
    """Generate a deck with automatic model fallback and image enrichment."""

    total_start = time.perf_counter()

    inputs = _validate_input(payload)

    preferred_provider = _choose_provider(
        inputs["topic"],
        inputs["theme"]
    )

    other_provider = (
        "claude" if preferred_provider == "chatgpt" else "chatgpt"
    )

    # Maximum of two generation attempts:
    # 1. Automatically selected model.
    # 2. Backup model with stricter JSON instructions.
    providers = [
        (preferred_provider, False),
        (other_provider, True),
    ]

    last_error = None
    deck = None

    for attempt_number, (provider, strict) in enumerate(
        providers, start=1
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

            deck = _validate_output(raw, inputs["slides"])

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

    deck["author_name"] = inputs["author_name"]
    deck["audience"] = inputs["audience"]
    deck["tone"] = inputs["tone"]
    deck["theme"] = inputs["theme"]
    deck["content_length"] = inputs["content_length"]
    deck["deck_type"] = inputs["deck_type"]

    # Image enrichment is measured separately so Render logs
    # can show whether image searches are slowing generation.
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
        logger.info("SlideWala image enrichment is disabled.")

    logger.info(
        "SlideWala total generation time: %.2f seconds.",
        time.perf_counter() - total_start,
    )

    return deck
