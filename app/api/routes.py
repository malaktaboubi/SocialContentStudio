"""Shell routes — pure plumbing, no business logic.

This file only:
- serves the SaaS landing page at `/`
- serves the dashboard shell at `/app`
- exposes the platform registry as JSON at `/api/platforms`
- serves each platform's panel.html / panel.js / panel.css
  files from their `app/platforms/<id>/` folder

Each platform's HTTP business endpoints are mounted at /api/<id>/...
by the aggregate router built in `app.platforms.registry`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core.config import PLATFORMS_DIR, STATIC_DIR
from ..platforms.registry import all_platforms_dict

router = APIRouter()

_PANEL_FILES = {
    "html": ("panel.html", "text/html"),
    "js": ("panel.js", "application/javascript"),
    "css": ("panel.css", "text/css"),
}


@router.get("/")
async def get_landing() -> FileResponse:
    return FileResponse(STATIC_DIR / "landing.html")


@router.get("/app")
async def get_dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.html")


@router.get("/api/platforms")
async def list_platforms() -> dict:
    items = []
    for meta in all_platforms_dict():
        pid = meta["id"]
        items.append(
            {
                **meta,
                "panel_html_url": f"/platforms/{pid}/panel.html",
                "panel_js_url": f"/platforms/{pid}/panel.js",
                "panel_css_url": f"/platforms/{pid}/panel.css",
                "api_prefix": f"/api/{pid}",
            }
        )
    return {"platforms": items}


def _safe_panel_path(platform_id: str, kind: str) -> Path:
    if kind not in _PANEL_FILES:
        raise HTTPException(status_code=404, detail="Unknown panel asset.")
    if not platform_id.isidentifier():
        raise HTTPException(status_code=400, detail="Invalid platform id.")

    filename, _ = _PANEL_FILES[kind]
    candidate = (PLATFORMS_DIR / platform_id / filename).resolve()

    try:
        candidate.relative_to(PLATFORMS_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path traversal blocked.") from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"{filename} not found for {platform_id}.")
    return candidate


@router.get("/platforms/{platform_id}/panel.html")
async def get_panel_html(platform_id: str) -> FileResponse:
    path = _safe_panel_path(platform_id, "html")
    return FileResponse(path, media_type="text/html")


@router.get("/platforms/{platform_id}/panel.js")
async def get_panel_js(platform_id: str) -> FileResponse:
    path = _safe_panel_path(platform_id, "js")
    return FileResponse(path, media_type="application/javascript")


@router.get("/platforms/{platform_id}/panel.css")
async def get_panel_css(platform_id: str) -> FileResponse:
    path = _safe_panel_path(platform_id, "css")
    return FileResponse(path, media_type="text/css")
