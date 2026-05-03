"""Instagram-only Pydantic schemas. Pattern Analytics — Instagram module."""

from pydantic import BaseModel, Field


class InstagramContent(BaseModel):
    instagram_caption: str
    hashtags: str
    image_prompt: str


class RegenerateTextRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    tone: str = "default"


class RegenerateImageRequest(BaseModel):
    image_prompt: str = Field(..., min_length=1)


class CaptionFromImageRequest(BaseModel):
    """Frontend sends base64-encoded image for vision-based caption generation."""
    image_b64: str = Field(..., min_length=1)
    mime_type: str = "image/jpeg"
    tone: str = "default"