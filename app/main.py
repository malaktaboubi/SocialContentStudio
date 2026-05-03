"""FastAPI app factory.

This file is shared infrastructure — it does NOT contain business logic.
It loads `.env`, builds the FastAPI app, mounts the shell routes, and
mounts every registered platform's router under /api/<id>/.

Each platform author edits ONLY their own folder under app/platforms/<id>/.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip()


_load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import router as shell_router
from .core.config import STATIC_DIR
from .platforms import registry as _registry  # noqa: F401  -- triggers platform auto-discovery


def create_app() -> FastAPI:
    app_instance = FastAPI(title="Social Content Studio · Pattern Analytics")
    app_instance.include_router(shell_router)
    app_instance.include_router(_registry.build_aggregate_router())
    app_instance.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app_instance


app = create_app()
