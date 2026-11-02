"""Real .pptx generation with python-pptx."""
import io

import requests
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

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

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def _rgb(triplet):
    return RGBColor(*triplet)


def _set_background(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(color)


def _add_text(slide, text, left, top, width, height, size, color,
              bold=False, align=PP_ALIGN.LEFT, font="Calibri",
              anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.alignment = align
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.name = font
    paragraph.font.color.rgb = _rgb(color)
    return box


def _add_bullets(slide, bullets, left, top, width, height, color, size=16):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0

    for index, bullet in enumerate(bullets):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = "\u2022  " + bullet
        paragraph.font.size = Pt(size)
        paragraph.font.name = "Calibri"
        paragraph.font.color.rgb = _rgb(color)
        paragraph.space_after = Pt(7)
        paragraph.line_spacing = 1.12


def _add_accent_line(slide, left, top, width, height, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    return shape


def _add_slide_number(slide, number, total, color):
    _add_text(
        slide, f"{number:02d} / {total:02d}",
        SLIDE_W - Inches(1.15), SLIDE_H - Inches(0.45),
        Inches(0.8), Inches(0.28), 9, color, align=PP_ALIGN.RIGHT,
    )


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


def _add_picture_fit(slide, image_bytes, left, top, width, height):
    if not image_bytes:
        return None
    try:
        stream = io.BytesIO(image_bytes)
        stream.seek(0)
        image = Image.open(stream)
        image_w, image_h = image.size
        if image_w <= 0 or image_h <= 0:
            return None

        box_ratio = width / height
        image_ratio = image_w / image_h

        if image_ratio > box_ratio:
            final_w = width
            final_h = int(width / image_ratio)
            x = left
            y = top + int((height - final_h) / 2)
        else:
            final_h = height
            final_w = int(height * image_ratio)
            y = top
            x = left + int((width - final_w) / 2)

        stream.seek(0)
        return slide.shapes.add_picture(stream, x, y, width=final_w, height=final_h)
    except Exception:
        return None


def _title_slide(slide, data, theme):
    _set_background(slide, theme["bg"])
    _add_accent_line(slide, Inches(0.9), Inches(1.55), Inches(0.9), Inches(0.08), theme["accent"])

    _add_text(
        slide, data.get("title") or "Presentation",
        Inches(0.9), Inches(1.8), Inches(11.4), Inches(1.9),
        42, theme["title"], bold=True,
    )
    subtitle = data.get("subtitle") or ""
    if subtitle:
        _add_text(
            slide, subtitle,
            Inches(0.9), Inches(3.85), Inches(10.5), Inches(0.9),
            18, theme["muted"],
        )

    _add_text(
        slide, "SLIDEWALA  \u00b7  AI PRESENTATION",
        Inches(0.9), Inches(6.7), Inches(6.0), Inches(0.3),
        9, theme["muted"],
    )


def _references_slide(slide, data, theme):
    _set_background(slide, theme["bg"])
    _add_text(
        slide, data.get("title") or "References",
        Inches(0.9), Inches(0.7), Inches(11.4), Inches(0.8),
        30, theme["title"], bold=True,
    )
    _add_accent_line(slide, Inches(0.9), Inches(1.45), Inches(0.8), Inches(0.06), theme["accent"])
    _add_bullets(
        slide, data.get("bullets") or [],
        Inches(0.9), Inches(1.9), Inches(11.3), Inches(4.8),
        theme["text"], 15,
    )


def _content_slide(slide, data, theme, image_bytes, slide_no, total):
    _set_background(slide, theme["bg"])
    layout = data.get("layout") or "content"
    has_image = bool(image_bytes)

    title_left = Inches(0.9)
    title_top = Inches(0.65)
    title_width = Inches(11.4)

    if has_image and layout in ("image-left", "full-image"):
        title_left = Inches(6.6)
        title_width = Inches(5.8)
    elif has_image and layout in ("image-right", "content", "intro"):
        title_left = Inches(0.9)
        title_width = Inches(6.2)

    _add_text(
        slide, data.get("title") or f"Slide {slide_no}",
        title_left, title_top, title_width, Inches(0.9),
        28, theme["title"], bold=True,
    )
    _add_accent_line(
        slide, title_left, Inches(1.55), Inches(0.8), Inches(0.06), theme["accent"],
    )

    if has_image and layout in ("image-left", "full-image"):
        if layout == "full-image":
            _add_picture_fit(slide, image_bytes, 0, 0, SLIDE_W, SLIDE_H)
            card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(0.7), Inches(4.35), Inches(6.8), Inches(2.45),
            )
            card.fill.solid()
            card.fill.fore_color.rgb = _rgb(theme["card"])
            card.line.fill.background()
            _add_text(
                slide, data.get("title") or "",
                Inches(1.0), Inches(4.6), Inches(6.2), Inches(0.6),
                22, theme["title"], bold=True,
            )
            _add_bullets(
                slide, data.get("bullets") or [],
                Inches(1.0), Inches(5.25), Inches(6.1), Inches(1.35),
                theme["text"], 12,
            )
        else:
            _add_picture_fit(
                slide, image_bytes,
                Inches(0.6), Inches(1.75), Inches(5.4), Inches(4.9),
            )
            _add_bullets(
                slide, data.get("bullets") or [],
                Inches(6.6), Inches(1.9), Inches(5.9), Inches(4.7),
                theme["text"], 16,
            )
    elif has_image:
        _add_picture_fit(
            slide, image_bytes,
            Inches(7.15), Inches(1.75), Inches(5.4), Inches(4.9),
        )
        _add_bullets(
            slide, data.get("bullets") or [],
            Inches(0.9), Inches(1.9), Inches(5.9), Inches(4.7),
            theme["text"], 16,
        )
    else:
        _add_bullets(
            slide, data.get("bullets") or [],
            Inches(0.9), Inches(1.9), Inches(11.3), Inches(4.8),
            theme["text"], 18,
        )

    _add_slide_number(slide, slide_no, total, theme["muted"])


def build_pptx(payload: dict):
    slides = payload.get("slides") or []
    if not isinstance(slides, list) or not slides:
        raise ValueError("No slides to export.")
    if len(slides) > 20:
        raise ValueError("Too many slides to export.")

    theme = THEMES.get(str(payload.get("theme") or "aurora").lower(), THEMES["aurora"])

    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H
    blank_layout = presentation.slide_layouts[6]

    for index, slide_data in enumerate(slides):
        slide = presentation.slides.add_slide(blank_layout)
        slide_no = index + 1
        layout = str(slide_data.get("layout") or "content").lower()

        image_bytes = _download_image(slide_data.get("image_source_url"))

        if slide_no == 1 or layout == "title":
            _title_slide(slide, slide_data, theme)
        elif layout == "references":
            _references_slide(slide, slide_data, theme)
        else:
            _content_slide(slide, slide_data, theme, image_bytes, slide_no, len(slides))

        notes = str(slide_data.get("speaker_notes") or "").strip()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    output = io.BytesIO()
    presentation.save(output)
    output.seek(0)
    return output
