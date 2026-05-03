// Twitter / X panel — Pattern Analytics.

const API = "/api/twitter";
const $ = (id) => document.getElementById(id);

async function generate() {
    const topic = $("twTopic").value.trim();
    const tone = $("twTone").value;
    const status = $("twStatus");
    const btn = $("twGenerateBtn");
    const result = $("twResultCard");

    if (!topic) {
        status.textContent = "Type something first.";
        return;
    }

    btn.disabled = true;
    status.textContent = "Generating…";
    try {
        const res = await fetch(`${API}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic, tone }),
        });
        if (!res.ok) {
            const detail = await res.text();
            throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        $("twPost").textContent = data.post || "";
        result.hidden = false;
        status.textContent = "";
    } catch (err) {
        status.textContent = String(err.message || err);
    } finally {
        btn.disabled = false;
    }
}

async function copyPost() {
    const text = $("twPost").textContent;
    try {
        await navigator.clipboard.writeText(text);
        $("twStatus").textContent = "Copied.";
    } catch {
        $("twStatus").textContent = "Copy failed.";
    }
}

$("twGenerateBtn")?.addEventListener("click", () => { void generate(); });
$("twCopyBtn")?.addEventListener("click", () => { void copyPost(); });
