"""LinkedIn business logic. Uses the configured LLM to generate captions."""

from __future__ import annotations
import os
import re
import json
import logging
from typing import Any
import requests

log = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "")
USE_OPENROUTER = os.getenv("USE_OPENROUTER", "true").lower() == "true"


def generate_post(image_base64: str, topic: str | None = None) -> dict:
    """Generate professional, short, and story-style captions from an image.

    Args:
        image_base64: Base64-encoded image data (with or without data URI prefix)
        topic: Optional topic/context for caption generation (ignored)

    Returns:
        Dictionary with "professional", "short", and "story" keys.

    Raises:
        ValueError: If image decoding fails.
    """
    try:
        captions = _generate_llm_captions(image_base64=image_base64, topic=topic)
        professional_caption = captions.get("professional", "").strip()
        short_caption = captions.get("short", "").strip()
        story_caption = captions.get("story", "").strip()

        if not professional_caption or not short_caption or not story_caption:
            fallback_seed = " ".join(
                [professional_caption, short_caption, story_caption, topic or ""]
            ).strip()
            if not professional_caption:
                professional_caption = _format_professional(fallback_seed)
            if not short_caption:
                short_caption = _format_short(fallback_seed) or "A quick takeaway from the image."
            if not story_caption:
                story_caption = _format_story(fallback_seed)

        hashtags = captions.get("hashtags", "").strip()
        if not hashtags:
            hashtags = _generate_hashtags(" ".join([professional_caption, short_caption, story_caption]))

        return {
            "professional": _append_hashtags(professional_caption, f"{hashtags} #ProfessionalDevelopment"),
            "short": _append_hashtags(short_caption, hashtags),
            "story": _append_hashtags(story_caption, f"{hashtags} #Storytelling"),
        }

    except Exception as exc:
        log.error("Pipeline failed: %s", exc, exc_info=True)
        # Graceful fallback with context-aware defaults
        return {
            "professional": "Exploring insights on recent learnings. A key learning for today.\n\n#LinkedIn #ProfessionalDevelopment #Growth",
            "short": "Insights on this picture.\n\n#Insights #Growth",
            "story": "Let me share a thought on this that resonated with me.\n\n#Storytelling #Learning #Perspective",
        }


def _format_professional(caption: str) -> str:
    """Format caption in professional tone."""
    caption = caption.strip()
    if not caption:
        return "Reflecting on recent learnings. Key insight: continuous learning drives excellence."

    # Capitalize and add professional framing
    sentences = caption.split(". ")
    formatted = ". ".join(s.capitalize() for s in sentences if s)
    if formatted and not formatted.endswith("."):
        formatted += "."

    return f"Insights to share: {formatted}"


def _format_short(caption: str) -> str:
    """Format caption in short/concise style."""
    caption = caption.strip()
    if not caption:
        return ""

    # Keep first sentence only, truncate if needed
    first_sentence = caption.split(". ")[0].strip()
    if len(first_sentence) > 100:
        first_sentence = first_sentence[:97] + "..."

    if first_sentence and not first_sentence.endswith("."):
        first_sentence += "."

    return first_sentence


def _format_story(caption: str) -> str:
    """Format caption in story-telling tone."""
    caption = caption.strip()
    if not caption:
        return "Here's something I learned recently. It changed my perspective."

    # Add narrative framing
    sentences = caption.split(". ")
    formatted = ". ".join(s.capitalize() for s in sentences if s)
    if formatted and not formatted.endswith("."):
        formatted += "."

    return f"Here's a reflection from this image: {formatted}"


def _append_hashtags(caption: str, hashtags: str) -> str:
    """Append hashtags to a caption when they are present."""
    caption = caption.strip()
    hashtags = hashtags.strip()
    if not hashtags:
        return caption
    return f"{caption}\n\n{hashtags}"


def _generate_llm_captions(image_base64: str, topic: str | None = None) -> dict[str, str]:
    """Generate LinkedIn captions using a vision summary + text model."""
    if not USE_OPENROUTER or not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured")

    vision_model = OPENROUTER_VISION_MODEL or OPENROUTER_MODEL
    if not vision_model:
        raise ValueError("OPENROUTER_VISION_MODEL is not configured")

    image_data = image_base64
    if "," not in image_data:
        image_data = f"data:image/png;base64,{image_data}"

    topic_text = topic.strip() if topic else ""

    summary_payload: dict[str, Any] = {
        "model": vision_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You describe images for LinkedIn post drafting. "
                    "Return a short, concrete description of the image content."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in 1-2 sentences."},
                    {"type": "image_url", "image_url": {"url": image_data}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 120,
    }

    summary_resp = _openrouter_chat(summary_payload, timeout=30)
    summary_message = summary_resp.get("choices", [{}])[0].get("message", {})
    summary_content = summary_message.get("content")
    if not isinstance(summary_content, str) or not summary_content.strip():
        summary_content = summary_message.get("reasoning")
    if not isinstance(summary_content, str) or not summary_content.strip():
        log.warning("Vision summary empty. OpenRouter response: %s", _truncate_json(summary_resp))
        raise ValueError("Vision model returned an empty summary")
    summary_text = summary_content.strip()

    caption_prompt = (
        "Generate three LinkedIn caption options for the image described below. "
        "Return only valid JSON with exactly these keys: professional, short, story, hashtags. "
        "Each value must be a plain string. "
        "professional should be polished and credible, short should be concise, story should be more reflective, "
        "and hashtags should be 3-5 relevant LinkedIn hashtags separated by spaces."
    )
    if topic_text:
        caption_prompt += f" The optional context/topic is: {topic_text}."

    caption_payload: dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write high-quality LinkedIn captions from image descriptions. "
                    "Be specific, professional, and avoid generic marketing language."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Image description: {summary_text}\n\n{caption_prompt}"
                ),
            },
        ],
        "temperature": 0.7,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }

    content = _openrouter_chat(caption_payload, timeout=30)["choices"][0]["message"]["content"]
    extracted = _extract_json_block(content)
    if extracted is None:
        raise ValueError("LLM did not return valid JSON")

    data = json.loads(extracted)
    if not isinstance(data, dict):
        raise ValueError("LLM response was not a JSON object")

    result = _normalize_caption_response(data)
    if not result["professional"] or not result["short"] or not result["story"]:
        log.warning("Caption JSON missing fields. Raw response: %s", _truncate_json(data))
    return result


def _openrouter_chat(payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "linkedin-caption-generator",
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    if not resp.ok:
        raise ValueError(f"OpenRouter error {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def _truncate_json(data: dict[str, Any], limit: int = 800) -> str:
    try:
        text = json.dumps(data, ensure_ascii=True)
    except Exception:
        text = str(data)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _extract_json_block(content: str) -> str | None:
    if not isinstance(content, str):
        return None
    content = content.strip()
    if not content:
        return None
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    # Attempt to extract the outermost JSON object.
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return content[start : end + 1]


def _normalize_caption_response(data: dict[str, Any]) -> dict[str, str]:
    return {
        "professional": str(data.get("professional", "") or "").strip(),
        "short": str(data.get("short", "") or "").strip(),
        "story": str(data.get("story", "") or "").strip(),
        "hashtags": str(data.get("hashtags", "") or "").strip(),
    }

def _generate_hashtags(caption: str) -> str:
    """Generate dynamic hashtags based on the caption text."""
    if not caption.strip():
        return "#LinkedIn #Growth #Perspective"

    if USE_OPENROUTER and OPENROUTER_API_KEY:
        try:
            payload = {
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a LinkedIn hashtag generator. Return a JSON object with exactly one key `hashtags` which is a single string containing 3-5 relevant LinkedIn hashtags separated by spaces for the provided caption.",
                    },
                    {
                        "role": "user",
                        "content": f"Generate hashtags for this caption: {caption}",
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 100,
                "response_format": {"type": "json_object"}
            }
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # find JSON block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            obj = json.loads(content.strip())
            if "hashtags" in obj:
                return obj["hashtags"]
        except Exception as exc:
            log.error("Failed to generate hashtags via LLM: %s", exc)

    # Fallback logic
    words = re.findall(r'\b\w+\b', caption.lower())
    stopwords = {"this", "that", "with", "from", "your", "what", "have", "some", "they", "just", "startseq", "endseq", "into", "onto", "over"}
    keywords = [w for w in words if len(w) > 3 and w not in stopwords]
    
    unique_keywords = list(dict.fromkeys(keywords))[:4]
    
    if not unique_keywords:
        return "#LinkedIn #Growth #Perspective"
        
    return " ".join(f"#{w.capitalize()}" for w in unique_keywords)
