// Dashboard shell — fetches /api/platforms, renders sidebar tabs,
// and dynamically loads each platform's panel.html / panel.css / panel.js
// when its tab is activated.

const PLATFORMS_ENDPOINT = "/api/platforms";

let platforms = [];
let activeId = null;

const tabsEl = document.getElementById("shellTabs");
const mountEl = document.getElementById("shellPanelMount");
const emptyEl = document.getElementById("shellEmpty");
const headerEl = document.getElementById("shellPanelHeader");
const headerIcon = document.getElementById("shellPanelIcon");
const headerLabel = document.getElementById("shellPanelLabel");
const headerTagline = document.getElementById("shellPanelTagline");
const headerOwner = document.getElementById("shellPanelOwner");
const toastEl = document.getElementById("shellToast");

function buildTabs() {
    tabsEl.innerHTML = "";
    for (const p of platforms) {
        const li = document.createElement("li");
        li.className = "shell-tab";
        li.dataset.platform = p.id;
        li.style.setProperty("--tab-accent", p.accent || "#6366f1");

        const icon = document.createElement("span");
        icon.className = "shell-tab-icon";
        icon.textContent = p.icon || "·";
        icon.style.color = p.accent || "var(--accent-2)";

        const label = document.createElement("span");
        label.className = "shell-tab-label";
        label.textContent = p.label;

        li.appendChild(icon);
        li.appendChild(label);
        if (p.owner && String(p.owner).trim()) {
            const owner = document.createElement("span");
            owner.className = "shell-tab-owner";
            owner.textContent = p.owner;
            li.appendChild(owner);
        }
        li.addEventListener("click", () => activatePlatform(p.id, true));
        tabsEl.appendChild(li);
    }
}

function setActiveTab(id) {
    for (const li of tabsEl.querySelectorAll(".shell-tab")) {
        li.classList.toggle("active", li.dataset.platform === id);
    }
}

function clearMount() {
    mountEl.innerHTML = "";
    mountEl.dataset.platform = "";

    document.querySelectorAll("link[data-panel-css]").forEach((el) => el.remove());
    document.querySelectorAll("script[data-panel-js]").forEach((el) => el.remove());
}

function showHeader(p) {
    headerIcon.textContent = p.icon || "·";
    headerIcon.style.color = p.accent || "var(--accent-2)";
    headerIcon.style.borderColor = p.accent ? `${p.accent}55` : "var(--border)";
    headerLabel.textContent = p.label;
    headerTagline.textContent = p.tagline || "";
    if (p.owner && String(p.owner).trim()) {
        headerOwner.textContent = `Owned by ${p.owner}`;
        headerOwner.hidden = false;
    } else {
        headerOwner.textContent = "";
        headerOwner.hidden = true;
    }
    headerEl.hidden = false;
}

async function loadPanelHtml(p) {
    const res = await fetch(p.panel_html_url, { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed to load ${p.id} panel.html (HTTP ${res.status})`);
    return await res.text();
}

function loadPanelCss(p) {
    return new Promise((resolve) => {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = `${p.panel_css_url}?v=${Date.now()}`;
        link.dataset.panelCss = p.id;
        link.onload = () => resolve();
        link.onerror = () => resolve();
        document.head.appendChild(link);
    });
}

function loadPanelJs(p) {
    return new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.type = "module";
        s.src = `${p.panel_js_url}?v=${Date.now()}`;
        s.dataset.panelJs = p.id;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error(`Failed to load ${p.id} panel.js`));
        document.body.appendChild(s);
    });
}

async function activatePlatform(id, updateHash) {
    const p = platforms.find((x) => x.id === id);
    if (!p) return;
    if (activeId === id) return;

    activeId = id;
    setActiveTab(id);
    if (updateHash) history.replaceState(null, "", `#${id}`);

    clearMount();
    emptyEl.style.display = "none";
    mountEl.dataset.platform = id;
    mountEl.innerHTML = `<div class="shell-empty"><div class="shell-empty-icon">…</div><p>Loading ${p.label}…</p></div>`;

    showHeader(p);

    try {
        const html = await loadPanelHtml(p);
        await loadPanelCss(p);
        mountEl.innerHTML = html;
        await loadPanelJs(p);
    } catch (err) {
        console.error(err);
        mountEl.innerHTML = `<div class="shell-empty"><div class="shell-empty-icon">!</div><p>Could not load ${p.label}: ${err.message}</p></div>`;
    }
}

function pickInitialPlatform() {
    const hash = (window.location.hash || "").replace(/^#/, "").trim();
    if (hash && platforms.some((p) => p.id === hash)) return hash;
    return platforms[0]?.id || null;
}

window.PlatformShell = {
    toast(message, ms = 2400) {
        if (!toastEl) return;
        toastEl.textContent = message;
        toastEl.hidden = false;
        setTimeout(() => { toastEl.hidden = true; }, ms);
    },
    setBusy(busy) {
        document.body.style.cursor = busy ? "progress" : "";
    },
    activePlatformId() {
        return activeId;
    },
};

window.addEventListener("hashchange", () => {
    const id = (window.location.hash || "").replace(/^#/, "");
    if (id && platforms.some((p) => p.id === id)) activatePlatform(id, false);
});

(async function init() {
    try {
        const res = await fetch(PLATFORMS_ENDPOINT, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        platforms = data.platforms || [];
    } catch (err) {
        emptyEl.innerHTML = `<div class="shell-empty-icon">!</div><p>Could not load platforms list: ${err.message}</p>`;
        return;
    }

    if (!platforms.length) {
        emptyEl.innerHTML = `<div class="shell-empty-icon">·</div><p>No platforms registered yet.</p>`;
        return;
    }

    buildTabs();
    const initial = pickInitialPlatform();
    if (initial) activatePlatform(initial, true);
})();
