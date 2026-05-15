// YouTube panel — Pattern Analytics.

const API = "/api/youtube";
const $ = (id) => document.getElementById(id);

const fileInput = $("ytFileInput");
const generateBtn = $("ytGenerateBtn");

function syncGenerateEnabled() {
    if (!generateBtn || !fileInput) return;
    generateBtn.disabled = !fileInput.files || fileInput.files.length === 0;
}

fileInput?.addEventListener("change", syncGenerateEnabled);
syncGenerateEnabled();

function renderResult(data) {
    $("ytTitle").textContent = data.title || "";
    $("ytThumb").src = data.thumbnail_url || "";
    const tags = Array.isArray(data.hashtags) ? data.hashtags.join(" ") : (data.hashtags || "");
    $("ytHashtags").textContent = tags;
    $("ytCaption").textContent = data.caption || "";
    const s = data.similarity_score ?? "?";
    const c = data.clip_score ?? "?";
    $("ytScores").textContent = `Sentence-BERT: ${s}    CLIP: ${c}`;
    $("ytResultCard").hidden = false;
}

async function generate() {
    const status = $("ytStatus");
    const btn = $("ytGenerateBtn");
    const result = $("ytResultCard");

    const file = fileInput?.files?.[0];
    if (!file) {
        status.textContent = "Choose an audio or video file first.";
        return;
    }

    btn.disabled = true;
    status.textContent = "Uploading…";
    result.hidden = true;

    const form = new FormData();
    form.append("file", file);

    try {
        const res = await fetch(`${API}/process-stream`, {
            method: "POST",
            body: form,
        });
        if (!res.ok || !res.body) {
            const detail = await res.text().catch(() => "");
            throw new Error(`HTTP ${res.status}: ${detail}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalPayload = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buffer.indexOf("\n\n")) !== -1) {
                const chunk = buffer.slice(0, idx).trim();
                buffer = buffer.slice(idx + 2);
                if (!chunk.startsWith("data:")) continue;
                const jsonStr = chunk.slice(5).trim();
                if (!jsonStr) continue;
                let evt;
                try { evt = JSON.parse(jsonStr); } catch { continue; }
                if (evt.type === "progress") {
                    status.textContent = evt.message || "Working…";
                } else if (evt.type === "complete") {
                    finalPayload = evt.data;
                } else if (evt.type === "error") {
                    throw new Error(evt.detail || "Server error");
                }
            }
        }

        if (!finalPayload) throw new Error("No result returned.");
        renderResult(finalPayload);
        status.textContent = "Done.";
    } catch (err) {
        status.textContent = String(err?.message || err);
    } finally {
        syncGenerateEnabled();
    }
}

async function copyAll() {
    const title = $("ytTitle").textContent;
    const tags = $("ytHashtags").textContent;
    const text = `TITLE\n${title}\n\nHASHTAGS\n${tags}`;
    try {
        await navigator.clipboard.writeText(text);
        $("ytStatus").textContent = "Copied.";
    } catch {
        $("ytStatus").textContent = "Copy failed.";
    }
}

$("ytGenerateBtn")?.addEventListener("click", () => { void generate(); });
$("ytCopyBtn")?.addEventListener("click", () => { void copyAll(); });
