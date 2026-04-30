from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..core.config import OUTPUT_DIR, STATIC_DIR
from ..services.content_service import process_audio_bytes

router = APIRouter()


@router.get("/")
async def get_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.post("/process")
async def process_audio(file: Annotated[UploadFile, File(...)]) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded filename.")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    try:
        return process_audio_bytes(file.filename, raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/images/{filename}")
async def get_image(filename: str) -> FileResponse:
    image_path = OUTPUT_DIR / filename
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")

    return FileResponse(path=image_path)
