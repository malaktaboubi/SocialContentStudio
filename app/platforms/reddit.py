"""Reddit: voice → post fields + image_prompt. Owner: implement your prompts/models here."""

from ..pipeline import generate_reddit_content
from .registry import PlatformMeta, register


def _generate(transcript: str) -> dict:
    return generate_reddit_content(transcript)


register(
    PlatformMeta(
        id="reddit",
        label="Reddit",
        description="Title, body, and image from your voice — classic post format.",
        icon="◉",
    ),
    _generate,
)
