"""Reddit-only Pydantic schemas. Pattern Analytics — Reddit module."""

from pydantic import BaseModel, Field


class RedditContent(BaseModel):
    reddit_title: str
    reddit_body: str
    image_prompt: str


class RegenerateTextRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    tone: str = "default"


class RegenerateImageRequest(BaseModel):
    image_prompt: str = Field(..., min_length=1)
