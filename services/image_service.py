"""AI Image Generation using Pollinations AI (Free, No API Key Required)."""
import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# 🚨 SAFETY FILTER
# If the AI tries to generate these, we block it to keep the site safe for school.
BLOCKED_PROMPT_WORDS = {
    "sex", "penis", "vagina", "nude", "naked", "breast", "genital", 
    "erotic", "porn", "nsfw", "explicit", "blood", "gore"
}

def _get_image_for_slide(slide: dict):
    prompt = (slide.get("image_query") or "").strip()
    title = (slide.get("title") or "").lower()

    # 🚨 SAFETY CHECK 1: Check the slide title
    if any(bad_word in title for bad_word in BLOCKED_PROMPT_WORDS):
        print(f"Blocked unsafe slide title: '{title}'")
        return slide

    if not prompt:
        return slide

    # 🚨 SAFETY CHECK 2: Check the prompt for unsafe words
    prompt_lower = prompt.lower()
    if any(bad_word in prompt_lower for bad_word in BLOCKED_PROMPT_WORDS):
        print(f"Blocked unsafe image prompt: '{prompt}'")
        return slide

    try:
        # Pollinations AI expects the prompt to be URL-encoded
        encoded_prompt = urllib.parse.quote(prompt)
        
        # We use the Flux model for high quality, and request a 16:9 landscape image
        # The 'nologo=true' parameter removes the watermark
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&model=flux&nologo=true&seed={hash(prompt)}"

        # We don't download the image here; we just pass the URL to the frontend.
        slide["image_source_url"] = image_url
        slide["image_url"] = "/api/image?url=" + urllib.parse.quote_plus(image_url)
        slide["image_alt"] = prompt[:160]
        slide["image_credit"] = "AI Generated"
        
        print(f"Generated image for: '{prompt[:50]}...'")

    except Exception as e:
        print(f"Error generating image: {e}")

    return slide


def enrich_slides_with_images(presentation: dict):
    """Attach one AI-generated image to each slide in parallel."""
    slides = presentation.get("slides") or []
    if not slides:
        return presentation

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(_get_image_for_slide, slides))

    return presentation


def proxy_image(url: str):
    """Fetch the generated image securely."""
    allowed_hosts = {"image.pollinations.ai"}
    parsed = urllib.parse.urlparse(url)
    
    if parsed.hostname not in allowed_hosts:
        raise ValueError("Image URL is not from an allowed source.")

    import requests
    resp = requests.get(url, timeout=25) # Pollinations can take a few seconds to generate
    if not resp.ok:
        raise RuntimeError(f"Image request failed: {resp.status_code}")

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise ValueError("URL did not return an image.")

    return resp.content, content_type
