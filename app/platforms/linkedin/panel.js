// LinkedIn panel — Pattern Analytics.

const API = "/api/linkedin";
const $ = (id) => document.getElementById(id);

async function generate() {
    const topic = $("liTopic").value.trim();
    const role = $("liRole").value;
    const status = $("liStatus");
    const btn = $("liGenerateBtn");
    const result = $("liResultCard");

    if (!topic) {
        status.textContent = "Type a topic first.";
        return;
    }

    btn.disabled = true;
    status.textContent = "Generating…";
    try {
        const res = await fetch(`${API}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic, role }),
        });
        if (!res.ok) {
            const detail = await res.text();
            throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        $("liPost").textContent = data.post || "";
        result.hidden = false;
        status.textContent = "";
    } catch (err) {
        status.textContent = String(err.message || err);
    } finally {
        btn.disabled = false;
    }
}

async function copyPost() {
    const text = $("liPost").textContent;
    try {
        await navigator.clipboard.writeText(text);
        $("liStatus").textContent = "Copied.";
    } catch {
        $("liStatus").textContent = "Copy failed.";
    }
}

$("liGenerateBtn")?.addEventListener("click", () => { void generate(); });
$("liCopyBtn")?.addEventListener("click", () => { void copyPost(); });
