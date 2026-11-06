"""Wikimedia Commons image search, proxy, and slide enrichment."""
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus, urlparse

import requests

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_IMAGE_HOSTS = {"upload.wikimedia.org", "commons.wikimedia.org"}

USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "SlideWala/1.0 (https://example.com; slidewala@example.com)",
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


def _is_allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ("http", "https")
            and parsed.hostname in ALLOWED_IMAGE_HOSTS
        )
    except Exception:
        return False


def proxy_image(url: str):
    """Fetch an allowed image server-side and return (bytes, content_type)."""
    if not _is_allowed_url(url):
        raise ValueError("Image URL is not from an allowed source.")

    resp = _SESSION.get(url, timeout=15, allow_redirects=True)
    if not resp.ok:
        raise RuntimeError(f"Image request failed with status {resp.status_code}.")
    if not _is_allowed_url(resp.url):
        raise ValueError("Image redirected to a disallowed host.")

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise ValueError("The URL did not return an image.")

    if len(resp.content) > 10 * 1024 * 1024:
        raise ValueError("Image is too large.")

    return resp.content, content_type


def search_wikimedia(query: str, limit: int = 6):
    """Search Wikimedia Commons for bitmap images. Keyless API."""
    if not query or not query.strip():
        return []

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query.strip()} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(min(max(limit, 1), 10)),
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "1600",
        "format": "json",
    }

    try:
        resp = _SESSION.get(WIKIMEDIA_API, params=params, timeout=8)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"Wikimedia API Error for '{query}': {e}")
        return []

    pages = (payload.get("query") or {}).get("pages") or {}
    results = []

    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            continue

        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 500 or height < 300:
            continue

        original = info.get("url")
        if not original:
            continue

        results.append(
            {
                "title": (page.get("title") or "").replace("File:", ""),
                "url": original,
                "width": width,
                "height": height,
                "mime": mime,
            }
        )

    return results


def _score_image(item: dict) -> int:
    """Prefer landscape images large enough for a 16:9 slide."""
    width = item.get("width") or 0
    height = item.get("height") or 0
    if not width or not height:
        return -1
    ratio = width / height
    score = 0
    if 1.2 <= ratio <= 2.0:
        score += 4
    elif 0.8 <= ratio < 1.2:
        score += 1
    if width >= 1200:
        score += 2
    if width >= 2000:
        score += 1
    return score


def _get_image_for_slide(slide: dict, fallback_query: str = ""):
    query = (slide.get("image_query") or "").strip()
    if not query:
        query = fallback_query

    if not query:
        return slide

    try:
        candidates = search_wikimedia(query)
        
        # Fallback: If no candidates found for specific query, try the main topic
        if not candidates and fallback_query and query != fallback_query:
            print(f"No images for '{query}'. Falling back to '{fallback_query}'.")
            candidates = search_wikimedia(fallback_query)

        if not candidates:
            print(f"No images found at all for '{query}'.")
            return slide

        best = max(candidates, key=_score_image)
        if _score_image(best) < 0:
            return slide

        slide["image_source_url"] = best["url"]
        slide["image_url"] = "/api/image?url=" + quote_plus(best["url"])
        slide["image_alt"] = best["title"][:160]
        slide["image_credit"] = "Wikimedia Commons"
        print(f"Image found for '{query}' -> {best['title']}")
        
    except Exception as e:
        print(f"Error fetching image for slide: {e}")

    return slide


def enrich_slides_with_images(presentation: dict, fallback_query: str = ""):
    """Attach one relevant Wikimedia image to each slide in parallel."""
    slides = presentation.get("slides") or []
    if not slides:
        return presentation

    print(f"Starting image enrichment for {len(slides)} slides...")

    def task(slide):
        return _get_image_for_slide(slide, fallback_query)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(task, slides))

    print("Image enrichment finished.")
    return presentation
