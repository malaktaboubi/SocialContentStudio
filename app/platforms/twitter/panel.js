// Twitter panel logic. Replicating Reddit's flow but for Twitter.

const API = "/api/twitter";
let mediaRecorder, audioChunks = [], isRecording = false, recordingStartTime = 0, timerInterval;

const ARC_CIRC = 408;
const MAX_REC_SECS = 120;
let lastTranscript = "";

async function loadTones() {
    const sel = document.getElementById("twToneSelect");
    if (!sel) return;
    try {
        const res = await fetch(`${API}/tones`);
        const data = await res.json();
        sel.innerHTML = data.tones.map(t => `<option value="${t.id}">${t.label}</option>`).join("");
    } catch (e) {
        sel.innerHTML = "<option value='default'>Standard Tweet</option>";
    }
}

function updateTimer() {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    document.getElementById("twTimer").innerText = `${mins}:${secs.toString().padStart(2, "0")}`;
    
    const arc = document.getElementById("twRingArc");
    if (arc) {
        const progress = Math.min(elapsed / MAX_REC_SECS, 1);
        arc.style.strokeDashoffset = ARC_CIRC * (1 - progress);
    }
}

async function toggleRecording() {
    const btn = document.getElementById("twRecordBtn");
    const btnText = document.getElementById("twBtnText");
    const btnIcon = document.getElementById("twBtnIcon");
    const timer = document.getElementById("twTimer");
    const processingCard = document.getElementById("twProcessingCard");
    const postCard = document.getElementById("twPostCard");

    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                const blob = new Blob(audioChunks, { type: "audio/webm" });
                const form = new FormData();
                form.append("file", blob);
                form.append("tone", document.getElementById("twToneSelect").value);

                processingCard.classList.add("active");
                postCard.classList.remove("active");
                
                try {
                    const res = await fetch(`${API}/process-stream`, { method: "POST", body: form });
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        const chunk = decoder.decode(value);
                        const lines = chunk.split("\n\n");
                        for (const line of lines) {
                            if (line.startsWith("data: ")) {
                                const ev = JSON.parse(line.slice(6));
                                if (ev.type === "progress") applyProgress(ev);
                                if (ev.type === "complete") applyData(ev.data);
                            }
                        }
                    }
                    processingCard.classList.remove("active");
                    postCard.classList.add("active");
                } catch (e) {
                    console.error(e);
                }
            };
            mediaRecorder.start();
            isRecording = true;
            btnIcon.innerText = "⏹";
            btnText.innerText = "Stop";
            timer.style.display = "block";
            recordingStartTime = Date.now();
            timerInterval = setInterval(updateTimer, 200);
        } catch (e) { console.error(e); }
    } else {
        mediaRecorder.stop();
        isRecording = false;
        btnIcon.innerText = "⏺";
        btnText.innerText = "Start Recording";
        timer.style.display = "none";
        clearInterval(timerInterval);
    }
}

function applyProgress(ev) {
    document.getElementById("twProgressBarFill").style.width = `${ev.percent}%`;
    document.getElementById("twProgressMessage").innerText = ev.message;
    document.getElementById("twProgressPercent").innerText = `${ev.percent}%`;
    if (ev.transcript) {
        document.getElementById("twTranscriptSection").style.display = "block";
        document.getElementById("twTranscriptText").innerText = ev.transcript;
        lastTranscript = ev.transcript;
    }
}

function applyData(data) {
    document.getElementById("twEditBody").value = data.twitter_body;
    document.getElementById("twEditImagePrompt").value = data.image_prompt;
    const img = document.getElementById("twPostImage");
    if (data.image_url) {
        img.src = data.image_url;
        img.style.display = "block";
    } else {
        img.style.display = "none";
    }
}

async function regenerateText() {
    const tone = document.getElementById("twToneSelect").value;
    const res = await fetch(`${API}/regenerate-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: lastTranscript, tone })
    });
    const data = await res.json();
    document.getElementById("twEditBody").value = data.twitter_body;
    document.getElementById("twEditImagePrompt").value = data.image_prompt;
}

async function regenerateImage() {
    const prompt = document.getElementById("twEditImagePrompt").value;
    const res = await fetch(`${API}/regenerate-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_prompt: prompt })
    });
    const data = await res.json();
    if (data.image_url) {
        document.getElementById("twPostImage").src = data.image_url;
    }
}

document.getElementById("twRecordBtn")?.addEventListener("click", toggleRecording);
document.getElementById("twRegenTextBtn")?.addEventListener("click", regenerateText);
document.getElementById("twRegenImageBtn")?.addEventListener("click", regenerateImage);
document.getElementById("twCopyBtn")?.addEventListener("click", () => {
    navigator.clipboard.writeText(document.getElementById("twEditBody").value);
});

loadTones();
