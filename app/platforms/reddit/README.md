# Reddit platform

Pattern Analytics — Reddit module.

Voice → transcript (Whisper) → Reddit title/body + image prompt (OpenRouter) → AI image (HuggingFace / Pollinations).

## Files in this folder (all yours)
- `__init__.py` — registers the platform and exposes the FastAPI router.
- `pipeline.py` — Whisper, OpenRouter, image providers.
- `service.py` — orchestrates the full flow + streaming events.
- `schemas.py` — Pydantic request/response models.
- `panel.html` — UI (recorder, tone selector, post editor, image preview, history).
- `panel.css` — styles, scoped under `.reddit-panel`.
- `panel.js` — wires the UI to the endpoints.
- `requirements.txt` — Python deps you need.
- `output_images/` — auto-created; serves AI images via `/api/reddit/images/{filename}`.

## HTTP endpoints (mounted automatically under /api/reddit)
- `GET  /api/reddit/tones`
- `POST /api/reddit/process`
- `POST /api/reddit/process-stream`
- `POST /api/reddit/regenerate-text`
- `POST /api/reddit/regenerate-image`
- `GET  /api/reddit/images/{filename}`

## Env vars used
```
OPENROUTER_API_KEY=
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
USE_OPENROUTER=true
HF_TOKEN=
HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell
USE_POLLINATIONS_IMAGE=true
WHISPER_MODEL_ID=tiny
```

## Run
```
pip install -r app/platforms/reddit/requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/app#reddit
```
