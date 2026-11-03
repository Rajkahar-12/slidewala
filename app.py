"""SlideWala - optimized Flask application."""

import io
import os
import re
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")


app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "slidewala-local-dev-key"
)

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600


# Simple in-memory rate limit for AI generation (protects your API key).
# Change these two numbers if you want more or fewer presentations.
RATE_LIMIT_COUNT = int(os.getenv("RATE_LIMIT_COUNT", 10))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 3600))  # seconds

_request_log = defaultdict(deque)


def too_many_requests():
    """Return True if this visitor made too many generate requests."""

    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = (forwarded.split(",")[0].strip() or request.remote_addr or "unknown")

    now = time.time()
    hits = _request_log[ip]

    while hits and now - hits[0] > RATE_LIMIT_WINDOW:
        hits.popleft()

    if len(hits) >= RATE_LIMIT_COUNT:
        return True

    hits.append(now)
    return False


def safe_filename(title):
    """Create a clean filename from the presentation title."""

    title = str(title or "presentation")

    name = re.sub(r"[^a-zA-Z0-9 _-]", "", title)
    name = re.sub(r"\s+", "-", name.strip())
    name = name[:60].strip("-")

    return (name or "presentation").lower()


@app.route("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    """Lightweight health check for Render and uptime monitoring."""

    return jsonify({
        "status": "ok",
        "app": "SlideWala",
        "ai_configured": bool(
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("AI_API_KEY")
        ),
    })


@app.post("/api/generate")
def api_generate():
    from services.ai_service import (
        AIConfigError,
        AIResponseError,
        generate_presentation,
    )

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            error="Invalid request. Please try again."
        ), 400

    if too_many_requests():
        return jsonify(
            error="Too many presentations created. Please try again later."
        ), 429

    try:
        deck = generate_presentation(payload)
        return jsonify(deck)

    except AIConfigError as exc:
        return jsonify(error=str(exc)), 503

    except AIResponseError as exc:
        return jsonify(error=str(exc)), 502

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("Presentation generation failed")

        return jsonify(
            error="Presentation generation failed. Please try again."
        ), 500


@app.get("/api/image")
def api_image():
    from services.image_service import proxy_image

    url = (request.args.get("url") or "").strip()

    if not url:
        return jsonify(error="Missing image URL."), 400

    try:
        result = proxy_image(url)

        if not result:
            return jsonify(error="Image is unavailable."), 404

        image_data, content_type = result

        return send_file(
            io.BytesIO(image_data),
            mimetype=content_type,
            max_age=86400,
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("Image loading failed")

        return jsonify(
            error="Could not load this image."
        ), 502


@app.post("/api/export/pptx")
def export_pptx():
    from services.pptx_service import build_pptx

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(error="Invalid presentation data."), 400

    try:
        buffer = build_pptx(payload)

        return send_file(
            buffer,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            as_attachment=True,
            download_name=(
                safe_filename(payload.get("title")) + ".pptx"
            ),
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("PowerPoint export failed")

        return jsonify(
            error="Could not create the PowerPoint file."
        ), 500


@app.post("/api/export/pdf")
def export_pdf():
    from services.pdf_service import build_pdf

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(error="Invalid presentation data."), 400

    try:
        buffer = build_pdf(payload)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=(
                safe_filename(payload.get("title")) + ".pdf"
            ),
        )

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception:
        app.logger.exception("PDF export failed")

        return jsonify(
            error="Could not create the PDF file."
        ), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False,
    )
