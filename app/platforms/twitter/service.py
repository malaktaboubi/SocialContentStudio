"""Twitter business logic. Replace this stub with your own."""

from __future__ import annotations


def generate_post(topic: str, tone: str) -> dict:
    snippet = (topic or "").strip()[:260] or "your topic"
    return {
        "post": (
            f"{snippet}\n\n"
            f"(Placeholder {tone} tweet — replace `service.py` with your own model.)"
        ),
        "tone": tone,
    }
