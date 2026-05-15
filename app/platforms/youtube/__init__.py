"""YouTube platform — audio/video → hook + thumbnail.

Pattern Analytics — edit only this folder. Endpoints live under /api/youtube/.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..registry import PlatformMeta, register
from .pipeline import OUTPUT_DIR
from .service import iter_process_video_bytes, process_video_bytes

router = APIRouter()


@router.post("/process")
async def process_video(file: Annotated[UploadFile, File(...)]) -> dict:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    name = file.filename or "video.mp4"
    try:
        return process_video_bytes(name, raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/process-stream")
async def process_video_stream(file: Annotated[UploadFile, File(...)]):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    name = file.filename or "video.mp4"

    def event_iter():
        try:
            for event in iter_process_video_bytes(name, raw_bytes):
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


@router.get("/thumbnails/{filename}")
async def get_thumbnail(filename: str) -> FileResponse:
    path = OUTPUT_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found.")
    return FileResponse(path=path)


register(
    PlatformMeta(
        id="youtube",
        label="YouTube",
        tagline="Upload audio → click-worthy title + thumbnail.",
        icon="▶",
        accent="#ff0000",
        owner="",
    ),
    router,
)
