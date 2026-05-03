"""Instagram-only orchestration: bytes → transcript → post → image."""

from __future__ import annotations

import base64
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .pipeline import (
    generate_caption_from_image,
    generate_image,
    generate_instagram_content,
    resolve_tone_id,
    transcribe_voice,
)


def iter_process_audio_bytes(
    filename: str, raw_bytes: bytes, tone_id: str = "default"
) -> Iterator[dict[str, Any]]:
    tone_key = resolve_tone_id(tone_id)
    suffix = Path(filename or "recording.webm").suffix or ".webm"
    audio_path = Path(f"temp_{uuid.uuid4()}{suffix}")
    audio_path.write_bytes(raw_bytes)

    try:
        yield {
            "type": "progress",
            "step": 1,
            "step_status": "running",
            "percent": 6,
            "message": "Transcribing your recording…",
            "detail": "Running speech-to-text (Whisper). This may take a little while.",
        }
        transcript = transcribe_voice(str(audio_path))
        yield {
            "type": "progress",
            "step": 1,
            "step_status": "done",
            "percent": 32,
            "message": "Transcription finished.",
            "detail": "Generating Instagram caption and hashtags…",
            "transcript": transcript,
        }

        yield {
            "type": "progress",
            "step": 2,
            "step_status": "running",
            "percent": 36,
            "message": "Writing your Instagram post…",
            "detail": "The model is crafting your caption and hashtags.",
        }
        content = generate_instagram_content(transcript, tone_key)
        caption = content.get("instagram_caption", "")
        hashtags = content.get("hashtags", "")
        image_prompt = content.get("image_prompt", "Beautiful aesthetic Instagram photo")
        yield {
            "type": "progress",
            "step": 2,
            "step_status": "done",
            "percent": 62,
            "message": "Caption and hashtags ready.",
            "detail": "Creating a square Instagram image from the generated prompt…",
        }

        yield {
            "type": "progress",
            "step": 3,
            "step_status": "running",
            "percent": 68,
            "message": "Generating image (1080×1080)…",
            "detail": "Image APIs can take up to a minute — still working.",
        }
        image_url = generate_image(image_prompt)
        image_error = "" if image_url else "Image generation failed — no provider available."

        yield {
            "type": "progress",
            "step": 3,
            "step_status": "done",
            "percent": 96,
            "message": "Image step finished.",
            "detail": "Preparing your post preview…",
        }

        yield {
            "type": "complete",
            "data": {
                "transcript": transcript,
                "instagram_caption": caption,
                "hashtags": hashtags,
                "image_prompt": image_prompt,
                "image_url": image_url,
                "image_error": image_error,
            },
        }
    finally:
        audio_path.unlink(missing_ok=True)


def process_audio_bytes(
    filename: str, raw_bytes: bytes, tone_id: str = "default"
) -> dict[str, str]:
    result: dict[str, str] | None = None
    for event in iter_process_audio_bytes(filename, raw_bytes, tone_id):
        if event.get("type") == "complete":
            result = event["data"]
    if result is None:
        raise RuntimeError("Processing finished without a result.")
    return result


def regenerate_post_text(transcript: str, tone_id: str) -> dict[str, str]:
    tone_key = resolve_tone_id(tone_id)
    content = generate_instagram_content(transcript.strip(), tone_key)
    return {
        "instagram_caption": content["instagram_caption"],
        "hashtags": content["hashtags"],
        "image_prompt": content["image_prompt"],
    }


def regenerate_post_image(image_prompt: str) -> dict[str, str]:
    prompt = image_prompt.strip()
    image_url = generate_image(prompt)
    image_error = "" if image_url else "Image generation failed — no provider available."
    return {"image_url": image_url, "image_error": image_error}


def caption_from_image_bytes(
    raw_bytes: bytes,
    mime_type: str = "image/jpeg",
    tone_id: str = "default",
) -> dict[str, str]:
    """Convert uploaded image bytes → base64 → vision API → caption + hashtags."""
    tone_key = resolve_tone_id(tone_id)
    image_b64 = base64.b64encode(raw_bytes).decode("utf-8")
    content = generate_caption_from_image(image_b64, mime_type, tone_key)
    return {
        "instagram_caption": content["instagram_caption"],
        "hashtags": content["hashtags"],
        "image_prompt": content["image_prompt"],
    }