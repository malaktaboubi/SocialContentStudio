from __future__ import annotations

from pydantic import BaseModel


class RegenerateTextRequest(BaseModel):
    transcript: str
    tone: str = "default"


class RegenerateImageRequest(BaseModel):
    image_prompt: str
