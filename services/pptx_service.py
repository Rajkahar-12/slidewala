
"""PowerPoint export service for SlideWala."""

import io
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from services.image_service import fetch_image_bytes


THEMES = {
    "aurora": {
        "bg": (248, 246, 255),
        "title": (24, 20, 44),
        "text": (55, 50, 80),
        "accent": (108, 76, 241),
        "muted": (120, 115, 140),
        "card": (255, 255, 255),
    },
    "midnight": {
        "bg": (15, 17, 32),
        "title": (255, 255, 255),
        "text": (225, 228, 242),
        "accent": (139, 120, 255),
        "muted": (160, 166, 195),
        "card": (27, 30, 50),
    },
    "minimal": {
        "bg": (255, 255, 255),
        "title": (17, 17, 17),
        "text": (55, 55, 55),
        "accent": (17, 17, 17),
        "muted": (130, 130, 130),
        "card": (245, 245, 245),
    },
    "corporate": {
        "bg": (245, 248, 252),
        "title": (16, 40, 70),
        "text": (45, 65, 90),
        "accent": (0, 112, 192),
        "muted": (110, 125, 145),
        "card": (255, 255, 255),
    },
    "ocean": {
        "bg": (235, 249, 250),
        "title": (9, 55, 68),
        "text": (35, 82, 91),
        "accent": (0, 155, 170),
        "muted": (91, 135, 143),
        "card": (255, 255, 255),
    },
    "sunset": {
        "bg": (255, 245, 237),
        "title": (91, 42, 30),
        "text": (111, 68, 52),
        "accent": (238, 112, 62),
        "muted": (164, 112, 91),
        "card": (255, 255, 255),
    },
    "forest": {
        "bg": (240, 247, 239),
        "title": (31, 65, 43),
        "text": (56, 87, 63),
        "accent": (65, 135, 78),
        "muted": (112, 143, 112),
        "card": (255, 255, 255),
    },
    "rose": {
        "bg": (255, 242, 247),
        "title": (91, 35, 59),
        "text": (112, 65, 83),
        "accent": (219, 91, 139),
        "muted": (166, 112, 134),
        "card": (255, 255, 255),
    },
    "lavender": {
        "bg": (247, 243, 255),
        "title": (65, 43, 103),
        "text": (91, 72, 125),
        "accent": (151, 112, 220),
        "muted": (139, 119, 169),
        "card": (255, 255, 255),
    },
    "graphite": {
        "bg": (37, 40, 46),
        "title": (245, 247, 250),
        "text": (220, 224, 231),
        "accent": (165, 174, 190),
        "muted": (159, 166, 179),
        "card": (53, 57, 65),
    },
    "sand": {
        "bg": (250, 246, 235),
        "title": (75, 61, 39),
        "text": (104, 88, 63),
        "accent": (181, 139, 76),
        "muted": (153, 133, 101),
        "card": (255, 252, 243),
    },
    "cyberpunk": {
        "bg": (19, 12, 31),
        "title": (255, 255, 255),
        "text": (231, 218, 245),
        "accent": (255, 46, 166),
        "muted": (177, 153, 197),
        "card": (39, 24, 57),
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


def _add_text(
    slide,
    text,
    left,
    top,
    width,
    height,
    size,
    color,
    bold=False,
    align=PP_ALIGN.LEFT,
    font="Calibri",
    anchor=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(
        left, top, width, height
    )

    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0

    paragraph = frame.paragraphs[0]
    paragraph.text = str(text)
    paragraph.alignment = align
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.name = font
    paragraph.font.color.rgb = _rgb(color)

    return box


def _add_bullets(
    slide,
    bullets,
    left,
    top,
    width,
    height,
    color,
    size=16,
):
    box = slide.shapes.add_textbox(
        left, top, width, height
    )

    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0

    for index, bullet in enumerate(bullets):
        paragraph = (
            frame.paragraphs[0]
            if index == 0
            else frame.add_paragraph()
        )

        paragraph.text = "\u2022  " + str(bullet)
        paragraph.font.size = Pt(size)
        paragraph.font.name = "Calibri"
        paragraph.font.color.rgb = _rgb(color)
        paragraph.space_after = Pt(7)
        paragraph.line_spacing = 1.12

    return box


def _add_accent_line(
    slide, left, top, width, height, color
):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        left,
        top,
        width,
        height,
    )

    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()

    return shape


def _add_slide_number(slide, number, total, color):
    _add_text(
        slide,
        f"{number:02d} / {total:02d}",
        SLIDE_W - Inches(1.15),
        SLIDE_H - Inches(0.45),
        Inches(0.8),
        Inches(0.28),
        9,
        color,
        align=PP_ALIGN.RIGHT,
    )


def _download_image(url, timeout=15):
    """Use the shared image cache from image_service."""

    if not url:
        return None

    try:
        return fetch_image_bytes(url)
    except Exception:
        return None


def _prefetch_images(slides):
    """Download slide images concurrently before building the deck."""

    image_results = {}

    def download_one(index, url):
        if not url:
            return index, None

        return index, _download_image(url)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []

        for index, slide_data in enumerate(slides):
            url = slide_data.get("image_source_url")
            if url:
                futures.append(
                    executor.submit(
                        download_one,
                        index,
                        url,
                    )
                )

        for future in as_completed(futures):
            try:
                index, image_bytes = future.result()
                image_results[index] = image_bytes
            except Exception:
                continue

    return image_results


def _add_picture_fit(
    slide,
    image_bytes,
    left,
    top,
    width,
    height,
):
    if not image_bytes:
        return None

    try:
        stream = io.BytesIO(image_bytes)
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

        return slide.shapes.add_picture(
            stream,
            x,
            y,
            width=final_w,
            height=final_h,
        )

    except Exception:
        return None


def _title_slide(slide, data, theme, author_name=""):
    """Build the opening slide without product branding."""

    _set_background(slide, theme["bg"])

    _add_accent_line(
        slide,
        Inches(0.9),
        Inches(1.55),
        Inches(0.9),
        Inches(0.08),
        theme["accent"],
    )

    _add_text(
        slide,
        data.get("title") or "Presentation",
        Inches(0.9),
        Inches(1.8),
        Inches(11.4),
        Inches(1.9),
        42,
        theme["title"],
        bold=True,
    )

    subtitle = data.get("subtitle") or ""

    if subtitle:
        _add_text(
            slide,
            subtitle,
            Inches(0.9),
            Inches(3.85),
            Inches(10.5),
            Inches(0.9),
            18,
            theme["muted"],
        )

    if author_name:
        _add_text(
            slide,
            f"Presented by: {author_name}",
            Inches(0.9),
            Inches(5.35),
            Inches(10.5),
            Inches(0.55),
            17,
            theme["text"],
            bold=True,
        )


def _thank_you_slide(
    slide,
    theme,
    author_name="",
    slide_no=1,
    total=1,
):
    """Build a clean closing slide with the presenter's name."""

    _set_background(slide, theme["bg"])

    _add_accent_line(
        slide,
        Inches(5.95),
        Inches(2.25),
        Inches(1.4),
        Inches(0.08),
        theme["accent"],
    )

    _add_text(
        slide,
        "Thank You",
        Inches(1.0),
        Inches(2.65),
        Inches(11.3),
        Inches(1.2),
        42,
        theme["title"],
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    if author_name:
        _add_text(
            slide,
            f"Presented by: {author_name}",
            Inches(2.0),
            Inches(4.15),
            Inches(9.3),
            Inches(0.6),
            18,
            theme["text"],
            align=PP_ALIGN.CENTER,
        )

    _add_slide_number(
        slide,
        slide_no,
        total,
        theme["muted"],
    )


def _references_slide(slide, data, theme):
    _set_background(slide, theme["bg"])

    _add_text(
        slide,
        data.get("title") or "References",
        Inches(0.9),
        Inches(0.7),
        Inches(11.4),
        Inches(0.8),
        30,
        theme["title"],
        bold=True,
    )

    _add_accent_line(
        slide,
        Inches(0.9),
        Inches(1.45),
        Inches(0.8),
        Inches(0.06),
        theme["accent"],
    )

    _add_bullets(
        slide,
        data.get("bullets") or [],
        Inches(0.9),
        Inches(1.9),
        Inches(11.3),
        Inches(4.8),
        theme["text"],
        15,
    )


def _content_slide(
    slide,
    data,
    theme,
    image_bytes,
    slide_no,
    total,
):
    _set_background(slide, theme["bg"])

    layout = data.get("layout") or "content"
    has_image = bool(image_bytes)

    title_left = Inches(0.9)
    title_top = Inches(0.65)
    title_width = Inches(11.4)

    if has_image and layout in ("image-left", "full-image"):
        title_left = Inches(6.6)
        title_width = Inches(5.8)

    elif has_image and layout in (
        "image-right", "content", "intro"
    ):
        title_left = Inches(0.9)
        title_width = Inches(6.2)

    _add_text(
        slide,
        data.get("title") or f"Slide {slide_no}",
        title_left,
        title_top,
        title_width,
        Inches(0.9),
        28,
        theme["title"],
        bold=True,
    )

    _add_accent_line(
        slide,
        title_left,
        Inches(1.55),
        Inches(0.8),
        Inches(0.06),
        theme["accent"],
    )

    if has_image and layout in (
        "image-left", "full-image"
    ):
        if layout == "full-image":
            _add_picture_fit(
                slide,
                image_bytes,
                0,
                0,
                SLIDE_W,
                SLIDE_H,
            )

            card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(0.7),
                Inches(4.35),
                Inches(6.8),
                Inches(2.45),
            )

            card.fill.solid()
            card.fill.fore_color.rgb = _rgb(
                theme["card"]
            )
            card.line.fill.background()

            _add_text(
                slide,
                data.get("title") or "",
                Inches(1.0),
                Inches(4.6),
                Inches(6.2),
                Inches(0.6),
                22,
                theme["title"],
                bold=True,
            )

            _add_bullets(
                slide,
                data.get("bullets") or [],
                Inches(1.0),
                Inches(5.25),
                Inches(6.1),
                Inches(1.35),
                theme["text"],
                12,
            )

        else:
            _add_picture_fit(
                slide,
                image_bytes,
                Inches(0.6),
                Inches(1.75),
                Inches(5.4),
                Inches(4.9),
            )

            _add_bullets(
                slide,
                data.get("bullets") or [],
                Inches(6.6),
                Inches(1.9),
                Inches(5.9),
                Inches(4.7),
                theme["text"],
                16,
            )

    elif has_image:
        _add_picture_fit(
            slide,
            image_bytes,
            Inches(7.15),
            Inches(1.75),
            Inches(5.4),
            Inches(4.9),
        )

        _add_bullets(
            slide,
            data.get("bullets") or [],
            Inches(0.9),
            Inches(1.9),
            Inches(5.9),
            Inches(4.7),
            theme["text"],
            16,
        )

    else:
        _add_bullets(
            slide,
            data.get("bullets") or [],
            Inches(0.9),
            Inches(1.9),
            Inches(11.3),
            Inches(4.8),
            theme["text"],
            18,
        )

    _add_slide_number(
        slide,
        slide_no,
        total,
        theme["muted"],
    )


def build_pptx(payload: dict):
    """Build an editable PowerPoint presentation."""

    slides = payload.get("slides") or []

    if not isinstance(slides, list) or not slides:
        raise ValueError("No slides to export.")

    if len(slides) > 20:
        raise ValueError("Too many slides to export.")

    author_name = str(
        payload.get("author_name") or ""
    ).strip()[:80]

    theme_name = str(
        payload.get("theme") or "aurora"
    ).strip().lower()

    if theme_name not in THEMES:
        raise ValueError(
            f"Unsupported PowerPoint theme: {theme_name}"
        )

    theme = THEMES[theme_name]

    # Fetch images concurrently to reduce export waiting time.
    image_results = _prefetch_images(slides)

    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H

    blank_layout = presentation.slide_layouts[6]
    total_slides = len(slides)

    for index, slide_data in enumerate(slides):
        if not isinstance(slide_data, dict):
            continue

        slide = presentation.slides.add_slide(blank_layout)

        slide_no = index + 1

        # Always create a dedicated closing slide.
        if slide_no == total_slides:
            _thank_you_slide(
                slide,
                theme,
                author_name,
                slide_no,
                total_slides,
            )

        elif slide_no == 1:
            _title_slide(
                slide,
                slide_data,
                theme,
                author_name,
            )

        else:
            layout = str(
                slide_data.get("layout") or "content"
            ).lower()

            image_bytes = image_results.get(index)

            if layout == "references":
                _references_slide(
                    slide,
                    slide_data,
                    theme,
                )

            else:
                _content_slide(
                    slide,
                    slide_data,
                    theme,
                    image_bytes,
                    slide_no,
                    total_slides,
                )

        notes = str(
            slide_data.get("speaker_notes") or ""
        ).strip()

        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    if not presentation.slides:
        raise ValueError("No valid slides were available to export.")

    output = io.BytesIO()
    presentation.save(output)
    output.seek(0)

    return output
