"""LinkedIn business logic. Replace this stub with your own."""

from __future__ import annotations


def generate_post(topic: str, role: str) -> dict:
    snippet = (topic or "").strip()[:300] or "your topic"
    return {
        "post": (
            f"As a {role}, here's a quick lesson I learned about {snippet}.\n\n"
            "1. Observation\n2. Insight\n3. Takeaway\n\n"
            "(Placeholder LinkedIn post — replace `service.py` with your own model.)"
        ),
        "role": role,
    }
