"""AI Image Generation using Pollinations AI (Free, No API Key Required)."""
import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# 🚨 SAFETY FILTER
BLOCKED_PROMPT_WORDS = {
    "nude", "naked", "breast", "genital", "erotic", "porn", "nsfw", "explicit", "blood", "gore"
}

def _get_image_for_slide(slide: dict):
    prompt = (slide.get("image_query") or "").strip()
    
    if not prompt:
        return slide

    # 🚨 SAFETY CHECK
    prompt_lower = prompt.lower()
    if any(bad_word in prompt_lower for bad_word in BLOCKED_PROMPT_WORDS):
        print(f"Blocked unsafe image prompt: '{prompt}'")
        return slide

    try:
        # Force an educational, safe prefix so the AI doesn't block medical topics
        safe_prompt = f"educational, safe for work, textbook diagram, clean background, {prompt[:120]}"
        
        encoded_prompt = urllib.parse.quote(safe_prompt, safe='')
        seed = abs(hash(safe_prompt)) % 1000000
        
        # Request a 16:9 landscape image using the Flux model
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&model=flux&nologo=true&seed={seed}"

        slide["image_source_url"] = image_url
        slide["image_url"] = "/api/image?url=" + urllib.parse.quote_plus(image_url)
        slide["image_alt"] = prompt[:160]
        slide["image_credit"] = "AI Generated"
        
        print(f"Generated image prompt for: '{prompt[:30]}...'")

    except Exception as e:
        print(f"Error generating image: {e}")

    return slide


def enrich_slides_with_images(presentation: dict):
    slides = presentation.get("slides") or []
    if not slides:
        return presentation

    # Use 4 workers to speed up the generation
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(_get_image_for_slide, slides))

    return presentation


def proxy_image(url: str):
    """Fetch the generated image securely."""
    allowed_hosts = {"image.pollinations.ai"}
    parsed = urllib.parse.urlparse(url)
    
    if parsed.hostname not in allowed_hosts:
        raise ValueError("Image URL is not from an allowed source.")

    import requests
    resp = requests.get(
        url, 
        timeout=45, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    if not resp.ok:
        raise RuntimeError(f"Image request failed: {resp.status_code}")

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise ValueError("URL did not return an image.")

    return resp.content, content_type
