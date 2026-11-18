/* BlackHole frontend — talks to /api/info and /api/download */
const form = document.getElementById("dl-form");
const urlInput = document.getElementById("url-input");
const dlBtn = document.getElementById("dl-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const multiResultEl = document.getElementById("multi-result");
const multiToggle = document.getElementById("multi-toggle");
const multiArea = document.getElementById("multi-area");
const multiInput = document.getElementById("multi-input");

multiToggle.addEventListener("click", () => {
  multiArea.classList.toggle("open");
  multiToggle.textContent = multiArea.classList.contains("open")
    ? "– Hide multiple links" : "＋ Multiple links";
});

function showStatus(html) {
  statusEl.innerHTML = html;
  statusEl.classList.add("show");
}
function hideStatus() {
  statusEl.classList.remove("show");
  statusEl.innerHTML = "";
}
function showError(msg) {
  showStatus(`<div class="error">${escapeHtml(msg)}</div>`);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function fmtDuration(sec) {
  if (!sec && sec !== 0) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const h = Math.floor(m / 60);
  const mm = h ? String(m % 60).padStart(2, "0") : String(m);
  return h ? `${h}:${mm}:${String(s).padStart(2, "0")}` : `${mm}:${String(s).padStart(2, "0")}`;
}

async function fetchInfo(url) {
  const res = await fetch("/api/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Could not fetch this link.");
  return data;
}

function downloadUrl(url, opt, title) {
  const q = new URLSearchParams({
    url,
    format: opt.id,
    kind: opt.kind,
    title: title || "video",
  });
  return `/api/download?${q.toString()}`;
}

function qualityButtons(url, options, title) {
  return options.map((opt, i) => {
    const size = opt.size_human ? `<small>${escapeHtml(opt.size_human)} · ${opt.ext.toUpperCase()}</small>` : `<small>${opt.ext.toUpperCase()}</small>`;
    const label = opt.kind === "audio" ? "🎵 MP3 audio" : `${escapeHtml(opt.label)} MP4`;
    return `<button class="q-btn${opt.kind === "audio" ? " mp3" : ""}" style="--d:${(i * 0.06).toFixed(2)}s" data-href="${escapeHtml(downloadUrl(url, opt, title))}">${label}${size}</button>`;
  }).join("");
}

/* Scroll-in: reveal sections as they enter the viewport */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add("in");
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.15 });
document.querySelectorAll(".reveal").forEach((el) => revealObserver.observe(el));

function renderResult(url, data) {
  resultEl.innerHTML = `
    <div class="result-top">
      ${data.thumbnail ? `<img src="${escapeHtml(data.thumbnail)}" alt="Video thumbnail">` : ""}
      <div class="result-meta">
        <h3>${escapeHtml(data.title)}</h3>
        <div class="meta">${escapeHtml(data.uploader || "")}${data.duration ? " · " + fmtDuration(data.duration) : ""}</div>
        ${data.platform ? `<span class="platform">${escapeHtml(data.platform)}</span>` : ""}
      </div>
    </div>
    <div class="qualities">${qualityButtons(url, data.options, data.title)}</div>`;
  resultEl.classList.add("show");
  resultEl.querySelectorAll(".q-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.disabled = true;
      btn.textContent = "Preparing download…";
      window.location.href = btn.dataset.href;
      setTimeout(() => { btn.disabled = false; btn.textContent = btn.dataset.label || "Download"; }, 4000);
    });
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const multi = multiArea.classList.contains("open");
  const urls = multi
    ? multiInput.value.split(/\n+/).map((s) => s.trim()).filter(Boolean).slice(0, 20)
    : [urlInput.value.trim()].filter(Boolean);
  if (!urls.length) {
    showError("Please paste a video link first.");
    return;
  }
  resultEl.classList.remove("show");
  resultEl.innerHTML = "";
  multiResultEl.innerHTML = "";
  dlBtn.disabled = true;

  if (!multi) {
    const url = urls[0];
    showStatus(`<span class="spin"></span>Reading link…`);
    try {
      const data = await fetchInfo(url);
      hideStatus();
      renderResult(url, data);
    } catch (err) {
      showError(err.message);
    } finally {
      dlBtn.disabled = false;
    }
    return;
  }

  // Multiple links: fetch each in turn, one compact card per video.
  showStatus(`<span class="spin"></span>Reading ${urls.length} link${urls.length > 1 ? "s" : ""}…`);
  for (const url of urls) {
    const item = document.createElement("div");
    item.className = "mr-item";
    item.innerHTML = `<div><div class="t">${escapeHtml(url)}</div><div class="s">Reading link…</div></div>`;
    multiResultEl.appendChild(item);
    try {
      const data = await fetchInfo(url);
      item.innerHTML = `
        ${data.thumbnail ? `<img src="${escapeHtml(data.thumbnail)}" alt="">` : ""}
        <div><div class="t">${escapeHtml(data.title)}</div>
        <div class="s">${escapeHtml(data.uploader || "")}${data.duration ? " · " + fmtDuration(data.duration) : ""}</div></div>
        <div class="q">${qualityButtons(url, data.options.slice(0, 4), data.title)}</div>`;
      item.querySelectorAll(".q-btn").forEach((btn) => {
        btn.addEventListener("click", () => { window.location.href = btn.dataset.href; });
      });
    } catch (err) {
      item.innerHTML = `<div><div class="t">${escapeHtml(url)}</div><div class="s" style="color:#fca5a5">${escapeHtml(err.message)}</div></div>`;
    }
  }
  hideStatus();
  dlBtn.disabled = false;
});
