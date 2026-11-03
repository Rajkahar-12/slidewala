

import os
import requests

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse


USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "SlideWala/1.0 (presentation generator)"
)

HEADERS = {"User-Agent": USER_AGENT}

ALLOWED_HOSTS = (
    "upload.wikimedia.org",
    "commons.wikimedia.org",
)


def is_valid_wikimedia_url(url):
    """Allow images only from Wikimedia domains."""
    try:
        host = urlparse(url).hostname
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
            timeout=12,
            stream=True
        ) as response:

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            )

            if not content_type.startswith("image/"):
                return None

            data = response.raw.read(10 * 1024 * 1024 + 1)

            if len(data) > 10 * 1024 * 1024:
                return None

            return data, content_type

    except requests.RequestException:
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
def search_wikimedia(query, limit=6):
    """Search Wikimedia Commons for relevant images."""
    if not query:
        return []

    api_url = "https://commons.wikimedia.org/w/api.php"

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1200,
        "format": "json",
    }

    try:
        with requests.get(
            api_url,
            params=params,
            headers=HEADERS,
            timeout=12
        ) as response:

            response.raise_for_status()
            payload = response.json()

        pages = payload.get("query", {}).get("pages", {})
        results = []

        for page in pages.values():
            image_info = page.get("imageinfo", [{}])[0]

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
        TypeError
    ):
        return []


def _get_image_for_slide(slide):
    """Find a relevant Wikimedia image for one slide."""

    # Prefer the AI-generated image search phrase.
    query = str(slide.get("image_query") or "").strip()

    # Fall back to the slide title and first bullet.
    if not query:
        title = str(slide.get("title") or "")
        bullets = slide.get("bullets", [])

        first_bullet = (
            str(bullets[0]) if bullets else ""
        )

        query = f"{title} {first_bullet}".strip()

    if not query:
        return slide

    images = search_wikimedia(query, limit=6)

    if not images:
        return slide

    selected = images[0]
    image_url = selected["url"]

    # JavaScript preview expects image_url.
    # PPTX and PDF services can continue using image_source_url.
    slide["image_url"] = image_url
    slide["image_source_url"] = image_url
    slide["image_source"] = "wikimedia"
    slide["image_license"] = selected.get("license", "")
    slide["image_title"] = selected.get("title", "")
    slide["image_alt"] = query

    return slide


def enrich_slides_with_images(slides):
    """Add relevant Wikimedia images to presentation slides."""

    if not isinstance(slides, list):
        return slides

    valid_slides = [
        slide for slide in slides
        if isinstance(slide, dict)
    ]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_get_image_for_slide, slide)
            for slide in valid_slides
        ]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass

    return slides
