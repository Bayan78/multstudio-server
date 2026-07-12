"""Generate a picture for each scene.

Default provider: Pollinations.ai — free, no API key, returns a PNG directly.
Optional: set POLLINATIONS_TOKEN for higher rate limits, or plug another
provider. On any failure a neon gradient is drawn so the pipeline never stalls.
"""
import os, hashlib, colorsys, random
from io import BytesIO
from urllib.parse import quote
import httpx
import numpy as np
from PIL import Image

POLLI_TOKEN = os.getenv("POLLINATIONS_TOKEN", "")
POLLI_MODEL = os.getenv("POLLINATIONS_MODEL", "flux")

# visual style presets appended to every image prompt
STYLES = {
    "cartoon": "colorful 2D cartoon illustration, clean bold outlines, vibrant",
    "pixar": "3D Pixar-style render, soft lighting, cinematic, highly detailed",
    "anime": "anime style, cel shaded, detailed background, studio quality",
    "watercolor": "soft watercolor storybook illustration, gentle colors",
    "comic": "comic book art, dynamic, ink shading, halftone",
    "realistic": "photorealistic, cinematic lighting, high detail",
}


def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return np.array([r * 255, g * 255, b * 255], np.float32)


def _gradient(seed_text, w, h):
    seed = int(hashlib.md5(seed_text.encode()).hexdigest(), 16)
    hue1 = (seed * 47) % 360
    hue2 = (hue1 + 90 + seed % 80) % 360
    c1, c2 = _hsl(hue1, 0.7, 0.16), _hsl(hue2, 0.68, 0.15)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx / w + yy / h) / 2.0
    arr = np.zeros((h, w, 3), np.float32)
    for i in range(3):
        arr[..., i] = c1[i] * (1 - t) + c2[i] * t
    cy, cx = h * 0.35, w * 0.5
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (max(w, h) * 0.6)
    glow = np.clip(1 - d, 0, 1)[..., None] * _hsl(hue1, 0.9, 0.6) * 0.35
    return np.clip(arr + glow, 0, 255).astype(np.uint8)


def fetch(prompt, w, h, style="cartoon"):
    """Return an (h, w, 3) uint8 array for the prompt."""
    style_txt = STYLES.get(style, STYLES["cartoon"])
    full = f"{prompt}, {style_txt}"
    seed = random.randint(1, 10_000_000)
    url = (f"https://image.pollinations.ai/prompt/{quote(full)}"
           f"?width={w}&height={h}&nologo=true&model={POLLI_MODEL}&seed={seed}")
    if POLLI_TOKEN:
        url += f"&token={POLLI_TOKEN}"
    try:
        r = httpx.get(url, timeout=120, follow_redirects=True)
        if r.status_code == 200 and r.content:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            if img.size != (w, h):
                img = img.resize((w, h))
            return np.array(img)
        print("Pollinations status:", r.status_code)
    except Exception as e:
        print("image fetch failed, gradient fallback:", e)
    return _gradient(prompt, w, h)
