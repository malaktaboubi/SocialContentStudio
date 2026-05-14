# Instagram platform

Pattern Analytics — Instagram module.

## What you own
Everything in this folder. Nothing outside it.

## Files
- `__init__.py` — declares your APIRouter and registers `PlatformMeta`.
- `pipeline.py` — your model loading / API clients (empty stub).
- `service.py` — your business logic (placeholder echo logic).
- `schemas.py` — your Pydantic input/output models.
- `panel.html` — the UI shown in the Instagram tab.
- `panel.css` — styles, scoped under `.ig-panel`.
- `panel.js` — wires the form to your endpoints under `/api/instagram/...`.
- `requirements.txt` — Python deps you need.

## Workflow
1. Edit `panel.html` with the inputs you want (text, image upload, voice, anything).
2. Edit `panel.js` to call your endpoints.
3. Add endpoints in `__init__.py` (`@router.post("/...")`).
4. Implement them in `service.py` / `pipeline.py`.
5. Add deps to `requirements.txt` and `pip install -r app/platforms/instagram/requirements.txt`.
6. `uvicorn app.main:app --reload` and open `http://127.0.0.1:8000/app#instagram`.

## Rules
- Never import from another platform folder.
- Use only your `/api/instagram/...` endpoints from `panel.js`.
- Ask the maintainer if you need a shared helper — by default, you don't.
