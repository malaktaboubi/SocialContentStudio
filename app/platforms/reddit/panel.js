// Reddit panel — owns its own UI logic. Shell loads this as an ES module
// when the user opens the Reddit tab. All endpoints under /api/reddit/.

const API = "/api/reddit";

let mediaRecorder, audioChunks = [], isRecording = false, recordingStartTime = 0, timerInterval;
let liveRecognition = null;
let liveCaptionsActive = false;
let liveCaptionFinal = "";

const ARC_CIRC = 408;
const MAX_REC_SECS = 120;
const STAGE_ICONS = { 1: "🎙", 2: "🧠", 3: "🎨" };

let lastTranscript = "";

const HISTORY_KEY = "voiceRedditRuns_v1";
const MAX_HISTORY = 8;

let activeHistoryId = null;

function newHistoryId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return `h-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function readHistory() {
    try {
        const raw = localStorage.getItem(HISTORY_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function writeHistory(entries) {
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
    } catch (err) {
        console.warn("Could not save history (storage full or disabled).", err);
    }
}

function getCurrentImagePath() {
    const img = document.getElementById("postImage");
    if (!img || img.style.display === "none") return "";
    const src = img.getAttribute("src");
    if (!src || src === "") return "";
    try {
        return new URL(src, window.location.href).pathname;
    } catch {
        const noQuery = src.split("?")[0];
        if (noQuery.startsWith("/")) return noQuery;
        return "";
    }
}

function buildHistoryEntry(id) {
    return {
        id,
        savedAt: new Date().toISOString(),
        transcript: lastTranscript,
        tone: document.getElementById("toneSelect")?.value || "default",
        reddit_title: document.getElementById("editTitle")?.value || "",
        reddit_body: document.getElementById("editBody")?.value || "",
        image_prompt: document.getElementById("editImagePrompt")?.value || "",
        image_url: getCurrentImagePath(),
    };
}

function commitHistorySnapshot(isNewRun) {
    if (isNewRun) {
        activeHistoryId = newHistoryId();
    } else if (!activeHistoryId) {
        activeHistoryId = newHistoryId();
    }
    const entry = buildHistoryEntry(activeHistoryId);
    let list = readHistory().filter((e) => e.id !== activeHistoryId);
    list.unshift(entry);
    while (list.length > MAX_HISTORY) list.pop();
    writeHistory(list);
    renderHistoryList();
}

function removeHistoryEntry(id, ev) {
    if (ev) ev.stopPropagation();
    const list = readHistory().filter((e) => e.id !== id);
    writeHistory(list);
    if (activeHistoryId === id) activeHistoryId = null;
    renderHistoryList();
}

function renderHistoryList() {
    const listEl = document.getElementById("historyList");
    const emptyEl = document.getElementById("historyEmpty");
    if (!listEl || !emptyEl) return;

    const entries = readHistory();
    listEl.innerHTML = "";

    if (entries.length === 0) {
        emptyEl.classList.remove("hidden");
        return;
    }
    emptyEl.classList.add("hidden");

    for (const entry of entries) {
        const li = document.createElement("li");
        li.className = "history-item";

        const mainBtn = document.createElement("button");
        mainBtn.type = "button";
        mainBtn.className = "history-item-main";

        const titleEl = document.createElement("div");
        titleEl.className = "history-item-title";
        titleEl.textContent = (entry.reddit_title && entry.reddit_title.trim()) || "(no title)";

        const metaEl = document.createElement("div");
        metaEl.className = "history-item-meta";
        const when = entry.savedAt ? new Date(entry.savedAt).toLocaleString() : "";
        const tone = entry.tone || "default";
        const imgNote = entry.image_url ? " · has image" : "";
        metaEl.textContent = `${when} · ${tone}${imgNote}`;

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

    const titleInput = document.getElementById("editTitle");
    const bodyInput = document.getElementById("editBody");
    const promptInput = document.getElementById("editImagePrompt");
    const toneSel = document.getElementById("toneSelect");
    const postImage = document.getElementById("postImage");
    const postCard = document.getElementById("postCard");

    if (titleInput) titleInput.value = entry.reddit_title || "";
    if (bodyInput) bodyInput.value = entry.reddit_body || "";
    if (promptInput) promptInput.value = entry.image_prompt || "";
    if (toneSel && entry.tone) {
        const ok = [...toneSel.options].some((o) => o.value === entry.tone);
        toneSel.value = ok ? entry.tone : "default";
    }

    if (postImage) {
        if (entry.image_url) {
            let path = String(entry.image_url).trim();
            if (path.startsWith("http://") || path.startsWith("https://")) {
                try { path = new URL(path).pathname; } catch { /* keep as-is */ }
            }
            postImage.src = `${path.split("?")[0]}?t=${Date.now()}`;
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

function updateDownloadImageButton() {
    const btn = document.getElementById("downloadImageBtn");
    if (!btn) return;
    btn.disabled = !getCurrentImagePath();
}

async function downloadCurrentImage() {
    const path = getCurrentImagePath();
    if (!path) {
        setRegenStatus("No image to download.");
        return;
    }
    try {
        const res = await fetch(path);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
        a.download = `reddit-voice-${stamp}.png`;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(objectUrl);
        setRegenStatus("Download started.");
    } catch (err) {
        console.warn(err);
        setRegenStatus("Download failed — check the network or open the image in a new tab.");
    }
}

function showPostCardError(message) {
    const errEl = document.getElementById("postCardError");
    const bodyEl = document.getElementById("postCardBody");
    if (errEl) {
        errEl.textContent = message;
        errEl.hidden = false;
    }
    if (bodyEl) bodyEl.hidden = true;
}

function hidePostCardError() {
    const errEl = document.getElementById("postCardError");
    const bodyEl = document.getElementById("postCardBody");
    if (errEl) {
        errEl.textContent = "";
        errEl.hidden = true;
    }
    if (bodyEl) bodyEl.hidden = false;
}

function applyPostData(data) {
    hidePostCardError();
    if (data.transcript) lastTranscript = data.transcript;

    const titleEl = document.getElementById("editTitle");
    const bodyEl = document.getElementById("editBody");
    const promptEl = document.getElementById("editImagePrompt");
    if (titleEl && data.reddit_title != null) titleEl.value = data.reddit_title;
    if (bodyEl && data.reddit_body != null) bodyEl.value = data.reddit_body;
    if (promptEl && data.image_prompt != null) promptEl.value = data.image_prompt;

    const postImage = document.getElementById("postImage");
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
    updateDownloadImageButton();
}

function setRegenStatus(text) {
    const el = document.getElementById("regenStatus");
    if (el) el.textContent = text || "";
}

function buildMarkdownFromEditors() {
    const title = document.getElementById("editTitle")?.value?.trim() || "";
    const body = document.getElementById("editBody")?.value?.trim() || "";
    if (!title && !body) return "";
    return `# ${title}\n\n${body}`;
}

async function copyToClipboard(text, okMsg) {
    try {
        await navigator.clipboard.writeText(text);
        setRegenStatus(okMsg || "Copied.");
    } catch {
        setRegenStatus("Copy failed — use HTTPS/localhost or allow clipboard access.");
    }
}

async function loadTones() {
    const sel = document.getElementById("toneSelect");
    if (!sel) return;
    try {
        const res = await fetch(`${API}/tones`);
        if (!res.ok) throw new Error("bad");
        const data = await res.json();
        sel.innerHTML = "";
        for (const t of data.tones) {
            const opt = document.createElement("option");
            opt.value = t.id;
            opt.textContent = t.label;
            sel.appendChild(opt);
        }
    } catch {
        sel.innerHTML = "<option value=\"default\">General Reddit</option>";
    }
}

async function regenerateTextAction() {
    if (!lastTranscript.trim()) {
        setRegenStatus("No transcript yet — record audio first.");
        return;
    }
    const tone = document.getElementById("toneSelect")?.value || "default";
    const btn = document.getElementById("regenTextBtn");
    const imgBtn = document.getElementById("regenImageBtn");
    setRegenStatus("Regenerating title, body, and image prompt…");
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
            try {
                const j = await res.json();
                if (j.detail) d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
            } catch (_) { /* ignore */ }
            throw new Error(d);
        }
        const data = await res.json();
        document.getElementById("editTitle").value = data.reddit_title || "";
        document.getElementById("editBody").value = data.reddit_body || "";
        document.getElementById("editImagePrompt").value = data.image_prompt || "";
        setRegenStatus("Text updated. Use \u201CRegenerate image\u201D if you want a new visual.");
        commitHistorySnapshot(false);
    } catch (e) {
        setRegenStatus(String(e.message || e));
    } finally {
        if (btn) btn.disabled = false;
        if (imgBtn) imgBtn.disabled = false;
    }
}

async function regenerateImageAction() {
    const prompt = document.getElementById("editImagePrompt")?.value?.trim() || "";
    if (!prompt) {
        setRegenStatus("Add an image prompt first (expand \u201CImage prompt\u201D).");
        return;
    }
    const btn = document.getElementById("regenImageBtn");
    const txtBtn = document.getElementById("regenTextBtn");
    setRegenStatus("Generating image — can take up to a minute…");
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
            try {
                const j = await res.json();
                if (j.detail) d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
            } catch (_) { /* ignore */ }
            throw new Error(d);
        }
        const data = await res.json();
        const postImage = document.getElementById("postImage");
        if (data.image_url && postImage) {
            const u = data.image_url;
            postImage.src = u + (u.includes("?") ? "&" : "?") + "t=" + Date.now();
            postImage.style.display = "block";
            setRegenStatus("New image ready.");
            if (data.image_error) setStatus("info", "Image", "Partial success.", data.image_error);
            else clearStatus();
        } else {
            postImage?.removeAttribute("src");
            if (postImage) postImage.style.display = "none";
            setRegenStatus(data.image_error || "Image failed.");
            setStatus("info", "Image", "Regeneration failed.", data.image_error || "");
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
    document.getElementById("copyTitleBtn")?.addEventListener("click", () => {
        const v = document.getElementById("editTitle")?.value?.trim() || "";
        if (!v) { setRegenStatus("Nothing in title to copy."); return; }
        void copyToClipboard(v, "Title copied.");
    });
    document.getElementById("copyBodyBtn")?.addEventListener("click", () => {
        const v = document.getElementById("editBody")?.value?.trim() || "";
        if (!v) { setRegenStatus("Nothing in body to copy."); return; }
        void copyToClipboard(v, "Body copied.");
    });
    document.getElementById("copyMdBtn")?.addEventListener("click", () => {
        const md = buildMarkdownFromEditors();
        if (!md.trim()) { setRegenStatus("Nothing to copy."); return; }
        void copyToClipboard(md, "Markdown copied.");
    });
    document.getElementById("regenTextBtn")?.addEventListener("click", () => { void regenerateTextAction(); });
    document.getElementById("regenImageBtn")?.addEventListener("click", () => { void regenerateImageAction(); });
    document.getElementById("downloadImageBtn")?.addEventListener("click", () => { void downloadCurrentImage(); });
}

function resetAllProcessingStages() {
    for (let i = 1; i <= 3; i++) {
        const stage = document.getElementById(`stage${i}`);
        if (!stage) continue;
        stage.classList.remove("active", "complete");
        const icon = stage.querySelector(".stage-icon");
        if (icon) icon.innerText = STAGE_ICONS[i];
    }
}

function resetStagesAfter(fromStep) {
    for (let i = fromStep + 1; i <= 3; i++) {
        const stage = document.getElementById(`stage${i}`);
        if (!stage) continue;
        stage.classList.remove("active", "complete");
        const icon = stage.querySelector(".stage-icon");
        if (icon) icon.innerText = STAGE_ICONS[i];
    }
}

function resetProcessingUI() {
    resetAllProcessingStages();
    const fill = document.getElementById("progressBarFill");
    const pctEl = document.getElementById("progressPercent");
    const msgEl = document.getElementById("progressMessage");
    const detEl = document.getElementById("progressDetail");
    if (fill) fill.style.width = "0%";
    if (pctEl) pctEl.textContent = "0%";
    if (msgEl) msgEl.textContent = "Starting…";
    if (detEl) detEl.textContent = "";
    const ts = document.getElementById("transcriptSection");
    if (ts) ts.style.display = "none";
}

function applyProgressEvent(ev) {
    const fill = document.getElementById("progressBarFill");
    const pctEl = document.getElementById("progressPercent");
    const msgEl = document.getElementById("progressMessage");
    const detEl = document.getElementById("progressDetail");
    const pct = Math.min(100, Number(ev.percent) || 0);
    if (fill) fill.style.width = `${pct}%`;
    if (pctEl) pctEl.textContent = `${Math.round(pct)}%`;
    if (msgEl) msgEl.textContent = ev.message || "";
    if (detEl) detEl.textContent = ev.detail || "";

    const step = ev.step;
    const ss = ev.step_status;
    if (step && ss === "running") {
        for (let i = 1; i < step; i++) updateStage(i, "complete");
        resetStagesAfter(step);
        updateStage(step, "active");
    }
    if (step && ss === "done") {
        updateStage(step, "complete");
        if (ev.transcript) {
            document.getElementById("transcriptSection").style.display = "block";
            document.getElementById("transcriptText").innerText = ev.transcript;
        }
    }
}

async function consumeProcessStream(form) {
    const res = await fetch(`${API}/process-stream`, { method: "POST", body: form });
    if (!res.ok) {
        let detail = `Server error: ${res.status}`;
        try {
            const errBody = await res.json();
            if (errBody.detail) detail = errBody.detail;
        } catch (_) {}
        throw new Error(detail);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalData = null;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const block of parts) {
            const lines = block.trim().split("\n");
            const dataLine = lines.find((l) => l.startsWith("data: "));
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

function resetRingArc() {
    const arc = document.getElementById("ringArc");
    if (arc) arc.style.strokeDashoffset = ARC_CIRC;
}

function updateTimer() {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    document.getElementById("timer").innerText = `${mins}:${secs.toString().padStart(2, "0")}`;

    const arc = document.getElementById("ringArc");
    if (arc) {
        const progress = Math.min(elapsed / MAX_REC_SECS, 1);
        arc.style.strokeDashoffset = ARC_CIRC * (1 - progress);
    }
}

function showError(message) {
    setStatus("error", "Recording error", message, "Check microphone permissions and try again.");
}

function setStatus(type, label, text, hint = "") {
    const box = document.getElementById("statusBox");
    if (!box) return;
    box.classList.remove("error", "info");
    box.classList.add("active", type);
    document.getElementById("statusLabel").innerText = label;
    document.getElementById("statusText").innerText = text;
    document.getElementById("statusHint").innerText = hint;
}

function clearStatus() {
    const box = document.getElementById("statusBox");
    if (box) box.classList.remove("active", "error", "info");
}

function stopLiveCaptions() {
    liveCaptionsActive = false;
    if (liveRecognition) {
        liveRecognition.onend = null;
        try { liveRecognition.abort(); } catch (_) {}
        try { liveRecognition.stop(); } catch (_) {}
        liveRecognition = null;
    }
    const wrap = document.getElementById("liveCaptionWrap");
    if (wrap) wrap.hidden = true;
}

function startLiveCaptions() {
    const wrap = document.getElementById("liveCaptionWrap");
    const textEl = document.getElementById("liveCaptionText");
    const hintEl = document.getElementById("liveCaptionHint");
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
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || "en-US";

    rec.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const piece = event.results[i][0].transcript;
            if (event.results[i].isFinal) liveCaptionFinal += piece;
            else interim += piece;
        }
        const combined = (liveCaptionFinal + interim).trim();
        textEl.textContent = combined || "…";
    };

    rec.onerror = (ev) => {
        if (ev.error === "not-allowed") hintEl.textContent = "Live captions blocked. Allow microphone permission.";
        else if (ev.error !== "aborted" && ev.error !== "no-speech") hintEl.textContent = `Live captions error: ${ev.error}`;
    };

    rec.onend = () => {
        if (liveRecognition === rec && liveCaptionsActive) {
            try { rec.start(); } catch (_) {}
        }
    };

    liveRecognition = rec;
    liveCaptionsActive = true;
    try { rec.start(); } catch (_) { hintEl.textContent = "Could not start live captions."; }
}

function getSupportedMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
    for (const type of candidates) {
        if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return "";
}

async function toggleRecording() {
    const btn = document.getElementById("recordBtn");
    const btnText = document.getElementById("btnText");
    const btnIcon = document.getElementById("btnIcon");
    const timer = document.getElementById("timer");
    const recordingIndicator = document.getElementById("recordingIndicator");
    const processingCard = document.getElementById("processingCard");
    const postCard = document.getElementById("postCard");

    if (!isRecording) {
        clearStatus();
        if (!window.isSecureContext) {
            showError("This page must be loaded from https or localhost to access the microphone.");
            return;
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showError("Your browser does not support microphone access.");
            return;
        }
        if (!window.MediaRecorder) {
            showError("MediaRecorder is not supported in this browser.");
            return;
        }
        try {
            setStatus("info", "Microphone", "Requesting microphone access...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            setStatus("info", "Microphone", "Access granted. Recording started.");

            const mimeType = getSupportedMimeType();
            mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onerror = (event) => {
                showError(`Recorder error: ${event.error?.message || "Unknown error"}`);
            };

            mediaRecorder.onstop = async () => {
                setStatus("info", "Upload", "Recording stopped. Uploading audio...");
                const blob = new Blob(audioChunks, { type: "audio/webm" });
                audioChunks = [];
                if (!blob.size) {
                    showError("No audio captured. Please try again and speak clearly.");
                    return;
                }

                const form = new FormData();
                form.append("file", blob, "recording.webm");
                form.append("tone", document.getElementById("toneSelect")?.value || "default");
                processingCard.classList.add("active");
                postCard.classList.remove("active");
                resetProcessingUI();

                try {
                    const data = await consumeProcessStream(form);

                    const fill = document.getElementById("progressBarFill");
                    const pctEl = document.getElementById("progressPercent");
                    if (fill) fill.style.width = "100%";
                    if (pctEl) pctEl.textContent = "100%";
                    updateStage(3, "complete");

                    processingCard.classList.remove("active");
                    postCard.classList.add("active");
                    applyPostData(data);
                    setRegenStatus("");

                    if (data.image_error) setStatus("info", "Image", "Text generated but image failed.", data.image_error);
                    else clearStatus();
                    commitHistorySnapshot(true);
                } catch (error) {
                    processingCard.classList.remove("active");
                    setStatus("error", "Processing", "Failed to process the audio.", String(error.message || error));
                    showPostCardError(`Error processing request: ${error.message}`);
                    postCard.classList.add("active");
                }
            };

            mediaRecorder.start();
            startLiveCaptions();
            isRecording = true;
            btnIcon.innerText = "⏹";
            btnText.innerText = "Stop Recording";
            btn.classList.add("recording");
            timer.style.display = "block";
            recordingIndicator.classList.add("active");
            recordingStartTime = Date.now();
            resetRingArc();
            timerInterval = setInterval(updateTimer, 200);
        } catch (error) {
            let errorMsg = "Could not access microphone. ";
            if (error.name === "NotAllowedError") errorMsg += "Please allow microphone access.";
            else if (error.name === "NotFoundError") errorMsg += "No microphone found.";
            else if (error.name === "NotSupportedError") errorMsg += "Recording is not supported in this browser.";
            else errorMsg += error.message || "Unknown error.";
            showError(errorMsg);
        }
    } else {
        stopLiveCaptions();
        if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
        isRecording = false;
        btnIcon.innerText = "⏺";
        btnText.innerText = "Start Recording";
        btn.classList.remove("recording");
        timer.style.display = "none";
        recordingIndicator.classList.remove("active");
        clearInterval(timerInterval);
        resetRingArc();
        if (mediaRecorder && mediaRecorder.stream) {
            mediaRecorder.stream.getTracks().forEach((track) => track.stop());
        }
    }
}

function updateStage(stageNum, status) {
    const stage = document.getElementById(`stage${stageNum}`);
    if (!stage) return;
    if (status === "active") {
        stage.classList.remove("complete");
        stage.classList.add("active");
    } else if (status === "complete") {
        stage.classList.remove("active");
        stage.classList.add("complete");
        stage.querySelector(".stage-icon").innerText = "✓";
    }
}

function initRecordingButton() {
    const button = document.getElementById("recordBtn");
    if (!button) return;
    button.addEventListener("click", () => { void toggleRecording(); });
    resetRingArc();
}

initRecordingButton();
initPostEditorActions();
void loadTones();
renderHistoryList();
