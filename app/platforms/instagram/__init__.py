"""Instagram platform — voice → Instagram post + AI image.

Pattern Analytics — edit only this folder. The shell calls `/api/instagram/...` here.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..registry import PlatformMeta, register
from .pipeline import OUTPUT_DIR, list_tone_options, resolve_tone_id
from .schemas import CaptionFromImageRequest, RegenerateImageRequest, RegenerateTextRequest
from .service import (
    caption_from_image_bytes,
    iter_process_audio_bytes,
    process_audio_bytes,
    regenerate_post_image,
    regenerate_post_text,
)

router = APIRouter()


@router.get("/tones")
async def get_tones() -> dict:
    return {"tones": list_tone_options()}


@router.post("/process")
async def process_audio(
    file: Annotated[UploadFile, File(...)],
    tone: str = Form("default"),
) -> dict[str, str]:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    name = file.filename or "recording.webm"
    tone_key = resolve_tone_id(tone)
    try:
        return process_audio_bytes(name, raw_bytes, tone_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/process-stream")
async def process_audio_stream(
    file: Annotated[UploadFile, File(...)],
    tone: str = Form("default"),
):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    name = file.filename or "recording.webm"
    tone_key = resolve_tone_id(tone)

    def event_iter():
        try:
            for event in iter_process_audio_bytes(name, raw_bytes, tone_key):
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/caption-from-image")
async def caption_from_image(
    file: Annotated[UploadFile, File(...)],
    tone: str = Form("default"),
) -> dict[str, str]:
    """Accept an uploaded image and return caption + hashtags via vision API."""
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    # Detect MIME type from upload or fall back to jpeg
    mime_type = file.content_type or "image/jpeg"
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if mime_type not in allowed:
        mime_type = "image/jpeg"

    tone_key = resolve_tone_id(tone)
    try:
        return caption_from_image_bytes(raw_bytes, mime_type, tone_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/regenerate-text")
async def regenerate_text(body: RegenerateTextRequest) -> dict[str, str]:
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is empty.")
    try:
        return regenerate_post_text(transcript, body.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/regenerate-image")
async def regenerate_image(body: RegenerateImageRequest) -> dict[str, str]:
    prompt = body.image_prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Image prompt is empty.")
    try:
        return regenerate_post_image(prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/images/{filename}")
async def get_image(filename: str) -> FileResponse:
    image_path = OUTPUT_DIR / filename
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path=image_path)


register(
    PlatformMeta(
        id="instagram",
        label="Instagram",
        tagline="Voice your idea — get a caption, hashtags + AI image.",
        icon="📸",
        accent="#e1306c",
        owner="",
    ),
    router,
)