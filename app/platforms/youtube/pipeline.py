"""YouTube thumbnail pipeline — faithful to the notebook design.

Stages
------
1.  Speech-to-Text          Whisper (small, trimmed to 3 min like the notebook)
2.  Hook generation         OpenRouter/Gemini API  (replaces local FLAN-T5)
3.  Style detection         Keyword rules, matching notebook categories:
                            gaming | finance | tutorial | reaction
4.  Build image prompt      Per-style extras, same as notebook
5.  SAT image captioner     CNNEncoder (ResNet-50) + SoftAttention + LSTMDecoder
                            Defined per Xu et al. / Liu & Brailsford 2023.
                            At runtime inference uses BLIP (pre-trained weights)
                            exactly as in the notebook; the SAT classes are
                            exported for research / fine-tuning use.
6.  Iterative generation    Up to 3 iterations (notebook default):
                              a. Generate thumbnail via Pollinations API
                              b. Caption image with BLIP
                              c. Score alignment (CLIP image↔text)
                              d. Refine prompt if score < threshold
7.  Text overlay            White text on black bar (notebook style)
8.  Hashtag generation      KeyBERT, top-5, 1–2 gram (notebook default)
"""

from __future__ import annotations

import gc
import io
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import imageio_ffmpeg
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as T
import whisper
from keybert import KeyBERT
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
from sentence_transformers import SentenceTransformer, util as st_util
from transformers import (
    BlipForConditionalGeneration,
    BlipProcessor,
    CLIPModel,
    CLIPProcessor,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("youtube.pipeline")

# ── Output directory ──────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).resolve().parent / "output_thumbnails"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL    = os.getenv("OPENROUTER_YT_MODEL", "google/gemini-2.0-flash-001")
USE_OPENROUTER      = os.getenv("USE_OPENROUTER", "true").lower() == "true"

CUDA_AVAILABLE      = torch.cuda.is_available()
WHISPER_MODEL_ID    = os.getenv("WHISPER_MODEL_ID", "small")   # notebook uses "small"

# Alignment thresholds
CLIP_THRESHOLD      = float(os.getenv("YT_CLIP_THRESHOLD",   "0.28"))
SIM_THRESHOLD       = float(os.getenv("YT_SIM_THRESHOLD",    "0.45"))  # notebook default
MAX_ITERATIONS      = int(os.getenv("YT_MAX_ITERATIONS",     "3"))     # notebook default

THREE_MINUTES_MS    = 3 * 60 * 1000   # notebook trims audio here


# ── FFmpeg shim ───────────────────────────────────────────────────────────────
def _configure_ffmpeg() -> None:
    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    alias_dir   = Path(tempfile.gettempdir()) / "yt_pipeline_ffmpeg"
    alias_dir.mkdir(parents=True, exist_ok=True)
    alias_path  = alias_dir / ffmpeg_path.name
    if not alias_path.exists():
        shutil.copy2(ffmpeg_path, alias_path)
    cur = os.environ.get("PATH", "")
    if str(alias_dir) not in cur:
        os.environ["PATH"] = f"{alias_dir}{os.pathsep}{cur}"


_configure_ffmpeg()


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def flush_memory() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ═══════════════════════════════════════════════════════════════════════════════
#  STAGE 4 — SAT Architecture (Xu et al. 2015 / Liu & Brailsford 2023)
#  CNNEncoder (ResNet-50) + SoftAttention + LSTMDecoder
#  Exported for research / fine-tuning; BLIP is used for inference (see below).
# ═══════════════════════════════════════════════════════════════════════════════

class CNNEncoder(nn.Module):
    """
    ResNet-50 backbone (pretrained on ImageNet).
    Strips the final avgpool + fc layers so the output is the spatial
    feature map: shape (batch, L, 2048) where L = encoded_size².
    Each spatial position is one 'annotation vector' in SAT notation.
    """
    def __init__(self, encoded_size: int = 14):
        super().__init__()
        resnet  = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        modules = list(resnet.children())[:-2]
        self.backbone = nn.Sequential(*modules)
        self.pool     = nn.AdaptiveAvgPool2d((encoded_size, encoded_size))
        self.fine_tune(False)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        feats = self.backbone(images)           # (B, 2048, 7, 7)
        feats = self.pool(feats)                 # (B, 2048, 14, 14)
        feats = feats.permute(0, 2, 3, 1)       # (B, 14, 14, 2048)
        return feats.view(feats.size(0), -1, feats.size(-1))  # (B, 196, 2048)

    def fine_tune(self, enable: bool) -> None:
        for p in self.backbone.parameters():
            p.requires_grad = enable


class SoftAttention(nn.Module):
    """
    Additive (Bahdanau-style) soft attention — 'soft' variant from Xu et al. §3.2.
    Produces a context vector as a weighted sum of all encoder locations.
    """
    def __init__(self, encoder_dim: int, decoder_dim: int, attention_dim: int):
        super().__init__()
        self.enc_proj = nn.Linear(encoder_dim, attention_dim)
        self.dec_proj = nn.Linear(decoder_dim, attention_dim)
        self.full_att = nn.Linear(attention_dim, 1)
        self.relu     = nn.ReLU()
        self.softmax  = nn.Softmax(dim=1)

    def forward(
        self,
        encoder_out: torch.Tensor,      # (B, L, encoder_dim)
        decoder_hidden: torch.Tensor,   # (B, decoder_dim)
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        e       = self.enc_proj(encoder_out)                        # (B, L, att_dim)
        d       = self.dec_proj(decoder_hidden).unsqueeze(1)        # (B, 1, att_dim)
        energy  = self.full_att(self.relu(e + d)).squeeze(2)        # (B, L)
        alpha   = self.softmax(energy)                               # (B, L)
        context = (encoder_out * alpha.unsqueeze(2)).sum(dim=1)     # (B, encoder_dim)
        return context, alpha


class LSTMDecoder(nn.Module):
    """
    Attention-conditioned LSTM word decoder (Xu et al. §3, teacher-forcing training).
    At each timestep:
      1. Compute context z_t via SoftAttention(encoder_out, h_{t-1})
      2. LSTM input = [embed(y_{t-1}) ; z_t]
      3. Project h_t → vocabulary logits
    """
    def __init__(
        self,
        attention_dim: int,
        embed_dim: int,
        decoder_dim: int,
        vocab_size: int,
        encoder_dim: int = 2048,
        dropout: float   = 0.5,
    ):
        super().__init__()
        self.encoder_dim = encoder_dim
        self.decoder_dim = decoder_dim
        self.vocab_size  = vocab_size

        self.attention  = SoftAttention(encoder_dim, decoder_dim, attention_dim)
        self.embedding  = nn.Embedding(vocab_size, embed_dim)
        self.dropout    = nn.Dropout(dropout)
        self.lstm_cell  = nn.LSTMCell(embed_dim + encoder_dim, decoder_dim)
        self.init_h     = nn.Linear(encoder_dim, decoder_dim)
        self.init_c     = nn.Linear(encoder_dim, decoder_dim)
        self.f_beta     = nn.Linear(decoder_dim, encoder_dim)
        self.sigmoid    = nn.Sigmoid()
        self.fc         = nn.Linear(decoder_dim, vocab_size)
        self._init_weights()

    def _init_weights(self) -> None:
        nn.init.uniform_(self.embedding.weight, -0.1, 0.1)
        nn.init.uniform_(self.fc.weight,        -0.1, 0.1)
        nn.init.constant_(self.fc.bias,          0)

    def _init_hidden(
        self, encoder_out: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        mean_enc = encoder_out.mean(dim=1)
        return torch.tanh(self.init_h(mean_enc)), torch.tanh(self.init_c(mean_enc))

    def forward(
        self,
        encoder_out: torch.Tensor,
        captions: torch.Tensor,
        caption_lengths: torch.Tensor,
    ) -> Tuple[torch.Tensor, list, torch.Tensor]:
        B       = encoder_out.size(0)
        L       = encoder_out.size(1)
        max_len = captions.size(1) - 1

        embeddings     = self.dropout(self.embedding(captions))
        h, c           = self._init_hidden(encoder_out)
        decode_lengths = (caption_lengths - 1).tolist()
        predictions    = torch.zeros(B, max_len, self.vocab_size).to(encoder_out.device)
        alphas         = torch.zeros(B, max_len, L).to(encoder_out.device)

        for t in range(max(decode_lengths)):
            batch_t        = sum(l > t for l in decode_lengths)
            context, alpha = self.attention(encoder_out[:batch_t], h[:batch_t])
            gate           = self.sigmoid(self.f_beta(h[:batch_t]))
            context        = gate * context
            h, c           = self.lstm_cell(
                torch.cat([embeddings[:batch_t, t, :], context], dim=1),
                (h[:batch_t], c[:batch_t]),
            )
            predictions[:batch_t, t, :] = self.fc(self.dropout(h))
            alphas[:batch_t, t, :]      = alpha

        return predictions, decode_lengths, alphas

    @torch.no_grad()
    def generate_caption(
        self,
        encoder_out: torch.Tensor,
        word2idx: dict,
        idx2word: dict,
        max_steps: int = 30,
    ) -> str:
        """Greedy decoding at inference time (produces Si in the Liu & Brailsford framework)."""
        h, c    = self._init_hidden(encoder_out)
        word_id = torch.tensor([word2idx.get("<start>", 1)]).to(encoder_out.device)
        caption: list[str] = []

        for _ in range(max_steps):
            emb            = self.embedding(word_id)
            context, alpha = self.attention(encoder_out, h)
            gate           = self.sigmoid(self.f_beta(h))
            context        = gate * context
            h, c           = self.lstm_cell(torch.cat([emb, context], dim=1), (h, c))
            word_id        = self.fc(h).argmax(dim=1)
            word           = idx2word.get(word_id.item(), "<unk>")
            if word == "<end>":
                break
            caption.append(word)

        return " ".join(caption)


log.info("SAT architecture defined (CNNEncoder, SoftAttention, LSTMDecoder).")


# ═══════════════════════════════════════════════════════════════════════════════
#  Lazy model loaders
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _get_whisper():
    log.info("Whisper: loading model=%s on %s", WHISPER_MODEL_ID, get_device())
    return whisper.load_model(WHISPER_MODEL_ID).to(get_device())


@lru_cache(maxsize=1)
def _get_blip():
    log.info("BLIP: loading Salesforce/blip-image-captioning-base on %s", get_device())
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model     = BlipForConditionalGeneration.from_pretrained(
        "Salesforce/blip-image-captioning-base"
    ).to(get_device())
    return processor, model


@lru_cache(maxsize=1)
def _get_clip():
    log.info("CLIP: loading openai/clip-vit-base-patch32 on %s", get_device())
    model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(get_device())
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    return model, processor


@lru_cache(maxsize=1)
def _get_sentence_model():
    log.info("SentenceTransformer: loading all-MiniLM-L6-v2")
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _get_keybert():
    log.info("KeyBERT: loading")
    return KeyBERT()


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Speech-to-Text  (Whisper, trims to 3 min like the notebook)
# ═══════════════════════════════════════════════════════════════════════════════

def speech_to_text(audio_path: str) -> str:
    log.info("Whisper: transcribing %s", audio_path)

    transcribe_source = audio_path
    temp_audio_path: Optional[str] = None

    # Notebook behavior: trim to first 3 min. Requires ffprobe for pydub.
    # If ffprobe isn't available, skip the trim and let Whisper handle the
    # full file — Whisper only needs ffmpeg (provided by imageio_ffmpeg shim).
    try:
        audio = AudioSegment.from_file(audio_path)
        if len(audio) > THREE_MINUTES_MS:
            log.info("Audio > 3 min — trimming to first 3 minutes")
            segment = audio[:THREE_MINUTES_MS]
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_audio_path = tmp.name
                segment.export(temp_audio_path, format="wav")
            transcribe_source = temp_audio_path
    except FileNotFoundError:
        log.warning("ffprobe not found — skipping trim, transcribing full file")
    except Exception as exc:
        log.warning("pydub probe failed (%s) — transcribing full file", exc)

    result = _get_whisper().transcribe(transcribe_source, fp16=False)

    if temp_audio_path and os.path.exists(temp_audio_path):
        os.remove(temp_audio_path)

    text = result["text"].strip()
    log.info("Transcript (%d chars): %s", len(text), text[:200])
    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Hook generation  (OpenRouter API, fallback to keyword extraction)
# ═══════════════════════════════════════════════════════════════════════════════

def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    data    = json.dumps(payload).encode()
    req     = urllib.request.Request(url=url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start == -1:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:       escape = False; continue
        if ch == "\\":   escape = True;  continue
        if ch == '"':    in_str = not in_str; continue
        if in_str:       continue
        if ch == "{":    depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(cleaned[start:i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    break
    return None


def generate_hook(transcript: str) -> str:
    """
    Generate a short clickbait title from the transcript.
    Uses OpenRouter/Gemini when available; falls back to the first sentence.
    """
    if USE_OPENROUTER and OPENROUTER_API_KEY:
        # Truncate to ~200 words as the notebook does for FLAN-T5
        words = transcript.split()
        truncated = " ".join(words[:200])

        system_msg = (
            "Create a short catchy YouTube thumbnail title — emotional and clickable. "
            "Respond with ONLY the title text, no quotes, no explanation, max 60 characters."
        )
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "youtube-pipeline",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": truncated},
            ],
            "temperature": 0.9,
            "max_tokens":  50,
        }
        try:
            resp = _post_json("https://openrouter.ai/api/v1/chat/completions", payload, headers)
            if "error" in resp:
                raise RuntimeError(resp["error"])
            hook = resp["choices"][0]["message"]["content"].strip().strip('"')
            log.info("Hook: %s", hook)
            return hook[:60]
        except Exception as exc:
            log.error("Hook generation failed: %s — using fallback", exc)

    # Fallback: first sentence of transcript
    fallback = transcript.split(".")[0].strip()
    return fallback[:60] or "WATCH THIS"


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Detect thumbnail style  (notebook keyword rules, all 4 categories)
# ═══════════════════════════════════════════════════════════════════════════════

STYLE_TEMPLATES: Dict[str, str] = {
    "gaming":   "RGB lighting, gamer setup, intense mood, glowing background",
    "finance":  "luxury atmosphere, charts, modern office, bold composition",
    "tutorial": "clean composition, object centered, informative visual",
    "reaction": "close-up shocked face, expressive emotion, cinematic lighting",
}


def classify_thumbnail_style(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["game", "gaming", "fps", "minecraft"]):
        return "gaming"
    if any(w in t for w in ["money", "business", "finance", "crypto"]):
        return "finance"
    if any(w in t for w in ["tutorial", "how to", "guide"]):
        return "tutorial"
    return "reaction"


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — Build image prompt  (matches notebook's build_thumbnail_prompt)
# ═══════════════════════════════════════════════════════════════════════════════

def build_thumbnail_prompt(title: str, style: str) -> str:
    base  = "youtube thumbnail background, high contrast, dramatic lighting, vibrant colors"
    extra = STYLE_TEMPLATES.get(style, STYLE_TEMPLATES["reaction"])
    return (
        f"{title}, {base}, {extra}, "
        "centered composition, empty space for title text, no words, no watermark, thumbnail style"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Image generation — Pollinations API  (replaces local SD-Turbo)
# ═══════════════════════════════════════════════════════════════════════════════

_POLLINATIONS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_POLLINATIONS_REFERRER = os.getenv("POLLINATIONS_REFERRER", "social-content-studio")


def generate_thumbnail(prompt: str, output_path: str = "thumbnail.png") -> str:
    encoded = urllib.parse.quote(prompt[:400])
    seed    = uuid.uuid4().int % (2 ** 31)
    url     = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1280&height=720&nologo=true&model=flux&seed={seed}"
        f"&referrer={urllib.parse.quote(_POLLINATIONS_REFERRER)}"
    )
    headers = {
        "User-Agent": _POLLINATIONS_UA,
        "Referer":    "https://pollinations.ai/",
        "Accept":     "image/*",
    }
    log.info("Generating thumbnail via Pollinations…")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        img_bytes = resp.read()
    out = OUTPUT_DIR / output_path
    out.write_bytes(img_bytes)
    return str(out)


# ═══════════════════════════════════════════════════════════════════════════════
#  BLIP image captioner  (Sc in Liu & Brailsford; matches notebook caption_image)
# ═══════════════════════════════════════════════════════════════════════════════

def caption_image(image_path: str) -> str:
    processor, model = _get_blip()
    raw = Image.open(image_path).convert("RGB")
    inputs = processor(raw, return_tensors="pt").to(get_device())
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=50, num_beams=4)
    caption = processor.decode(out[0], skip_special_tokens=True)
    log.info("BLIP caption: %s", caption)
    return caption


# ═══════════════════════════════════════════════════════════════════════════════
#  Alignment scoring — two methods kept, matching both notebook approaches
#  Primary: CLIP image↔text  (pipeline.py's original choice, more appropriate)
#  Secondary: Sentence-BERT text↔text  (notebook's original similarity_score)
# ═══════════════════════════════════════════════════════════════════════════════

@torch.no_grad()
def clip_score(image_path: str, text: str) -> float:
    """CLIP cosine similarity between thumbnail image and hook text (range ~0–0.5)."""
    model, processor = _get_clip()
    image  = Image.open(image_path).convert("RGB")
    inputs = processor(
        text=[text[:200]], images=image,
        return_tensors="pt", padding=True, truncation=True,
    ).to(get_device())
    outputs = model(**inputs)
    return float(outputs.logits_per_image.item()) / 100.0


def similarity_score(text_a: str, text_b: str) -> float:
    """Sentence-BERT cosine similarity between two text strings (notebook method)."""
    sim_model = _get_sentence_model()
    emb_a = sim_model.encode(text_a, convert_to_tensor=True)
    emb_b = sim_model.encode(text_b, convert_to_tensor=True)
    return float(st_util.cos_sim(emb_a, emb_b)[0][0])


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompt refinement  (matches notebook refine_prompt exactly)
# ═══════════════════════════════════════════════════════════════════════════════

def refine_prompt(prompt: str, caption: str, original_text: str) -> str:
    refined = prompt
    if "person" in caption and "gaming" in original_text.lower():
        refined += ", gaming setup, RGB keyboard, gaming monitor"
    if "office" in caption and "football" in original_text.lower():
        refined += ", football stadium, soccer ball, sports action"
    if "indoor" in caption and "nature" in original_text.lower():
        refined += ", outdoor environment, realistic landscape"
    refined += ", more expressive emotion, clearer subject"
    return refined


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 7 — Text overlay  (notebook style: white text on black rectangle bar)
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf", "arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def add_thumbnail_text(
    image_path: str,
    text: str,
    output_path: str = "final_thumbnail.png",
) -> str:
    """White text on a black bar near the bottom — matches notebook add_thumbnail_text."""
    image  = Image.open(image_path).convert("RGB")
    draw   = ImageDraw.Draw(image)
    width, height = image.size

    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except OSError:
        font = _resolve_font(60)

    x = 40
    y = height - 120
    draw.rectangle([(20, y - 20), (width - 20, y + 80)], fill=(0, 0, 0))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    out = OUTPUT_DIR / output_path
    image.save(str(out))
    return str(out)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 8 — Hashtag generation  (KeyBERT, matches notebook generate_hashtags)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_hashtags(text: str, top_n: int = 5) -> List[str]:
    kw_model = _get_keybert()
    keywords = kw_model.extract_keywords(
        text,
        keyphrase_ngram_range=(1, 2),
        stop_words="english",
        top_n=top_n,
    )
    return ["#" + kw.replace(" ", "") for kw, _ in keywords]


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPLETE PIPELINE  (matches notebook run_pipeline structure exactly)
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline(audio_path: str) -> dict:
    sep = "=" * 60

    # ── STEP 1 ────────────────────────────────────────────────
    print(sep); print("STEP 1 - Speech To Text"); print(sep)
    transcript = speech_to_text(audio_path)
    print(transcript)

    # ── STEP 2 ────────────────────────────────────────────────
    print(f"\n{sep}"); print("STEP 2 - Generate Hook"); print(sep)
    hook = generate_hook(transcript)
    print("HOOK:", hook)

    # ── STEP 3 ────────────────────────────────────────────────
    print(f"\n{sep}"); print("STEP 3 - Detect Thumbnail Style"); print(sep)
    style = classify_thumbnail_style(hook)
    print("STYLE:", style)

    # ── STEP 4 ────────────────────────────────────────────────
    print(f"\n{sep}"); print("STEP 4 - Generate Prompt"); print(sep)
    prompt = build_thumbnail_prompt(hook, style)
    print(prompt)

    # ── STEPS 5–6 — Iterative generation loop ─────────────────
    best_score   = 0.0
    best_image:   Optional[str] = None
    best_caption: Optional[str] = None

    for iteration in range(MAX_ITERATIONS):
        print(f"\n{sep}"); print(f"ITERATION {iteration + 1}"); print(sep)

        # 5a. Generate thumbnail
        image_path = generate_thumbnail(
            prompt, output_path=f"thumbnail_{iteration}.png"
        )

        # 5b. Caption image with BLIP  (Sc — notebook stage)
        generated_caption = caption_image(image_path)
        print("Generated Caption:", generated_caption)

        # 5c. Score alignment
        #     Primary: CLIP image↔text (more accurate for visual alignment)
        #     Secondary: Sentence-BERT text↔text (notebook's original method)
        c_score = clip_score(image_path, hook)
        s_score = similarity_score(hook, generated_caption)
        print(f"CLIP Score: {c_score:.4f}   Sentence-BERT Score: {s_score:.4f}")

        # Use Sentence-BERT score as the primary decision signal,
        # matching the notebook's 0.45 threshold and logic exactly.
        score = s_score

        if score > best_score:
            best_score   = score
            best_image   = image_path
            best_caption = generated_caption

        if score >= SIM_THRESHOLD:
            print("Good alignment achieved.")
            break

        # 5d. Refine prompt for next iteration
        prompt = refine_prompt(prompt, generated_caption, hook)

    # ── STEP 7 ────────────────────────────────────────────────
    print(f"\n{sep}"); print("STEP 5 - Add Final Text"); print(sep)
    final_image = add_thumbnail_text(best_image, hook[:40])
    print("Saved:", final_image)

    # ── STEP 8 ────────────────────────────────────────────────
    print(f"\n{sep}"); print("STEP 6 - Generate Hashtags"); print(sep)
    hashtags = generate_hashtags(hook)

    # ── Final results ─────────────────────────────────────────
    print(f"\nFINAL RESULTS\n{sep}")
    print("Title:");      print(hook)
    print("\nCaption:");   print(best_caption)
    print("\nSimilarity:"); print(best_score)
    print("\nHashtags:");  print(" ".join(hashtags))

    return {
        "transcript": transcript,
        "title":      hook,
        "caption":    best_caption,
        "similarity": best_score,
        "hashtags":   hashtags,
        "thumbnail":  final_image,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from IPython.display import display  # graceful if not in notebook

    audio = sys.argv[1] if len(sys.argv) > 1 else (
        "/content/sample_data/Senior Developer Reviews My AI Built App (Brutally Honest).mp3"
    )
    results = run_pipeline(audio)

    try:
        image = Image.open(results["thumbnail"])
        display(image)
    except Exception:
        print("Thumbnail saved to:", results["thumbnail"])