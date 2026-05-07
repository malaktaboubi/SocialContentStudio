const API = "/api/linkedin";
const $ = (id) => document.getElementById(id);

let _uploadedImage = null;

function updateControls() {
    const hasImage = Boolean(_uploadedImage);
    $("liGenerateBtn").disabled = !hasImage;
    $("liRegenerateBtn").disabled = !hasImage;
    $("liRemoveImg").hidden = !hasImage;
}

// Image Selection Logic[cite: 1, 2]
$("liDropZone").onclick = () => $("liFileInput").click();
$("liFileInput").onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
        _uploadedImage = event.target.result;
        $("liPreviewImg").src = _uploadedImage;
        $("liDropZone").hidden = true;
        $("liPreviewWrap").hidden = false;
        $("liClearImg").hidden = false;
        updateControls();
    };
    reader.readAsDataURL(file);
};

function clearImage() {
    _uploadedImage = null;
    $("liDropZone").hidden = false;
    $("liPreviewWrap").hidden = true;
    $("liFileInput").value = "";
    $("liClearImg").hidden = true;
    updateControls();
}

$("liClearImg").onclick = clearImage;
$("liRemoveImg").onclick = clearImage;

// Generation Logic[cite: 1, 2, 7]
async function generate() {
    const status = $("liStatus");
    const btn = $("liGenerateBtn");
    const regenBtn = $("liRegenerateBtn");

    btn.disabled = true;
    regenBtn.disabled = true;
    status.textContent = "Processing image...";
    
    if (_uploadedImage) {
        $("liScanOverlay").hidden = false;
        let p = 0;
        const inv = setInterval(() => {
            p += 10;
            $("liProgressFill").style.width = p + "%";
            if(p >= 100) clearInterval(inv);
        }, 100);
    }

    try {
        const res = await fetch(`${API}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image: _uploadedImage }),
        });
        
        const data = await res.json();
        
        // Map to vertical slots[cite: 1, 2]
        $("liPost0").textContent = data.professional || data.post;
        $("liPost1").textContent = data.short || data.post;
        $("liPost2").textContent = data.story || data.post;

        $("liScanOverlay").hidden = true;
        $("liResultCard").hidden = false;
        status.textContent = "";
    } catch (err) {
        status.textContent = "Error generating captions.";
        $("liScanOverlay").hidden = true;
    } finally {
        btn.disabled = false;
        regenBtn.disabled = false;
    }
}

$("liGenerateBtn")?.addEventListener("click", generate);
$("liRegenerateBtn")?.addEventListener("click", generate);

updateControls();

// Copy functionality for vertical items[cite: 1, 2]
document.addEventListener("click", (e) => {
    if (e.target.classList.contains("li-copy-btn")) {
        const text = $(e.target.dataset.target).textContent;
        navigator.clipboard.writeText(text);
        const originalText = e.target.textContent;
        e.target.textContent = "Copied!";
        setTimeout(() => e.target.textContent = originalText, 2000);
    }
});