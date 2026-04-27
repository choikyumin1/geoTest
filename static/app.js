// ===== DOM Elements =====
const form = document.getElementById("search-form");
const input = document.getElementById("url-input");
const btn = document.getElementById("search-btn");
const btnText = btn.querySelector(".btn-text");
const btnLoading = btn.querySelector(".btn-loading");
const errorMsg = document.getElementById("error-msg");
const heroSection = document.getElementById("hero");
const resultsSection = document.getElementById("results");
const resultDomain = document.getElementById("result-domain");
const resultBrand = document.getElementById("result-brand");
const cardsContainer = document.getElementById("llm-cards");
const statusBar = document.getElementById("llm-status");
const numQueriesSelect = document.getElementById("num-queries");
const autoOptions = document.getElementById("auto-options");
const customPromptArea = document.getElementById("custom-prompt-area");
const promptList = document.getElementById("prompt-list");
const addPromptBtn = document.getElementById("add-prompt-btn");

const competitorInput = document.getElementById("competitor-input");
const summaryMetrics = document.getElementById("summary-metrics");

// Chart instances
let citationChart = null;
let domainChart = null;
let sentimentChart = null;
let positionChart = null;
let competitorChart = null;

// Current query mode
let queryMode = "auto";

// LLM color mapping
const LLM_COLORS = {
  ChatGPT: "#10a37f",
  Perplexity: "#20b8cd",
  Claude: "#d97706",
  Gemini: "#4285f4",
};

// ===== Load LLM Status on page load =====
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const status = await res.json();
    statusBar.innerHTML = "";
    for (const [name, mode] of Object.entries(status)) {
      const chip = document.createElement("span");
      chip.className = `status-chip ${mode}`;
      chip.innerHTML = `<span class="dot"></span>${name} <span style="opacity:0.7">${mode === "live" ? "API" : "Mock"}</span>`;
      statusBar.appendChild(chip);
    }
  } catch {
    // silently ignore
  }
}

loadStatus();

// ===== Query Mode Toggle =====
document.querySelectorAll(".mode-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".mode-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    queryMode = tab.dataset.mode;

    if (queryMode === "auto") {
      autoOptions.hidden = false;
      customPromptArea.hidden = true;
    } else {
      autoOptions.hidden = true;
      customPromptArea.hidden = false;
    }
  });
});

// ===== Custom Prompt Management =====
addPromptBtn.addEventListener("click", () => {
  addPromptRow();
});

function addPromptRow() {
  const rows = promptList.querySelectorAll(".prompt-row");
  const num = rows.length + 1;
  const row = document.createElement("div");
  row.className = "prompt-row";
  row.innerHTML = `
    <span class="prompt-num">${num}</span>
    <textarea class="prompt-input" rows="2" placeholder="프롬프트를 입력하세요..."></textarea>
    <button type="button" class="remove-prompt-btn" title="삭제">&times;</button>
  `;
  row.querySelector(".remove-prompt-btn").addEventListener("click", () => {
    row.remove();
    renumberPrompts();
  });
  promptList.appendChild(row);
  // Show remove buttons when more than 1 row
  updateRemoveButtons();
}

function renumberPrompts() {
  promptList.querySelectorAll(".prompt-row").forEach((row, i) => {
    row.querySelector(".prompt-num").textContent = i + 1;
  });
  updateRemoveButtons();
}

function updateRemoveButtons() {
  const rows = promptList.querySelectorAll(".prompt-row");
  rows.forEach((row) => {
    const btn = row.querySelector(".remove-prompt-btn");
    btn.hidden = rows.length <= 1;
  });
}

function getCustomPrompts() {
  const prompts = [];
  promptList.querySelectorAll(".prompt-input").forEach((ta) => {
    const val = ta.value.trim();
    if (val) prompts.push(val);
  });
  return prompts;
}

// ===== Form Submit =====
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!url) return;

  const body = { url };

  // Competitors
  const compText = competitorInput.value.trim();
  if (compText) {
    body.competitors = compText.split(",").map((s) => s.trim()).filter(Boolean);
  }

  if (queryMode === "custom") {
    const prompts = getCustomPrompts();
    if (prompts.length === 0) {
      showError("프롬프트를 최소 1개 입력해주세요.");
      return;
    }
    body.custom_prompts = prompts;
    body.num_queries = prompts.length;
  } else {
    body.num_queries = parseInt(numQueriesSelect.value, 10);
  }

  setLoading(true);
  hideError();
  resultsSection.hidden = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) throw new Error(`Server error (${res.status})`);

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    showError(err.message || "Analysis failed.");
  } finally {
    setLoading(false);
  }
});

// ===== UI Helpers =====
function setLoading(loading) {
  btn.disabled = loading;
  input.disabled = loading;
  btnText.hidden = loading;
  btnLoading.hidden = !loading;
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.hidden = false;
}

function hideError() {
  errorMsg.hidden = true;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ===== Render Results =====
function renderResults(data) {
  heroSection.classList.add("compact");
  resultsSection.hidden = false;
  resultDomain.textContent = data.target_domain;
  resultBrand.textContent = data.brand ? `Brand: ${data.brand}` : "";

  renderSummaryMetrics(data.results);
  renderCitationChart(data.results);
  renderSentimentChart(data.results);
  renderPositionChart(data.results);
  renderCompetitorChart(data.results, data.target_domain);
  renderLLMCards(data.results, data.target_domain);
  renderDomainChart(data.results);

  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ===== Summary Metric Cards =====
function renderSummaryMetrics(results) {
  const live = results.filter((r) => r.mode === "live");
  const source = live.length > 0 ? live : results;

  const avgCitation = avg(source.map((r) => r.citation_rate));
  const avgMention = avg(source.map((r) => r.mention_rate));
  const avgSent = avg(source.map((r) => r.avg_sentiment));
  const avgPos = avg(
    source.map((r) => r.avg_position).filter((p) => p >= 0)
  );

  const sentLabel = avgSent > 0.2 ? "Positive" : avgSent < -0.2 ? "Negative" : "Neutral";
  const sentColor = avgSent > 0.2 ? "var(--green)" : avgSent < -0.2 ? "#f87171" : "var(--muted)";
  const posLabel = avgPos < 0 ? "N/A" : avgPos <= 33 ? "Top" : avgPos <= 66 ? "Middle" : "Bottom";
  const posColor = avgPos <= 33 ? "var(--green)" : avgPos <= 66 ? "#facc15" : "#f87171";

  summaryMetrics.innerHTML = `
    <div class="metric-card">
      <div class="metric-value" style="color:var(--accent)">${avgCitation.toFixed(1)}%</div>
      <div class="metric-label">Avg Citation Rate</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:var(--chart-5)">${avgMention.toFixed(1)}%</div>
      <div class="metric-label">Avg Mention Rate</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:${sentColor}">${sentLabel}</div>
      <div class="metric-label">Avg Sentiment (${avgSent.toFixed(2)})</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:${posColor}">${posLabel}</div>
      <div class="metric-label">Avg Position${avgPos >= 0 ? ` (${avgPos.toFixed(0)}%)` : ""}</div>
    </div>
  `;
}

function avg(arr) {
  if (!arr.length) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function sentimentLabel(score) {
  if (score > 0.2) return "positive";
  if (score < -0.2) return "negative";
  return "neutral";
}

function positionLabel(pct) {
  if (pct < 0) return "none";
  if (pct <= 33) return "top";
  if (pct <= 66) return "middle";
  return "bottom";
}

// ===== 1. Main Bar Chart: Citation Rate per LLM =====
function renderCitationChart(results) {
  const ctx = document.getElementById("citation-chart").getContext("2d");
  if (citationChart) citationChart.destroy();

  const labels = results.map((r) => r.llm);
  const rates = results.map((r) => r.citation_rate);
  const colors = labels.map((l) => LLM_COLORS[l] || "#6c63ff");

  citationChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels.map((l, i) => {
        const mode = results[i].mode;
        return mode === "mock" ? `${l} (Mock)` : l;
      }),
      datasets: [
        {
          label: "Citation Rate (%)",
          data: rates,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 2,
          borderRadius: 8,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Citation Rate: ${ctx.parsed.y}%`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: {
            color: "#8b8fa8",
            callback: (v) => v + "%",
          },
        },
        x: {
          grid: { display: false },
          ticks: { color: "#e4e6f0", font: { weight: "bold", size: 13 } },
        },
      },
    },
  });
}

// ===== 2. Sentiment Chart =====
function renderSentimentChart(results) {
  const ctx = document.getElementById("sentiment-chart").getContext("2d");
  if (sentimentChart) sentimentChart.destroy();

  const labels = results.map((r) => r.llm);
  const posData = results.map((r) => r.sentiment_dist?.positive || 0);
  const neuData = results.map((r) => r.sentiment_dist?.neutral || 0);
  const negData = results.map((r) => r.sentiment_dist?.negative || 0);

  sentimentChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Positive", data: posData, backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Neutral", data: neuData, backgroundColor: "#8b8fa8", borderRadius: 4 },
        { label: "Negative", data: negData, backgroundColor: "#f87171", borderRadius: 4 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { labels: { color: "#8b8fa8", font: { size: 11 } } } },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { stacked: true, beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#8b8fa8", stepSize: 1 } },
      },
    },
  });
}

// ===== 3. Position Chart =====
function renderPositionChart(results) {
  const ctx = document.getElementById("position-chart").getContext("2d");
  if (positionChart) positionChart.destroy();

  const labels = results.map((r) => r.llm);
  const topData = results.map((r) => r.position_dist?.top || 0);
  const midData = results.map((r) => r.position_dist?.middle || 0);
  const botData = results.map((r) => r.position_dist?.bottom || 0);
  const noneData = results.map((r) => r.position_dist?.none || 0);

  positionChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Top (상단)", data: topData, backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Middle (중간)", data: midData, backgroundColor: "#facc15", borderRadius: 4 },
        { label: "Bottom (하단)", data: botData, backgroundColor: "#f87171", borderRadius: 4 },
        { label: "None (없음)", data: noneData, backgroundColor: "#3a3d52", borderRadius: 4 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { labels: { color: "#8b8fa8", font: { size: 11 } } } },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { stacked: true, beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#8b8fa8", stepSize: 1 } },
      },
    },
  });
}

// ===== 4. Competitor Comparison Chart =====
function renderCompetitorChart(results, targetDomain) {
  const section = document.getElementById("competitor-section");
  const hasCompetitors = results.some((r) => Object.keys(r.competitor_rates || {}).length > 0);

  if (!hasCompetitors) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const ctx = document.getElementById("competitor-chart").getContext("2d");
  if (competitorChart) competitorChart.destroy();

  // Gather all domains (target + competitors)
  const competitors = new Set();
  results.forEach((r) => {
    Object.keys(r.competitor_rates || {}).forEach((c) => competitors.add(c));
  });

  const allDomains = [targetDomain, ...competitors];
  const palette = ["#6c63ff", "#f472b6", "#facc15", "#60a5fa", "#fb923c", "#a78bfa"];

  const datasets = allDomains.map((domain, i) => ({
    label: domain,
    data: results.map((r) => {
      if (domain === targetDomain) return r.citation_rate;
      return r.competitor_rates?.[domain] || 0;
    }),
    backgroundColor: palette[i % palette.length],
    borderRadius: 4,
  }));

  competitorChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: results.map((r) => r.llm),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { labels: { color: "#8b8fa8", font: { size: 11 } } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#8b8fa8", callback: (v) => v + "%" } },
      },
    },
  });
}

// ===== 5. LLM Detail Cards with Query Details =====
function renderLLMCards(results, targetDomain) {
  cardsContainer.innerHTML = "";

  results.forEach((r) => {
    const color = LLM_COLORS[r.llm] || "#6c63ff";
    const modeClass = r.mode === "live" ? "live" : "mock";
    const modeLabel = r.mode === "live" ? "LIVE" : "MOCK";
    const details = r.query_details || [];

    // Build query detail rows
    let detailsHtml = "";
    details.forEach((d, i) => {
      const citedClass = d.cited ? "cited-yes" : "cited-no";
      const citedLabel = d.cited ? "CITED" : "NOT CITED";
      const errorHtml = d.error
        ? `<div class="detail-error">Error: ${escapeHtml(d.error)}</div>`
        : "";

      // Highlight target domain URLs in the response
      let responseHtml = escapeHtml(d.response);
      if (targetDomain) {
        const urlPattern = new RegExp(
          `(https?://[^\\s)\\]}>,"']*${targetDomain.replace(/\./g, "\\.")}[^\\s)\\]}>,"']*)`,
          "gi"
        );
        responseHtml = responseHtml.replace(
          urlPattern,
          '<span class="highlight-url">$1</span>'
        );
      }

      // Extracted URLs list
      let urlsHtml = "";
      if (d.urls && d.urls.length > 0) {
        const urlItems = d.urls
          .map((u) => {
            const isTarget = targetDomain && u.includes(targetDomain);
            return `<li class="${isTarget ? "target-url" : ""}">${escapeHtml(u)}</li>`;
          })
          .join("");
        urlsHtml = `<div class="detail-urls"><strong>Extracted URLs (${d.urls.length}):</strong><ul>${urlItems}</ul></div>`;
      }

      detailsHtml += `
        <div class="query-detail">
          <div class="detail-header">
            <span class="detail-index">Q${i + 1}</span>
            <span class="cited-badge ${citedClass}">${citedLabel}</span>
            ${d.brand_mentioned ? '<span class="cited-badge cited-yes">MENTIONED</span>' : ""}
            ${d.sentiment ? `<span class="sentiment-badge ${d.sentiment.label}">${d.sentiment.label}</span>` : ""}
            ${d.position ? `<span class="position-badge ${d.position.section}">${d.position.section}</span>` : ""}
          </div>
          <div class="detail-query"><strong>Query:</strong> ${escapeHtml(d.query)}</div>
          ${errorHtml}
          <div class="detail-response"><strong>Response:</strong><div class="response-text">${responseHtml}</div></div>
          ${urlsHtml}
        </div>
      `;
    });

    const card = document.createElement("div");
    card.className = "llm-card full-width";
    card.innerHTML = `
      <div class="card-header">
        <span class="llm-name" style="color:${color}">
          ${r.llm}
          <span class="mode-badge ${modeClass}">${modeLabel}</span>
        </span>
        <span class="rate-badge" style="color:${color}">${r.citation_rate}%</span>
      </div>
      <div class="stat-row"><span>Total Queries</span><span>${r.total_queries}</span></div>
      <div class="stat-row"><span>Successful</span><span>${r.successful_queries}</span></div>
      <div class="stat-row"><span>Citation Rate</span><span>${r.citation_rate}%</span></div>
      <div class="stat-row"><span>Mention Rate</span><span>${r.mention_rate}%</span></div>
      <div class="stat-row"><span>Sentiment</span><span><span class="sentiment-badge ${sentimentLabel(r.avg_sentiment)}">${sentimentLabel(r.avg_sentiment)} (${r.avg_sentiment})</span></span></div>
      <div class="stat-row"><span>Avg Position</span><span><span class="position-badge ${positionLabel(r.avg_position)}">${positionLabel(r.avg_position)}${r.avg_position >= 0 ? ` (${r.avg_position}%)` : ""}</span></span></div>
      ${r.errors > 0 ? `<div class="stat-row"><span style="color:#f87171">Errors</span><span style="color:#f87171">${r.errors}</span></div>` : ""}
      <div class="bar-track">
        <div class="bar-fill" style="width:${r.citation_rate}%;background:${color}"></div>
      </div>
      ${details.length > 0 ? `
        <button class="toggle-details" onclick="this.parentElement.querySelector('.query-details').classList.toggle('open'); this.textContent = this.textContent.includes('+') ? '- Hide Details' : '+ Show Details'">
          + Show Details
        </button>
        <div class="query-details">${detailsHtml}</div>
      ` : ""}
    `;
    cardsContainer.appendChild(card);
  });
}

// ===== 3. Top Domains Horizontal Bar Chart =====
function renderDomainChart(results) {
  const domainTotals = {};
  results.forEach((r) => {
    for (const [domain, count] of Object.entries(r.top_domains)) {
      domainTotals[domain] = (domainTotals[domain] || 0) + count;
    }
  });

  const sorted = Object.entries(domainTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  const ctx = document.getElementById("domain-chart").getContext("2d");
  if (domainChart) domainChart.destroy();

  const palette = [
    "#6c63ff", "#f472b6", "#34d399", "#facc15",
    "#60a5fa", "#fb923c", "#a78bfa", "#e879f9",
  ];

  domainChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map(([d]) => d),
      datasets: [
        {
          label: "Citation Count",
          data: sorted.map(([, c]) => c),
          backgroundColor: sorted.map((_, i) => palette[i % palette.length]),
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#8b8fa8" },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#e4e6f0", font: { size: 12 } },
        },
      },
    },
  });
}
