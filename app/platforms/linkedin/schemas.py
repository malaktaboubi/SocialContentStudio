"""LinkedIn-only schemas. Replace with whatever your inputs need."""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    role: str = Field("engineer", description="engineer | manager | founder | student")
