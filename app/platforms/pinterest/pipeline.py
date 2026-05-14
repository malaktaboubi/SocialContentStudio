"""Pinterest-only pipeline: Whisper STT + OpenRouter text/vision + image generation."""

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
log = logging.getLogger("pinterest.pipeline")

CUDA_AVAILABLE = torch.cuda.is_available()
WHISPER_MODEL_ID = os.getenv("WHISPER_MODEL_ID", "base" if CUDA_AVAILABLE else "tiny")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-2.0-flash-001")
USE_OPENROUTER = os.getenv("USE_OPENROUTER", "true").lower() == "true"

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

USE_POLLINATIONS_IMAGE = os.getenv("USE_POLLINATIONS_IMAGE", "true").lower() == "true"

OUTPUT_DIR = Path(__file__).resolve().parent / "output_images"
OUTPUT_DIR.mkdir(exist_ok=True)


def _configure_ffmpeg() -> None:
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    alias_dir = Path(tempfile.gettempdir()) / "voice_to_pinterest_ffmpeg"
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


TONE_PRESETS: Dict[str, str] = {
    "default": (
        "Tone: inspirational and warm — descriptive, inviting, perfect for Pinterest boards."
    ),
    "aesthetic": (
        "Tone: aesthetic and poetic — dreamy language, focus on beauty and mood."
    ),
    "diy": (
        "Tone: practical DIY — step-hint language, helpful and encouraging."
    ),
    "travel": (
        "Tone: wanderlust travel — evocative, adventurous, makes readers want to go there."
    ),
    "fashion": (
        "Tone: fashion-forward — stylish, trendy, uses relevant fashion vocabulary."
    ),
}

DEFAULT_TONE_ID = "default"

_TONE_LABELS: Dict[str, str] = {
    "default": "Inspirational",
    "aesthetic": "Aesthetic / Poetic",
    "diy": "DIY / Tutorial",
    "travel": "Travel / Wanderlust",
    "fashion": "Fashion / Style",
}


def list_tone_options() -> List[Dict[str, str]]:
    return [
        {"id": key, "label": _TONE_LABELS.get(key, key)} for key in TONE_PRESETS
    ]


def resolve_tone_id(tone_id: Optional[str]) -> str:
    if not tone_id:
        return DEFAULT_TONE_ID
    key = tone_id.strip().lower()
    if key in TONE_PRESETS:
        return key
    return DEFAULT_TONE_ID


def _build_messages(transcript: str, tone_id: str) -> list:
    tone_line = TONE_PRESETS.get(tone_id, TONE_PRESETS[DEFAULT_TONE_ID])
    system_msg = (
        "You are an expert Pinterest content creator and social media strategist. "
        f"{tone_line} "
        "Your task is to TRANSFORM the user's input into a high-quality Pinterest pin description. "
        "DO NOT just repeat the input. Create an engaging, inspiring description. "
        "Respond with ONLY a single JSON object. No markdown, no preamble. "
        "Required keys: pinterest_caption, hashtags, image_prompt. "
        "pinterest_caption: An inspiring Pinterest description (150-300 words), storytelling style. "
        "hashtags: 20-30 relevant Pinterest hashtags as a single string. "
        "image_prompt: A detailed vertical image prompt (2:3 ratio) for text-to-image generation."
    )
    user_msg = f"INPUT TO TRANSFORM:\n{transcript}\n\nReturn the JSON object now:"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_vision_messages(image_b64: str, mime_type: str, tone_id: str) -> list:
    tone_line = TONE_PRESETS.get(tone_id, TONE_PRESETS[DEFAULT_TONE_ID])
    system_msg = (
        "You are an expert Pinterest content creator. "
        f"{tone_line} "
        "Analyze the image and create a Pinterest pin description. "
        "Respond with ONLY a single JSON object. No markdown, no preamble. "
        "Required keys: pinterest_caption, hashtags, image_prompt. "
        "pinterest_caption: An inspiring Pinterest description (150-300 words). "
        "hashtags: 20-30 relevant Pinterest hashtags as a single string. "
        "image_prompt: A detailed vertical image prompt (2:3 ratio) based on the image."
    )
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_b64}"
                    },
                },
                {"type": "text", "text": system_msg},
            ],
        }
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
    return None


def _fallback_content(transcript: str) -> Dict[str, str]:
    snippet = transcript.strip() or "a beautiful moment"
    return {
        "pinterest_caption": (
            f"Discover the beauty in everyday moments. {snippet[:200]} "
            "Save this pin to your board and share the inspiration with others!"
        ),
        "hashtags": (
            "#pinterest #inspiration #lifestyle #beautiful #aesthetic "
            "#inspo #pinoftheday #style #creative #mood"
        ),
        "image_prompt": (
            f"Beautiful vertical Pinterest-style photograph representing: {snippet[:100]}, "
            "warm lighting, aesthetic composition, 2:3 ratio"
        ),
    }


def _normalize_content(obj: dict, transcript: str) -> Dict[str, str]:
    fallback = _fallback_content(transcript)
    return {
        "pinterest_caption": str(obj.get("pinterest_caption") or fallback["pinterest_caption"]),
        "hashtags": str(obj.get("hashtags") or fallback["hashtags"]),
        "image_prompt": str(obj.get("image_prompt") or fallback["image_prompt"])[:500],
    }


def _generate_via_openrouter(transcript: str, tone_id: str) -> Dict[str, str]:
    log.info("OpenRouter: model=%s tone=%s", OPENROUTER_MODEL, tone_id)
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": _build_messages(transcript, tone_id),
        "temperature": 0.8,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "voice-to-pinterest",
    }
    response = _post_json(
        "https://openrouter.ai/api/v1/chat/completions", payload, headers
    )
    if "error" in response:
        raise RuntimeError(f"OpenRouter error: {response['error']}")
    message = response["choices"][0]["message"]["content"]
    log.info("OpenRouter: raw output (%d chars): %s", len(message), message[:300])
    obj = _extract_json(message)
    if obj is None:
        log.warning("OpenRouter: failed to extract JSON, using fallback")
        return _fallback_content(transcript)
    return _normalize_content(obj, transcript)


def _generate_via_vision(image_b64: str, mime_type: str, tone_id: str) -> Dict[str, str]:
    log.info("OpenRouter Vision: model=%s tone=%s", OPENROUTER_VISION_MODEL, tone_id)
    payload = {
        "model": OPENROUTER_VISION_MODEL,
        "messages": _build_vision_messages(image_b64, mime_type, tone_id),
        "temperature": 0.8,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "voice-to-pinterest",
    }
    response = _post_json(
        "https://openrouter.ai/api/v1/chat/completions", payload, headers
    )
    if "error" in response:
        raise RuntimeError(f"OpenRouter Vision error: {response['error']}")
    message = response["choices"][0]["message"]["content"]
    obj = _extract_json(message)
    if obj is None:
        return _fallback_content("image input")
    return _normalize_content(obj, "image input")


def generate_pinterest_content(
    transcript: str, tone_id: str = DEFAULT_TONE_ID
) -> Dict[str, str]:
    tone_key = resolve_tone_id(tone_id)
    if not USE_OPENROUTER or not OPENROUTER_API_KEY:
        log.warning("OpenRouter disabled or no key, using fallback")
        return _fallback_content(transcript)
    try:
        return _generate_via_openrouter(transcript, tone_key)
    except Exception as exc:
        log.error("OpenRouter generation failed: %s", exc)
        return _fallback_content(transcript)


def generate_pinterest_content_from_image(
    image_b64: str, mime_type: str, tone_id: str = DEFAULT_TONE_ID
) -> Dict[str, str]:
    tone_key = resolve_tone_id(tone_id)
    if not USE_OPENROUTER or not OPENROUTER_API_KEY:
        return _fallback_content("image input")
    try:
        return _generate_via_vision(image_b64, mime_type, tone_key)
    except Exception as exc:
        log.error("Vision generation failed: %s", exc)
        return _fallback_content("image input")


def _save_image_bytes(image_bytes: bytes) -> str:
    filename = f"{uuid.uuid4()}.png"
    path = OUTPUT_DIR / filename
    path.write_bytes(image_bytes)
    return f"/api/pinterest/images/{filename}"


@lru_cache(maxsize=1)
def _hf_client() -> InferenceClient:
    return InferenceClient(token=HF_TOKEN, timeout=180)


def _generate_image_huggingface(prompt: str) -> str:
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN not set")
    log.info("HuggingFace: model=%s", HF_IMAGE_MODEL)
    image = _hf_client().text_to_image(prompt[:500], model=HF_IMAGE_MODEL)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return _save_image_bytes(buf.getvalue())


def _generate_image_pollinations(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt[:400])
    seed = int(time.time())
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=768&height=1152&nologo=true&model=flux&seed={seed}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 voice-to-pinterest/1.0",
            "Referer": "http://localhost:8000/",
            "Accept": "image/*",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        image_bytes = resp.read()
    return _save_image_bytes(image_bytes)


def generate_image(prompt: str) -> str:
    log.info("generate_image: prompt=%s", prompt[:120])
    if HF_TOKEN:
        try:
            return _generate_image_huggingface(prompt)
        except Exception as exc:
            log.warning("HuggingFace failed: %s", exc)
    if USE_POLLINATIONS_IMAGE:
        try:
            return _generate_image_pollinations(prompt)
        except Exception as exc:
            log.error("Pollinations failed: %s", exc)
    return ""