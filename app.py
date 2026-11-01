"""SlideWala — Phase 2 (AI PowerPoint Maker).

Flask backend with an OpenAI-compatible Chat Completions integration.
The API key is read only on the server; it is never sent to the browser.
"""
import json
import os
import re

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-this")

# --- AI configuration (server-side only) ---
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
try:
    AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))
except ValueError:
    AI_TIMEOUT = 60

ALLOWED_SLIDE_COUNTS = {5, 8, 10, 12}
MAX_TOPIC_LEN = 160

SYSTEM_PROMPT = (
    "You are SlideWala, an expert presentation designer for students and "
    "professionals. You always reply with a single, valid JSON object and "
    "never add commentary outside the JSON."
)


# ---------- Helpers ----------

def build_user_prompt(topic: str, audience: str, slide_count: int) -> str:
    return f"""Create a slide-by-slide presentation for a {audience} audience.

Topic: {topic}

Hard requirements:
- Return exactly {slide_count} slides.
- Slide 1 must be a clear introduction.
- The last slide must be a strong conclusion / call to action.
- Middle slides must flow logically (main content).
- Every slide must have:
  - "title": short, punchy slide title
  - "bullets": 3 to 5 bullet points, each one short sentence
  - "speaker_notes": 2 to 4 sentences a speaker can read aloud
- Language must fit a {audience} audience (do not mix tones).

Return ONLY valid JSON in this exact shape (no markdown, no extra text):

{{
  "title": "Overall presentation title",
  "subtitle": "One-line subtitle",
  "slides": [
    {{
      "title": "Slide title",
      "bullets": ["point 1", "point 2", "point 3"],
      "speaker_notes": "What the speaker should say."
    }}
  ]
}}
"""


def extract_json_from_text(text: str) -> dict:
    """Handle responses that are wrapped in ```json ... ``` fences."""
    text = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("The AI returned content that is not valid JSON.")


def validate_presentation(data: dict, expected_slides: int) -> dict:
    if not isinstance(data, dict):
        raise ValueError("The AI response was not a JSON object.")

    title = str(data.get("title") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    slides_raw = data.get("slides")

    if not title:
        raise ValueError("The AI response is missing the presentation title.")
    if not isinstance(slides_raw, list) or not slides_raw:
        raise ValueError("The AI response is missing slides.")

    cleaned = []
    for i, slide in enumerate(slides_raw, start=1):
        if not isinstance(slide, dict):
            continue
        s_title = str(slide.get("title") or f"Slide {i}").strip()
        raw_bullets = slide.get("bullets") or []
        bullets = [str(b).strip() for b in raw_bullets if str(b).strip()]
        if not bullets:
            bullets = ["(No bullet points were generated for this slide.)"]
        notes = str(slide.get("speaker_notes") or "").strip()
        cleaned.append(
            {"title": s_title, "bullets": bullets, "speaker_notes": notes}
        )

    if len(cleaned) != expected_slides:
        raise ValueError(
            f"The AI returned {len(cleaned)} slide(s) but you asked for "
            f"{expected_slides}. Please try again."
        )

    return {
        "title": title,
        "subtitle": subtitle,
        "slides": cleaned,
        "count": len(cleaned),
    }


def call_ai(topic: str, audience: str, slide_count: int) -> dict:
    """Call the OpenAI-compatible Chat Completions endpoint."""
    url = f"{AI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(topic, audience, slide_count)},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)

    # Some OpenAI-compatible providers reject response_format; retry without it.
    if resp.status_code == 400 and "response_format" in (resp.text or ""):
        payload.pop("response_format", None)
        resp = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)

    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise ValueError(f"AI service error ({resp.status_code}): {detail}")

    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise ValueError("The AI service returned an unexpected response shape.")

    parsed = extract_json_from_text(content)
    return validate_presentation(parsed, slide_count)


# ---------- Routes ----------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify(status="ok", app="SlideWala", phase=2, ai_configured=bool(AI_API_KEY))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    # 1) Feature not configured?
    if not AI_API_KEY:
        return (
            jsonify(
                error=(
                    "AI is not configured yet. Add AI_API_KEY to your .env file "
                    "locally, or to the environment variables on Render, then "
                    "restart the server."
                )
            ),
            503,
        )

    # 2) Validate input
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    audience = (data.get("audience") or "").strip().lower()
    slides_raw = data.get("slides")

    if not topic:
        return jsonify(error="Please enter a presentation topic."), 400
    if len(topic) > MAX_TOPIC_LEN:
        return jsonify(error=f"Topic must be at most {MAX_TOPIC_LEN} characters."), 400
    if audience not in ("student", "professional"):
        return jsonify(error="Audience must be 'student' or 'professional'."), 400
    try:
        slide_count = int(slides_raw)
    except (TypeError, ValueError):
        return jsonify(error="Slide count must be a number."), 400
    if slide_count not in ALLOWED_SLIDE_COUNTS:
        allowed = ", ".join(str(n) for n in sorted(ALLOWED_SLIDE_COUNTS))
        return jsonify(error=f"Slide count must be one of: {allowed}."), 400

    # 3) Call the AI with friendly error handling
    try:
        presentation = call_ai(topic, audience, slide_count)
    except requests.Timeout:
        return (
            jsonify(
                error="The AI service took too long to respond. Please try again."
            ),
            504,
        )
    except requests.ConnectionError:
        return (
            jsonify(
                error="Could not reach the AI service. Check your AI_BASE_URL and internet connection."
            ),
            502,
        )
    except requests.RequestException as exc:
        return jsonify(error=f"Network error while contacting the AI: {exc}"), 502
    except ValueError as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(presentation)


if __name__ == "__main__":
    app.run(debug=True)
