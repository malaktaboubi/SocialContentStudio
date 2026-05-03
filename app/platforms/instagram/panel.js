// Instagram panel — voice OR image → caption + hashtags + AI image.
// All endpoints under /api/instagram/.

const API = "/api/instagram";

// ── State ─────────────────────────────────────────────────────────────────────
let mediaRecorder, audioChunks = [], isRecording = false, recordingStartTime = 0, timerInterval;
let liveRecognition = null, liveCaptionsActive = false, liveCaptionFinal = "";
let lastTranscript = "";
let currentMode = "voice"; // "voice" | "image"
let uploadedFile = null;   // File object from image upload

const ARC_CIRC = 408;
const MAX_REC_SECS = 120;
const VOICE_STAGE_ICONS = { 1: "🎙", 2: "✍️", 3: "🎨" };
const IMAGE_STAGE_ICONS = { 1: "🖼", 2: "✍️" };

const HISTORY_KEY = "voiceInstagramRuns_v1";
const MAX_HISTORY = 8;
let activeHistoryId = null;

// ── Mode switcher ──────────────────────────────────────────────────────────────

function initModeSwitcher() {
    document.getElementById("igModeVoiceBtn")?.addEventListener("click", () => switchMode("voice"));
    document.getElementById("igModeImageBtn")?.addEventListener("click", () => switchMode("image"));
}

function switchMode(mode) {
    currentMode = mode;
    const voiceBtn = document.getElementById("igModeVoiceBtn");
    const imageBtn = document.getElementById("igModeImageBtn");
    const voicePanel = document.getElementById("igVoicePanel");
    const imagePanel = document.getElementById("igImagePanel");

    if (mode === "voice") {
        voiceBtn?.classList.add("active");
        voiceBtn?.setAttribute("aria-selected", "true");
        imageBtn?.classList.remove("active");
        imageBtn?.setAttribute("aria-selected", "false");
        if (voicePanel) voicePanel.style.display = "";
        if (imagePanel) imagePanel.style.display = "none";
    } else {
        imageBtn?.classList.add("active");
        imageBtn?.setAttribute("aria-selected", "true");
        voiceBtn?.classList.remove("active");
        voiceBtn?.setAttribute("aria-selected", "false");
        if (imagePanel) imagePanel.style.display = "";
        if (voicePanel) voicePanel.style.display = "none";
    }
}

// ── Image upload ───────────────────────────────────────────────────────────────

function initImageUpload() {
    const dropzone = document.getElementById("igDropzone");
    const fileInput = document.getElementById("igFileInput");
    const preview = document.getElementById("igUploadPreview");
    const genBtn = document.getElementById("igGenerateFromImageBtn");

    if (!dropzone || !fileInput) return;

    // Click to open file picker
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
    });

    // Drag & drop
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("drag-over");
        const file = e.dataTransfer?.files?.[0];
        if (file) handleImageFile(file);
    });

    // File input change
    fileInput.addEventListener("change", () => {
        const file = fileInput.files?.[0];
        if (file) handleImageFile(file);
        fileInput.value = ""; // reset so same file can be re-selected
    });

    // Generate button
    genBtn?.addEventListener("click", () => { void generateFromImage(); });
}

function handleImageFile(file) {
    const allowed = ["image/jpeg", "image/png", "image/webp"];
    if (!allowed.includes(file.type)) {
        setUploadStatus("error", "Invalid file", "Please upload a JPG, PNG, or WebP image.", "");
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        setUploadStatus("error", "File too large", "Please upload an image under 10 MB.", "");
        return;
    }

    uploadedFile = file;
    clearUploadStatus();

    const preview = document.getElementById("igUploadPreview");
    const inner = document.getElementById("igDropzoneInner");
    const genBtn = document.getElementById("igGenerateFromImageBtn");

    const reader = new FileReader();
    reader.onload = (e) => {
        if (preview) {
            preview.src = e.target.result;
            preview.style.display = "block";
        }
        if (inner) inner.style.display = "none";
        if (genBtn) genBtn.disabled = false;
        setUploadStatus("info", "Ready", `${file.name} (${(file.size / 1024).toFixed(0)} KB)`, "Click 'Generate Caption' to analyse this image.");
    };
    reader.readAsDataURL(file);
}

async function generateFromImage() {
    if (!uploadedFile) {
        setUploadStatus("error", "No image", "Please upload an image first.", "");
        return;
    }

    const processingCard = document.getElementById("igProcessingCard");
    const postCard = document.getElementById("igPostCard");
    const genBtn = document.getElementById("igGenerateFromImageBtn");

    if (genBtn) genBtn.disabled = true;

    // Show image-mode stages, hide voice stages
    const voiceStages = document.getElementById("igVoiceStages");
    const imageStages = document.getElementById("igImageStages");
    if (voiceStages) voiceStages.style.display = "none";
    if (imageStages) imageStages.style.display = "flex";

    processingCard?.classList.add("active");
    postCard?.classList.remove("active");
    resetImageProcessingUI();

    setImageStage(1, "active");
    setProgress(10, "Analysing your image…", "Sending to vision API — no local GPU needed.");

    try {
        const tone = document.getElementById("igToneSelect")?.value || "default";
        const form = new FormData();
        form.append("file", uploadedFile, uploadedFile.name);
        form.append("tone", tone);

        const res = await fetch(`${API}/caption-from-image`, { method: "POST", body: form });

        if (!res.ok) {
            let detail = `Server error ${res.status}`;
            try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
            throw new Error(detail);
        }

        setImageStage(1, "complete");
        setProgress(60, "Caption generated!", "Finishing up…");
        setImageStage(2, "active");

        const data = await res.json();

        setImageStage(2, "complete");
        setProgress(100, "Done!", "");

        processingCard?.classList.remove("active");
        postCard?.classList.add("active");

        // Show the uploaded image in post card instead of generated one
        const postImage = document.getElementById("igPostImage");
        const postSource = document.getElementById("igPostSource");
        if (postImage && uploadedFile) {
            postImage.src = URL.createObjectURL(uploadedFile);
            postImage.style.display = "block";
        }
        if (postSource) postSource.textContent = "Generated from uploaded image";

        applyPostData(data, /*skipImage=*/true);
        setRegenStatus("Caption generated from your image. Use ↻ Regenerate image to create a new AI visual.");
        commitHistorySnapshot(true);

    } catch (err) {
        processingCard?.classList.remove("active");
        setUploadStatus("error", "Failed", String(err.message || err), "");
        showPostCardError(`Error: ${err.message}`);
        postCard?.classList.add("active");
    } finally {
        if (genBtn) genBtn.disabled = false;
    }
}

function resetImageProcessingUI() {
    setProgress(0, "Starting…", "");
    const ts = document.getElementById("igTranscriptSection");
    if (ts) ts.style.display = "none";
    for (let i = 1; i <= 2; i++) {
        const s = document.getElementById(`igImgStage${i}`);
        if (!s) continue;
        s.classList.remove("active", "complete");
        const icon = s.querySelector(".stage-icon");
        if (icon) icon.innerText = IMAGE_STAGE_ICONS[i];
    }
}

function setImageStage(num, status) {
    const stage = document.getElementById(`igImgStage${num}`);
    if (!stage) return;
    if (status === "active") {
        stage.classList.remove("complete"); stage.classList.add("active");
    } else if (status === "complete") {
        stage.classList.remove("active"); stage.classList.add("complete");
        const icon = stage.querySelector(".stage-icon");
        if (icon) icon.innerText = "✓";
    }
}

function setProgress(percent, message, detail) {
    const fill = document.getElementById("igProgressBarFill");
    const pctEl = document.getElementById("igProgressPercent");
    const msgEl = document.getElementById("igProgressMessage");
    const detEl = document.getElementById("igProgressDetail");
    if (fill) fill.style.width = `${percent}%`;
    if (pctEl) pctEl.textContent = `${Math.round(percent)}%`;
    if (msgEl) msgEl.textContent = message;
    if (detEl) detEl.textContent = detail;
}

// ── Upload status box ──────────────────────────────────────────────────────────

function setUploadStatus(type, label, text, hint = "") {
    const box = document.getElementById("igUploadStatusBox");
    if (!box) return;
    box.classList.remove("error", "info");
    box.classList.add("active", type);
    const labelEl = document.getElementById("igUploadStatusLabel");
    const textEl = document.getElementById("igUploadStatusText");
    const hintEl = document.getElementById("igUploadStatusHint");
    if (labelEl) labelEl.innerText = label;
    if (textEl) textEl.innerText = text;
    if (hintEl) hintEl.innerText = hint;
}

function clearUploadStatus() {
    const box = document.getElementById("igUploadStatusBox");
    if (box) box.classList.remove("active", "error", "info");
}

// ── History ────────────────────────────────────────────────────────────────────

function newHistoryId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return `h-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
function readHistory() {
    try { const r = localStorage.getItem(HISTORY_KEY); return r ? JSON.parse(r) : []; } catch { return []; }
}
function writeHistory(entries) {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(entries)); } catch (e) { console.warn(e); }
}
function getCurrentImagePath() {
    const img = document.getElementById("igPostImage");
    if (!img || img.style.display === "none") return "";
    const src = img.getAttribute("src") || "";
    if (!src || src.startsWith("blob:")) return ""; // blob URLs are local, don't persist
    try { return new URL(src, window.location.href).pathname; } catch { return src.startsWith("/") ? src.split("?")[0] : ""; }
}
function buildHistoryEntry(id) {
    return {
        id,
        savedAt: new Date().toISOString(),
        source: currentMode,
        transcript: lastTranscript,
        tone: document.getElementById("igToneSelect")?.value || "default",
        instagram_caption: document.getElementById("igEditCaption")?.value || "",
        hashtags: document.getElementById("igEditHashtags")?.value || "",
        image_prompt: document.getElementById("igEditImagePrompt")?.value || "",
        image_url: getCurrentImagePath(),
    };
}
function commitHistorySnapshot(isNewRun) {
    if (isNewRun) activeHistoryId = newHistoryId();
    else if (!activeHistoryId) activeHistoryId = newHistoryId();
    const entry = buildHistoryEntry(activeHistoryId);
    let list = readHistory().filter((e) => e.id !== activeHistoryId);
    list.unshift(entry);
    while (list.length > MAX_HISTORY) list.pop();
    writeHistory(list);
    renderHistoryList();
}
function removeHistoryEntry(id, ev) {
    if (ev) ev.stopPropagation();
    writeHistory(readHistory().filter((e) => e.id !== id));
    if (activeHistoryId === id) activeHistoryId = null;
    renderHistoryList();
}
function renderHistoryList() {
    const listEl = document.getElementById("igHistoryList");
    const emptyEl = document.getElementById("igHistoryEmpty");
    if (!listEl || !emptyEl) return;
    const entries = readHistory();
    listEl.innerHTML = "";
    if (entries.length === 0) { emptyEl.classList.remove("hidden"); return; }
    emptyEl.classList.add("hidden");
    for (const entry of entries) {
        const li = document.createElement("li");
        li.className = "history-item";
        const mainBtn = document.createElement("button");
        mainBtn.type = "button";
        mainBtn.className = "history-item-main";
        const titleEl = document.createElement("div");
        titleEl.className = "history-item-title";
        titleEl.textContent = (entry.instagram_caption || "").split("\n")[0].trim() || "(no caption)";
        const metaEl = document.createElement("div");
        metaEl.className = "history-item-meta";
        const when = entry.savedAt ? new Date(entry.savedAt).toLocaleString() : "";
        const src = entry.source === "image" ? "📷 image" : "🎙 voice";
        const imgNote = entry.image_url ? " · has image" : "";
        metaEl.textContent = `${when} · ${src} · ${entry.tone || "default"}${imgNote}`;
        mainBtn.appendChild(titleEl);
        mainBtn.appendChild(metaEl);
        mainBtn.addEventListener("click", () => restoreHistoryEntry(entry.id));
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "history-item-remove";
        rm.setAttribute("aria-label", "Remove from history");
        rm.textContent = "×";
        rm.addEventListener("click", (e) => removeHistoryEntry(entry.id, e));
        li.appendChild(mainBtn);
        li.appendChild(rm);
        listEl.appendChild(li);
    }
}
function restoreHistoryEntry(id) {
    const entry = readHistory().find((e) => e.id === id);
    if (!entry) return;
    activeHistoryId = entry.id;
    lastTranscript = entry.transcript || "";
    currentMode = entry.source || "voice";

    const captionInput = document.getElementById("igEditCaption");
    const hashtagsInput = document.getElementById("igEditHashtags");
    const promptInput = document.getElementById("igEditImagePrompt");
    const toneSel = document.getElementById("igToneSelect");
    const postImage = document.getElementById("igPostImage");
    const postCard = document.getElementById("igPostCard");
    const postSource = document.getElementById("igPostSource");

    if (captionInput) captionInput.value = entry.instagram_caption || "";
    if (hashtagsInput) hashtagsInput.value = entry.hashtags || "";
    if (promptInput) promptInput.value = entry.image_prompt || "";
    if (toneSel && entry.tone) {
        const ok = [...toneSel.options].some((o) => o.value === entry.tone);
        toneSel.value = ok ? entry.tone : "default";
    }
    if (postSource) postSource.textContent = currentMode === "image" ? "Generated from uploaded image" : "Generated from voice";
    if (postImage) {
        if (entry.image_url) {
            postImage.src = `${entry.image_url.split("?")[0]}?t=${Date.now()}`;
            postImage.style.display = "block";
        } else {
            postImage.removeAttribute("src");
            postImage.style.display = "none";
        }
    }
    hidePostCardError();
    if (postCard) postCard.classList.add("active");
    setRegenStatus("Restored from history.");
    updateDownloadImageButton();
}

// ── Post card helpers ──────────────────────────────────────────────────────────

function updateDownloadImageButton() {
    const btn = document.getElementById("igDownloadImageBtn");
    if (!btn) return;
    btn.disabled = !getCurrentImagePath();
}
async function downloadCurrentImage() {
    const path = getCurrentImagePath();
    if (!path) { setRegenStatus("No downloadable image (uploaded images are local)."); return; }
    try {
        const res = await fetch(path);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        a.download = `instagram-voice-${new Date().toISOString().slice(0,19).replace(/[:T]/g,"-")}.png`;
        a.rel = "noopener";
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(objectUrl);
        setRegenStatus("Download started.");
    } catch (err) {
        setRegenStatus("Download failed — check the network.");
    }
}
function showPostCardError(message) {
    const errEl = document.getElementById("igPostCardError");
    const bodyEl = document.getElementById("igPostCardBody");
    if (errEl) { errEl.textContent = message; errEl.hidden = false; }
    if (bodyEl) bodyEl.hidden = true;
}
function hidePostCardError() {
    const errEl = document.getElementById("igPostCardError");
    const bodyEl = document.getElementById("igPostCardBody");
    if (errEl) { errEl.textContent = ""; errEl.hidden = true; }
    if (bodyEl) bodyEl.hidden = false;
}
function applyPostData(data, skipImage = false) {
    hidePostCardError();
    if (data.transcript) lastTranscript = data.transcript;
    const captionEl = document.getElementById("igEditCaption");
    const hashtagsEl = document.getElementById("igEditHashtags");
    const promptEl = document.getElementById("igEditImagePrompt");
    if (captionEl && data.instagram_caption != null) captionEl.value = data.instagram_caption;
    if (hashtagsEl && data.hashtags != null) hashtagsEl.value = data.hashtags;
    if (promptEl && data.image_prompt != null) promptEl.value = data.image_prompt;
    if (!skipImage) {
        const postImage = document.getElementById("igPostImage");
        if (postImage) {
            if (data.image_url) {
                const u = data.image_url;
                postImage.src = u + (u.includes("?") ? "&" : "?") + "t=" + Date.now();
                postImage.style.display = "block";
            } else {
                postImage.removeAttribute("src");
                postImage.style.display = "none";
            }
        }
    }
    updateDownloadImageButton();
}
function setRegenStatus(text) {
    const el = document.getElementById("igRegenStatus");
    if (el) el.textContent = text || "";
}
function buildCaptionWithHashtags() {
    const c = document.getElementById("igEditCaption")?.value?.trim() || "";
    const h = document.getElementById("igEditHashtags")?.value?.trim() || "";
    if (!c && !h) return "";
    return h ? `${c}\n\n${h}` : c;
}
async function copyToClipboard(text, okMsg) {
    try { await navigator.clipboard.writeText(text); setRegenStatus(okMsg || "Copied."); }
    catch { setRegenStatus("Copy failed — use HTTPS/localhost or allow clipboard access."); }
}

// ── Tones ──────────────────────────────────────────────────────────────────────

async function loadTones() {
    const sel = document.getElementById("igToneSelect");
    if (!sel) return;
    try {
        const res = await fetch(`${API}/tones`);
        if (!res.ok) throw new Error("bad");
        const data = await res.json();
        sel.innerHTML = "";
        for (const t of data.tones) {
            const opt = document.createElement("option");
            opt.value = t.id; opt.textContent = t.label;
            sel.appendChild(opt);
        }
    } catch { sel.innerHTML = '<option value="default">General Instagram</option>'; }
}

// ── Regenerate text ────────────────────────────────────────────────────────────

async function regenerateTextAction() {
    if (!lastTranscript.trim()) {
        setRegenStatus("No transcript yet — record audio first.");
        return;
    }
    const tone = document.getElementById("igToneSelect")?.value || "default";
    const btn = document.getElementById("igRegenTextBtn");
    const imgBtn = document.getElementById("igRegenImageBtn");
    setRegenStatus("Regenerating caption and hashtags…");
    if (btn) btn.disabled = true;
    if (imgBtn) imgBtn.disabled = true;
    try {
        const res = await fetch(`${API}/regenerate-text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: lastTranscript, tone }),
        });
        if (!res.ok) {
            let d = `Error ${res.status}`;
            try { const j = await res.json(); if (j.detail) d = String(j.detail); } catch (_) {}
            throw new Error(d);
        }
        const data = await res.json();
        document.getElementById("igEditCaption").value = data.instagram_caption || "";
        document.getElementById("igEditHashtags").value = data.hashtags || "";
        document.getElementById("igEditImagePrompt").value = data.image_prompt || "";
        setRegenStatus("Caption updated. Use \u201CRegenerate image\u201D if you want a new visual.");
        commitHistorySnapshot(false);
    } catch (e) {
        setRegenStatus(String(e.message || e));
    } finally {
        if (btn) btn.disabled = false;
        if (imgBtn) imgBtn.disabled = false;
    }
}

// ── Regenerate image ───────────────────────────────────────────────────────────

async function regenerateImageAction() {
    const prompt = document.getElementById("igEditImagePrompt")?.value?.trim() || "";
    if (!prompt) { setRegenStatus("Add an image prompt first (expand \u201CImage prompt\u201D)."); return; }
    const btn = document.getElementById("igRegenImageBtn");
    const txtBtn = document.getElementById("igRegenTextBtn");
    setRegenStatus("Generating 1080\u00d71080 image \u2014 can take up to a minute\u2026");
    if (btn) btn.disabled = true;
    if (txtBtn) txtBtn.disabled = true;
    try {
        const res = await fetch(`${API}/regenerate-image`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_prompt: prompt }),
        });
        if (!res.ok) {
            let d = `Error ${res.status}`;
            try { const j = await res.json(); if (j.detail) d = String(j.detail); } catch (_) {}
            throw new Error(d);
        }
        const data = await res.json();
        const postImage = document.getElementById("igPostImage");
        if (data.image_url && postImage) {
            const u = data.image_url;
            postImage.src = u + (u.includes("?") ? "&" : "?") + "t=" + Date.now();
            postImage.style.display = "block";
            setRegenStatus("New image ready.");
        } else {
            postImage?.removeAttribute("src");
            if (postImage) postImage.style.display = "none";
            setRegenStatus(data.image_error || "Image failed.");
        }
        commitHistorySnapshot(false);
        updateDownloadImageButton();
    } catch (e) {
        setRegenStatus(String(e.message || e));
    } finally {
        if (btn) btn.disabled = false;
        if (txtBtn) txtBtn.disabled = false;
        updateDownloadImageButton();
    }
}

function initPostEditorActions() {
    document.getElementById("igCopyCaptionBtn")?.addEventListener("click", () => {
        const v = document.getElementById("igEditCaption")?.value?.trim() || "";
        if (!v) { setRegenStatus("Nothing in caption to copy."); return; }
        void copyToClipboard(v, "Caption copied.");
    });
    document.getElementById("igCopyHashtagsBtn")?.addEventListener("click", () => {
        const v = document.getElementById("igEditHashtags")?.value?.trim() || "";
        if (!v) { setRegenStatus("Nothing in hashtags to copy."); return; }
        void copyToClipboard(v, "Hashtags copied.");
    });
    document.getElementById("igCopyAllBtn")?.addEventListener("click", () => {
        const full = buildCaptionWithHashtags();
        if (!full.trim()) { setRegenStatus("Nothing to copy."); return; }
        void copyToClipboard(full, "Caption + hashtags copied.");
    });
    document.getElementById("igRegenTextBtn")?.addEventListener("click", () => { void regenerateTextAction(); });
    document.getElementById("igRegenImageBtn")?.addEventListener("click", () => { void regenerateImageAction(); });
    document.getElementById("igDownloadImageBtn")?.addEventListener("click", () => { void downloadCurrentImage(); });
}

// ── Voice recording ────────────────────────────────────────────────────────────

function resetRingArc() {
    const arc = document.getElementById("igRingArc");
    if (arc) arc.style.strokeDashoffset = ARC_CIRC;
}
function updateTimer() {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mins = Math.floor(elapsed / 60), secs = elapsed % 60;
    const timerEl = document.getElementById("igTimer");
    if (timerEl) timerEl.innerText = `${mins}:${secs.toString().padStart(2, "0")}`;
    const arc = document.getElementById("igRingArc");
    if (arc) arc.style.strokeDashoffset = ARC_CIRC * (1 - Math.min(elapsed / MAX_REC_SECS, 1));
}
function showError(message) { setStatus("error", "Recording error", message, "Check microphone permissions and try again."); }
function setStatus(type, label, text, hint = "") {
    const box = document.getElementById("igStatusBox");
    if (!box) return;
    box.classList.remove("error", "info"); box.classList.add("active", type);
    document.getElementById("igStatusLabel").innerText = label;
    document.getElementById("igStatusText").innerText = text;
    document.getElementById("igStatusHint").innerText = hint;
}
function clearStatus() { document.getElementById("igStatusBox")?.classList.remove("active", "error", "info"); }

function stopLiveCaptions() {
    liveCaptionsActive = false;
    if (liveRecognition) {
        liveRecognition.onend = null;
        try { liveRecognition.abort(); } catch (_) {}
        liveRecognition = null;
    }
    const wrap = document.getElementById("igLiveCaptionWrap");
    if (wrap) wrap.hidden = true;
}
function startLiveCaptions() {
    const wrap = document.getElementById("igLiveCaptionWrap");
    const textEl = document.getElementById("igLiveCaptionText");
    const hintEl = document.getElementById("igLiveCaptionHint");
    if (!wrap || !textEl || !hintEl) return;
    stopLiveCaptions();
    liveCaptionFinal = "";
    textEl.textContent = "";
    hintEl.textContent = "";
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        wrap.hidden = false;
        hintEl.textContent = "Live captions need Chrome or Edge. Recording still works.";
        return;
    }
    wrap.hidden = false;
    hintEl.textContent = "Preview while you speak. Final transcript is generated on server.";
    const rec = new SpeechRecognition();
    rec.continuous = true; rec.interimResults = true; rec.lang = navigator.language || "en-US";
    rec.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const piece = event.results[i][0].transcript;
            if (event.results[i].isFinal) liveCaptionFinal += piece;
            else interim += piece;
        }
        textEl.textContent = (liveCaptionFinal + interim).trim() || "…";
    };
    rec.onerror = (ev) => {
        if (ev.error === "not-allowed") hintEl.textContent = "Live captions blocked.";
        else if (ev.error !== "aborted" && ev.error !== "no-speech") hintEl.textContent = `Live captions error: ${ev.error}`;
    };
    rec.onend = () => { if (liveRecognition === rec && liveCaptionsActive) { try { rec.start(); } catch (_) {} } };
    liveRecognition = rec;
    liveCaptionsActive = true;
    try { rec.start(); } catch (_) { hintEl.textContent = "Could not start live captions."; }
}
function getSupportedMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
    for (const t of candidates) { if (MediaRecorder.isTypeSupported(t)) return t; }
    return "";
}

// ── Voice stages ───────────────────────────────────────────────────────────────

function resetAllVoiceStages() {
    for (let i = 1; i <= 3; i++) {
        const s = document.getElementById(`igStage${i}`);
        if (!s) continue;
        s.classList.remove("active", "complete");
        const icon = s.querySelector(".stage-icon");
        if (icon) icon.innerText = VOICE_STAGE_ICONS[i];
    }
}
function resetVoiceStagesAfter(fromStep) {
    for (let i = fromStep + 1; i <= 3; i++) {
        const s = document.getElementById(`igStage${i}`);
        if (!s) continue;
        s.classList.remove("active", "complete");
        const icon = s.querySelector(".stage-icon");
        if (icon) icon.innerText = VOICE_STAGE_ICONS[i];
    }
}
function resetVoiceProcessingUI() {
    resetAllVoiceStages();
    setProgress(0, "Starting…", "");
    const ts = document.getElementById("igTranscriptSection");
    if (ts) ts.style.display = "none";
}
function applyProgressEvent(ev) {
    const pct = Math.min(100, Number(ev.percent) || 0);
    setProgress(pct, ev.message || "", ev.detail || "");
    const step = ev.step, ss = ev.step_status;
    if (step && ss === "running") {
        for (let i = 1; i < step; i++) updateVoiceStage(i, "complete");
        resetVoiceStagesAfter(step);
        updateVoiceStage(step, "active");
    }
    if (step && ss === "done") {
        updateVoiceStage(step, "complete");
        if (ev.transcript) {
            document.getElementById("igTranscriptSection").style.display = "block";
            document.getElementById("igTranscriptText").innerText = ev.transcript;
        }
    }
}
function updateVoiceStage(num, status) {
    const s = document.getElementById(`igStage${num}`);
    if (!s) return;
    if (status === "active") { s.classList.remove("complete"); s.classList.add("active"); }
    else if (status === "complete") {
        s.classList.remove("active"); s.classList.add("complete");
        s.querySelector(".stage-icon").innerText = "✓";
    }
}

async function consumeProcessStream(form) {
    const res = await fetch(`${API}/process-stream`, { method: "POST", body: form });
    if (!res.ok) {
        let detail = `Server error: ${res.status}`;
        try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
        throw new Error(detail);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", finalData = null;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const block of parts) {
            const dataLine = block.trim().split("\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            let ev;
            try { ev = JSON.parse(dataLine.slice(6)); } catch (_) { continue; }
            if (ev.type === "error") throw new Error(ev.detail || "Processing failed");
            if (ev.type === "complete") { finalData = ev.data; continue; }
            if (ev.type === "progress") applyProgressEvent(ev);
        }
    }
    if (!finalData) throw new Error("Connection closed before completion.");
    return finalData;
}

async function toggleRecording() {
    const btn = document.getElementById("igRecordBtn");
    const btnText = document.getElementById("igBtnText");
    const btnIcon = document.getElementById("igBtnIcon");
    const timer = document.getElementById("igTimer");
    const indicator = document.getElementById("igRecordingIndicator");
    const processingCard = document.getElementById("igProcessingCard");
    const postCard = document.getElementById("igPostCard");

    if (!isRecording) {
        clearStatus();
        if (!window.isSecureContext) { showError("Needs HTTPS or localhost."); return; }
        if (!navigator.mediaDevices?.getUserMedia) { showError("Microphone not supported."); return; }
        if (!window.MediaRecorder) { showError("MediaRecorder not supported."); return; }
        try {
            setStatus("info", "Microphone", "Requesting access...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            setStatus("info", "Microphone", "Recording started.");
            const mimeType = getSupportedMimeType();
            mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onerror = (ev) => showError(`Recorder error: ${ev.error?.message || "Unknown"}`);
            mediaRecorder.onstop = async () => {
                setStatus("info", "Upload", "Uploading audio…");
                const blob = new Blob(audioChunks, { type: "audio/webm" });
                audioChunks = [];
                if (!blob.size) { showError("No audio captured."); return; }

                // Show voice stages, hide image stages
                const voiceStages = document.getElementById("igVoiceStages");
                const imageStages = document.getElementById("igImageStages");
                if (voiceStages) voiceStages.style.display = "flex";
                if (imageStages) imageStages.style.display = "none";

                const form = new FormData();
                form.append("file", blob, "recording.webm");
                form.append("tone", document.getElementById("igToneSelect")?.value || "default");
                processingCard?.classList.add("active");
                postCard?.classList.remove("active");
                resetVoiceProcessingUI();

                try {
                    const data = await consumeProcessStream(form);
                    setProgress(100, "Done!", "");
                    updateVoiceStage(3, "complete");
                    processingCard?.classList.remove("active");
                    postCard?.classList.add("active");

                    const postSource = document.getElementById("igPostSource");
                    if (postSource) postSource.textContent = "Generated from voice";

                    applyPostData(data);
                    setRegenStatus("");
                    if (data.image_error) setStatus("info", "Image", "Caption ready, image failed.", data.image_error);
                    else clearStatus();
                    commitHistorySnapshot(true);
                } catch (err) {
                    processingCard?.classList.remove("active");
                    setStatus("error", "Processing", "Failed.", String(err.message || err));
                    showPostCardError(`Error: ${err.message}`);
                    postCard?.classList.add("active");
                }
            };
            mediaRecorder.start();
            startLiveCaptions();
            isRecording = true;
            if (btnIcon) btnIcon.innerText = "⏹";
            if (btnText) btnText.innerText = "Stop Recording";
            btn?.classList.add("recording");
            if (timer) timer.style.display = "block";
            indicator?.classList.add("active");
            recordingStartTime = Date.now();
            resetRingArc();
            timerInterval = setInterval(updateTimer, 200);
        } catch (err) {
            let msg = "Could not access microphone. ";
            if (err.name === "NotAllowedError") msg += "Please allow access.";
            else if (err.name === "NotFoundError") msg += "No microphone found.";
            else msg += err.message || "Unknown error.";
            showError(msg);
        }
    } else {
        stopLiveCaptions();
        if (mediaRecorder?.state !== "inactive") mediaRecorder.stop();
        isRecording = false;
        if (btnIcon) btnIcon.innerText = "⏺";
        if (btnText) btnText.innerText = "Start Recording";
        btn?.classList.remove("recording");
        if (timer) timer.style.display = "none";
        indicator?.classList.remove("active");
        clearInterval(timerInterval);
        resetRingArc();
        mediaRecorder?.stream?.getTracks().forEach((t) => t.stop());
    }
}

function initRecordingButton() {
    document.getElementById("igRecordBtn")?.addEventListener("click", () => { void toggleRecording(); });
    resetRingArc();
}



function speakCaption(text) {
    // On annule toute lecture en cours
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'fr-FR'; // Ou 'en-US' selon la langue
    utterance.rate = 1.0;     // Vitesse de lecture
    utterance.pitch = 1.0;    // Tonalité

    window.speechSynthesis.speak(utterance);
}


// ── Fonction de Synthèse Vocale (Accessibilité) ──────────────────────────────

// ── Fonction de Synthèse Vocale forcée en Anglais ──────────────────────────────

function initAccessibilitySpeech() {
    const speakBtn = document.getElementById("igSpeakBtn");
    const captionArea = document.getElementById("igEditCaption");

    if (!speakBtn || !captionArea) return;

    speakBtn.addEventListener("click", () => {
        const textToRead = captionArea.value.trim();
        if (!textToRead) return;

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(textToRead);
        const voices = window.speechSynthesis.getVoices();

        // --- DÉTECTION AUTOMATIQUE DE LA LANGUE ---
        // On regarde si le texte contient des mots très communs en français
        const frenchWords = /\b(le|la|les|est|dans|une|avec|pour|votre|maison)\b/i;
        const isFrench = frenchWords.test(textToRead);

        let targetLang = isFrench ? 'fr-FR' : 'en-US';
        
        // On cherche la voix qui correspond à la langue détectée
        const matchedVoice = voices.find(v => v.lang.startsWith(isFrench ? 'fr' : 'en'));

        if (matchedVoice) {
            utterance.voice = matchedVoice;
        }
        
        utterance.lang = targetLang;
        utterance.rate = 1.0;

        // Feedback visuel
        speakBtn.textContent = "⌛";
        utterance.onend = () => { speakBtn.textContent = "🔊"; };

        window.speechSynthesis.speak(utterance);
        console.log(`Lecture en mode: ${isFrench ? 'Français' : 'Anglais'}`);
    });
}

// Initialisation forcée des voix (nécessaire pour Chrome/Edge)
window.speechSynthesis.getVoices();
if (speechSynthesis.onvoiceschanged !== undefined) {
    speechSynthesis.onvoiceschanged = initAccessibilitySpeech;
} else {
    initAccessibilitySpeech();
}

// Appeler la fonction au chargement du script
initAccessibilitySpeech();

// ── Boot ──────────────────────────────────────────────────────────────────────
initModeSwitcher();
initRecordingButton();
initImageUpload();
initPostEditorActions();
void loadTones();
renderHistoryList();