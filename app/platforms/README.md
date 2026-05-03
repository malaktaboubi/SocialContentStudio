# Platforms — Pattern Analytics plugin contract

Each platform module owns exactly **one folder** in here:

```
app/platforms/
├── reddit/
├── instagram/
├── twitter/
├── linkedin/
└── youtube/
```

You edit only your folder. Never import from another platform folder. Never edit
`registry.py`, `__init__.py`, or anything outside `app/platforms/`.

## What each folder must contain

| File | Purpose |
|---|---|
| `__init__.py` | Build a FastAPI `APIRouter` and call `register(PlatformMeta(...), router)`. |
| `pipeline.py` | Your model loading / API clients. May be empty. |
| `service.py`  | Your business logic. Called from `__init__.py` endpoints. |
| `schemas.py`  | Your Pydantic request/response models. |
| `panel.html`  | The HTML for your tab. Free design, any inputs. |
| `panel.css`   | Styles. **Scope all selectors under `.your-prefix-panel`** so you don't break siblings. |
| `panel.js`    | Wires the form to your endpoints. Loaded as an ES module. |
| `requirements.txt` | Your Python deps. |
| `README.md`   | Anything you want your future self / the team to know. |

## Auto-mounting

When the app starts, `app/platforms/__init__.py` imports every subpackage. That triggers
your `register(...)` call, which mounts your `router` under `/api/<your_id>/...`.

The shell (`app/static/app.html` + `shell.js`) calls `GET /api/platforms` to list every
registered platform and renders one tab per result. Your `panel.html` / `panel.css` /
`panel.js` are loaded into the active tab.

## Hard rules

1. **No shared backend code.** Don't `from app.pipeline import ...` — it doesn't exist.
2. **No imports across platforms.** Don't `from ..reddit import ...`.
3. **Stay under your own URL prefix.** All your endpoints live under `/api/<your_id>/`.
4. **Scope your CSS.** Wrap your panel in `<div class="<your-prefix>-panel">` and prefix all
   selectors with that class. The dashboard does not provide CSS resets for your panel.
5. **Don't write to `app/static/`.** Your assets stay in your own folder.

## How to run

```bash
pip install -r requirements.txt                       # shell deps (fastapi, uvicorn)
pip install -r app/platforms/<your_id>/requirements.txt  # your own deps
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/app#<your_id>
```
