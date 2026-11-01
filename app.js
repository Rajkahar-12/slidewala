(() => {
  "use strict";
  const cards = document.querySelectorAll(".choice-card");
  const audienceLabel = document.getElementById("audienceLabel");
  const topic = document.getElementById("topic");
  const notice = document.getElementById("notice");
  let audience = "student";

  cards.forEach(card => {
    card.addEventListener("click", () => {
      cards.forEach(item => item.classList.remove("selected"));
      card.classList.add("selected");
      audience = card.dataset.audience;
      audienceLabel.textContent = `Selected: ${audience === "student" ? "Student" : "Professional"}`;
      notice.textContent = "";
    });
  });

  document.getElementById("createBtn").addEventListener("click", () => {
    const value = topic.value.trim();
    if (!value) {
      notice.textContent = "Please enter a presentation topic to continue.";
      topic.focus();
      return;
    }
    notice.textContent = `Great! "${value}" is saved in this preview. AI slide generation will be connected in Phase 2.`;
  });
})();
