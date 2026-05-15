"""YouTube-only schemas. Replace with whatever your inputs need."""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    kind: str = Field("tutorial", description="tutorial | vlog | review | shorts")
