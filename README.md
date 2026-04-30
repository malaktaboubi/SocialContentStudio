# Voice to Reddit FastAPI Project

Records voice -> transcribes -> generates a Reddit-style post + AI image, using **only free APIs**.

## Architecture
- `app/main.py` — app factory, loads `.env`
- `app/api/routes.py` — HTTP endpoints (`/`, `/process`, `/images/{filename}`)
- `app/services/content_service.py` — orchestrates the voice-to-post flow
- `app/pipeline.py` — Whisper STT + OpenRouter text + image provider chain
- `app/core/config.py` — paths
- `app/static/` — frontend (HTML/CSS/JS)

## Free providers used
| Stage | Provider | Cost | Notes |
|---|---|---|---|
| Speech-to-text | Whisper `tiny` (local) | Free | 72MB, runs on CPU |
| Reddit text | OpenRouter `nvidia/nemotron-3-super-120b-a12b:free` | Free | Needs OpenRouter API key |
| Image | HuggingFace Inference (FLUX.1-schnell) | Free | Needs HF token |
| Image fallback | Pollinations.ai | Free | No auth needed, may rate-limit |

## Setup

1. Create venv and install deps:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   ```

2. Get free API keys:
   - **OpenRouter**: https://openrouter.ai/keys (free tier)
   - **HuggingFace** (recommended for reliable images): https://huggingface.co/settings/tokens (read access is enough)

3. Fill in `.env`:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
   USE_OPENROUTER=true

   HF_TOKEN=hf_...
   HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell

   USE_POLLINATIONS_IMAGE=true
   WHISPER_MODEL_ID=tiny
   ```

4. Run:
   ```bash
   uvicorn app.main:app --reload
   ```

5. Open `http://127.0.0.1:8000` and click record.

## Notes
- If `HF_TOKEN` is set, image generation uses HuggingFace first (reliable).
- Pollinations is a no-auth fallback but may return 429 if hit too often.
- All generated images are saved under `output_images/` and served via `/images/{filename}`.
- The app bundles FFmpeg through `imageio-ffmpeg` for Whisper.
- Manual Reddit fallback is built in: use `Copy Post` and `Open Reddit Submit` to publish without API access.
