"""Platform registry — pure metadata + router aggregation.

This file contains NO business logic. It exists only so each platform
package can `register(PlatformMeta(...), router)` itself, and so the
shared shell can list registered platforms and dispatch HTTP traffic
to each platform's APIRouter under `/api/<platform_id>/...`.

Platform authors: import `PlatformMeta` and `register` from this module
inside your own `app/platforms/<your_platform>/__init__.py`.
NEVER add backend logic here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Tuple

from fastapi import APIRouter


@dataclass(frozen=True)
class PlatformMeta:
    id: str
    label: str
    tagline: str
    icon: str
    accent: str
    owner: str


_PLATFORMS: List[Tuple[PlatformMeta, APIRouter]] = []


def register(meta: PlatformMeta, router: APIRouter) -> None:
    """Add a platform to the registry. Called once per platform at import time."""
    if not isinstance(meta, PlatformMeta):
        raise TypeError("meta must be a PlatformMeta")
    if not isinstance(router, APIRouter):
        raise TypeError("router must be a FastAPI APIRouter")

    for existing_meta, _ in _PLATFORMS:
        if existing_meta.id == meta.id:
            return

    _PLATFORMS.append((meta, router))


def all_platforms() -> List[PlatformMeta]:
    return [meta for meta, _ in _PLATFORMS]


def all_platforms_dict() -> List[dict]:
    return [asdict(meta) for meta, _ in _PLATFORMS]


def build_aggregate_router() -> APIRouter:
    """Return a single APIRouter that mounts each platform router at /api/<id>."""
    aggregate = APIRouter(prefix="/api")
    for meta, router in _PLATFORMS:
        aggregate.include_router(router, prefix=f"/{meta.id}", tags=[meta.id])
    return aggregate
