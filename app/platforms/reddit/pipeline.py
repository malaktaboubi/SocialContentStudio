"""Reddit-only pipeline: Whisper STT + OpenRouter text + free image providers.

Reddit module only (Pattern Analytics). Other platform folders do NOT import from here.
"""

from __future__ import annotations

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
log = logging.getLogger("reddit.pipeline")

CUDA_AVAILABLE = torch.cuda.is_available()
WHISPER_MODEL_ID = os.getenv("WHISPER_MODEL_ID", "base" if CUDA_AVAILABLE else "tiny")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
USE_OPENROUTER = os.getenv("USE_OPENROUTER", "true").lower() == "true"

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

USE_POLLINATIONS_IMAGE = os.getenv("USE_POLLINATIONS_IMAGE", "true").lower() == "true"

OUTPUT_DIR = Path(__file__).resolve().parent / "output_images"
OUTPUT_DIR.mkdir(exist_ok=True)


def _configure_ffmpeg() -> None:
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    alias_dir = Path(tempfile.gettempdir()) / "voice_to_reddit_ffmpeg"
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
        "Tone: general Reddit — conversational, authentic, and engaging."
    ),
    "eli5": (
        "Tone: explain like I'm five — very simple words, friendly analogies, no jargon; "
        "still readable as a real Reddit post."
    ),
    "rant": (
        "Tone: passionate rant — strong voice and emotion; mix short punchy lines with longer vents; "
        "never use slurs or hate; stay readable."
    ),
    "askreddit": (
        "Tone: r/AskReddit — title sparks discussion or stories; body adds context or a follow-up; "
        "curious, inclusive, and inviting."
    ),
    "humor": (
        "Tone: witty and light — jokes and sarcasm welcome; stay kind and avoid punching down."
    ),
    "professional": (
        "Tone: calm and informative — clear paragraphs, minimal slang, helpful and neutral."
    ),
}

DEFAULT_TONE_ID = "default"

_TONE_LABELS: Dict[str, str] = {
    "default": "General Reddit",
    "eli5": "ELI5",
    "rant": "Rant",
    "askreddit": "r/AskReddit style",
    "humor": "Humor / witty",
    "professional": "Professional",
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
        "You are an expert Social Media Manager and Reddit content creator. "
        f"{tone_line} "
        "Convert the user's transcript into a complete Reddit post. "
        "Respond with ONLY a single JSON object, no preamble, no markdown fences, no commentary. "
        "Required keys exactly: reddit_title, reddit_body, image_prompt. "
        "reddit_title: short, attention-grabbing (max 300 chars). "
        "reddit_body: 2-4 paragraphs matching the tone above. "
        "image_prompt: descriptive text-to-image prompt aligned with the post. "
        "If the transcript is too short or unclear, infer a creative interpretation."
    )
    user_msg = f"TRANSCRIPT TO TRANSFORM:\n{transcript}\n\nReturn the JSON object now:"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _extract_json(text: str) -> Optional[dict]:
    """Robustly extract a JSON object from LLM output."""
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
                candidate = cleaned[start : i + 1]
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


def _fallback_content(transcript: str) -> Dict[str, str]:
    snippet = transcript.strip() or "a creative idea"
    return {
        "reddit_title": f"Thought: {snippet[:80]}...",
        "reddit_body": f"I've been thinking about this lately: {snippet}. What do you all think?",
        "image_prompt": f"Detailed digital art illustration representing: {snippet[:100]}, vibrant colors, cinematic lighting.",
    }


def _normalize_content(obj: dict, transcript: str) -> Dict[str, str]:
    fallback = _fallback_content(transcript)
    return {
        "reddit_title": str(obj.get("reddit_title") or fallback["reddit_title"])[:300],
        "reddit_body": str(obj.get("reddit_body") or fallback["reddit_body"]),
        "image_prompt": str(obj.get("image_prompt") or fallback["image_prompt"])[:500],
    }


def _generate_via_openrouter(transcript: str, tone_id: str) -> Dict[str, str]:
    log.info("OpenRouter: model=%s tone=%s", OPENROUTER_MODEL, tone_id)
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": _build_messages(transcript, tone_id),
        "temperature": 0.7,
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "voice-to-reddit",
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

    result = _normalize_content(obj, transcript)
    log.info("OpenRouter: parsed title=%s", result["reddit_title"][:80])
    return result


def generate_reddit_content(
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


def _save_image_bytes(image_bytes: bytes) -> str:
    filename = f"{uuid.uuid4()}.png"
    path = OUTPUT_DIR / filename
    path.write_bytes(image_bytes)
    return f"/api/reddit/images/{filename}"


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
    image_bytes = buf.getvalue()
    log.info("HuggingFace: got %d bytes", len(image_bytes))
    return _save_image_bytes(image_bytes)


def _generate_image_pollinations(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt[:400])
    seed = int(time.time())
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=768&height=512&nologo=true&model=flux&seed={seed}"
    )
    log.info("Pollinations: requesting...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) voice-to-reddit/1.0",
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
