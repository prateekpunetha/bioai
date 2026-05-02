const form = document.querySelector("#reportForm");
const fileInput = document.querySelector("#reportFile");
const loadSample = document.querySelector("#loadSample");
const markerGrid = document.querySelector("#markerGrid");
const summaryTitle = document.querySelector("#summaryTitle");
const summaryText = document.querySelector("#summaryText");
const scoreValue = document.querySelector("#scoreValue");
const greatCount = document.querySelector("#greatCount");
const focusCount = document.querySelector("#focusCount");
const disclaimer = document.querySelector("#disclaimer");
const note = document.querySelector("#note");

loadSample.addEventListener("click", async () => {
  setLoading(true, "Loading sample...");
  try {
    const response = await fetch("/api/sample", { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load sample PDF.");
    renderResult(result);
    const label = document.querySelector(".dropzone strong");
    label.textContent = result.sample_file || "Sample PDF";
  } catch (error) {
    summaryTitle.textContent = "Sample failed";
    summaryText.textContent = error.message;
  } finally {
    setLoading(false);
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  const label = document.querySelector(".dropzone strong");
  label.textContent = file ? file.name : "Drop a report or choose file";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    summaryTitle.textContent = "Choose a report first";
    summaryText.textContent = "Upload a PDF, TXT, CSV, or TSV file, or use the sample report.";
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
    summaryTitle.textContent = "Analysis failed";
    summaryText.textContent = error.message;
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading, label = "Analyzing...") {
  const button = form.querySelector(".primary");
  button.disabled = isLoading;
  loadSample.disabled = isLoading;
  button.textContent = isLoading ? label : "Analyze report";
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
        <p class="about"><b>What it is:</b> ${escapeHtml(marker.about || "Read this marker with nearby results and your lab range.")}</p>
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
