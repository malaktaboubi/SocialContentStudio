"""YouTube platform — title + description + thumbnail prompt.

Pattern Analytics — edit only this folder. Endpoints live under /api/youtube/.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..registry import PlatformMeta, register
from .schemas import GenerateRequest
from .service import generate_video_meta

router = APIRouter()


@router.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    try:
        return generate_video_meta(body.subject, body.kind)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


register(
    PlatformMeta(
        id="youtube",
        label="YouTube",
        tagline="Click-worthy titles + SEO-ready descriptions.",
        icon="▶",
        accent="#ff0000",
        owner="",
    ),
    router,
)
