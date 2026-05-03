"""Twitter-only schemas. Replace with whatever your inputs need."""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="What you want to post about")
    tone: str = Field("casual", description="casual | thread | newsy")
