"""Twitter-only orchestration: bytes → transcript → post → image."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .pipeline import (
    generate_image,
    generate_twitter_content,
    resolve_tone_id,
    transcribe_voice,
)


def iter_process_audio_bytes(
    filename: str, raw_bytes: bytes, tone_id: str = "default"
) -> Iterator[dict[str, Any]]:
    tone_key = resolve_tone_id(tone_id)
    suffix = Path(filename or "recording.webm").suffix or ".webm"
    audio_path = Path(f"temp_tw_{uuid.uuid4()}{suffix}")
    audio_path.write_bytes(raw_bytes)

    try:
        yield {
            "type": "progress",
            "step": 1,
            "step_status": "running",
            "percent": 10,
            "message": "Transcribing audio...",
            "detail": "Using Whisper to listen to your voice.",
        }
        transcript = transcribe_voice(str(audio_path))
        yield {
            "type": "progress",
            "step": 1,
            "step_status": "done",
            "percent": 35,
            "message": "Transcription finished.",
            "detail": "Now crafting your tweet...",
            "transcript": transcript,
        }

        yield {
            "type": "progress",
            "step": 2,
            "step_status": "running",
            "percent": 40,
            "message": "Drafting tweet...",
            "detail": "Turning your idea into a punchy post.",
        }
        content = generate_twitter_content(transcript, tone_key)
        twitter_body = content.get("twitter_body", "")
        image_prompt = content.get("image_prompt", "")
        yield {
            "type": "progress",
            "step": 2,
            "step_status": "done",
            "percent": 65,
            "message": "Tweet drafted.",
            "detail": "Generating a matching image...",
        }

        yield {
            "type": "progress",
            "step": 3,
            "step_status": "running",
            "percent": 70,
            "message": "Generating image...",
            "detail": "This can take a moment.",
        }
        image_url = generate_image(image_prompt)
        image_error = "" if image_url else "Image generation failed."

        yield {
            "type": "progress",
            "step": 3,
            "step_status": "done",
            "percent": 100,
            "message": "Complete!",
            "detail": "Your Twitter post is ready.",
        }

        yield {
            "type": "complete",
            "data": {
                "transcript": transcript,
                "twitter_body": twitter_body,
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
        raise RuntimeError("Processing failed.")
    return result


def regenerate_post_text(transcript: str, tone_id: str) -> dict[str, str]:
    tone_key = resolve_tone_id(tone_id)
    content = generate_twitter_content(transcript.strip(), tone_key)
    return {
        "twitter_body": content["twitter_body"],
        "image_prompt": content["image_prompt"],
    }


def regenerate_post_image(image_prompt: str) -> dict[str, str]:
    image_url = generate_image(image_prompt.strip())
    image_error = "" if image_url else "Image generation failed."
    return {"image_url": image_url, "image_error": image_error}
