"""LinkedIn platform — professional posts.

Pattern Analytics — edit only this folder. Endpoints live under /api/linkedin/.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..registry import PlatformMeta, register
from .schemas import GenerateRequest, GenerateResponse
from .service import generate_post

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate(body: GenerateRequest) -> dict:
    try:
        return generate_post(body.image, body.topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
