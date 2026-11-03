"""Real PDF generation with ReportLab, one presentation slide per page."""

import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from services.image_service import fetch_image_bytes

PAGE_W = 13.333 * 72
PAGE_H = 7.5 * 72
MARGIN = 65
CONTENT_W = PAGE_W - 2 * MARGIN


def _theme(bg, title, text, accent, muted, card):
    return {
        "bg": bg, "title": title, "text": text,
        "accent": accent, "muted": muted, "card": card,
    }


THEMES = {
    "aurora": _theme((248, 246, 255), (24, 20, 44), (55, 50, 80), (108, 76, 241), (120, 115, 140), (255, 255, 255)),
    "midnight": _theme((15, 17, 32), (255, 255, 255), (225, 228, 242), (139, 120, 255), (160, 166, 195), (27, 30, 50)),
    "minimal": _theme((255, 255, 255), (17, 17, 17), (55, 55, 55), (17, 17, 17), (130, 130, 130), (245, 245, 245)),
    "corporate": _theme((245, 248, 252), (16, 40, 70), (45, 65, 90), (0, 112, 192), (110, 125, 145), (255, 255, 255)),
    "ocean": _theme((234, 246, 248), (7, 59, 76), (36, 85, 99), (0, 166, 166), (102, 139, 150), (255, 255, 255)),
    "sunset": _theme((255, 241, 233), (84, 37, 26), (112, 67, 52), (242, 107, 56), (167, 122, 105), (255, 250, 246)),
    "forest": _theme((237, 244, 236), (23, 59, 44), (54, 92, 71), (50, 134, 90), (120, 145, 125), (255, 255, 255)),
    "rose": _theme((255, 240, 244), (85, 34, 56), (120, 70, 90), (223, 91, 136), (167, 123, 140), (255, 255, 255)),
    "lavender": _theme((242, 239, 255), (48, 36, 92), (80, 68, 119), (148, 116, 232), (136, 126, 170), (255, 255, 255)),
    "graphite": _theme((32, 36, 43), (255, 255, 255), (224, 228, 233), (169, 180, 192), (160, 168, 178), (48, 55, 64)),
    "sand": _theme((245, 239, 227), (73, 59, 43), (103, 87, 66), (189, 139, 69), (155, 138, 114), (255, 250, 240)),
    "cyberpunk": _theme((21, 19, 38), (255, 255, 255), (231, 222, 254), (255, 79, 216), (170, 160, 206), (41, 33, 61)),
}

DATA_LAYOUTS = ("stats", "two-column", "timeline", "quote")

FONT_REG = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _register_fonts():
    global FONT_REG, FONT_BOLD

    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/Library/Fonts/DejaVuSans.ttf",
            "/Library/Fonts/DejaVuSans-Bold.ttf",
        ),
        (
            "C:\\Windows\\Fonts\\DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf",
        ),
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
    text = str(text or "")

    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"',
        "\u201d": '"', "\u2013": "-", "\u2014": "-",
        "\u2026": "...", "\u2022": "*",
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


def _draw_centered(c, text, cx, y, max_width, font, size, color, max_lines=3):
    """Centered, wrapped text. Returns the y position after the last line."""

    lines = simpleSplit(_safe_text(text), font, size, max_width)[:max_lines]
    leading = size * 1.3

    c.setFont(font, size)
    c.setFillColor(_color(color))

    for line in lines:
        c.drawCentredString(cx, y, line)
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
        lines = simpleSplit(
            bullet, FONT_REG, size, max_width - bullet_indent
        )

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


def _draw_page_number(c, theme, slide_no, total):
    c.setFont(FONT_REG, 8)
    c.setFillColor(_color(theme["muted"]))
    c.drawRightString(PAGE_W - MARGIN, 30, f"{slide_no:02d} / {total:02d}")


def _draw_header(c, data, theme, slide_no):
    """Standard slide title with a short accent line."""

    c.setFont(FONT_BOLD, 28)
    c.setFillColor(_color(theme["title"]))
    c.drawString(
        MARGIN, PAGE_H - 85,
        _safe_text(data.get("title") or f"Slide {slide_no}")[:70]
    )

    c.setFillColor(_color(theme["accent"]))
    c.rect(MARGIN, PAGE_H - 105, 58, 4, fill=1, stroke=0)


def _prefetch_images(slides):
    """Download slide images concurrently using the safe shared cache.

    Only Wikimedia URLs are fetched (checked inside image_service), so the
    server cannot be tricked into requesting other websites.
    """

    results = {}

    def download_one(index, url):
        try:
            return index, fetch_image_bytes(url)
        except Exception:
            return index, None

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []

        for index, slide_data in enumerate(slides):
            if not isinstance(slide_data, dict):
                continue

            url = slide_data.get("image_source_url")

            if url:
                futures.append(executor.submit(download_one, index, url))

        for future in as_completed(futures):
            try:
                index, image_bytes = future.result()
                results[index] = image_bytes
            except Exception:
                continue

    return results


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

        c.drawImage(
            reader, final_x, final_y, final_w, final_h,
            preserveAspectRatio=True
        )

        return True

    except Exception:
        return False


def _title_page(c, data, theme, author_name=""):
    """Build the opening page without product branding."""

    _draw_background(c, theme["bg"])

    c.setFillColor(_color(theme["accent"]))
    c.rect(MARGIN, PAGE_H - 115, 65, 5, fill=1, stroke=0)

    y = PAGE_H - 190

    c.setFont(FONT_BOLD, 42)
    c.setFillColor(_color(theme["title"]))

    title_lines = simpleSplit(
        _safe_text(data.get("title") or "Presentation"),
        FONT_BOLD,
        42,
        PAGE_W - 130,
    )

    for line in title_lines:
        c.drawString(MARGIN, y, line)
        y -= 52

    subtitle = data.get("subtitle")

    if subtitle:
        y -= 8
        y = _draw_text(
            c, subtitle, MARGIN, y, PAGE_W - 160,
            FONT_REG, 18, theme["muted"]
        )

    if author_name:
        _draw_text(
            c, f"Presented by: {author_name}",
            MARGIN, max(y - 55, 90), PAGE_W - 160,
            FONT_BOLD, 15, theme["text"],
        )


def _thank_you_page(c, theme, author_name="", slide_no=1, total=1):
    """Build a clean closing page with the presenter's name."""

    _draw_background(c, theme["bg"])

    c.setFillColor(_color(theme["accent"]))
    c.rect(PAGE_W / 2 - 45, PAGE_H / 2 + 75, 90, 5, fill=1, stroke=0)

    c.setFont(FONT_BOLD, 42)
    c.setFillColor(_color(theme["title"]))
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 15, "Thank You")

    if author_name:
        c.setFont(FONT_REG, 17)
        c.setFillColor(_color(theme["text"]))
        c.drawCentredString(
            PAGE_W / 2, PAGE_H / 2 - 35,
            _safe_text(f"Presented by: {author_name}"),
        )

    _draw_page_number(c, theme, slide_no, total)


def _references_page(c, data, theme):
    _draw_background(c, theme["bg"])

    c.setFont(FONT_BOLD, 30)
    c.setFillColor(_color(theme["title"]))
    c.drawString(
        MARGIN, PAGE_H - 85,
        _safe_text(data.get("title") or "References")
    )

    c.setFillColor(_color(theme["accent"]))
    c.rect(MARGIN, PAGE_H - 105, 58, 4, fill=1, stroke=0)

    _draw_bullets(
        c, data.get("bullets") or [],
        MARGIN, PAGE_H - 150, PAGE_W - 130, 13, theme["text"]
    )


# ---------------------------------------------------------------
# New slide types
# ---------------------------------------------------------------

def _stats_page(c, data, theme, slide_no, total):
    _draw_background(c, theme["bg"])
    _draw_header(c, data, theme, slide_no)

    stats = data["stats"][:4]
    count = len(stats)
    gap = 22
    card_w = (CONTENT_W - gap * (count - 1)) / count
    card_h = 190
    card_y = PAGE_H - 135 - card_h

    for i, item in enumerate(stats):
        x = MARGIN + i * (card_w + gap)
        cx = x + card_w / 2

        c.setFillColor(_color(theme["card"]))
        c.roundRect(x, card_y, card_w, card_h, 12, fill=1, stroke=0)

        value = _safe_text(item["value"])
        size = 40

        while size > 18 and pdfmetrics.stringWidth(
            value, FONT_BOLD, size
        ) > card_w - 24:
            size -= 2

        c.setFont(FONT_BOLD, size)
        c.setFillColor(_color(theme["accent"]))
        c.drawCentredString(cx, card_y + 110, value)

        _draw_centered(
            c, item["label"], cx, card_y + 72, card_w - 30,
            FONT_REG, 13, theme["muted"],
        )

    if data.get("bullets"):
        _draw_bullets(
            c, data["bullets"][:3],
            MARGIN, card_y - 40, CONTENT_W, 12, theme["text"]
        )

    _draw_page_number(c, theme, slide_no, total)


def _two_column_page(c, data, theme, slide_no, total):
    _draw_background(c, theme["bg"])
    _draw_header(c, data, theme, slide_no)

    gap = 22
    card_w = (CONTENT_W - gap) / 2
    card_h = 330
    card_y = PAGE_H - 135 - card_h

    for i, column in enumerate(data["columns"][:2]):
        x = MARGIN + i * (card_w + gap)

        c.setFillColor(_color(theme["card"]))
        c.roundRect(x, card_y, card_w, card_h, 12, fill=1, stroke=0)

        _draw_text(
            c, column["heading"], x + 22, card_y + card_h - 40,
            card_w - 44, FONT_BOLD, 19, theme["accent"],
        )

        _draw_bullets(
            c, column["bullets"],
            x + 22, card_y + card_h - 82, card_w - 44, 13, theme["text"]
        )

    _draw_page_number(c, theme, slide_no, total)


def _timeline_page(c, data, theme, slide_no, total):
    _draw_background(c, theme["bg"])
    _draw_header(c, data, theme, slide_no)

    steps = data["steps"][:5]
    col_w = CONTENT_W / len(steps)
    line_y = PAGE_H - 200

    c.setFillColor(_color(theme["accent"]))
    c.rect(MARGIN, line_y - 1.5, CONTENT_W, 3, fill=1, stroke=0)

    for i, step in enumerate(steps):
        x = MARGIN + i * col_w
        cx = x + 16

        c.setFillColor(_color(theme["accent"]))
        c.circle(cx, line_y, 16, fill=1, stroke=0)

        c.setFont(FONT_BOLD, 13)
        c.setFillColor(Color(1, 1, 1))
        c.drawCentredString(cx, line_y - 5, str(i + 1))

        y = _draw_text(
            c, step["label"], x, line_y - 50, col_w - 18,
            FONT_BOLD, 15, theme["title"],
        )

        _draw_text(
            c, step["text"], x, y - 6, col_w - 18,
            FONT_REG, 11.5, theme["text"], leading=15,
        )

    if data.get("bullets"):
        _draw_bullets(
            c, data["bullets"][:2],
            MARGIN, 105, CONTENT_W, 11, theme["muted"]
        )

    _draw_page_number(c, theme, slide_no, total)


def _quote_page(c, data, theme, slide_no, total):
    _draw_background(c, theme["bg"])

    c.setFont(FONT_BOLD, 14)
    c.setFillColor(_color(theme["accent"]))
    c.drawString(MARGIN, PAGE_H - 70, _safe_text(data.get("title") or "")[:80])

    c.setFillColor(_color(theme["accent"]))
    c.rect(MARGIN, 140, 5, 280, fill=1, stroke=0)

    c.setFont(FONT_BOLD, 80)
    c.drawString(MARGIN + 30, PAGE_H - 175, '"')

    y = _draw_text(
        c, data["quote"], MARGIN + 30, PAGE_H - 235, PAGE_W - 200,
        FONT_REG, 26, theme["title"], leading=36,
    )

    if data.get("quote_author"):
        _draw_text(
            c, "- " + data["quote_author"], MARGIN + 30, y - 20,
            PAGE_W - 200, FONT_REG, 16, theme["muted"],
        )

    _draw_page_number(c, theme, slide_no, total)


def _section_page(c, data, theme, slide_no, total):
    _draw_background(c, theme["bg"])

    c.setFillColor(_color(theme["accent"]))
    c.rect(0, 0, 25, PAGE_H, fill=1, stroke=0)

    y = _draw_text(
        c, data.get("title") or "", 85, PAGE_H / 2 + 40, PAGE_W - 170,
        FONT_BOLD, 40, theme["title"], leading=48,
    )

    c.setFillColor(_color(theme["accent"]))
    c.rect(85, y - 5, 80, 5, fill=1, stroke=0)

    bullets = data.get("bullets") or []

    if bullets:
        _draw_text(
            c, bullets[0], 85, y - 40, PAGE_W - 170,
            FONT_REG, 18, theme["muted"],
        )

    _draw_page_number(c, theme, slide_no, total)


def _has_data(layout, data):
    """Check the slide really contains what its layout needs."""

    if layout == "stats":
        return len(data.get("stats") or []) >= 2

    if layout == "two-column":
        return len(data.get("columns") or []) == 2

    if layout == "timeline":
        return len(data.get("steps") or []) >= 3

    if layout == "quote":
        return bool(data.get("quote"))

    return True


def _content_page(c, data, theme, image_bytes, slide_no, total):
    _draw_background(c, theme["bg"])

    layout = data.get("layout") or "content"
    has_image = bool(image_bytes)

    text_x = MARGIN
    text_width = PAGE_W - 130
    text_y = PAGE_H - 145

    if has_image and layout in ("image-left", "full-image"):
        text_x = PAGE_W * 0.51
        text_width = PAGE_W - text_x - MARGIN

    elif has_image and layout in ("image-right", "content", "intro"):
        text_x = MARGIN
        text_width = PAGE_W * 0.43

    c.setFont(FONT_BOLD, 26)
    c.setFillColor(_color(theme["title"]))

    title_lines = simpleSplit(
        _safe_text(data.get("title") or f"Slide {slide_no}"),
        FONT_BOLD,
        26,
        text_width,
    )

    y = text_y

    for line in title_lines[:2]:
        c.drawString(text_x, y, line)
        y -= 30

    c.setFillColor(_color(theme["accent"]))
    c.rect(text_x, y - 4, 52, 4, fill=1, stroke=0)
    y -= 36

    _draw_bullets(
        c, data.get("bullets") or [],
        text_x, y, text_width, 13, theme["text"]
    )

    if has_image:
        if layout == "full-image":
            _draw_image_fit(c, image_bytes, 0, 0, PAGE_W, PAGE_H)

            card_x, card_y = 55, 38
            card_w, card_h = PAGE_W * 0.52, 165

            c.setFillColor(_color(theme["card"]))
            c.roundRect(
                card_x, card_y, card_w, card_h, 12, fill=1, stroke=0
            )

            _draw_text(
                c, data.get("title") or "",
                card_x + 20, card_y + card_h - 38,
                card_w - 40, FONT_BOLD, 18, theme["title"]
            )

            _draw_bullets(
                c, data.get("bullets") or [],
                card_x + 20, card_y + card_h - 70,
                card_w - 40, 9, theme["text"]
            )

        elif layout == "image-left":
            _draw_image_fit(
                c, image_bytes, 40, 90, PAGE_W * 0.43, PAGE_H - 150
            )

        else:
            _draw_image_fit(
                c, image_bytes, PAGE_W * 0.55, 90,
                PAGE_W * 0.39, PAGE_H - 150
            )

    _draw_page_number(c, theme, slide_no, total)


def _notes_pages(c, slides, theme):
    c.showPage()
    _draw_background(c, theme["bg"])

    c.setFont(FONT_BOLD, 28)
    c.setFillColor(_color(theme["title"]))
    c.drawString(MARGIN, PAGE_H - 75, "Speaker Notes")

    y = PAGE_H - 125

    for index, slide in enumerate(slides, start=1):
        title = f"Slide {index}: {slide.get('title') or ''}"
        notes = slide.get("speaker_notes") or ""

        if index == len(slides):
            title = f"Slide {index}: Thank You"

        c.setFont(FONT_BOLD, 12)
        c.setFillColor(_color(theme["accent"]))
        c.drawString(MARGIN, y, _safe_text(title)[:100])
        y -= 18

        y = _draw_text(
            c, notes, MARGIN, y, PAGE_W - 130,
            FONT_REG, 10, theme["text"], leading=14
        )

        y -= 14

        if y < 60 and index < len(slides):
            c.showPage()
            _draw_background(c, theme["bg"])
            y = PAGE_H - 75


def build_pdf(payload: dict):
    """Build a clean PDF presentation with optional presenter name."""

    slides = payload.get("slides") or []

    if not isinstance(slides, list) or not slides:
        raise ValueError("No slides to export.")

    if len(slides) > 20:
        raise ValueError("Too many slides to export.")

    author_name = str(payload.get("author_name") or "").strip()[:80]

    theme_name = str(payload.get("theme") or "aurora").lower()
    theme = THEMES.get(theme_name, THEMES["aurora"])

    image_results = _prefetch_images(slides)

    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(PAGE_W, PAGE_H))

    c.setTitle(_safe_text(payload.get("title") or "Presentation"))

    if author_name:
        c.setAuthor(_safe_text(author_name))

    total_slides = len(slides)

    for index, slide_data in enumerate(slides):
        if not isinstance(slide_data, dict):
            continue

        slide_no = index + 1

        # Always make the final presentation page a Thank You page.
        if slide_no == total_slides:
            _thank_you_page(c, theme, author_name, slide_no, total_slides)

        elif slide_no == 1:
            _title_page(c, slide_data, theme, author_name)

        else:
            layout = str(slide_data.get("layout") or "content").lower()

            if layout in DATA_LAYOUTS and not _has_data(layout, slide_data):
                layout = "content"

            image_bytes = image_results.get(index)

            if layout == "references":
                _references_page(c, slide_data, theme)

            elif layout == "stats":
                _stats_page(c, slide_data, theme, slide_no, total_slides)

            elif layout == "two-column":
                _two_column_page(c, slide_data, theme, slide_no, total_slides)

            elif layout == "timeline":
                _timeline_page(c, slide_data, theme, slide_no, total_slides)

            elif layout == "quote":
                _quote_page(c, slide_data, theme, slide_no, total_slides)

            elif layout == "section":
                _section_page(c, slide_data, theme, slide_no, total_slides)

            else:
                _content_page(
                    c, slide_data, theme, image_bytes,
                    slide_no, total_slides,
                )

        c.showPage()

    _notes_pages(c, slides, theme)

    c.save()
    output.seek(0)

    return output
