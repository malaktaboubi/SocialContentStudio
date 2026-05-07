"""LinkedIn-only schemas. Replace with whatever your inputs need."""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    image: str = Field(..., description="Base64-encoded image")
    topic: str | None = Field(None, description="Topic or context for caption generation (optional)")


class GenerateResponse(BaseModel):
    professional: str = Field(..., description="Professional tone caption")
    short: str = Field(..., description="Short/concise caption")
    story: str = Field(..., description="Story-telling tone caption")
