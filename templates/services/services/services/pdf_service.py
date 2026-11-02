
"""Real PDF generation with ReportLab, one presentation slide per page."""
import io
import os

import requests
from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PAGE_W = 13.333 * 72
PAGE_H = 7.5 * 72

THEMES = {
    "midnight": {
        "bg": (15, 17, 32), "title": (255, 255, 255), "text": (225, 228, 242),
        "accent": (139, 120, 255), "muted": (160, 166, 195), "card": (27, 30, 50),
    },
    "aurora": {
        "bg": (248, 246, 255), "title": (24, 20, 44), "text": (55, 50, 80),
        "accent": (108, 76, 241), "muted": (120, 115, 140), "card": (255, 255, 255),
    },
    "minimal": {
        "bg": (255, 255, 255), "title": (17, 17, 17), "text": (55, 55, 55),
        "accent": (17, 17, 17), "muted": (130, 130, 130), "card": (245, 245, 245),
    },
    "corporate": {
        "bg": (245, 248, 252), "title": (16, 40, 70), "text": (45, 65, 90),
        "accent": (0, 112, 192), "muted": (110, 125, 145), "card": (255, 255, 255),
    },
}

FONT_REG = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _register_fonts():
    global FONT_REG, FONT_BOLD
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/DejaVuSans.ttf", "/Library/Fonts/DejaVuSans-Bold.ttf"),
        ("C:\\Windows\\Fonts\\DejaVuSans.ttf", "C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("SlideWala-Regular", regular))
            pdfmetrics.registerFont(TTFont("SlideWala-Bold", bold))
            FONT_REG = "SlideWala-Regular"
            FONT_BOLD = "SlideWala-Bold"
            return


_register_fonts()


def _color(rgb):
    return Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)


def _safe_text(text):
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u2022": "*",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    try:
        return text.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return text


def _draw_background(c, color):
    c.setFillColor(_color(color))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _draw_text(c, text, x, y, max_width, font, size, color, leading=None):
    text = _safe_text(text)
    leading = leading or size * 1.25
    lines = simpleSplit(text, font, size, max_width)
    c.setFont(font, size)
    c.setFillColor(_color(color))
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def _draw_bullets(c, bullets, x, y, max_width, size, color):
    c.setFont(FONT_REG, size)
    c.setFillColor(_color(color))
    bullet_indent = size * 0.95
    line_height = size * 1.42
    bottom_margin = 50

    for bullet in bullets:
        bullet = _safe_text(bullet)
        lines = simpleSplit(bullet, FONT_REG, size, max_width - bullet_indent)
        if not lines:
            continue

        if y < bottom_margin + line_height * len(lines):
            c.setFont(FONT_BOLD, size)
            c.drawString(x, y, "...")
            break

        c.circle(x + 2.5, y + size * 0.32, 2.2, fill=1, stroke=0)
        c.setFont(FONT_REG, size)
        for line in lines:
            c.drawString(x + bullet_indent, y, line)
            y -= line_height
        y -= 3


def _download_image(url, timeout=15):
    if not url:
        return None
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "SlideWala/1.0 (https://example.com)"},
        )
        if response.ok and (response.headers.get("content-type") or "").startswith("image/"):
            if len(response.content) <= 10 * 1024 * 1024:
                return response.content
    except Exception:
        pass
    return None


def _draw_image_fit(c, image_bytes, x, y, width, height):
    if not image_bytes:
        return False
    try:
        reader = ImageReader(io.BytesIO(image_bytes))
        image = Image.open(io.BytesIO(image_bytes))
        image_w, image_h = image.size
        if image_w <= 0 or image_h <= 0:
            return False

        box_ratio = width / height
        image_ratio = image_w / image_h

        if image_ratio > box_ratio:
            final_w = width
            final_h = width / image_ratio
            final_x = x
            final_y = y + (height - final_h) / 2
        else:
            final_h = height
            final_w = height * image_ratio
            final_y = y
            final_x = x + (width - final_w) / 2

        c.drawImage(reader, final_x, final_y, final_w, final_h, preserveAspectRatio=True)
        return True
    except Exception:
        return False


def _title_page(c, data, theme):
    _draw_background(c, theme["bg"])
    c.setFillColor(_color(theme["accent"]))
    c.rect(65, PAGE_H - 115, 65, 5, fill=1, stroke=0)

    y = PAGE_H - 190
    c.setFont(FONT_BOLD, 42)
    c.setFillColor(_color(theme["title"]))
    title_lines = simpleSplit(
        _safe_text(data.get("title") or "Presentation"), FONT_BOLD, 42, PAGE_W - 130
    )
    for line in title_lines:
        c.drawString(65, y, line)
        y -= 52

    subtitle = data.get("subtitle")
    if subtitle:
        y -= 8
        _draw_text(c, subtitle, 65, y, PAGE_W - 160, FONT_REG, 18, theme["muted"])

    c.setFont(FONT_REG, 8)
    c.setFillColor(_color(theme["muted"]))
    c.drawString(65, 35, "SLIDEWALA  \u00b7  AI PRESENTATION")


def _references_page(c, data, theme):
    _draw_background(c, theme["bg"])
    c.setFont(FONT_BOLD, 30)
    c.setFillColor(_color(theme["title"]))
    c.drawString(65, PAGE_H - 85, _safe_text(data.get("title") or "References"))
    c.setFillColor(_color(theme["accent"]))
    c.rect(65, PAGE_H - 105, 58, 4, fill=1, stroke=0)
    _draw_bullets(c, data.get("bullets") or [], 65, PAGE_H - 150, PAGE_W - 130, 13, theme["text"])


def _content_page(c, data, theme, image_bytes, slide_no, total):
    _draw_background(c, theme["bg"])
    layout = data.get("layout") or "content"
    has_image = bool(image_bytes)

    text_x = 65
    text_width = PAGE_W - 130
    text_y = PAGE_H - 145

    if has_image and layout in ("image-left", "full-image"):
        text_x = PAGE_W * 0.51
        text_width = PAGE_W - text_x - 65
    elif has_image and layout in ("image-right", "content", "intro"):
        text_x = 65
        text_width = PAGE_W * 0.43

    c.setFont(FONT_BOLD, 26)
    c.setFillColor(_color(theme["title"]))
    title_lines = simpleSplit(
        _safe_text(data.get("title") or f"Slide {slide_no}"), FONT_BOLD, 26, text_width
    )
    y = text_y
    for line in title_lines[:2]:
        c.drawString(text_x, y, line)
        y -= 30

    c.setFillColor(_color(theme["accent"]))
    c.rect(text_x, y - 4, 52, 4, fill=1, stroke=0)
    y -= 36

    _draw_bullets(c, data.get("bullets") or [], text_x, y, text_width, 13, theme["text"])

    if has_image:
        if layout == "full-image":
            _draw_image_fit(c, image_bytes, 0, 0, PAGE_W, PAGE_H)
            card_x, card_y = 55, 38
            card_w, card_h = PAGE_W * 0.52, 165
            c.setFillColor(_color(theme["card"]))
            c.roundRect(card_x, card_y, card_w, card_h, 12, fill=1, stroke=0)
            _draw_text(c, data.get("title") or "", card_x + 20, card_y + card_h - 38,
                       card_w - 40, FONT_BOLD, 18, theme["title"])
            _draw_bullets(c, data.get("bullets") or [], card_x + 20, card_y + card_h - 70,
                          card_w - 40, 9, theme["text"])
        elif layout == "image-left":
            _draw_image_fit(c, image_bytes, 40, 90, PAGE_W * 0.43, PAGE_H - 150)
        else:
            _draw_image_fit(c, image_bytes, PAGE_W * 0.55, 90, PAGE_W * 0.39, PAGE_H - 150)

    c.setFont(FONT_REG, 8)
    c.setFillColor(_color(theme["muted"]))
    c.drawRightString(PAGE_W - 65, 30, f"{slide_no:02d} / {total:02d}")


def _notes_pages(c, slides, theme):
    c.showPage()
    _draw_background(c, theme["bg"])
    c.setFont(FONT_BOLD, 28)
    c.setFillColor(_color(theme["title"]))
    c.drawString(65, PAGE_H - 75, "Speaker Notes")
    y = PAGE_H - 125

    for index, slide in enumerate(slides, start=1):
        title = f"Slide {index}: {slide.get('title') or ''}"
        notes = slide.get("speaker_notes") or ""

        c.setFont(FONT_BOLD, 12)
        c.setFillColor(_color(theme["accent"]))
        c.drawString(65, y, _safe_text(title)[:100])
        y -= 18

        y = _draw_text(c, notes, 65, y, PAGE_W - 130, FONT_REG, 10, theme["text"], leading=14)
        y -= 14

        if y < 60 and index < len(slides):
            c.showPage()
            _draw_background(c, theme["bg"])
            y = PAGE_H - 75


def build_pdf(payload: dict):
    slides = payload.get("slides") or []
    if not isinstance(slides, list) or not slides:
        raise ValueError("No slides to export.")
    if len(slides) > 20:
        raise ValueError("Too many slides to export.")

    theme = THEMES.get(str(payload.get("theme") or "aurora").lower(), THEMES["aurora"])

    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(_safe_text(payload.get("title") or "SlideWala Presentation"))

    for index, slide_data in enumerate(slides):
        slide_no = index + 1
        layout = str(slide_data.get("layout") or "content").lower()
        image_bytes = _download_image(slide_data.get("image_source_url"))

        if slide_no == 1 or layout == "title":
            _title_page(c, slide_data, theme)
        elif layout == "references":
            _references_page(c, slide_data, theme)
        else:
            _content_page(c, slide_data, theme, image_bytes, slide_no, len(slides))

        c.showPage()

    _notes_pages(c, slides, theme)
    c.save()
    output.seek(0)
    return output
