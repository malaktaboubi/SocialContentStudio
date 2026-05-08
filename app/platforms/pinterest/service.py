"""Pinterest orchestration: bytes → transcript → caption + image."""

from __future__ import annotations

import base64
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .pipeline import (
    generate_image,
    generate_pinterest_content,
    generate_pinterest_content_from_image,
    resolve_tone_id,
    transcribe_voice,
)


def iter_process_audio_bytes(
    filename: str, raw_bytes: bytes, tone_id: str = "default"
) -> Iterator[dict[str, Any]]:
    tone_key = resolve_tone_id(tone_id)
    suffix = Path(filename or "recording.webm").suffix or ".webm"
    audio_path = Path(f"temp_pin_{uuid.uuid4()}{suffix}")
    audio_path.write_bytes(raw_bytes)

    try:
        yield {
            "type": "progress", "step": 1, "step_status": "running",
            "percent": 10, "message": "Transcribing audio...",
            "detail": "Using Whisper to listen to your voice.",
        }
        transcript = transcribe_voice(str(audio_path))
        yield {
            "type": "progress", "step": 1, "step_status": "done",
            "percent": 35, "message": "Transcription finished.",
            "detail": "Now crafting your Pinterest caption...",
            "transcript": transcript,
        }

        yield {
            "type": "progress", "step": 2, "step_status": "running",
            "percent": 40, "message": "Drafting Pinterest caption...",
            "detail": "Turning your idea into an inspiring pin.",
        }
        content = generate_pinterest_content(transcript, tone_key)
        yield {
            "type": "progress", "step": 2, "step_status": "done",
            "percent": 65, "message": "Caption drafted.",
            "detail": "Generating a matching vertical image...",
        }

        yield {
            "type": "progress", "step": 3, "step_status": "running",
            "percent": 70, "message": "Generating image...",
            "detail": "Creating a beautiful vertical Pinterest image.",
        }
        image_url = generate_image(content.get("image_prompt", ""))
        image_error = "" if image_url else "Image generation failed."

        yield {
            "type": "progress", "step": 3, "step_status": "done",
            "percent": 100, "message": "Complete!",
            "detail": "Your Pinterest pin is ready.",
        }
        yield {
            "type": "complete",
            "data": {
                "transcript": transcript,
                "pinterest_caption": content.get("pinterest_caption", ""),
                "hashtags": content.get("hashtags", ""),
                "image_prompt": content.get("image_prompt", ""),
                "image_url": image_url,
                "image_error": image_error,
            },
        }
    finally:
        audio_path.unlink(missing_ok=True)


def process_audio_bytes(
    filename: str, raw_bytes: bytes, tone_id: str = "default"
) -> dict[str, Any]:
    result = {}
    for event in iter_process_audio_bytes(filename, raw_bytes, tone_id):
        if event.get("type") == "complete":
            result = event["data"]
    return result


def caption_from_image_bytes(
    raw_bytes: bytes, mime_type: str = "image/jpeg", tone_id: str = "default"
) -> dict[str, Any]:
    tone_key = resolve_tone_id(tone_id)
    image_b64 = base64.b64encode(raw_bytes).decode("utf-8")
    content = generate_pinterest_content_from_image(image_b64, mime_type, tone_key)
    image_url = generate_image(content.get("image_prompt", ""))
    return {
        "pinterest_caption": content.get("pinterest_caption", ""),
        "hashtags": content.get("hashtags", ""),
        "image_prompt": content.get("image_prompt", ""),
        "image_url": image_url,
        "image_error": "" if image_url else "Image generation failed.",
    }


def regenerate_post_text(
    transcript: str, tone_id: str = "default"
) -> dict[str, str]:
    tone_key = resolve_tone_id(tone_id)
    content = generate_pinterest_content(transcript, tone_key)
    return {
        "pinterest_caption": content.get("pinterest_caption", ""),
        "hashtags": content.get("hashtags", ""),
        "image_prompt": content.get("image_prompt", ""),
    }


def regenerate_post_image(image_prompt: str) -> dict[str, str]:
    image_url = generate_image(image_prompt)
    return {
        "image_url": image_url,
        "image_error": "" if image_url else "Image generation failed.",
    }