"""YouTube-only Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List

class YouTubeContentResponse(BaseModel):
    title: str
    description: str
    thumbnail_url: str
    alignment_score: float

class YouTubeProcessRequest(BaseModel):
    audio_file_path: str = Field(..., description="Path to the extracted audio of the video")
    target_style: Optional[str] = "educational"

class ThumbnailRefinementRequest(BaseModel):
    current_prompt: str
    feedback: str = Field(..., description="What was wrong with the last image?")

class YouTubeMetadata(BaseModel):
    hook: str
    hashtags: List[str]
    suggested_tags: List[str]