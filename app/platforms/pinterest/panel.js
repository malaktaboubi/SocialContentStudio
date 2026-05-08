// Pinterest panel — ES module

const API = "/api/pinterest";

// Elements
const toneSelect    = document.getElementById("pin-tone");
const tabs          = document.querySelectorAll(".pin-tab");
const tabContents   = document.querySelectorAll(".pin-tab-content");

const dropzone      = document.getElementById("pin-dropzone");
const imageInput    = document.getElementById("pin-image-input");
const dropInner     = document.getElementById("pin-drop-inner");
const preview       = document.getElementById("pin-preview");
const imageBtn      = document.getElementById("pin-image-btn");

const recordBtn     = document.getElementById("pin-record-btn");
const recordStatus  = document.getElementById("pin-record-status");
const voiceBtn      = document.getElementById("pin-voice-btn");

const progressBox   = document.getElementById("pin-progress");
const progressFill  = document.getElementById("pin-progress-fill");
const progressMsg   = document.getElementById("pin-progress-msg");

const resultBox     = document.getElementById("pin-result");
const resultImg     = document.getElementById("pin-result-img");
const captionTA     = document.getElementById("pin-caption");
const hashtagsTA    = document.getElementById("pin-hashtags");
const regenTextBtn  = document.getElementById("pin-regen-text-btn");
const regenImgBtn   = document.getElementById("pin-regen-image-btn");
const copyBtn       = document.getElementById("pin-copy-btn");

const errorBox      = document.getElementById("pin-error");

let selectedImageFile = null;
let audioBlob = null;
let mediaRecorder = null;
let isRecording = false;
let lastTranscript = "";
let lastImagePrompt = "";

// ── TABS ─────────────────────────────────────────────────────────────────────
tabs.forEach(tab => {
  tab.addEventListener("click", () => {
    tabs.forEach(t => t.classList.remove("active"));
    tabContents.forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// ── DROPZONE ─────────────────────────────────────────────────────────────────
dropzone.addEventListener("click", () => imageInput.click());

dropzone.addEventListener("dragover", e => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", e => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith("image/")) loadImage(file);
});

imageInput.addEventListener("change", () => {
  if (imageInput.files[0]) loadImage(imageInput.files[0]);
});

function loadImage(file) {
  selectedImageFile = file;
  const url = URL.createObjectURL(file);
  preview.src = url;
  preview.hidden = false;
  dropInner.hidden = true;
  imageBtn.disabled = false;
}

// ── VOICE RECORDER ───────────────────────────────────────────────────────────
recordBtn.addEventListener("click", async () => {
  if (!isRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = e => chunks.push(e.data);
      mediaRecorder.onstop = () => {
        audioBlob = new Blob(chunks, { type: "audio/webm" });
        voiceBtn.disabled = false;
        recordStatus.textContent = "Recording saved ✓";
      };
      mediaRecorder.start();
      isRecording = true;
      recordBtn.textContent = "⏹ Stop Recording";
      recordBtn.classList.add("recording");
      recordStatus.textContent = "Recording...";
    } catch {
      showError("Microphone access denied.");
    }
  } else {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    isRecording = false;
    recordBtn.textContent = "🎙 Start Recording";
    recordBtn.classList.remove("recording");
  }
});

// ── GENERATE FROM IMAGE ───────────────────────────────────────────────────────
imageBtn.addEventListener("click", async () => {
  if (!selectedImageFile) return;
  const form = new FormData();
  form.append("file", selectedImageFile);
  form.append("tone", toneSelect.value);

  showProgress(10, "Analyzing your image...");
  hideError();
  resultBox.hidden = true;

  try {
    const res = await fetch(`${API}/caption-from-image`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    showProgress(100, "Done!");
    setTimeout(() => showResult(data), 400);
  } catch (err) {
    hideProgress();
    showError("Error: " + err.message);
  }
});

// ── GENERATE FROM VOICE ───────────────────────────────────────────────────────
voiceBtn.addEventListener("click", async () => {
  if (!audioBlob) return;
  const form = new FormData();
  form.append("file", audioBlob, "recording.webm");
  form.append("tone", toneSelect.value);

  hideError();
  resultBox.hidden = true;

  const evtSource = await fetch(`${API}/process-stream`, { method: "POST", body: form });
  const reader = evtSource.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      try {
        const event = JSON.parse(line.slice(5).trim());
        if (event.type === "progress") {
          showProgress(event.percent, event.message);
          if (event.transcript) lastTranscript = event.transcript;
        } else if (event.type === "complete") {
          showProgress(100, "Done!");
          setTimeout(() => showResult(event.data), 400);
        } else if (event.type === "error") {
          hideProgress();
          showError(event.detail);
        }
      } catch {}
    }
  }
});

// ── REGENERATE ────────────────────────────────────────────────────────────────
regenTextBtn.addEventListener("click", async () => {
  if (!lastTranscript) return;
  regenTextBtn.disabled = true;
  regenTextBtn.textContent = "⏳ Regenerating...";
  try {
    const res = await fetch(`${API}/regenerate-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: lastTranscript, tone: toneSelect.value }),
    });
    const data = await res.json();
    captionTA.value = data.pinterest_caption || "";
    hashtagsTA.value = data.hashtags || "";
    if (data.image_prompt) lastImagePrompt = data.image_prompt;
  } catch (err) {
    showError("Regenerate failed: " + err.message);
  } finally {
    regenTextBtn.disabled = false;
    regenTextBtn.textContent = "🔄 Regenerate Caption";
  }
});

regenImgBtn.addEventListener("click", async () => {
  if (!lastImagePrompt) return;
  regenImgBtn.disabled = true;
  regenImgBtn.textContent = "⏳ Generating...";
  try {
    const res = await fetch(`${API}/regenerate-image`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_prompt: lastImagePrompt }),
    });
    const data = await res.json();
    if (data.image_url) resultImg.src = data.image_url + "?t=" + Date.now();
  } catch (err) {
    showError("Image regeneration failed: " + err.message);
  } finally {
    regenImgBtn.disabled = false;
    regenImgBtn.textContent = "🔄 New Image";
  }
});

// ── COPY ──────────────────────────────────────────────────────────────────────
copyBtn.addEventListener("click", () => {
  const text = `${captionTA.value}\n\n${hashtagsTA.value}`;
  navigator.clipboard.writeText(text).then(() => {
    copyBtn.textContent = "✅ Copied!";
    setTimeout(() => copyBtn.textContent = "📋 Copy All", 2000);
  });
});

// ── HELPERS ───────────────────────────────────────────────────────────────────
function showProgress(percent, msg) {
  progressBox.hidden = false;
  progressFill.style.width = percent + "%";
  progressMsg.textContent = msg;
}
function hideProgress() {
  progressBox.hidden = true;
}
function showResult(data) {
  hideProgress();
  captionTA.value = data.pinterest_caption || "";
  hashtagsTA.value = data.hashtags || "";
  if (data.image_url) resultImg.src = data.image_url;
  if (data.image_prompt) lastImagePrompt = data.image_prompt;
  if (data.transcript) lastTranscript = data.transcript;
  resultBox.hidden = false;
}
function showError(msg) {
  errorBox.textContent = msg;
  errorBox.hidden = false;
}
function hideError() {
  errorBox.hidden = true;
}