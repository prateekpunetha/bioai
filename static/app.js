const form = document.querySelector("#reportForm");
const fileInput = document.querySelector("#reportFile");
const loadSample = document.querySelector("#loadSample");
const markerGrid = document.querySelector("#markerGrid");
const categoryGrid = document.querySelector("#categoryGrid");
const aiReview = document.querySelector("#aiReview");
const aiReviewTitle = document.querySelector("#aiReviewTitle");
const aiSummaryText = document.querySelector("#aiSummaryText");
const aiInsightGrid = document.querySelector("#aiInsightGrid");
const detailsPanel = document.querySelector("#detailsPanel");
const detailsTitle = document.querySelector("#detailsTitle");
const closeDetails = document.querySelector("#closeDetails");
const summaryTitle = document.querySelector("#summaryTitle");
const summaryText = document.querySelector("#summaryText");
const scoreValue = document.querySelector("#scoreValue");
const greatCount = document.querySelector("#greatCount");
const focusCount = document.querySelector("#focusCount");
const disclaimer = document.querySelector("#disclaimer");
const note = document.querySelector("#note");
const fileLabel = document.querySelector("#fileLabel");
const startScreen = document.querySelector("#startScreen");
const reportScreen = document.querySelector("#reportScreen");
const resultNav = document.querySelector("#resultNav");
const backToStart = document.querySelector("#backToStart");
const analyzeAnother = document.querySelector("#analyzeAnother");
const dropzone = document.querySelector(".dropzone");
const scoreRing = document.querySelector(".score-ring");

let currentResult = null;
let activeCategory = "";

const markerIcons = {
  Blood: "bloodtype",
  Electrolytes: "water_drop",
  Hormones: "fitness_center",
  Inflammation: "local_fire_department",
  Iron: "hardware",
  Kidney: "health_and_safety",
  Lipids: "favorite",
  Liver: "science",
  Metabolic: "monitor_heart",
  Vitamins: "wb_sunny",
};

loadSample.addEventListener("click", async () => {
  setLoading(true, "Loading Sample...");
  try {
    const response = await fetch("/api/sample", { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load sample PDF.");
    renderResult(result);
    fileLabel.textContent = result.sample_file || "Sample PDF";
  } catch (error) {
    showStartError("Sample failed", error.message);
  } finally {
    setLoading(false);
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileLabel.textContent = file ? file.name : "Choose File";
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer.files[0];
  if (!file) return;
  fileInput.files = event.dataTransfer.files;
  fileLabel.textContent = file.name;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    showStartError("Choose a report first", "Upload a PDF, TXT, CSV, or TSV file, or use the sample report.");
    return;
  }

  setLoading(true);
  const data = new FormData(form);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: data,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not analyze report.");
    renderResult(result);
  } catch (error) {
    showStartError("Analysis failed", error.message);
  } finally {
    setLoading(false);
  }
});

backToStart.addEventListener("click", () => {
  currentResult = null;
  startScreen.classList.remove("hidden");
  reportScreen.classList.add("hidden");
  resultNav.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

analyzeAnother.addEventListener("click", () => {
  currentResult = null;
  form.reset();
  fileLabel.textContent = "Choose File";
  scoreValue.textContent = "--";
  scoreRing.style.setProperty("--score", 0);
  categoryGrid.innerHTML = "";
  categoryGrid.classList.add("hidden");
  aiReview.classList.add("hidden");
  aiSummaryText.textContent = "";
  aiInsightGrid.innerHTML = "";
  detailsPanel.classList.add("hidden");
  detailsTitle.textContent = "Select a category";
  markerGrid.innerHTML = "";
  startScreen.classList.remove("hidden");
  reportScreen.classList.add("hidden");
  resultNav.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

closeDetails.addEventListener("click", () => {
  activeCategory = "";
  detailsPanel.classList.add("hidden");
  markerGrid.innerHTML = "";
  categoryGrid.querySelectorAll(".category-card").forEach((button) => {
    button.setAttribute("aria-pressed", "false");
  });
  updateResultNav();
});

function setLoading(isLoading, label = "Analyzing...") {
  const button = form.querySelector(".primary");
  button.disabled = isLoading;
  loadSample.disabled = isLoading;
  button.textContent = isLoading ? label : "Analyze Report";
}

function showStartError(title, message) {
  currentResult = null;
  startScreen.classList.add("hidden");
  reportScreen.classList.remove("hidden");
  resultNav.classList.add("hidden");
  summaryTitle.textContent = title;
  summaryText.textContent = message;
  scoreValue.textContent = "--";
  scoreRing.style.setProperty("--score", 0);
  greatCount.textContent = "0";
  focusCount.textContent = "0";
  categoryGrid.innerHTML = "";
  categoryGrid.classList.add("hidden");
  aiReview.classList.add("hidden");
  aiSummaryText.textContent = "";
  aiInsightGrid.innerHTML = "";
  detailsPanel.classList.add("hidden");
  detailsTitle.textContent = "Select a category";
  markerGrid.innerHTML = "";
  note.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderResult(result) {
  currentResult = result;
  activeCategory = "";
  startScreen.classList.add("hidden");
  reportScreen.classList.remove("hidden");
  resultNav.classList.add("hidden");

  const score = result.score || 0;
  animateScore(score);
  summaryTitle.textContent = titleForScore(score, result.markers.length);
  summaryText.textContent = formatResultSummary(result);
  disclaimer.textContent = result.disclaimer;
  greatCount.textContent = result.counts.great || 0;
  focusCount.textContent = (result.counts.low || 0) + (result.counts.high || 0);

  if (result.note) {
    note.textContent = result.note;
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }

  renderCategoryFilters(result);
  renderAiReview(result);
  detailsPanel.classList.add("hidden");
  detailsTitle.textContent = "Select a category";
  markerGrid.innerHTML = "";

  window.scrollTo({ top: 0, behavior: "smooth" });
  updateResultNav();
}

window.addEventListener("scroll", updateResultNav, { passive: true });
window.addEventListener("resize", updateResultNav);

function updateResultNav() {
  if (reportScreen.classList.contains("hidden") || !currentResult?.markers?.length) {
    resultNav.classList.add("hidden");
    return;
  }

  const footerTop = disclaimer.getBoundingClientRect().top + window.scrollY;
  const shouldShow = window.scrollY + window.innerHeight >= footerTop - 20;
  resultNav.classList.toggle("hidden", !shouldShow);
}

function animateScore(targetScore) {
  const finalScore = Number(targetScore) || 0;
  const duration = 950;
  const startTime = performance.now();

  scoreValue.textContent = finalScore ? "0" : "--";
  scoreRing.style.setProperty("--score", 0);

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      scoreRing.style.setProperty("--score", finalScore);
    });
  });

  if (!finalScore) return;

  function tick(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    scoreValue.textContent = Math.round(finalScore * eased);
    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

function formatResultSummary(result) {
  if (!result.markers.length) {
    return "No recognizable biomarkers were found. Try a text-based PDF, TXT, CSV, or TSV report.";
  }

  const total = result.markers.length;
  const sections = result.categories.length;
  const review = (result.counts.low || 0) + (result.counts.high || 0);
  const strong = result.counts.great || 0;
  const inRange = result.counts.ok || 0;
  const reviewText = review ? `${review} need review` : "no urgent flags";
  return `Analyzed ${total} biomarkers in ${sections} sections. ${reviewText}; ${strong} look strong; ${inRange} are in range.`;
}

function renderAiReview(result) {
  aiInsightGrid.innerHTML = "";
  if (!result.markers.length) {
    aiReview.classList.add("hidden");
    return;
  }

  aiReview.classList.remove("hidden");
  const analysis = normalizeAiAnalysis(result);
  aiReviewTitle.textContent = analysis.isAi ? "Gemini Analysis" : "Gemini Error";
  aiSummaryText.textContent = analysis.summary;

  addInsightSection("Review First", analysis.reviewFirst, "priority_high");
  addInsightSection("Patterns", analysis.patterns, "hub");
  addInsightSection("Suggested Next Steps", analysis.nextSteps, "checklist");
  addInsightSection("Ask Your Clinician", analysis.questions, "help");
}

function normalizeAiAnalysis(result) {
  const ai = result.ai_analysis || {};
  const hasUsefulAi = result.ai_enabled && typeof ai.summary === "string" && ai.summary.trim().length >= 80;
  if (hasUsefulAi) {
    return {
      isAi: true,
      summary: ai.summary.trim(),
      reviewFirst: normalizeAiReviewItems(ai.review_first),
      patterns: normalizeTextItems(ai.patterns),
      nextSteps: normalizeTextItems(ai.next_steps),
      questions: normalizeTextItems(ai.clinician_questions),
    };
  }

  return {
    isAi: false,
    summary: result.ai_error || "Gemini did not return an analysis. Check GEMINI_API_KEY / GOOGLE_API_KEY, model name, network access, and API key restrictions.",
    reviewFirst: [],
    patterns: [],
    nextSteps: [],
    questions: [],
  };
}

function addInsightSection(title, items, icon) {
  if (!items.length) return;
  const section = document.createElement("section");
  section.className = "ai-insight-section";
  const rows = items
    .map((item) => {
      const titleText = typeof item === "string" ? item : item.title;
      const bodyText = typeof item === "string" ? "" : item.body;
      return `
        <div class="ai-insight-item">
          <span class="ai-focus-badge">${escapeHtml(initialsFromText(titleText))}</span>
          <div>
            <strong>${escapeHtml(titleText)}</strong>
            ${bodyText ? `<small>${escapeHtml(bodyText)}</small>` : ""}
          </div>
        </div>
      `;
    })
    .join("");
  section.innerHTML = `
    <h3><span class="material-symbols-outlined">${icon}</span>${escapeHtml(title)}</h3>
    <div class="ai-insight-list">${rows}</div>
  `;
  aiInsightGrid.appendChild(section);
}

function normalizeAiReviewItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => ({
      title: String(item.marker || "Review marker").trim(),
      body: [item.reason, item.suggestion].filter(Boolean).join(" "),
    }))
    .filter((item) => item.title || item.body)
    .slice(0, 4);
}

function normalizeTextItems(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => String(item).trim()).filter(Boolean).slice(0, 4);
}

function initialsFromText(text) {
  return String(text)
    .replace(/[^a-zA-Z0-9 ]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

function joinHuman(items) {
  if (items.length <= 1) return items[0] || "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function renderCategoryFilters(result) {
  categoryGrid.innerHTML = "";
  if (!result.markers.length) {
    categoryGrid.classList.add("hidden");
    return;
  }

  categoryGrid.classList.remove("hidden");

  result.categories.forEach((category) => {
    categoryGrid.appendChild(
      createCategoryButton(category.name, category.name, category.markers.length, category.score, markerIcons[category.name] || "category")
    );
  });
}

function createCategoryButton(value, label, count, score, icon) {
  const button = document.createElement("button");
  button.className = "category-card";
  button.type = "button";
  button.dataset.category = value;
  button.setAttribute("aria-pressed", value === activeCategory ? "true" : "false");
  button.innerHTML = `
    <span class="category-icon material-symbols-outlined">${icon}</span>
    <span class="category-copy">
      <strong>${escapeHtml(label)}</strong>
      <small>${count} marker${count === 1 ? "" : "s"} &middot; ${score}/100 &middot; tap to view</small>
    </span>
  `;
  button.addEventListener("click", () => renderMarkersForCategory(value));
  return button;
}

function renderMarkersForCategory(categoryName) {
  activeCategory = categoryName;
  categoryGrid.querySelectorAll(".category-card").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.category === activeCategory ? "true" : "false");
  });

  markerGrid.innerHTML = "";
  if (!currentResult?.markers?.length) {
    markerGrid.appendChild(createEmptyCard());
    return;
  }

  const markers =
    currentResult.markers.filter((marker) => marker.category === categoryName);

  detailsTitle.textContent = `${categoryName} Markers`;
  detailsPanel.classList.remove("hidden");
  markers.forEach((marker) => markerGrid.appendChild(createMarkerCard(marker)));
  detailsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  updateResultNav();
}

function createMarkerCard(marker) {
  const card = document.createElement("article");
  const tone = toneForMarker(marker);
  const position = markerPosition(marker);
  const optimal = optimalRangePosition(marker);
  const tips = marker.tips.slice(0, 2).map((tip) => `<li>${escapeHtml(tip)}</li>`).join("");

  card.className = "marker-card";
  card.dataset.tone = tone;
  card.style.setProperty("--marker-position", `${position}%`);
  card.style.setProperty("--opt-start", `${optimal.start}%`);
  card.style.setProperty("--opt-width", `${optimal.width}%`);

  card.innerHTML = `
    <div class="marker-top">
      <div class="marker-heading">
        <span class="marker-icon">
          <span class="material-symbols-outlined">${iconForMarker(marker)}</span>
        </span>
        <div class="marker-title">
          <div class="marker-category">${escapeHtml(marker.category)}</div>
          <h2>${escapeHtml(marker.name)}</h2>
        </div>
      </div>
      <span class="status-pill ${marker.status}">${labelForStatus(marker.status)}</span>
    </div>

    <div>
      <div class="value-row">
        <span class="value">${formatNumber(marker.value)}</span>
        <span class="unit">${escapeHtml(marker.unit)}</span>
      </div>
      <div class="range-bar" aria-label="${escapeHtml(marker.name)} score ${marker.score} out of 100">
        <span class="range-fill"></span>
        <span class="range-optimal"></span>
        <span class="range-dot"></span>
      </div>
      <div class="range-labels">
        <span>Ref ${formatNumber(marker.range.low)}</span>
        <span>Score ${marker.score}/100</span>
        <span>${formatNumber(marker.range.high)}</span>
      </div>
    </div>

    <div class="marker-info">
      <h3><span class="material-symbols-outlined">info</span> What is this?</h3>
      <p>${escapeHtml(marker.about || marker.message)}</p>
    </div>

    <ul class="marker-tips">${tips}</ul>
  `;

  return card;
}

function createEmptyCard() {
  const card = document.createElement("article");
  card.className = "marker-card";
  card.dataset.tone = "gold";
  card.innerHTML = `
    <div class="marker-top">
      <div class="marker-heading">
        <span class="marker-icon">
          <span class="material-symbols-outlined">search</span>
        </span>
        <div class="marker-title">
          <div class="marker-category">No markers found</div>
          <h2>Try a clearer report</h2>
        </div>
      </div>
    </div>
    <div class="marker-info">
      <h3><span class="material-symbols-outlined">info</span> What happened?</h3>
      <p>The app needs readable report text. If the PDF is scanned as an image, run OCR first or upload a text/CSV version.</p>
    </div>
  `;
  return card;
}

function titleForScore(score, markerCount) {
  if (!markerCount) return "Report Analysis";
  if (score >= 85) return "Strong Report";
  if (score >= 70) return "Good Report";
  if (score >= 50) return "Needs Review";
  return "Review First";
}

function toneForMarker(marker) {
  if (marker.status === "low" || marker.status === "high") return "gold";
  if (marker.status === "great") {
    return marker.category === "Vitamins" || marker.category === "Iron" ? "gold" : "mint";
  }
  if (marker.category === "Lipids" || marker.category === "Blood") return "mint";
  return "pink";
}

function iconForMarker(marker) {
  return markerIcons[marker.category] || "monitor_heart";
}

function markerPosition(marker) {
  const low = Number(marker.range.low);
  const high = Number(marker.range.high);
  const value = Number(marker.value);
  const span = Math.max(high - low, 1);
  const paddedLow = low - span * 0.25;
  const paddedHigh = high + span * 0.25;
  return clamp(((value - paddedLow) / (paddedHigh - paddedLow)) * 100, 4, 96);
}

function optimalRangePosition(marker) {
  const low = Number(marker.range.low);
  const high = Number(marker.range.high);
  const optLow = Number(marker.optimal?.low ?? low);
  const optHigh = Number(marker.optimal?.high ?? high);
  const span = Math.max(high - low, 1);
  const paddedLow = low - span * 0.25;
  const paddedHigh = high + span * 0.25;
  const start = clamp(((optLow - paddedLow) / (paddedHigh - paddedLow)) * 100, 0, 100);
  const end = clamp(((optHigh - paddedLow) / (paddedHigh - paddedLow)) * 100, 0, 100);
  return { start, width: Math.max(end - start, 8) };
}

function labelForStatus(status) {
  if (status === "great") return "Great";
  if (status === "ok") return "In Range";
  if (status === "low") return "Low";
  if (status === "high") return "High";
  return status;
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isInteger(number) ? number.toString() : number.toFixed(1).replace(/\.0$/, "");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
