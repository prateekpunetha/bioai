const form = document.querySelector("#reportForm");
const fileInput = document.querySelector("#reportFile");
const textInput = document.querySelector("#reportText");
const loadSample = document.querySelector("#loadSample");
const markerGrid = document.querySelector("#markerGrid");
const summaryTitle = document.querySelector("#summaryTitle");
const summaryText = document.querySelector("#summaryText");
const scoreValue = document.querySelector("#scoreValue");
const greatCount = document.querySelector("#greatCount");
const focusCount = document.querySelector("#focusCount");
const disclaimer = document.querySelector("#disclaimer");
const note = document.querySelector("#note");

const sampleReport = `Vitamin D 28 ng/mL
Vitamin B12 520 pg/mL
Ferritin 38 ng/mL
Hemoglobin 14.2 g/dL
WBC 6.4 10^3/uL
RBC 4.9 10^6/uL
Hematocrit 43 %
Platelets 240 10^3/uL
MCV 88 fL
HbA1c 5.2 %
Fasting Glucose 93 mg/dL
Fasting Insulin 7 uIU/mL
TSH 2.2 mIU/L
Free T4 1.2 ng/dL
ALT 24 U/L
AST 22 U/L
Creatinine 0.9 mg/dL
eGFR 101 mL/min
Sodium 140 mmol/L
Potassium 4.2 mmol/L
Total Cholesterol 188 mg/dL
HDL 54 mg/dL
LDL 112 mg/dL
Triglycerides 92 mg/dL
CRP 0.7 mg/L`;

loadSample.addEventListener("click", () => {
  textInput.value = sampleReport;
  form.requestSubmit();
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  const label = document.querySelector(".dropzone strong");
  label.textContent = file ? file.name : "Drop a report or choose file";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
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
    summaryTitle.textContent = "Analysis failed";
    summaryText.textContent = error.message;
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  const button = form.querySelector(".primary");
  button.disabled = isLoading;
  button.textContent = isLoading ? "Analyzing..." : "Analyze report";
}

function renderResult(result) {
  scoreValue.textContent = result.score || "--";
  summaryTitle.textContent = result.markers.length ? `Report score: ${result.score}/100` : "No biomarkers found yet";
  summaryText.textContent = result.ai_summary || result.summary;
  disclaimer.textContent = result.disclaimer;
  greatCount.textContent = result.counts.great || 0;
  focusCount.textContent = (result.counts.low || 0) + (result.counts.high || 0);

  if (result.note) {
    note.textContent = result.note;
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }

  markerGrid.innerHTML = "";
  if (result.focus?.length) markerGrid.appendChild(createPrioritySection("Review first", result.focus));
  if (result.wins?.length) markerGrid.appendChild(createPrioritySection("Looking good", result.wins));
  result.categories.forEach((category) => markerGrid.appendChild(createCategorySection(category)));
}

function createPrioritySection(title, markers) {
  const section = document.createElement("section");
  section.className = "report-section priority-section";
  const rows = markers.map(createMarkerRow).join("");
  section.innerHTML = `
    <div class="section-head">
      <div>
        <p class="eyebrow">${escapeHtml(title)}</p>
        <h3>${title === "Review first" ? "Values that need attention" : "Strong markers to keep doing"}</h3>
      </div>
      <span class="section-count">${markers.length}</span>
    </div>
    <div class="marker-list">${rows}</div>
  `;
  return section;
}

function createCategorySection(category) {
  const section = document.createElement("section");
  section.className = "report-section";
  const rows = category.markers.map(createMarkerRow).join("");
  section.innerHTML = `
    <div class="section-head">
      <div>
        <p class="eyebrow">${escapeHtml(category.name)}</p>
        <h3>${escapeHtml(category.label)} section</h3>
      </div>
      <div class="section-score">${category.score}<small>/100</small></div>
    </div>
    <div class="marker-list">${rows}</div>
  `;
  return section;
}

function createMarkerRow(marker) {
  const tips = marker.tips.slice(0, 2).map((tip) => `<li>${escapeHtml(tip)}</li>`).join("");
  return `
    <article class="marker-row">
      <div class="marker-main">
        <div class="marker-title">
          <h4>${escapeHtml(marker.name)}</h4>
          <span class="status-pill ${marker.status}">${labelForStatus(marker.status)}</span>
        </div>
        <p class="about">${escapeHtml(marker.about || "This marker should be read with nearby results and your lab reference range.")}</p>
        <p>${escapeHtml(marker.message)}</p>
        <ul class="tips">${tips}</ul>
      </div>
      <div class="marker-metric">
        <div class="value-row">
          <span class="value">${formatNumber(marker.value)}</span>
          <span class="unit">${escapeHtml(marker.unit)}</span>
        </div>
        <div class="range-text">Ref ${formatNumber(marker.range.low)}-${formatNumber(marker.range.high)}</div>
        <div class="bar" aria-hidden="true">
          <div class="fill" style="--score: ${marker.score}%"></div>
        </div>
        <div class="range-text">Score ${marker.score}/100</div>
      </div>
    </article>
  `;
}

function createMarkerCard(marker) {
  const card = document.createElement("article");
  card.className = "marker-card";

  card.innerHTML = `
    <div class="marker-top">
      <div>
        <div class="category">${escapeHtml(marker.category)}</div>
        <h3 class="marker-name">${escapeHtml(marker.name)}</h3>
      </div>
      <span class="status-pill ${marker.status}">${labelForStatus(marker.status)}</span>
    </div>
    <div class="value-row">
      <span class="value">${formatNumber(marker.value)}</span>
      <span class="unit">${escapeHtml(marker.unit)}</span>
    </div>
  `;
  return card;
}

function labelForStatus(status) {
  if (status === "great") return "great";
  if (status === "ok") return "in range";
  return status;
}

function formatNumber(value) {
  return Number.isInteger(value) ? value.toString() : value.toFixed(1).replace(/\.0$/, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
