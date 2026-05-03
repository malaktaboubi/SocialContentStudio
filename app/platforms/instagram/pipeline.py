"""Instagram-only pipeline: Whisper STT + OpenRouter text/vision + free image providers.

Instagram module only (Pattern Analytics). Other platform folders do NOT import from here.
"""

from __future__ import annotations

import base64
import gc
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import imageio_ffmpeg
import torch
import whisper
from huggingface_hub import InferenceClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("instagram.pipeline")

CUDA_AVAILABLE = torch.cuda.is_available()
WHISPER_MODEL_ID = os.getenv("WHISPER_MODEL_ID", "base" if CUDA_AVAILABLE else "tiny")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

# Vision model — free tier on OpenRouter, very lightweight (no local GPU needed)
# Vision model — Utilisation d'un modèle stable et rapide
OPENROUTER_VISION_MODEL = os.getenv(
    "OPENROUTER_VISION_MODEL",
    "google/gemini-2.0-flash-001",  # Version stable actuelle
)
USE_OPENROUTER = os.getenv("USE_OPENROUTER", "true").lower() == "true"

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

USE_POLLINATIONS_IMAGE = os.getenv("USE_POLLINATIONS_IMAGE", "true").lower() == "true"

OUTPUT_DIR = Path(__file__).resolve().parent / "output_images"
OUTPUT_DIR.mkdir(exist_ok=True)


def _configure_ffmpeg() -> None:
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    alias_dir = Path(tempfile.gettempdir()) / "voice_to_instagram_ffmpeg"
    alias_dir.mkdir(parents=True, exist_ok=True)
    alias_path = alias_dir / "ffmpeg.exe"

    if not alias_path.exists():
        shutil.copy2(ffmpeg_path, alias_path)

    current_path = os.environ.get("PATH", "")
    alias_dir_str = str(alias_dir)
    if alias_dir_str not in current_path:
        os.environ["PATH"] = f"{alias_dir_str}{os.pathsep}{current_path}"


_configure_ffmpeg()


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def flush_memory() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@lru_cache(maxsize=1)
def _get_whisper_model():
    log.info("Whisper: loading model=%s on %s", WHISPER_MODEL_ID, get_device())
    return whisper.load_model(WHISPER_MODEL_ID).to(get_device())


def transcribe_voice(audio_path: str) -> str:
    log.info("Whisper: transcribing %s", audio_path)
    model = _get_whisper_model()
    result = model.transcribe(audio_path, fp16=False)
    transcript = result["text"].strip()
    log.info("Whisper: transcript (%d chars): %s", len(transcript), transcript[:200])
    return transcript


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, method="POST")
    for key, value in headers.items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


# ── Tone presets ───────────────────────────────────────────────────────────────

TONE_PRESETS: Dict[str, str] = {
    "default": (
        "Tone: general Instagram — warm, authentic, visually descriptive, and engaging. "
        "Use emojis naturally. End with a call-to-action or open question."
    ),
    "lifestyle": (
        "Tone: aspirational lifestyle — evocative, sensory language that paints a mood; "
        "short poetic lines; feels personal and curated."
    ),
    "motivational": (
        "Tone: motivational and uplifting — short punchy lines, power words, "
        "inspiring energy. Add relevant emojis. Close with a strong call-to-action."
    ),
    "humorous": (
        "Tone: funny and relatable — self-deprecating humor welcome; witty observations; "
        "stay light and kind. Emojis that add to the joke."
    ),
    "educational": (
        "Tone: informative carousel style — clear numbered points or tips; "
        "each point is a single punchy sentence. End with 'Save this for later 🔖'."
    ),
    "aesthetic": (
        "Tone: minimalist aesthetic — very short, almost poetic; maximum 3 lines; "
        "no hashtags in caption body, list them separately; dreamy or abstract imagery."
    ),
    "brand": (
        "Tone: professional brand voice — confident, polished, benefit-focused; "
        "clear value proposition; subtle CTA at the end."
    ),
}

DEFAULT_TONE_ID = "default"

_TONE_LABELS: Dict[str, str] = {
    "default": "General Instagram",
    "lifestyle": "Lifestyle / Aesthetic",
    "motivational": "Motivational",
    "humorous": "Humor / Relatable",
    "educational": "Educational / Tips",
    "aesthetic": "Minimalist Aesthetic",
    "brand": "Brand / Professional",
}


def list_tone_options() -> List[Dict[str, str]]:
    return [{"id": key, "label": _TONE_LABELS.get(key, key)} for key in TONE_PRESETS]


def resolve_tone_id(tone_id: Optional[str]) -> str:
    if not tone_id:
        return DEFAULT_TONE_ID
    key = tone_id.strip().lower()
    return key if key in TONE_PRESETS else DEFAULT_TONE_ID


# ── Text generation (from transcript) ─────────────────────────────────────────

def _build_messages(transcript: str, tone_id: str) -> list:
    tone_line = TONE_PRESETS.get(tone_id, TONE_PRESETS[DEFAULT_TONE_ID])
    system_msg = (
        "You are an expert Instagram content creator. "
        f"{tone_line} "
        "Convert the user's transcript into a complete Instagram post. "
        "Respond with ONLY a single JSON object, no preamble, no markdown fences, no commentary. "
        "Required keys exactly: instagram_caption, hashtags, image_prompt. "
        "instagram_caption: engaging caption (max 2200 chars), emojis allowed, no hashtags here. "
        "hashtags: a string of 10-15 relevant hashtags starting with #, space-separated. "
        "image_prompt: vivid text-to-image prompt for a square (1:1) Instagram-ready image. "
        "If the transcript is too short or unclear, infer a creative interpretation."
    )
    user_msg = f'Transcript: "{transcript}"\n\nReturn the JSON object now:'
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ── Vision generation (from image) ────────────────────────────────────────────

def _build_vision_messages(image_b64: str, mime_type: str, tone_id: str) -> list:
    """Build OpenRouter messages with an inline base64 image for vision models."""
    tone_line = TONE_PRESETS.get(tone_id, TONE_PRESETS[DEFAULT_TONE_ID])
    system_msg = (
        "You are an expert Instagram content creator. "
        f"{tone_line} "
        "Look at the provided image carefully and generate a complete Instagram post for it. "
        "Respond with ONLY a single JSON object, no preamble, no markdown fences, no commentary. "
        "Required keys exactly: instagram_caption, hashtags, image_prompt. "
        "instagram_caption: engaging caption (max 2200 chars), emojis allowed, no hashtags here. "
        "hashtags: a string of 10-15 relevant hashtags starting with #, space-separated. "
        "image_prompt: describe the image style as a text-to-image prompt (for regeneration)."
    )
    return [
        {"role": "system", "content": system_msg},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_b64}"
                    },
                },
                {
                    "type": "text",
                    "text": "Generate the Instagram post JSON for this image now:",
                },
            ],
        },
    ]


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start: i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    break

    truncated = cleaned[start:]
    for repair in (truncated + '"}', truncated + "}", truncated + '" }'):
        try:
            obj = json.loads(repair)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    return None


def _fallback_content(source: str = "") -> Dict[str, str]:
    snippet = source.strip() or "a moment worth sharing"
    return {
        "instagram_caption": f"✨ {snippet[:200]}\n\nWhat do you think? Drop your thoughts below! 👇",
        "hashtags": "#instagram #photooftheday #explore #trending #viral #instagood #content #share #daily #life",
        "image_prompt": "Beautiful aesthetic square photo, vibrant colors, Instagram style",
    }


def _normalize_content(obj: dict, source: str = "") -> Dict[str, str]:
    fallback = _fallback_content(source)
    return {
        "instagram_caption": str(obj.get("instagram_caption") or fallback["instagram_caption"])[:2200],
        "hashtags": str(obj.get("hashtags") or fallback["hashtags"])[:500],
        "image_prompt": str(obj.get("image_prompt") or fallback["image_prompt"])[:500],
    }


def _call_openrouter(messages: list, model: str, temperature: float = 0.75, max_tokens: int = 900) -> str:
    """Generic OpenRouter call, returns raw content string."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "voice-to-instagram",
    }
    response = _post_json("https://openrouter.ai/api/v1/chat/completions", payload, headers)
    if "error" in response:
        raise RuntimeError(f"OpenRouter error: {response['error']}")
    return response["choices"][0]["message"]["content"]


def _generate_via_openrouter(transcript: str, tone_id: str) -> Dict[str, str]:
    log.info("OpenRouter text: model=%s tone=%s", OPENROUTER_MODEL, tone_id)
    messages = _build_messages(transcript, tone_id)
    raw = _call_openrouter(messages, OPENROUTER_MODEL)
    log.info("OpenRouter text: raw (%d chars): %s", len(raw), raw[:200])
    obj = _extract_json(raw)
    if obj is None:
        log.warning("OpenRouter text: JSON extraction failed, using fallback")
        return _fallback_content(transcript)
    result = _normalize_content(obj, transcript)
    log.info("OpenRouter text: caption=%s", result["instagram_caption"][:80])
    return result


def _generate_via_openrouter_vision(image_b64: str, mime_type: str, tone_id: str) -> Dict[str, str]:
    """Use a free vision model on OpenRouter — no local GPU needed."""
    log.info("OpenRouter vision: model=%s tone=%s mime=%s", OPENROUTER_VISION_MODEL, tone_id, mime_type)
    messages = _build_vision_messages(image_b64, mime_type, tone_id)
    raw = _call_openrouter(messages, OPENROUTER_VISION_MODEL, temperature=0.7, max_tokens=900)
    log.info("OpenRouter vision: raw (%d chars): %s", len(raw), raw[:200])
    obj = _extract_json(raw)
    if obj is None:
        log.warning("OpenRouter vision: JSON extraction failed, using fallback")
        return _fallback_content("uploaded image")
    result = _normalize_content(obj, "uploaded image")
    log.info("OpenRouter vision: caption=%s", result["instagram_caption"][:80])
    return result


def generate_instagram_content(transcript: str, tone_id: str = DEFAULT_TONE_ID) -> Dict[str, str]:
    """Generate caption/hashtags from a voice transcript."""
    tone_key = resolve_tone_id(tone_id)
    if not USE_OPENROUTER or not OPENROUTER_API_KEY:
        log.warning("OpenRouter disabled or no key, using fallback")
        return _fallback_content(transcript)
    try:
        return _generate_via_openrouter(transcript, tone_key)
    except Exception as exc:
        log.error("OpenRouter text generation failed: %s", exc)
        return _fallback_content(transcript)


def generate_caption_from_image(
    image_b64: str,
    mime_type: str = "image/jpeg",
    tone_id: str = DEFAULT_TONE_ID,
) -> Dict[str, str]:
    """Generate caption/hashtags from an uploaded image using a free vision API."""
    tone_key = resolve_tone_id(tone_id)
    if not USE_OPENROUTER or not OPENROUTER_API_KEY:
        log.warning("OpenRouter disabled or no key, using fallback")
        return _fallback_content("uploaded image")
    try:
        return _generate_via_openrouter_vision(image_b64, mime_type, tone_key)
    except Exception as exc:
        log.error("OpenRouter vision generation failed: %s", exc)
        return _fallback_content("uploaded image")


# ── Image generation ───────────────────────────────────────────────────────────

def _save_image_bytes(image_bytes: bytes) -> str:
    filename = f"{uuid.uuid4()}.png"
    path = OUTPUT_DIR / filename
    path.write_bytes(image_bytes)
    return f"/api/instagram/images/{filename}"


@lru_cache(maxsize=1)
def _hf_client() -> InferenceClient:
    return InferenceClient(token=HF_TOKEN, timeout=180)


def _generate_image_huggingface(prompt: str) -> str:
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN not set")
    log.info("HuggingFace: model=%s", HF_IMAGE_MODEL)
    image = _hf_client().text_to_image(
        prompt[:500] + ", square format, Instagram style",
        model=HF_IMAGE_MODEL,
    )
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()
    log.info("HuggingFace: got %d bytes", len(image_bytes))
    return _save_image_bytes(image_bytes)


def _generate_image_pollinations(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt[:400] + ", square crop, Instagram aesthetic")
    seed = int(time.time())
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1080&height=1080&nologo=true&model=flux&seed={seed}"
    )
    log.info("Pollinations: requesting 1080x1080...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) voice-to-instagram/1.0",
            "Referer": "http://localhost:8000/",
            "Accept": "image/*",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        image_bytes = resp.read()

    if len(image_bytes) < 1000:
        raise RuntimeError(f"Pollinations returned tiny payload: {len(image_bytes)} bytes")

    log.info("Pollinations: got %d bytes", len(image_bytes))
    return _save_image_bytes(image_bytes)


def generate_image(prompt: str) -> str:
    """Try multiple free image providers. Returns image URL or '' on total failure."""
    log.info("generate_image: prompt=%s", prompt[:120])

    providers = []
    if HF_TOKEN:
        providers.append(("HuggingFace", _generate_image_huggingface))
    if USE_POLLINATIONS_IMAGE:
        providers.append(("Pollinations", _generate_image_pollinations))

    if not providers:
        log.error("No image providers configured")
        return ""

    for name, fn in providers:
        for attempt in range(2):
            try:
                url = fn(prompt)
                log.info("%s: success url=%s", name, url)
                return url
            except Exception as exc:
                log.warning("%s attempt %d failed: %s", name, attempt + 1, exc)
                if attempt == 0:
                    time.sleep(3)

    log.error("All image providers failed")
    return ""