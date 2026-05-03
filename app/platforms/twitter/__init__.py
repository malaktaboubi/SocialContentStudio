"""Twitter / X platform — short posts and threads.

Pattern Analytics — edit only this folder. Endpoints live under /api/twitter/.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..registry import PlatformMeta, register
from .schemas import GenerateRequest
from .service import generate_post

router = APIRouter()


@router.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    try:
        return generate_post(body.topic, body.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


register(
    PlatformMeta(
        id="twitter",
        label="Twitter",
        tagline="Short posts and threads that fit the timeline.",
        icon="𝕏",
        accent="#1d9bf0",
        owner="",
    ),
    router,
)
