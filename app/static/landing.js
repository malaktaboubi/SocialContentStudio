// Landing — fetches /api/platforms and renders platform cards in #platforms only.
// Footer shows the group name only (no platform list).

const PLATFORMS_ENDPOINT = "/api/platforms";

const grid = document.getElementById("ldPlatformsGrid");
const credits = document.getElementById("ldFooterCredits");

function renderEmpty(message) {
    grid.innerHTML = `<div class="ld-platforms-empty">${message}</div>`;
}

function renderPlatforms(platforms) {
    if (!platforms.length) {
        renderEmpty("No platforms registered yet. Drop a folder in <code>app/platforms/</code> and refresh.");
        return;
    }

    grid.innerHTML = "";
    for (const p of platforms) {
        const card = document.createElement("a");
        card.className = "ld-platform-card";
        card.href = `/app#${p.id}`;
        if (p.accent) card.style.setProperty("--accent-color", p.accent);

        const head = document.createElement("div");
        head.className = "ld-platform-head";

        const icon = document.createElement("div");
        icon.className = "ld-platform-icon";
        icon.textContent = p.icon || "·";
        if (p.accent) {
            icon.style.color = p.accent;
            icon.style.borderColor = `${p.accent}55`;
        }

        const label = document.createElement("h3");
        label.className = "ld-platform-label";
        label.textContent = p.label;

        head.appendChild(icon);
        head.appendChild(label);

        const tagline = document.createElement("p");
        tagline.className = "ld-platform-tagline";
        tagline.textContent = p.tagline || "";

        const foot = document.createElement("div");
        foot.className = "ld-platform-foot";

        const owner = document.createElement("span");
        owner.className = "ld-platform-owner";
        owner.textContent = p.owner ? `By ${p.owner}` : "";

        const open = document.createElement("span");
        open.className = "ld-platform-open";
        open.textContent = "Open →";

        foot.appendChild(owner);
        foot.appendChild(open);

        card.appendChild(head);
        card.appendChild(tagline);
        card.appendChild(foot);
        grid.appendChild(card);
    }
}

function renderCredits() {
    if (!credits) return;
    credits.innerHTML = "";
    const group = document.createElement("span");
    group.className = "ld-footer-group-name";
    group.textContent = "Pattern Analytics";
    credits.appendChild(group);
}

(async function init() {
    try {
        const res = await fetch(PLATFORMS_ENDPOINT, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const platforms = data.platforms || [];
        renderPlatforms(platforms);
        renderCredits();
    } catch (err) {
        renderEmpty(`Could not load platforms list: ${err.message}`);
        renderCredits();
    }
})();
