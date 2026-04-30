let mediaRecorder, audioChunks = [], isRecording = false, recordingStartTime = 0, timerInterval;
let liveRecognition = null;
let liveCaptionsActive = false;
let liveCaptionFinal = "";

const ARC_CIRC = 408;
const MAX_REC_SECS = 120;

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
    box.classList.remove("error", "info");
    box.classList.add("active", type);
    document.getElementById("statusLabel").innerText = label;
    document.getElementById("statusText").innerText = text;
    document.getElementById("statusHint").innerText = hint;
}

function clearStatus() {
    const box = document.getElementById("statusBox");
    box.classList.remove("active", "error", "info");
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
            if (event.results[i].isFinal) {
                liveCaptionFinal += piece;
            } else {
                interim += piece;
            }
        }
        const combined = (liveCaptionFinal + interim).trim();
        textEl.textContent = combined || "…";
    };

    rec.onerror = (ev) => {
        if (ev.error === "not-allowed") {
            hintEl.textContent = "Live captions blocked. Allow microphone permission.";
        } else if (ev.error !== "aborted" && ev.error !== "no-speech") {
            hintEl.textContent = `Live captions error: ${ev.error}`;
        }
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
                processingCard.classList.add("active");
                postCard.classList.remove("active");
                updateStage(1, "active");

                try {
                    const res = await fetch("/process", { method: "POST", body: form });
                    if (!res.ok) {
                        let detail = `Server error: ${res.status}`;
                        try {
                            const errBody = await res.json();
                            if (errBody.detail) detail = errBody.detail;
                        } catch (_) {}
                        throw new Error(detail);
                    }
                    const data = await res.json();

                    updateStage(1, "complete");
                    updateStage(2, "active");
                    document.getElementById("transcriptSection").style.display = "block";
                    document.getElementById("transcriptText").innerText = data.transcript;

                    await new Promise((r) => setTimeout(r, 350));
                    updateStage(2, "complete");
                    updateStage(3, "active");
                    await new Promise((r) => setTimeout(r, 350));
                    updateStage(3, "complete");

                    processingCard.classList.remove("active");
                    postCard.classList.add("active");
                    document.getElementById("postTitle").innerText = data.reddit_title;
                    document.getElementById("postBody").innerText = data.reddit_body;

                    const postImage = document.getElementById("postImage");
                    if (data.image_url) {
                        postImage.src = data.image_url;
                        postImage.style.display = "block";
                    } else {
                        postImage.removeAttribute("src");
                        postImage.style.display = "none";
                    }

                    if (data.image_error) {
                        setStatus("info", "Image", "Text generated but image failed.", data.image_error);
                    } else {
                        clearStatus();
                    }
                } catch (error) {
                    processingCard.classList.remove("active");
                    setStatus("error", "Processing", "Failed to process the audio.", String(error.message || error));
                    postCard.innerHTML = `<div class="error-msg">Error processing request: ${error.message}</div>`;
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

document.addEventListener("DOMContentLoaded", initRecordingButton);
