import uuid
from pathlib import Path

from ..core.config import OUTPUT_DIR
from ..pipeline import generate_image, generate_reddit_content, transcribe_voice


def process_audio_bytes(filename: str, raw_bytes: bytes) -> dict[str, str]:
    suffix = Path(filename or "recording.webm").suffix or ".webm"
    audio_path = Path(f"temp_{uuid.uuid4()}{suffix}")
    audio_path.write_bytes(raw_bytes)

    try:
        transcript = transcribe_voice(str(audio_path))
        content = generate_reddit_content(transcript)

        title = content.get("reddit_title", "Untitled")
        body = content.get("reddit_body", "")
        image_prompt = content.get("image_prompt", "Abstract colorful background")
        image_url = generate_image(image_prompt)
        image_error = "" if image_url else "Image generation failed — no provider available."
    finally:
        audio_path.unlink(missing_ok=True)

    return {
        "transcript": transcript,
        "reddit_title": title,
        "reddit_body": body,
        "image_url": image_url,
        "image_error": image_error,
    }
