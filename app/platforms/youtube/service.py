"""YouTube business logic. Replace this stub with your own."""

from __future__ import annotations


def generate_video_meta(subject: str, kind: str) -> dict:
    snippet = (subject or "").strip()[:300] or "your subject"
    return {
        "title": f"{snippet} — the {kind} you didn't know you needed",
        "description": (
            f"In this {kind}, we cover {snippet}.\n\n"
            "00:00 Intro\n01:00 Setup\n03:00 Walkthrough\n08:00 Wrap-up\n\n"
            "(Placeholder YouTube description — replace `service.py` with your own model.)"
        ),
        "thumbnail_prompt": f"Bold, contrasted YouTube thumbnail about {snippet}, vibrant colors",
        "tags": ["#" + kind, "#tutorial", "#youtube"],
    }
