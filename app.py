"""SlideWala Phase 3 — premium AI presentation maker."""
import io
import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file

from services.ai_service import AIConfigError, AIResponseError, generate_presentation
from services.image_service import proxy_image
from services.pdf_service import build_pdf
from services.pptx_service import build_pptx

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-this")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB JSON limit


def _safe_filename(title: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9 _-]", "", title or "slidewala-presentation").strip()
    base = re.sub(r"\s+", "-", base)[:60].strip("-") or "slidewala-presentation"
    return base.lower()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    configured = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY"))
    return jsonify(
        status="ok",
        app="SlideWala",
        phase=3,
        ai_configured=configured,
    )


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(silent=True) or {}
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
        app.logger.exception("Generation failed")
        return jsonify(error="Generation failed. Please try again."), 500


@app.get("/api/image")
def api_image():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify(error="Missing image URL."), 400
    try:
        data, content_type = proxy_image(url)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error="Could not load image."), 502
    return send_file(io.BytesIO(data), mimetype=content_type, max_age=86400)


@app.post("/api/export/pptx")
def export_pptx():
    payload = request.get_json(silent=True) or {}
    try:
        buffer = build_pptx(payload)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("PPTX export failed")
        return jsonify(error="Could not build the PowerPoint file."), 500

    filename = _safe_filename(payload.get("title")) + ".pptx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name=filename,
    )


@app.post("/api/export/pdf")
def export_pdf():
    payload = request.get_json(silent=True) or {}
    try:
        buffer = build_pdf(payload)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("PDF export failed")
        return jsonify(error="Could not build the PDF file."), 500

    filename = _safe_filename(payload.get("title")) + ".pdf"
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True)
