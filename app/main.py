import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse


def _early_load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip()


_early_load_dotenv()

from .pipeline import generate_image, generate_reddit_content, transcribe_voice

app = FastAPI(title="Voice-to-Reddit API")
OUTPUT_DIR = Path("output_images")
OUTPUT_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def get_index() -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Voice-to-Reddit AI</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --card-bg: #ffffff;
                --header-bg: #ff4500;
                --text: #1c1c1c;
                --text-light: #666;
                --muted: #999;
                --accent: #ff4500;
                --success: #4caf50;
                --border: #e0e0e0;
                --shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Inter', -apple-system, sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                padding-bottom: 40px;
            }
            header {
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 20px 24px;
                display: flex;
                align-items: center;
                gap: 12px;
                box-shadow: var(--shadow);
            }
            header h1 { color: #fff; font-size: 24px; font-weight: 800; }
            .layout {
                max-width: 800px;
                margin: 30px auto;
                padding: 0 16px;
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            .card {
                background: var(--card-bg);
                border: none;
                border-radius: 12px;
                padding: 32px;
                box-shadow: var(--shadow);
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }
            .card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.15); }
            .card h2 { font-size: 20px; font-weight: 800; margin-bottom: 8px; color: var(--text); }
            .card p.sub { font-size: 14px; color: var(--text-light); margin-bottom: 28px; line-height: 1.5; }
            
            .record-section { display: flex; flex-direction: column; align-items: center; gap: 20px; }
            
            .record-button {
                width: 120px;
                height: 120px;
                border-radius: 50%;
                border: none;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-size: 48px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: var(--shadow);
                transition: all 0.3s ease;
            }
            .record-button:hover { transform: scale(1.05); box-shadow: 0 8px 30px rgba(102, 126, 234, 0.4); }
            .record-button.recording {
                background: linear-gradient(135deg, #f44336 0%, #c62828 100%);
                animation: pulse-record 1.5s ease-in-out infinite;
            }
            @keyframes pulse-record {
                0%, 100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7); }
                50% { box-shadow: 0 0 0 20px rgba(244, 67, 54, 0); }
            }
            
            .timer { font-size: 18px; font-weight: 700; color: var(--accent); font-family: monospace; }
            .recording-indicator { display: none; text-align: center; }
            .recording-indicator.active { display: block; animation: fadeIn 0.3s ease; }
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            
            .waveform { display: flex; align-items: flex-end; gap: 4px; height: 40px; }
            .waveform-bar { width: 4px; background: linear-gradient(to top, #667eea, #764ba2); border-radius: 2px; animation: waveform-animate 0.6s ease-in-out infinite; }
            @keyframes waveform-animate {
                0%, 100% { height: 8px; }
                50% { height: 35px; }
            }
            .waveform-bar:nth-child(1) { animation-delay: 0s; }
            .waveform-bar:nth-child(2) { animation-delay: 0.1s; }
            .waveform-bar:nth-child(3) { animation-delay: 0.2s; }
            .waveform-bar:nth-child(4) { animation-delay: 0.3s; }
            .waveform-bar:nth-child(5) { animation-delay: 0.4s; }
            
            .progress-stages { display: flex; justify-content: space-between; align-items: center; margin: 30px 0; gap: 8px; }
            .stage {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
            }
            .stage-icon {
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: #f0f0f0;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                transition: all 0.3s ease;
            }
            .stage.active .stage-icon {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                box-shadow: 0 0 0 8px rgba(102, 126, 234, 0.2);
                animation: pulse 1.5s ease-in-out infinite;
            }
            .stage.complete .stage-icon {
                background: var(--success);
            }
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.08); }
            }
            .stage-label { font-size: 12px; font-weight: 600; color: var(--muted); text-align: center; }
            .stage-arrow { color: #e0e0e0; font-size: 20px; }
            .stage-arrow:last-child { display: none; }
            
            .processing-card { display: none; }
            .processing-card.active {
                display: block;
                animation: slideUp 0.3s ease;
            }
            @keyframes slideUp {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            .transcript-section {
                background: linear-gradient(135deg, #f5f7ff 0%, #f0f3ff 100%);
                border-left: 4px solid #667eea;
                padding: 16px 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }
            .transcript-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #667eea; letter-spacing: 0.5px; margin-bottom: 8px; }
            .transcript-text {
                font-size: 16px;
                line-height: 1.6;
                color: var(--text);
                font-weight: 500;
                word-wrap: break-word;
            }
            
            .post-card { display: none; animation: slideUp 0.5s ease; }
            .post-card.active { display: block; }
            .post-meta { font-size: 12px; color: var(--muted); margin-bottom: 12px; font-weight: 600; }
            .post-title {
                font-size: 24px;
                font-weight: 800;
                line-height: 1.3;
                margin-bottom: 16px;
                color: var(--text);
            }
            .post-body {
                font-size: 15px;
                line-height: 1.8;
                white-space: pre-wrap;
                margin-bottom: 20px;
                color: var(--text-light);
            }
            .post-image {
                width: 100%;
                border-radius: 8px;
                border: 1px solid var(--border);
                margin-bottom: 20px;
                transition: transform 0.3s ease;
            }
            .post-image:hover { transform: scale(1.01); }
            .post-actions {
                display: flex;
                gap: 16px;
                padding-top: 16px;
                border-top: 1px solid var(--border);
            }
            .action-btn {
                flex: 1;
                font-size: 13px;
                font-weight: 700;
                color: var(--muted);
                background: none;
                border: none;
                padding: 12px;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .action-btn:hover { background: #f5f5f5; color: var(--accent); }
            
            .error-msg {
                background: #ffebee;
                color: #c62828;
                padding: 16px;
                border-radius: 8px;
                border-left: 4px solid #f44336;
                margin-bottom: 16px;
                font-weight: 600;
            }
            .status-box {
                display: none;
                width: 100%;
                max-width: 520px;
                border-radius: 10px;
                padding: 14px 16px;
                background: #f5f7ff;
                border-left: 4px solid #667eea;
                color: #2a3a8f;
                font-size: 14px;
                line-height: 1.5;
            }
            .status-box.active { display: block; }
            .status-box.error {
                background: #ffebee;
                color: #c62828;
                border-left-color: #f44336;
            }
            .status-box.info {
                background: #eef6ff;
                color: #1e3c72;
                border-left-color: #3f51b5;
            }
            .status-label {
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.6px;
                font-weight: 700;
                margin-bottom: 6px;
            }
            .status-hint {
                color: var(--muted);
                font-size: 12px;
                margin-top: 6px;
            }
        </style>
    </head>
    <body>
        <header>
            <span style="font-size:32px">🎙️</span>
            <h1>Voice-to-Reddit AI</h1>
        </header>
        <div class="layout">
            <!-- Recording Card -->
            <div class="card">
                <h2>📝 Create a Reddit Post</h2>
                <p class="sub">Speak your mind. The AI will transform your voice into a complete Reddit post with title, content, and an AI-generated image.</p>
                <div class="record-section">
                    <button id="recordBtn" class="record-button" onclick="toggleRecording()">
                        <span id="btnIcon">🔴</span>
                    </button>
                    <div>
                        <div style="font-size: 16px; font-weight: 700; color: var(--text);">
                            <span id="btnText">Start Recording</span>
                        </div>
                        <div id="timer" class="timer" style="display:none;">0:00</div>
                    </div>
                    <div id="recordingIndicator" class="recording-indicator">
                        <div class="waveform">
                            <div class="waveform-bar"></div>
                            <div class="waveform-bar"></div>
                            <div class="waveform-bar"></div>
                            <div class="waveform-bar"></div>
                            <div class="waveform-bar"></div>
                        </div>
                        <p style="margin-top: 12px; color: var(--accent); font-weight: 700;">Recording...</p>
                    </div>
                    <div id="statusBox" class="status-box">
                        <div class="status-label" id="statusLabel">Status</div>
                        <div id="statusText"></div>
                        <div class="status-hint" id="statusHint"></div>
                    </div>
                </div>
            </div>
            
            <!-- Progress Stages -->
            <div class="card processing-card" id="processingCard">
                <div class="progress-stages">
                    <div class="stage active" id="stage1">
                        <div class="stage-icon">🎙️</div>
                        <div class="stage-label">Transcribing</div>
                    </div>
                    <div class="stage-arrow">→</div>
                    <div class="stage" id="stage2">
                        <div class="stage-icon">🧠</div>
                        <div class="stage-label">Generating</div>
                    </div>
                    <div class="stage-arrow">→</div>
                    <div class="stage" id="stage3">
                        <div class="stage-icon">🎨</div>
                        <div class="stage-label">Creating Image</div>
                    </div>
                </div>
                <div id="transcriptSection" class="transcript-section" style="display:none;">
                    <div class="transcript-label">📢 What we heard:</div>
                    <div class="transcript-text" id="transcriptText"></div>
                </div>
            </div>
            
            <!-- Reddit Post Preview -->
            <div class="card post-card" id="postCard">
                <div class="post-meta">r/general · Posted by <strong>u/VoiceAI_Bot</strong> · just now</div>
                <div class="post-title" id="postTitle"></div>
                <div class="post-body" id="postBody"></div>
                <img class="post-image" id="postImage" src="" alt="AI Generated Image" />
                <div class="post-actions">
                    <button class="action-btn">⬆️ Upvote</button>
                    <button class="action-btn">⬇️ Downvote</button>
                    <button class="action-btn">💬 Comment</button>
                    <button class="action-btn">🔗 Share</button>
                </div>
            </div>
        </div>
        <script>
            let mediaRecorder, audioChunks = [], isRecording = false, recordingStartTime = 0, timerInterval;

            function updateTimer() {
                const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                document.getElementById('timer').innerText = \`\${mins}:\${secs.toString().padStart(2, '0')}\`;
            }

            function showError(message) {
                setStatus("error", "Recording error", message, "Check microphone permissions and try again.");
                console.error(message);
            }

            function setStatus(type, label, text, hint = "") {
                const box = document.getElementById("statusBox");
                const statusLabel = document.getElementById("statusLabel");
                const statusText = document.getElementById("statusText");
                const statusHint = document.getElementById("statusHint");
                box.classList.remove("error", "info");
                box.classList.add("active", type);
                statusLabel.innerText = label;
                statusText.innerText = text;
                statusHint.innerText = hint;
            }

            function clearStatus() {
                const box = document.getElementById("statusBox");
                box.classList.remove("active", "error", "info");
            }

            function getSupportedMimeType() {
                const candidates = [
                    "audio/webm;codecs=opus",
                    "audio/webm",
                    "audio/ogg;codecs=opus",
                    "audio/ogg"
                ];
                for (const type of candidates) {
                    if (MediaRecorder.isTypeSupported(type)) {
                        return type;
                    }
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
                        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                        mediaRecorder.onerror = event => {
                            showError("Recorder error: " + (event.error?.message || "Unknown error"));
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
                                if (!res.ok) throw new Error(\`Server error: \${res.status}\`);
                                const data = await res.json();

                                // Show transcript
                                updateStage(1, "complete");
                                updateStage(2, "active");
                                document.getElementById("transcriptSection").style.display = "block";
                                document.getElementById("transcriptText").innerText = data.transcript;

                                // Simulate generation stage
                                await new Promise(r => setTimeout(r, 500));
                                updateStage(2, "complete");
                                updateStage(3, "active");
                                
                                await new Promise(r => setTimeout(r, 500));
                                updateStage(3, "complete");

                                // Show result
                                processingCard.classList.remove("active");
                                postCard.classList.add("active");
                                document.getElementById("postTitle").innerText = data.reddit_title;
                                document.getElementById("postBody").innerText = data.reddit_body;
                                document.getElementById("postImage").src = data.image_url;
                            } catch (error) {
                                console.error("Processing error:", error);
                                processingCard.classList.remove("active");
                                setStatus("error", "Processing", "Failed to process the audio.", "Check the server logs and try again.");
                                const errorDiv = document.createElement("div");
                                errorDiv.className = "error-msg";
                                errorDiv.innerText = "❌ Error processing your request. " + error.message;
                                postCard.innerHTML = "";
                                postCard.prepend(errorDiv);
                                postCard.classList.add("active");
                            }
                        };
                        mediaRecorder.start();
                        isRecording = true;
                        btnIcon.innerText = "⏹";
                        btnText.innerText = "Stop Recording";
                        btn.classList.add("recording");
                        timer.style.display = "block";
                        recordingIndicator.classList.add("active");
                        recordingStartTime = Date.now();
                        timerInterval = setInterval(updateTimer, 100);
                    } catch (error) {
                        console.error("Recording error:", error);
                        let errorMsg = "Could not access microphone. ";
                        if (error.name === "NotAllowedError") {
                            errorMsg += "Please allow microphone access in your browser settings.";
                        } else if (error.name === "NotFoundError") {
                            errorMsg += "No microphone found. Please check your audio device.";
                        } else if (error.name === "NotSupportedError") {
                            errorMsg += "Recording is not supported in your browser.";
                        } else {
                            errorMsg += error.message || "Unknown error occurred.";
                        }
                        showError(errorMsg);
                    }
                } else {
                    // Stop recording
                    console.log("Stopping recording...");
                    if (mediaRecorder && mediaRecorder.state !== "inactive") {
                        mediaRecorder.stop();
                    }
                    isRecording = false;
                    btnIcon.innerText = "🔴";
                    btnText.innerText = "Start Recording";
                    btn.classList.remove("recording");
                    timer.style.display = "none";
                    recordingIndicator.classList.remove("active");
                    clearInterval(timerInterval);
                    // Stop audio stream
                    if (mediaRecorder && mediaRecorder.stream) {
                        mediaRecorder.stream.getTracks().forEach(track => track.stop());
                    }
                }
            }

            function updateStage(stageNum, status) {
                const stage = document.getElementById(\`stage\${stageNum}\`);
                if (status === "active") {
                    stage.classList.remove("complete");
                    stage.classList.add("active");
                } else if (status === "complete") {
                    stage.classList.remove("active");
                    stage.classList.add("complete");
                    const icon = stage.querySelector(".stage-icon");
                    const labels = ["", "✓", "✓", "✓"];
                    icon.innerText = labels[stageNum];
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/process")
async def process_audio(file: Annotated[UploadFile, File(...)]):
    suffix = Path(file.filename or "recording.webm").suffix or ".webm"
    audio_path = Path(f"temp_{uuid.uuid4()}{suffix}")
    audio_path.write_bytes(await file.read())

    transcript = transcribe_voice(str(audio_path))
    content = generate_reddit_content(transcript)

    title = content.get("reddit_title", "Untitled")
    body = content.get("reddit_body", "")
    image_prompt = content.get("image_prompt", "Abstract colorful background")

    image = generate_image(image_prompt)
    image_filename = f"{uuid.uuid4()}.png"
    image_path = OUTPUT_DIR / image_filename
    image.save(image_path)

    audio_path.unlink(missing_ok=True)

    return {
        "transcript": transcript,
        "reddit_title": title,
        "reddit_body": body,
        "image_url": f"/images/{image_filename}",
    }


@app.get("/images/{filename}")
async def get_image(filename: str):
    return FileResponse(OUTPUT_DIR / filename)


# -----------------------------------------------------------------------------
# Canonical app export (overrides legacy inline app above)
# -----------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles

from .api.routes import router as api_router
from .core.config import STATIC_DIR


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip()


def create_app() -> FastAPI:
    app_instance = FastAPI(title="Voice-to-Reddit API")
    app_instance.include_router(api_router)
    app_instance.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app_instance


_load_dotenv()
app = create_app()
