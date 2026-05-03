// YouTube panel — Pattern Analytics.

const API = "/api/youtube";
const $ = (id) => document.getElementById(id);

async function generate() {
    const subject = $("ytSubject").value.trim();
    const kind = $("ytKind").value;
    const status = $("ytStatus");
    const btn = $("ytGenerateBtn");
    const result = $("ytResultCard");

    if (!subject) {
        status.textContent = "Type a video subject first.";
        return;
    }

    btn.disabled = true;
    status.textContent = "Generating…";
    try {
        const res = await fetch(`${API}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ subject, kind }),
        });
        if (!res.ok) {
            const detail = await res.text();
            throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const data = await res.json();
        $("ytTitle").textContent = data.title || "";
        $("ytDescription").textContent = data.description || "";
        $("ytThumb").textContent = data.thumbnail_prompt || "";
        $("ytTags").textContent = (data.tags || []).join(" ");
        result.hidden = false;
        status.textContent = "";
    } catch (err) {
        status.textContent = String(err.message || err);
    } finally {
        btn.disabled = false;
    }
}

async function copyAll() {
    const title = $("ytTitle").textContent;
    const desc = $("ytDescription").textContent;
    const thumb = $("ytThumb").textContent;
    const tags = $("ytTags").textContent;
    const text = `TITLE\n${title}\n\nDESCRIPTION\n${desc}\n\nTHUMBNAIL\n${thumb}\n\nTAGS\n${tags}`;
    try {
        await navigator.clipboard.writeText(text);
        $("ytStatus").textContent = "Copied everything.";
    } catch {
        $("ytStatus").textContent = "Copy failed.";
    }
}

$("ytGenerateBtn")?.addEventListener("click", () => { void generate(); });
$("ytCopyBtn")?.addEventListener("click", () => { void copyAll(); });
