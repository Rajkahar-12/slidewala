(() => {
  "use strict";

  const cards = document.querySelectorAll(".choice-card");
  const audienceLabel = document.getElementById("audienceLabel");
  const topicInput = document.getElementById("topic");
  const notice = document.getElementById("notice");
  const createBtn = document.getElementById("createBtn");
  const countBtns = document.querySelectorAll(".count-btn");
  const resultsSection = document.getElementById("results");
  const resultTitle = document.getElementById("resultTitle");
  const resultSubtitle = document.getElementById("resultSubtitle");
  const slidesList = document.getElementById("slidesList");
  const copyBtn = document.getElementById("copyBtn");
  const resetBtn = document.getElementById("resetBtn");

  let audience = "student";
  let slideCount = 10;
  let currentPresentation = null;

  // ---------- Audience selector ----------
  cards.forEach((card) => {
    card.addEventListener("click", () => {
      cards.forEach((item) => item.classList.remove("selected"));
      card.classList.add("selected");
      audience = card.dataset.audience;
      audienceLabel.textContent =
        "Selected: " + (audience === "student" ? "Student" : "Professional");
      setNotice("");
    });
  });

  // ---------- Slide count selector ----------
  countBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      countBtns.forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      slideCount = Number(btn.dataset.count);
    });
  });

  // ---------- Helpers ----------
  function setNotice(message, kind) {
    notice.textContent = message || "";
    notice.className = "notice" + (kind ? " notice-" + kind : "");
  }

  function setLoading(on) {
    createBtn.disabled = on;
    createBtn.classList.toggle("loading", on);
    createBtn.innerHTML = on
      ? '<span class="spinner"></span> Generating…'
      : 'Continue <span>→</span>';
  }

  // ---------- Generate ----------
  async function generate() {
    const value = topicInput.value.trim();

    if (!value) {
      setNotice("Please enter a presentation topic to continue.", "error");
      topicInput.focus();
      return;
    }
    if (value.length > 160) {
      setNotice("Please keep the topic under 160 characters.", "error");
      return;
    }

    setLoading(true);
    setNotice(
      "Generating your presentation… this usually takes 10–30 seconds.",
      "info"
    );

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: value,
          audience: audience,
          slides: slideCount,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.error || "Request failed (" + res.status + ").");
      }
      if (!data || !Array.isArray(data.slides) || data.slides.length === 0) {
        throw new Error("The AI response was empty or incomplete. Please try again.");
      }

      currentPresentation = data;
      renderPresentation(data);
      resultsSection.hidden = false;
      setNotice("Presentation ready — preview it below.", "success");
      resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setNotice(err.message || "Something went wrong. Please try again.", "error");
    } finally {
      setLoading(false);
    }
  }

  function renderPresentation(data) {
    resultTitle.textContent = data.title || "Your presentation";
    resultSubtitle.textContent = data.subtitle || "";
    slidesList.innerHTML = "";

    data.slides.forEach((slide, index) => {
      const article = document.createElement("article");
      article.className = "slide-item";

      const head = document.createElement("header");
      head.className = "slide-item-head";

      const num = document.createElement("span");
      num.className = "slide-num";
      num.textContent = String(index + 1).padStart(2, "0");

      const h3 = document.createElement("h3");
      h3.textContent = slide.title || "Slide " + (index + 1);

      head.appendChild(num);
      head.appendChild(h3);

      const ul = document.createElement("ul");
      ul.className = "slide-bullets";
      (slide.bullets || []).forEach((b) => {
        const li = document.createElement("li");
        li.textContent = b;
        ul.appendChild(li);
      });

      const details = document.createElement("details");
      details.className = "slide-notes";
      const summary = document.createElement("summary");
      summary.textContent = "Speaker notes";
      const p = document.createElement("p");
      p.textContent =
        slide.speaker_notes || "No speaker notes were generated for this slide.";
      details.appendChild(summary);
      details.appendChild(p);

      article.appendChild(head);
      article.appendChild(ul);
      article.appendChild(details);
      slidesList.appendChild(article);
    });
  }

  // ---------- Copy outline ----------
  function buildOutlineText(data) {
    const lines = [];
    lines.push("# " + data.title);
    if (data.subtitle) lines.push(data.subtitle);
    lines.push("");
    data.slides.forEach((s, i) => {
      lines.push("Slide " + (i + 1) + ": " + s.title);
      (s.bullets || []).forEach((b) => lines.push("  • " + b));
      if (s.speaker_notes) {
        lines.push("  Speaker notes: " + s.speaker_notes);
      }
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  async function copyOutline() {
    if (!currentPresentation) return;
    const text = buildOutlineText(currentPresentation);
    let copied = false;

    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (_) {
        /* fall through */
      }
    }

    if (!copied) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        copied = true;
      } catch (_) {
        copied = false;
      }
      document.body.removeChild(ta);
    }

    if (copied) {
      copyBtn.textContent = "Copied!";
      copyBtn.disabled = true;
    } else {
      copyBtn.textContent = "Copy failed";
    }
    setTimeout(() => {
      copyBtn.textContent = "Copy outline";
      copyBtn.disabled = false;
    }, 1800);
  }

  // ---------- Reset / generate another ----------
  function resetForm() {
    resultsSection.hidden = true;
    slidesList.innerHTML = "";
    currentPresentation = null;
    topicInput.value = "";
    setNotice("");
    document.getElementById("create").scrollIntoView({ behavior: "smooth" });
    topicInput.focus();
  }

  // ---------- Wire up ----------
  createBtn.addEventListener("click", generate);
  topicInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      generate();
    }
  });
  copyBtn.addEventListener("click", copyOutline);
  resetBtn.addEventListener("click", resetForm);
})();
