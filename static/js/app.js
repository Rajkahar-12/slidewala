(() => {
  "use strict";

  // ----------------------------------------
  // ELEMENTS
  // ----------------------------------------

  const $ = (id) => document.getElementById(id);

  const form = $("createForm");
  const topicInput = $("topic");
  const topicCount = $("topicCount");
  const audienceSelect = $("audience");
  const toneSelect = $("tone");
  const themeSelect = $("theme");
  const deckTypeSelect = $("deckType");
  const slideCountGroup = $("slideCount");
  const contentLengthGroup = $("contentLength");
  const generateBtn = $("generateBtn");

  const workspace = $("workspace");
  const deckTitleEl = $("deckTitle");
  const deckSubtitleEl = $("deckSubtitle");
  const stage = $("slideStage");
  const slideCounter = $("slideCounter");
  const prevBtn = $("prevBtn");
  const nextBtn = $("nextBtn");
  const thumbnailsEl = $("thumbnails");
  const thumbCount = $("thumbCount");
  const speakerNotesEl = $("speakerNotes");

  const copyBtn = $("copyBtn");
  const regenerateBtn = $("regenerateBtn");
  const downloadPptxBtn = $("downloadPptx");
  const downloadPdfBtn = $("downloadPdf");

  const toastEl = $("toast");
  const loadingOverlay = $("loadingOverlay");
  const loadingTitle = $("loadingTitle");
  const loadingMessage = $("loadingMessage");

  const createSection = $("create");
  const cards = document.querySelectorAll(".choice-card");
  const previewNav = $("previewNav");

  // ----------------------------------------
  // STATE
  // ----------------------------------------

  let currentDeck = null;
  let currentIndex = 0;
  let selectedSlideCount = 10;
  let selectedContentLength = "medium";
  let isBusy = false;
  let loadingInterval = null;

  // ----------------------------------------
  // THEME COLORS
  // ----------------------------------------

  const THEMES = {
    aurora: { bg: "#f8f6ff", title: "#18142c", text: "#373250", accent: "#6c4cf1", muted: "#78738c", card: "#ffffff" },
    midnight: { bg: "#0f1120", title: "#ffffff", text: "#e1e4f2", accent: "#8b78ff", muted: "#a0a6c3", card: "#1b1e32" },
    minimal: { bg: "#ffffff", title: "#111111", text: "#373737", accent: "#111111", muted: "#828282", card: "#f5f5f5" },
    corporate: { bg: "#f5f8fc", title: "#102846", text: "#2d415a", accent: "#0070c0", muted: "#6e7d91", card: "#ffffff" },
    ocean: { bg: "#effaff", title: "#063b52", text: "#285568", accent: "#009bc2", muted: "#6b8996", card: "#ffffff" },
    sunset: { bg: "#fff5ef", title: "#542b25", text: "#70483e", accent: "#ef7954", muted: "#a17b70", card: "#ffffff" },
    forest: { bg: "#f1f7f0", title: "#173d2a", text: "#355a43", accent: "#368451", muted: "#78917e", card: "#ffffff" },
    rose: { bg: "#fff3f6", title: "#522638", text: "#704255", accent: "#d94c82", muted: "#a77c8d", card: "#ffffff" },
    lavender: { bg: "#f7f3ff", title: "#30204e", text: "#51416d", accent: "#9570e8", muted: "#9283aa", card: "#ffffff" },
    graphite: { bg: "#eeeeef", title: "#202124", text: "#414348", accent: "#555b66", muted: "#858990", card: "#ffffff" },
    sand: { bg: "#faf5e9", title: "#493b26", text: "#65563e", accent: "#b38a43", muted: "#998b72", card: "#ffffff" },
    cyberpunk: { bg: "#151323", title: "#ffffff", text: "#e4defa", accent: "#ed4dff", muted: "#a89cce", card: "#211d38" }
  };

  // ----------------------------------------
  // HELPERS
  // ----------------------------------------

  function showToast(message, kind = "") {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = "toast show " + kind;
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      toastEl.className = "toast " + kind;
    }, 3400);
  }

  function setBusy(on, title, message) {
    isBusy = on;
    if (loadingOverlay) loadingOverlay.classList.toggle("hidden", !on);
    if (on) {
      if (loadingTitle) loadingTitle.textContent = title || "Designing your presentation";
      if (loadingMessage) loadingMessage.textContent = message || "Creating your presentation...";
      if (generateBtn) generateBtn.disabled = true;
      if (downloadPptxBtn) downloadPptxBtn.disabled = true;
      if (downloadPdfBtn) downloadPdfBtn.disabled = true;
    } else {
      if (generateBtn) generateBtn.disabled = false;
      if (downloadPptxBtn) downloadPptxBtn.disabled = false;
      if (downloadPdfBtn) downloadPdfBtn.disabled = false;
    }
  }

  // ✅ NEW: Dynamic Loading Text
  function startLoadingText() {
    const messages = [
      "Analyzing your topic...",
      "Researching important points...",
      "Drafting slide content and notes...",
      "Designing slide layouts...",
      "Finalizing your presentation..."
    ];
    let step = 0;
    
    if (loadingMessage) loadingMessage.textContent = messages[0];

    loadingInterval = setInterval(() => {
      step = (step + 1) % messages.length;
      if (loadingMessage) loadingMessage.textContent = messages[step];
    }, 7000); // Har 7 second me text badlega
  }

  function stopLoadingText() {
    if (loadingInterval) {
      clearInterval(loadingInterval);
      loadingInterval = null;
    }
  }

  async function safeJson(res) {
    try { return await res.json(); } catch { return {}; }
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getSelectedContentLength() {
    if (!contentLengthGroup) return selectedContentLength;
    const activeButton = contentLengthGroup.querySelector("button.active");
    if (!activeButton) return selectedContentLength;
    const value =
      activeButton.dataset.length ||
      activeButton.dataset.contentLength ||
      activeButton.dataset.value ||
      activeButton.textContent.trim().toLowerCase();
    const normalized = String(value).toLowerCase();
    if (normalized.includes("detail")) return "detailed";
    if (normalized.includes("short")) return "short";
    return "medium";
  }

  async function downloadBlob(url, payload, fallbackName) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const data = await safeJson(res);
      throw new Error(data.error || "Download failed.");
    }
    const blob = await res.blob();
    const disposition = res.headers.get("content-disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match ? match[1] : fallbackName;
    const link = document.createElement("a");
    const objectUrl = URL.createObjectURL(blob);
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => { URL.revokeObjectURL(objectUrl); }, 2000);
  }

  // ----------------------------------------
  // POLL JOB STATUS
  // ----------------------------------------

  async function pollJobStatus(jobId, options = {}) {
    const intervalMs = options.intervalMs || 1500;
    const maxWaitMs = options.maxWaitMs || 180000; // 3 minutes
    const start = Date.now();

    while (Date.now() - start < maxWaitMs) {
      let res;
      try {
        res = await fetch(`/api/status/${encodeURIComponent(jobId)}`);
      } catch {
        await new Promise((r) => setTimeout(r, intervalMs));
        continue;
      }

      const data = await safeJson(res);

      if (!res.ok) {
        throw new Error(data.error || `Status check failed (${res.status}).`);
      }

      if (data.status === "completed" && data.result) {
        return data.result;
      }

      if (data.status === "failed") {
        throw new Error(data.error || "Presentation generation failed.");
      }

      await new Promise((r) => setTimeout(r, intervalMs));
    }

    throw new Error("Generation is taking too long. Please try again.");
  }

  // ----------------------------------------
  // SELECTIONS
  // ----------------------------------------

  if (cards.length > 0) {
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        cards.forEach((item) => item.classList.remove("selected"));
        card.classList.add("selected");
        if (audienceSelect) audienceSelect.value = card.dataset.audience;
        showToast("Audience selected.", "success");
      });
    });
  }

  if (slideCountGroup) {
    slideCountGroup.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        slideCountGroup.querySelectorAll("button").forEach((button) => {
          button.classList.remove("active");
          button.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        const count = Number(btn.dataset.count);
        if ([5, 8, 10, 12].includes(count)) selectedSlideCount = count;
      });
    });
  }

  if (contentLengthGroup) {
    contentLengthGroup.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        contentLengthGroup.querySelectorAll("button").forEach((button) => {
          button.classList.remove("active");
          button.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        selectedContentLength = getSelectedContentLength();
      });
    });
    selectedContentLength = getSelectedContentLength();
  }

  if (topicInput && topicCount) {
    topicInput.addEventListener("input", () => {
      topicCount.textContent = String(topicInput.value.length);
    });
  }

  // ----------------------------------------
  // GENERATE PRESENTATION
  // ----------------------------------------

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (isBusy) return;

      const topic = topicInput ? topicInput.value.trim() : "";
      if (!topic) {
        showToast("Please enter a presentation topic.", "error");
        if (topicInput) topicInput.focus();
        return;
      }

      if (!audienceSelect || !toneSelect || !themeSelect) {
        showToast("Some presentation settings are missing.", "error");
        return;
      }

      const payload = {
        topic: topic,
        audience: audienceSelect.value,
        tone: toneSelect.value,
        deck_type: deckTypeSelect ? deckTypeSelect.value : "lecture",
        theme: themeSelect.value,
        slides: selectedSlideCount,
        content_length: getSelectedContentLength()
      };

      setBusy(true, "Creating your presentation", "Initializing...");
      startLoadingText(); // ✅ Start fake progress

      try {
        const res = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        const data = await safeJson(res);

        if (!res.ok) {
          throw new Error(data.error || `Request failed (${res.status}).`);
        }

        let deck = null;

        if (data.status === "completed" && data.result) {
          deck = data.result;
        } else if (data.job_id) {
          deck = await pollJobStatus(data.job_id);
        } else {
          throw new Error("Server did not return a job ID. Please try again.");
        }

        if (!deck || !Array.isArray(deck.slides) || deck.slides.length === 0) {
          throw new Error("The AI response was empty or incomplete. Please try again.");
        }

        currentDeck = deck;
        currentIndex = 0;
        renderDeck();

        if (workspace) workspace.classList.remove("hidden");
        if (createSection) createSection.style.display = "none";

        showToast("Presentation ready.", "success");
        window.scrollTo({ top: 0, behavior: "smooth" });

      } catch (err) {
        showToast(err.message || "Something went wrong. Please try again.", "error");
      } finally {
        stopLoadingText(); // ✅ Stop fake progress
        setBusy(false);
      }
    });
  }

  // ----------------------------------------
  // RENDER PRESENTATION
  // ----------------------------------------

  function renderDeck() {
    if (!currentDeck) return;
    if (deckTitleEl) deckTitleEl.textContent = currentDeck.title || "Your presentation";
    if (deckSubtitleEl) deckSubtitleEl.textContent = currentDeck.subtitle || "";
    if (thumbCount) thumbCount.textContent = String(currentDeck.slides.length);
    renderThumbnails();
    renderSlide(0);
  }

  function renderThumbnails() {
    if (!thumbnailsEl || !currentDeck) return;
    thumbnailsEl.innerHTML = "";
    currentDeck.slides.forEach((slide, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "thumb" + (index === 0 ? " active" : "");
      btn.innerHTML = `
        <span class="thumb-num">${String(index + 1).padStart(2, "0")}</span>
        <span class="thumb-title">${escapeHtml(slide.title || "Slide " + (index + 1))}</span>
      `;
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

    if (stage) {
      stage.style.background = theme.bg;
      stage.innerHTML = buildSlideHtml(slide, currentIndex, total, theme);
    }
    if (slideCounter) slideCounter.textContent = `${currentIndex + 1} / ${total}`;
    if (speakerNotesEl) speakerNotesEl.textContent = slide.speaker_notes || "No speaker notes for this slide.";

    if (thumbnailsEl) {
      thumbnailsEl.querySelectorAll(".thumb").forEach((el, i) => {
        el.classList.toggle("active", i === currentIndex);
      });
    }
    if (prevBtn) prevBtn.disabled = currentIndex === 0;
    if (nextBtn) nextBtn.disabled = currentIndex === total - 1;
  }

  function buildSlideHtml(slide, index, total, theme) {
    const layout = slide.layout || "content";
    const isTitle = index === 0 || layout === "title";
    const hasImage = !!slide.image_url;
    const isFull = layout === "full-image" && hasImage;

    const kicker = isTitle ? "PRESENTATION" : `SLIDE ${String(index + 1).padStart(2, "0")}`;

    const bulletsHtml = (slide.bullets || [])
      .map((bullet) => `<li>${escapeHtml(bullet)}</li>`)
      .join("");

    const mediaHtml = hasImage ? `
      <div class="slide-media">
        <img src="${escapeHtml(slide.image_url)}" alt="${escapeHtml(slide.image_alt || "")}"
             loading="lazy" onerror="this.parentElement.style.display='none'">
      </div>
    ` : "";

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
          <span>${escapeHtml(currentDeck.title || "Presentation")}</span>
          <span>${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}</span>
        </div>
      </div>
    `;
  }

  // ----------------------------------------
  // NAVIGATION
  // ----------------------------------------

  if (prevBtn) prevBtn.addEventListener("click", () => renderSlide(currentIndex - 1));
  if (nextBtn) nextBtn.addEventListener("click", () => renderSlide(currentIndex + 1));

  document.addEventListener("keydown", (event) => {
    if (!currentDeck) return;
    if (event.key === "ArrowLeft") renderSlide(currentIndex - 1);
    if (event.key === "ArrowRight") renderSlide(currentIndex + 1);
  });

  if (previewNav) {
    previewNav.addEventListener("click", (event) => {
      if (!currentDeck) {
        event.preventDefault();
        showToast("Generate a presentation first.", "error");
      }
    });
  }

  // ----------------------------------------
  // OUTLINE & COPY
  // ----------------------------------------

  function buildOutlineText(deck) {
    const lines = [];
    lines.push("# " + (deck.title || "Presentation"));
    if (deck.subtitle) lines.push(deck.subtitle);
    lines.push("");
    deck.slides.forEach((slide, index) => {
      lines.push(`Slide ${index + 1}: ${slide.title || ""}`);
      (slide.bullets || []).forEach((bullet) => lines.push("  • " + bullet));
      if (slide.speaker_notes) lines.push("  Speaker notes: " + slide.speaker_notes);
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      if (!currentDeck) return;
      const text = buildOutlineText(currentDeck);
      let copied = false;

      if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(text); copied = true; } catch {}
      }

      if (!copied) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        try { copied = document.execCommand("copy"); } catch {}
        document.body.removeChild(textarea);
      }

      if (copied) {
        const original = copyBtn.textContent;
        copyBtn.textContent = "Copied!";
        copyBtn.disabled = true;
        showToast("Outline copied to clipboard.", "success");
        setTimeout(() => {
          copyBtn.textContent = original;
          copyBtn.disabled = false;
        }, 1600);
      } else {
        showToast("Could not copy. Your browser may block clipboard access.", "error");
      }
    });
  }

  if (regenerateBtn) {
    regenerateBtn.addEventListener("click", () => {
      if (createSection) createSection.style.display = "flex";
      if (workspace) workspace.classList.add("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
      if (topicInput) topicInput.focus();
    });
  }

  // ----------------------------------------
  // DOWNLOADS
  // ----------------------------------------

  if (downloadPptxBtn) {
    downloadPptxBtn.addEventListener("click", async () => {
      if (!currentDeck || isBusy) return;
      setBusy(true, "Building PowerPoint", "Assembling your PowerPoint slides...");
      try {
        await downloadBlob("/api/export/pptx", currentDeck, "presentation.pptx");
        showToast("PPTX downloaded.", "success");
      } catch (err) {
        showToast(err.message || "Could not download PPTX.", "error");
      } finally {
        setBusy(false);
      }
    });
  }

  if (downloadPdfBtn) {
    downloadPdfBtn.addEventListener("click", async () => {
      if (!currentDeck || isBusy) return;
      setBusy(true, "Building PDF", "Rendering your presentation to PDF...");
      try {
        await downloadBlob("/api/export/pdf", currentDeck, "presentation.pdf");
        showToast("PDF downloaded.", "success");
      } catch (err) {
        showToast(err.message || "Could not download PDF.", "error");
      } finally {
        setBusy(false);
      }
    });
  }

})();
