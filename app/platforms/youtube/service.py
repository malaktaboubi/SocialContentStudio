
"""YouTube orchestration: audio bytes → notebook-style pipeline → SSE events."""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

log = logging.getLogger("youtube.service")

from .pipeline import (
    MAX_ITERATIONS,
    SIM_THRESHOLD,
    add_thumbnail_text,
    build_thumbnail_prompt,
    caption_image,
    classify_thumbnail_style,
    clip_score,
    generate_hashtags,
    generate_hook,
    generate_thumbnail,
    refine_prompt,
    similarity_score,
    speech_to_text,
)


def iter_process_video_bytes(filename: str, raw_bytes: bytes) -> Iterator[dict[str, Any]]:
    """SSE-friendly generator that mirrors the notebook's run_pipeline."""
    suffix = Path(filename or "video.mp4").suffix or ".mp4"
    # Write to the OS temp dir, NOT the project dir — otherwise uvicorn --reload
    # detects the file and restarts the worker mid-request.
    audio_path = Path(tempfile.gettempdir()) / f"yt_{uuid.uuid4()}{suffix}"
    audio_path.write_bytes(raw_bytes)
    run_id = uuid.uuid4().hex[:8]

    try:
        yield {
            "type": "progress",
            "step": 1,
            "percent": 6,
            "message": "Transcribing audio…",
        }
        transcript = speech_to_text(str(audio_path))

        yield {
            "type": "progress",
            "step": 2,
            "percent": 22,
            "message": "Generating hook…",
            "transcript": transcript,
        }
        hook = generate_hook(transcript)

        yield {
            "type": "progress",
            "step": 3,
            "percent": 30,
            "message": f"Detecting style for '{hook[:40]}…'",
            "hook": hook,
        }
        style = classify_thumbnail_style(hook)
        prompt = build_thumbnail_prompt(hook, style)

        best_score = 0.0
        best_image: str | None = None
        best_caption: str | None = None
        best_clip = 0.0

        for iteration in range(MAX_ITERATIONS):
            base = 30 + int(50 * iteration / MAX_ITERATIONS)
            yield {
                "type": "progress",
                "step": 4,
                "percent": base + 2,
                "message": f"Generating thumbnail (iter {iteration + 1}/{MAX_ITERATIONS})…",
            }
            try:
                image_path = generate_thumbnail(
                    prompt, output_path=f"yt_{run_id}_iter{iteration}.png"
                )
            except Exception as exc:
                log.exception("Thumbnail iteration %d failed", iteration + 1)
                yield {
                    "type": "progress",
                    "step": 4,
                    "percent": base + 8,
                    "message": f"Thumbnail iteration {iteration + 1} failed: {exc!r}",
                }
                continue

            yield {
                "type": "progress",
                "step": 4,
                "percent": base + 8,
                "message": "Captioning and scoring…",
            }
            try:
                gen_caption = caption_image(image_path)
                c_score = clip_score(image_path, hook)
                s_score = similarity_score(hook, gen_caption)
            except Exception as exc:
                log.exception("Scoring failed on iteration %d", iteration + 1)
                yield {
                    "type": "progress",
                    "step": 4,
                    "percent": base + 12,
                    "message": f"Scoring failed: {exc!r}",
                }
                continue

            if s_score > best_score:
                best_score = s_score
                best_image = image_path
                best_caption = gen_caption
                best_clip = c_score

            if s_score >= SIM_THRESHOLD:
                break

            prompt = refine_prompt(prompt, gen_caption, hook)

        if best_image is None:
            raise RuntimeError("Thumbnail generation failed on every iteration.")

        yield {
            "type": "progress",
            "step": 5,
            "percent": 88,
            "message": "Adding title overlay…",
        }
        final_image = add_thumbnail_text(
            best_image, hook[:40], output_path=f"yt_final_{run_id}.png"
        )

        yield {
            "type": "progress",
            "step": 6,
            "percent": 95,
            "message": "Extracting hashtags…",
        }
        hashtags = generate_hashtags(hook)

        yield {
            "type": "complete",
            "data": {
                "title": hook,
                "caption": best_caption,
                "hashtags": hashtags,
                "similarity_score": round(best_score, 4),
                "clip_score": round(best_clip, 4),
                "thumbnail_url": f"/api/youtube/thumbnails/{Path(final_image).name}",
                "transcript": transcript,
            },
        }
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            # Whisper/pydub may still hold a handle on Windows; ignore.
            pass


def process_video_bytes(filename: str, raw_bytes: bytes) -> dict[str, Any]:
    """Synchronous wrapper around the streaming generator."""
    result: dict[str, Any] | None = None
    for event in iter_process_video_bytes(filename, raw_bytes):
        if event.get("type") == "complete":
            result = event["data"]
    if result is None:
        raise RuntimeError("Processing finished without a result.")
    return result
