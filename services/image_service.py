
"""Fast, cached Wikimedia image service for SlideWala."""

import os
import re
import logging
import requests

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "SlideWala/1.0 (presentation generator)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
}

ALLOWED_HOSTS = (
    "upload.wikimedia.org",
    "commons.wikimedia.org",
)

# Separate connection and response timeouts.
IMAGE_SEARCH_TIMEOUT = (3, 5)
IMAGE_DOWNLOAD_TIMEOUT = (3, 8)

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_WORKERS = 6
SEARCH_RESULT_LIMIT = 3

# Layouts that never need an image.
NO_IMAGE_LAYOUTS = {
    "title", "conclusion", "references",
    "section", "stats", "two-column",
    "timeline", "quote",
}


def is_valid_wikimedia_url(url):
    """Allow images only from Wikimedia domains."""

    try:
        parsed = urlparse(url)

        if parsed.scheme != "https":
            return False

        host = parsed.hostname

        return bool(host) and any(
            host == allowed or host.endswith("." + allowed)
            for allowed in ALLOWED_HOSTS
        )

    except Exception:
        return False


@lru_cache(maxsize=256)
def _fetch_image_cached(url):
    """Download and cache an image."""

    if not is_valid_wikimedia_url(url):
        return None

    try:
        with requests.get(
            url,
            headers=HEADERS,
            timeout=IMAGE_DOWNLOAD_TIMEOUT,
            stream=True,
        ) as response:

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].lower()

            if not content_type.startswith("image/"):
                return None

            data = response.raw.read(MAX_IMAGE_SIZE + 1)

            if not data or len(data) > MAX_IMAGE_SIZE:
                return None

            return data, content_type

    except requests.RequestException:
        logger.warning("Wikimedia image download failed.")
        return None


def fetch_image_bytes(url):
    """Get cached image bytes for PPTX and PDF exports."""

    if not url:
        return None

    result = _fetch_image_cached(url)

    return result[0] if result else None


def proxy_image(url):
    """Return image bytes and content type for image proxy routes."""

    if not url:
        return None

    return _fetch_image_cached(url)


@lru_cache(maxsize=256)
def search_wikimedia(query, limit=SEARCH_RESULT_LIMIT):
    """Search Wikimedia Commons for relevant images."""

    query = str(query or "").strip()

    if not query:
        return []

    # Avoid unnecessarily long search requests.
    query = query[:180]

    api_url = "https://commons.wikimedia.org/w/api.php"

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6,
        "gsrlimit": min(max(int(limit), 1), 4),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1000,
        "format": "json",
    }

    try:
        with requests.get(
            api_url,
            params=params,
            headers=HEADERS,
            timeout=IMAGE_SEARCH_TIMEOUT,
        ) as response:

            response.raise_for_status()
            payload = response.json()

        pages = payload.get(
            "query", {}
        ).get("pages", {})

        results = []

        for page in pages.values():

            image_info_list = page.get("imageinfo") or []

            if not image_info_list:
                continue

            image_info = image_info_list[0]

            image_url = (
                image_info.get("thumburl")
                or image_info.get("url")
            )

            if not image_url or not is_valid_wikimedia_url(image_url):
                continue

            metadata = image_info.get("extmetadata", {})

            results.append({
                "title": page.get("title", ""),
                "url": image_url,
                "description": metadata.get(
                    "ImageDescription", {}
                ).get("value", ""),
                "license": metadata.get(
                    "LicenseShortName", {}
                ).get("value", ""),
            })

        return results

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ):
        logger.warning(
            "Wikimedia search failed for query: %s",
            query[:70],
        )
        return []


def _get_image_for_slide(slide):
    """Find a relevant Wikimedia image for one slide."""

    query = str(
        slide.get("image_query") or ""
    ).strip()

    if not query:
        title = str(slide.get("title") or "")
        bullets = slide.get("bullets", [])

        first_bullet = (
            str(bullets[0]) if bullets else ""
        )

        query = f"{title} {first_bullet}".strip()

    if not query:
        return slide

    query = re.sub(r"\s+", " ", query)[:180]

    images = search_wikimedia(
        query,
        limit=SEARCH_RESULT_LIMIT,
    )

    if not images:
        return slide

    selected = images[0]
    image_url = selected["url"]

    slide["image_url"] = image_url
    slide["image_source_url"] = image_url
    slide["image_source"] = "wikimedia"
    slide["image_license"] = selected.get("license", "")
    slide["image_title"] = selected.get("title", "")
    slide["image_alt"] = query

    return slide


def enrich_slides_with_images(slides):
    """Add relevant Wikimedia images using parallel cached searches."""

    if not isinstance(slides, list):
        return slides

    eligible_slides = []

    for slide in slides:

        if not isinstance(slide, dict):
            continue

        layout = str(
            slide.get("layout") or "content"
        ).lower()

        title = str(
            slide.get("title") or ""
        ).strip().lower()

        if layout in NO_IMAGE_LAYOUTS:
            continue

        if title in {"thank you", "thank you!"}:
            continue

        eligible_slides.append(slide)

    if not eligible_slides:
        return slides

    worker_count = min(
        MAX_WORKERS,
        len(eligible_slides),
    )

    start_count = 0

    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="slidewala-image",
    ) as executor:

        futures = [
            executor.submit(
                _get_image_for_slide,
                slide,
            )
            for slide in eligible_slides
        ]

        for future in as_completed(futures):

            try:
                future.result()
                start_count += 1

            except Exception:
                logger.exception(
                    "An image search failed for a slide."
                )

    logger.info(
        "SlideWala processed images for %s slides.",
        start_count,
    )

    return slides
