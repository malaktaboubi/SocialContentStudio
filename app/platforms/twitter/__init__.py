"""Twitter platform — voice → Tweet + AI image."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..registry import PlatformMeta, register
from .pipeline import OUTPUT_DIR, list_tone_options, resolve_tone_id
from .schemas import RegenerateImageRequest, RegenerateTextRequest
from .service import (
    iter_process_audio_bytes,
    process_audio_bytes,
    regenerate_post_image,
    regenerate_post_text,
)

router = APIRouter()


@router.get("/tones")
async def get_tones() -> dict:
    return {"tones": list_tone_options()}


@router.post("/process-stream")
async def process_audio_stream(
    file: Annotated[UploadFile, File(...)],
    tone: str = Form("default"),
):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")

    name = file.filename or "recording.webm"
    tone_key = resolve_tone_id(tone)

    def event_iter():
        try:
            for event in iter_process_audio_bytes(name, raw_bytes, tone_key):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/regenerate-text")
async def regenerate_text(body: RegenerateTextRequest) -> dict[str, str]:
    try:
        return regenerate_post_text(body.transcript, body.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/regenerate-image")
async def regenerate_image(body: RegenerateImageRequest) -> dict[str, str]:
    try:
        return regenerate_post_image(body.image_prompt)
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
        id="twitter",
        label="Twitter",
        tagline="Voice your thoughts — get a Tweet + AI image.",
        icon="𝕏",
        accent="#1d9bf0",
        owner="",
    ),
    router,
)
