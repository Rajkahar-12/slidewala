(() => {
  "use strict";

  const form = document.getElementById("createForm");
  const topicInput = document.getElementById("topic");
  const topicCount = document.getElementById("topicCount");
  const audienceSelect = document.getElementById("audience");
  const toneSelect = document.getElementById("tone");
  const themeSelect = document.getElementById("theme");
  const slideCountGroup = document.getElementById("slideCount");
  const generateBtn = document.getElementById("generateBtn");

  const workspace = document.getElementById("workspace");
  const deckTitleEl = document.getElementById("deckTitle");
  const deckSubtitleEl = document.getElementById("deckSubtitle");
  const stage = document.getElementById("slideStage");
  const slideCounter = document.getElementById("slideCounter");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const thumbnailsEl = document.getElementById("thumbnails");
  const thumbCount = document.getElementById("thumbCount");
  const speakerNotesEl = document.getElementById("speakerNotes");

  const copyBtn = document.getElementById("copyBtn");
  const regenerateBtn = document.getElementById("regenerateBtn");
  const downloadPptxBtn = document.getElementById("downloadPptx");
  const downloadPdfBtn = document.getElementById("downloadPdf");

  const toastEl = document.getElementById("toast");
  const loadingOverlay = document.getElementById("loadingOverlay");
  const loadingTitle = document.getElementById("loadingTitle");
  const loadingMessage = document.getElementById("loadingMessage");
  const previewNav = document.getElementById("previewNav");

  let currentDeck = null;
  let currentIndex = 0;
  let selectedSlideCount = 10;
  let isBusy = false;

  const THEMES = {
    aurora:    { bg: "#f8f6ff", title: "#18142c", text: "#373250", accent: "#6c4cf1", muted: "#78738c", card: "#ffffff" },
    midnight:  { bg: "#0f1120", title: "#ffffff", text: "#e1e4f2", accent: "#8b78ff", muted: "#a0a6c3", card: "#1b1e32" },
    minimal:   { bg: "#ffffff", title: "#111111", text: "#373737", accent: "#111111", muted: "#828282", card: "#f5f5f5" },
    corporate: { bg: "#f5f8fc", title: "#102846", text: "#2d415a", accent: "#0070c0", muted: "#6e7d91", card: "#ffffff" }
  };

  function showToast(message, kind = "") {
    toastEl.textContent = message;
    toastEl.className = "toast show " + kind;
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => { toastEl.className = "toast " + kind; }, 3400);
  }

  function setBusy(on, title, message) {
    isBusy = on;
    loadingOverlay.classList.toggle("hidden", !on);
    if (on) {
      loadingTitle.textContent = title || "Designing your presentation";
      loadingMessage.textContent = message || "Writing the story and finding relevant visuals…";
      generateBtn.disabled = true;
    } else {
      generateBtn.disabled = false;
    }
  }

  async function safeJson(res) { try { return await res.json(); } catch { return {}; } }

  async function downloadBlob(url, payload, fallbackName) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) { const data = await safeJson(res); throw new Error(data.error || "Download failed."); }
    const blob = await res.blob();
    const disposition = res.headers.get("content-disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match ? match[1] : fallbackName;
    const link = document.createElement("a");
    const objectUrl = URL.createObjectURL(blob);
    link.href = objectUrl; link.download = filename;
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  slideCountGroup.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      slideCountGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedSlideCount = Number(btn.dataset.count);
    });
  });

  topicInput.addEventListener("input", () => { topicCount.textContent = String(topicInput.value.length); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isBusy) return;
    const topic = topicInput.value.trim();
    if (!topic) { showToast("Please enter a presentation topic.", "error"); topicInput.focus(); return; }

    setBusy(true, "Designing your presentation", "Writing the story and finding relevant visuals…");
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, audience: audienceSelect.value, tone: toneSelect.value, theme: themeSelect.value, slides: selectedSlideCount })
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || `Request failed (${res.status}).`);
      if (!data || !Array.isArray(data.slides) || data.slides.length === 0) throw new Error("The AI response was empty or incomplete. Please try again.");

      currentDeck = data; currentIndex = 0;
      renderDeck();
      workspace.classList.remove("hidden");
      showToast("Presentation ready.", "success");
      workspace.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showToast(err.message || "Something went wrong. Please try again.", "error");
    } finally { setBusy(false); }
  });

  function renderDeck() {
    deckTitleEl.textContent = currentDeck.title || "Your presentation";
    deckSubtitleEl.textContent = currentDeck.subtitle || "";
    thumbCount.textContent = String(currentDeck.slides.length);
    renderThumbnails();
    renderSlide(0);
  }

  function renderThumbnails() {
    thumbnailsEl.innerHTML = "";
    currentDeck.slides.forEach((slide, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "thumb" + (index === 0 ? " active" : "");
      btn.innerHTML = `<span class="thumb-num">${String(index + 1).padStart(2, "0")}</span><span class="thumb-title">${escapeHtml(slide.title || "Slide " + (index + 1))}</span>`;
      btn.addEventListener("click", () => renderSlide(index));
      thumbnailsEl.appendChild(btn);
    });
  }

  function renderSlide(index) {
    if (!currentDeck) return;
    const total = currentDeck.slides.length;
    currentIndex = Math.max(0, Math.min(index, total - 1));
    const slide = currentDeck.slides[currentIndex];
    const theme = THEMES[currentDeck.theme] || THEMES.aurora;

    stage.style.background = theme.bg;
    stage.innerHTML = buildSlideHtml(slide, currentIndex, total, theme);
    slideCounter.textContent = `${currentIndex + 1} / ${total}`;
    speakerNotesEl.textContent = slide.speaker_notes || "No speaker notes for this slide.";

    thumbnailsEl.querySelectorAll(".thumb").forEach((el, i) => { el.classList.toggle("active", i === currentIndex); });
    prevBtn.disabled = currentIndex === 0;
    nextBtn.disabled = currentIndex === total - 1;
  }

  function buildSlideHtml(slide, index, total, theme) {
    const layout = slide.layout || "content";
    const isTitle = index === 0 || layout === "title";
    const hasImage = !!slide.image_url;
    const isFull = layout === "full-image" && hasImage;
    const kicker = isTitle ? "SLIDEWALA" : `SLIDE ${String(index + 1).padStart(2, "0")}`;
    const bulletsHtml = (slide.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    const mediaHtml = hasImage ? `<div class="slide-media"><img src="${escapeHtml(slide.image_url)}" alt="${escapeHtml(slide.image_alt || "")}" loading="lazy" onerror="this.parentElement.style.display='none'"></div>` : "";

    let wrapperClass = "slide-canvas-inner";
    if (isFull) wrapperClass += " full-image";
    else if (hasImage && layout === "image-left") wrapperClass += " is-image is-image-left";
    else if (hasImage && layout === "image-right") wrapperClass += " is-image is-image-right";
    else if (hasImage) wrapperClass += " is-image is-image-right";

    return `
      <div class="${wrapperClass}" style="color:${theme.text}">
        ${isFull ? mediaHtml : ""}
        <div class="slide-content">
          <div class="slide-kicker" style="color:${theme.accent}">${escapeHtml(kicker)}</div>
          <h3 class="slide-title" style="color:${theme.title}">${escapeHtml(slide.title || "Slide " + (index + 1))}</h3>
          <ul class="slide-bullets">${bulletsHtml}</ul>
        </div>
        ${!isFull ? mediaHtml : ""}
        <div class="slide-footer">
          <span>${escapeHtml(currentDeck.title || "SlideWala")}</span>
          <span>${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}</span>
        </div>
      </div>`;
  }

  prevBtn.addEventListener("click", () => renderSlide(currentIndex - 1));
  nextBtn.addEventListener("click", () => renderSlide(currentIndex + 1));
  document.addEventListener("keydown", (event) => {
    if (!currentDeck) return;
    if (event.key === "ArrowLeft") renderSlide(currentIndex - 1);
    if (event.key === "ArrowRight") renderSlide(currentIndex + 1);
  });
  previewNav.addEventListener("click", (event) => { if (!currentDeck) { event.preventDefault(); showToast("Generate a presentation first.", "error"); } });

  function buildOutlineText(deck) {
    const lines = [];
    lines.push("# " + (deck.title || "Presentation"));
    if (deck.subtitle) lines.push(deck.subtitle);
    lines.push("");
    deck.slides.forEach((slide, i) => {
      lines.push(`Slide ${i + 1}: ${slide.title || ""}`);
      (slide.bullets || []).forEach((b) => lines.push("  • " + b));
      if (slide.speaker_notes) lines.push("  Speaker notes: " + slide.speaker_notes);
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  copyBtn.addEventListener("click", async () => {
    if (!currentDeck) return;
    const text = buildOutlineText(currentDeck);
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) { try { await navigator.clipboard.writeText(text); copied = true; } catch {} }
    if (!copied) {
      const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); copied = true; } catch {}
      document.body.removeChild(ta);
    }
    if (copied) {
      const original = copyBtn.textContent; copyBtn.textContent = "Copied!"; copyBtn.disabled = true;
      showToast("Outline copied to clipboard.", "success");
      setTimeout(() => { copyBtn.textContent = original; copyBtn.disabled = false; }, 1600);
    } else { showToast("Could not copy. Your browser may block clipboard access.", "error"); }
  });

  regenerateBtn.addEventListener("click", () => { document.getElementById("create").scrollIntoView({ behavior: "smooth" }); topicInput.focus(); });

  downloadPptxBtn.addEventListener("click", async () => {
    if (!currentDeck || isBusy) return;
    setBusy(true, "Building PowerPoint", "Assembling real slides with python-pptx…");
    try { await downloadBlob("/api/export/pptx", currentDeck, "slidewala-presentation.pptx"); showToast("PPTX downloaded.", "success"); }
    catch (err) { showToast(err.message || "Could not download PPTX.", "error"); }
    finally { setBusy(false); }
  });

  downloadPdfBtn.addEventListener("click", async () => {
    if (!currentDeck || isBusy) return;
    setBusy(true, "Building PDF", "Rendering slides and notes to PDF…");
    try { await downloadBlob("/api/export/pdf", currentDeck, "slidewala-presentation.pdf"); showToast("PDF downloaded.", "success"); }
    catch (err) { showToast(err.message || "Could not download PDF.", "error"); }
    finally { setBusy(false); }
  });
})();
