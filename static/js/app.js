
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const form = $("createForm");
  const topicInput = $("topic");
  const topicCount = $("topicCount");
  const audienceSelect = $("audience");
  const toneSelect = $("tone");
  const themeSelect = $("theme");
  const slideCountGroup = $("slideCount");
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
  const previewNav = $("previewNav");

  let currentDeck = null;
  let currentIndex = 0;
  let selectedSlideCount = 10;
  let lastRequest = null;
  let isBusy = false;
  let toastTimer = null;

  const THEMES = {
    aurora: { bg: "#f8f6ff", title: "#18142c", text: "#373250", accent: "#6c4cf1", muted: "#78738c", card: "#ffffff" },
    midnight: { bg: "#0f1120", title: "#ffffff", text: "#e1e4f2", accent: "#8b78ff", muted: "#a0a6c3", card: "#1b1e32" },
    minimal: { bg: "#ffffff", title: "#111111", text: "#373737", accent: "#111111", muted: "#828282", card: "#f5f5f5" },
    corporate: { bg: "#f5f8fc", title: "#102846", text: "#2d415a", accent: "#0070c0", muted: "#6e7d91", card: "#ffffff" },
    ocean: { bg: "#eaf6f8", title: "#073b4c", text: "#245563", accent: "#00a6a6", muted: "#668b96", card: "#ffffff" },
    sunset: { bg: "#fff1e9", title: "#54251a", text: "#704334", accent: "#f26b38", muted: "#a77a69", card: "#fffaf6" },
    forest: { bg: "#edf4ec", title: "#173b2c", text: "#365c47", accent: "#32865a", muted: "#78917d", card: "#ffffff" },
    rose: { bg: "#fff0f4", title: "#552238", text: "#78465a", accent: "#df5b88", muted: "#a77b8c", card: "#ffffff" },
    lavender: { bg: "#f2efff", title: "#30245c", text: "#504477", accent: "#9474e8", muted: "#887eaa", card: "#ffffff" },
    graphite: { bg: "#20242b", title: "#ffffff", text: "#e0e4e9", accent: "#a9b4c0", muted: "#a0a8b2", card: "#303740" },
    sand: { bg: "#f5efe3", title: "#493b2b", text: "#675742", accent: "#bd8b45", muted: "#9b8a72", card: "#fffaf0" },
    cyberpunk: { bg: "#151326", title: "#ffffff", text: "#e7defe", accent: "#ff4fd8", muted: "#aaa0ce", card: "#29213d" }
  };

  function showToast(message, kind = "") {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = "toast show " + kind;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.className = "toast " + kind;
    }, 4500);
  }

  function setBusy(on, title = "", message = "") {
    isBusy = on;
    loadingOverlay.classList.toggle("hidden", !on);

    if (on) {
      loadingTitle.textContent = title || "Designing your presentation";
      loadingMessage.textContent = message || "Please wait while SlideWala works...";
    }

    generateBtn.disabled = on;
    regenerateBtn.disabled = on;
    downloadPptxBtn.disabled = on;
    downloadPdfBtn.disabled = on;
    copyBtn.disabled = on;
  }

  async function safeJson(response) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[character]
    );
  }

  function getRequestData() {
    return {
      topic: topicInput.value.trim(),
      audience: audienceSelect.value,
      tone: toneSelect.value,
      theme: themeSelect.value,
      slides: selectedSlideCount
    };
  }

  // SLIDE COUNT

  slideCountGroup.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      slideCountGroup.querySelectorAll("button").forEach((item) => {
        item.classList.remove("active");
        item.setAttribute("aria-checked", "false");
      });

      button.classList.add("active");
      button.setAttribute("aria-checked", "true");
      selectedSlideCount = Number(button.dataset.count);
    });
  });

  // TOPIC CHARACTER COUNTER

  topicInput.addEventListener("input", () => {
    topicCount.textContent = String(topicInput.value.length);
  });

  // GENERATE PRESENTATION

  async function generateDeck(requestData, isRegeneration = false) {
    if (isBusy) return;

    setBusy(
      true,
      isRegeneration ? "Creating a fresh presentation" : "Designing your presentation",
      "Writing slide content and finding relevant visuals..."
    );

    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData)
      });

      const data = await safeJson(response);

      if (!response.ok) {
        throw new Error(
          data.error || `The server returned error ${response.status}. Check the server logs.`
        );
      }

      if (!data || !Array.isArray(data.slides) || data.slides.length === 0) {
        throw new Error("The AI returned an empty presentation. Please try again.");
      }

      currentDeck = data;
      currentIndex = 0;
      lastRequest = { ...requestData };

      renderDeck();
      workspace.classList.remove("hidden");

      showToast(
        isRegeneration ? "A new presentation has been generated." : "Your presentation is ready.",
        "success"
      );

      workspace.scrollIntoView({ behavior: "smooth", block: "start" });

    } catch (error) {
      console.error("SlideWala generation error:", error);
      showToast(error.message || "Something went wrong. Please try again.", "error");

    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isBusy) return;

    const requestData = getRequestData();

    if (!requestData.topic) {
      showToast("Please enter a presentation topic.", "error");
      topicInput.focus();
      return;
    }

    await generateDeck(requestData, false);
  });

  // RENDER PRESENTATION

  function renderDeck() {
    if (!currentDeck) return;

    deckTitleEl.textContent = currentDeck.title || "Your presentation";
    deckSubtitleEl.textContent = currentDeck.subtitle || "";
    thumbCount.textContent = String(currentDeck.slides.length);

    renderThumbnails();
    renderSlide(0);
  }

  // SLIDE THUMBNAILS

  function renderThumbnails() {
    thumbnailsEl.innerHTML = "";

    currentDeck.slides.forEach((slide, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "thumb";

      button.innerHTML = `
        <span class="thumb-num">${String(index + 1).padStart(2, "0")}</span>
        <span class="thumb-title">${escapeHtml(slide.title || "Slide " + (index + 1))}</span>
      `;

      button.addEventListener("click", () => renderSlide(index));
      thumbnailsEl.appendChild(button);
    });
  }

  // RENDER INDIVIDUAL SLIDE

  function renderSlide(index) {
    if (!currentDeck) return;

    const total = currentDeck.slides.length;
    currentIndex = Math.max(0, Math.min(index, total - 1));

    const slide = currentDeck.slides[currentIndex];
    const theme = THEMES[currentDeck.theme] || THEMES.aurora;

    stage.style.background = theme.bg;
    stage.style.setProperty("--slide-card", theme.card);
    stage.innerHTML = buildSlideHtml(slide, currentIndex, total, theme);

    slideCounter.textContent = `${currentIndex + 1} / ${total}`;
    speakerNotesEl.textContent = slide.speaker_notes || "No speaker notes for this slide.";

    thumbnailsEl.querySelectorAll(".thumb").forEach((button, buttonIndex) => {
      button.classList.toggle("active", buttonIndex === currentIndex);
    });

    prevBtn.disabled = currentIndex === 0;
    nextBtn.disabled = currentIndex === total - 1;
  }

  // SLIDE HTML

  function buildSlideHtml(slide, index, total, theme) {
    const layout = slide.layout || "content";
    const isTitle = index === 0 || layout === "title";
    const hasImage = Boolean(slide.image_url);
    const isFull = layout === "full-image" && hasImage;

    const kicker = isTitle
      ? "SLIDEWALA"
      : `SLIDE ${String(index + 1).padStart(2, "0")}`;

    const bullets = Array.isArray(slide.bullets) ? slide.bullets : [];
    const bulletsHtml = bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("");

    const mediaHtml = hasImage
      ? `
        <div class="slide-media">
          <img
            src="${escapeHtml(slide.image_url)}"
            alt="${escapeHtml(slide.image_alt || "")}"
            loading="lazy"
            onerror="this.parentElement.style.display='none'"
          >
        </div>
      `
      : "";

    let wrapperClass = "slide-canvas-inner";

    if (isFull) {
      wrapperClass += " full-image";
    } else if (hasImage && layout === "image-left") {
      wrapperClass += " is-image is-image-left";
    } else if (hasImage) {
      wrapperClass += " is-image is-image-right";
    }

    return `
      <div class="${wrapperClass}" style="color:${theme.text}">
        ${isFull ? mediaHtml : ""}

        <div class="slide-content">
          <div class="slide-kicker" style="color:${theme.accent}">
            ${escapeHtml(kicker)}
          </div>

          <h3 class="slide-title" style="color:${theme.title}">
            ${escapeHtml(slide.title || "Slide " + (index + 1))}
          </h3>

          <ul class="slide-bullets">${bulletsHtml}</ul>
        </div>

        ${!isFull ? mediaHtml : ""}

        <div class="slide-footer">
          <span>${escapeHtml(currentDeck.title || "SlideWala")}</span>
          <span>${String(index + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}</span>
        </div>
      </div>
    `;
  }

  // PREVIOUS / NEXT

  prevBtn.addEventListener("click", () => renderSlide(currentIndex - 1));
  nextBtn.addEventListener("click", () => renderSlide(currentIndex + 1));

  document.addEventListener("keydown", (event) => {
    if (!currentDeck || isBusy) return;
    if (event.key === "ArrowLeft") renderSlide(currentIndex - 1);
    if (event.key === "ArrowRight") renderSlide(currentIndex + 1);
  });

  // PREVIEW NAVIGATION

  previewNav.addEventListener("click", (event) => {
    if (!currentDeck) {
      event.preventDefault();
      showToast("Generate a presentation first.", "error");
    }
  });

  // COPY PRESENTATION OUTLINE

  function buildOutlineText(deck) {
    const lines = [];
    lines.push("# " + (deck.title || "Presentation"));

    if (deck.subtitle) lines.push(deck.subtitle);
    lines.push("");

    deck.slides.forEach((slide, index) => {
      lines.push(`Slide ${index + 1}: ${slide.title || ""}`);

      (slide.bullets || []).forEach((bullet) => {
        lines.push("  - " + bullet);
      });

      if (slide.speaker_notes) {
        lines.push("  Speaker notes: " + slide.speaker_notes);
      }

      lines.push("");
    });

    return lines.join("\n").trim();
  }

  copyBtn.addEventListener("click", async () => {
    if (!currentDeck || isBusy) return;

    const text = buildOutlineText(currentDeck);

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";

        document.body.appendChild(textarea);
        textarea.select();

        const success = document.execCommand("copy");
        document.body.removeChild(textarea);

        if (!success) throw new Error("Clipboard copy was blocked.");
      }

      showToast("Presentation outline copied.", "success");

    } catch (error) {
      console.error("Clipboard error:", error);
      showToast("Could not copy the outline.", "error");
    }
  });

  // REGENERATE PRESENTATION

  regenerateBtn.addEventListener("click", async () => {
    if (isBusy) return;

    if (!lastRequest) {
      showToast("Generate a presentation first.", "error");
      return;
    }

    await generateDeck({ ...lastRequest }, true);
  });

  // DOWNLOAD FILE

  async function downloadBlob(url, payload, fallbackName) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const data = await safeJson(response);
      throw new Error(data.error || `Download failed (${response.status}).`);
    }

    const blob = await response.blob();
    if (!blob.size) throw new Error("The downloaded file is empty.");

    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match ? match[1] : fallbackName;

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = objectUrl;
    link.download = filename;

    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(objectUrl), 3000);
  }

  // POWERPOINT DOWNLOAD

  downloadPptxBtn.addEventListener("click", async () => {
    if (!currentDeck || isBusy) return;

    setBusy(true, "Building PowerPoint", "Creating your editable PPTX presentation...");

    try {
      await downloadBlob("/api/export/pptx", currentDeck, "slidewala-presentation.pptx");
      showToast("PowerPoint downloaded.", "success");
    } catch (error) {
      console.error("PPTX export error:", error);
      showToast(error.message || "Could not download PowerPoint.", "error");
    } finally {
      setBusy(false);
    }
  });

  // PDF DOWNLOAD

  downloadPdfBtn.addEventListener("click", async () => {
    if (!currentDeck || isBusy) return;

    setBusy(true, "Building PDF", "Creating your presentation PDF...");

    try {
      await downloadBlob("/api/export/pdf", currentDeck, "slidewala-presentation.pdf");
      showToast("PDF downloaded.", "success");
    } catch (error) {
      console.error("PDF export error:", error);
      showToast(error.message || "Could not download PDF.", "error");
    } finally {
      setBusy(false);
    }
  });

})();
