"""Instagram: replace `_generate` with your caption / carousel / reel logic. Keep `image_prompt` for shared image step."""

from .registry import PlatformMeta, register


def _generate(transcript: str) -> dict:
    snippet = (transcript or "").strip()[:280] or "your idea"
    return {
        "caption": f"[Placeholder — replace in instagram.py] {snippet}",
        "hashtags": ["#yourbrand", "#content"],
        "image_prompt": f"Instagram-style lifestyle photo, bright and clean, inspired by: {snippet[:200]}",
    }


register(
    PlatformMeta(
        id="instagram",
        label="Instagram",
        description="Captions and hashtags tuned for feeds and reels.",
        icon="◎",
    ),
    _generate,
)
