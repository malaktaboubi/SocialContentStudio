"""LinkedIn platform — professional posts.

Pattern Analytics — edit only this folder. Endpoints live under /api/linkedin/.
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
        return generate_post(body.topic, body.role)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


register(
    PlatformMeta(
        id="linkedin",
        label="LinkedIn",
        tagline="Professional posts that don't read like marketing fluff.",
        icon="◨",
        accent="#0a66c2",
        owner="",
    ),
    router,
)
