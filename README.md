# Social Content Studio · Pattern Analytics

> Multi-platform social content generation. Each platform is a self-contained module; the app provides the shared shell.

```
http://127.0.0.1:8000/        ← SaaS landing page
http://127.0.0.1:8000/app     ← dashboard (one tab per platform)
http://127.0.0.1:8000/app#reddit
http://127.0.0.1:8000/app#instagram
http://127.0.0.1:8000/app#twitter
http://127.0.0.1:8000/app#linkedin
http://127.0.0.1:8000/app#youtube
```

## How the project is split

**Pattern Analytics** owns the **shell** (landing page + dashboard tabs). Every other line of code
lives inside a **platform folder** — one folder per social network, with no shared backend between them.

```
app/
├── main.py                    [shared infra — do not edit]
├── api/routes.py              [shared infra — only serves landing/app/platforms metadata]
├── core/config.py             [shared infra — paths only]
├── static/                    [shared UI — landing page + dashboard shell]
└── platforms/
    ├── registry.py            [shared infra — pure metadata + router aggregation]
    ├── __init__.py            [shared infra — auto-loads every subpackage]
    │
    ├── reddit/
    │   ├── pipeline.py
    │   ├── service.py
    │   ├── schemas.py
    │   ├── __init__.py        ← exposes the FastAPI APIRouter
    │   ├── panel.html / .css / .js
    │   ├── requirements.txt
    │   └── README.md
    ├── instagram/
    ├── twitter/
    ├── linkedin/
    └── youtube/
```

There is **no shared backend code**. No `pipeline.py` at the app level, no shared
schemas, no shared services. If two modules need Whisper, they each install
and load it inside their own folder.

## Run it

```bash
python -m venv .venv
.\.venv\Scripts\activate                    # Windows
# source .venv/bin/activate                 # macOS / Linux

pip install -r requirements.txt             # shell deps only (fastapi, uvicorn)

# install your own platform deps:
pip install -r app/platforms/reddit/requirements.txt

# (optional) install everyone's deps:
# Windows PowerShell:
#   Get-ChildItem app/platforms -Filter requirements.txt -Recurse | ForEach-Object { pip install -r $_.FullName }
# bash:
#   for f in app/platforms/*/requirements.txt; do pip install -r "$f"; done

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — landing page lists every registered platform automatically.

## Adding your work (the rule)

> **Edit only `app/platforms/<your_id>/`. Never touch anything else.**

1. Pick your folder (one of `reddit`, `instagram`, `twitter`, `linkedin`, `youtube`).
2. Open `panel.html` and design any input form you want — text, voice, file upload, dropdowns, sliders.
3. Open `panel.js` and call your endpoints under `/api/<your_id>/...`.
4. Add endpoints in `__init__.py` (`@router.post("/...")`) and implement them in `service.py` / `pipeline.py`.
5. Add Python deps to `app/platforms/<your_id>/requirements.txt` and `pip install -r` them.
6. `uvicorn app.main:app --reload` and open `http://127.0.0.1:8000/app#<your_id>`.

Hard rules:
- Never `from app.pipeline import ...` (it doesn't exist).
- Never import from another platform folder.
- Don't touch `app/main.py`, `app/api/routes.py`, `app/core/`, `app/static/`, or `app/platforms/registry.py`.

See `app/platforms/README.md` for the full contract.

## Environment variables

Each platform decides its own env vars. The shell does not require any. As an example,
the Reddit platform reads:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
USE_OPENROUTER=true
HF_TOKEN=hf_...
HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell
USE_POLLINATIONS_IMAGE=true
WHISPER_MODEL_ID=tiny
```

Put them in a single root-level `.env` — `app/main.py` loads it once at startup.

## Architecture at a glance

```
Browser → /                 → landing.html (auto-lists registered platforms)
       → /app               → app.html (dashboard shell)
       → /api/platforms     → JSON of every registered PlatformMeta
       → /platforms/<id>/panel.{html,js,css}  → platform panel assets
       → /api/<id>/...      → platform APIRouter (own endpoints)
```

When the FastAPI app boots, `app/platforms/__init__.py` imports every subpackage,
each of which calls `register(PlatformMeta(...), router)`. The shell discovers all
registered platforms via `GET /api/platforms` and loads each tab on demand.
