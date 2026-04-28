// ===== DOM =====
const form = document.getElementById("search-form");
const input = document.getElementById("url-input");
const btn = document.getElementById("search-btn");
const btnText = btn.querySelector(".btn-text");
const btnLoading = btn.querySelector(".btn-loading");
const errorMsg = document.getElementById("error-msg");
const heroSection = document.getElementById("hero");
const dashboard = document.getElementById("dashboard");
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

// Charts
let charts = {};
let queryMode = "auto";

const LLM_COLORS = {
  ChatGPT: "#10a37f",
  Perplexity: "#20b8cd",
  Claude: "#d97706",
  Gemini: "#4285f4",
};

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: { legend: { labels: { color: "#8b8fa8", font: { size: 11 } } } },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#e4e6f0", font: { size: 11 } } },
    y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8" } },
  },
};

// ===== Status =====
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
  } catch {}
}
loadStatus();

// ===== Query Mode =====
document.querySelectorAll(".mode-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".mode-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    queryMode = tab.dataset.mode;
    autoOptions.hidden = queryMode !== "auto";
    customPromptArea.hidden = queryMode !== "custom";
  });
});

// ===== Custom Prompts =====
addPromptBtn.addEventListener("click", addPromptRow);

function addPromptRow() {
  const rows = promptList.querySelectorAll(".prompt-row");
  const row = document.createElement("div");
  row.className = "prompt-row";
  row.innerHTML = `
    <span class="prompt-num">${rows.length + 1}</span>
    <textarea class="prompt-input" rows="2" placeholder="프롬프트를 입력하세요..."></textarea>
    <button type="button" class="remove-prompt-btn" title="삭제">&times;</button>
  `;
  row.querySelector(".remove-prompt-btn").addEventListener("click", () => { row.remove(); renumberPrompts(); });
  promptList.appendChild(row);
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
  rows.forEach((row) => { row.querySelector(".remove-prompt-btn").hidden = rows.length <= 1; });
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
  const compText = competitorInput.value.trim();
  if (compText) body.competitors = compText.split(",").map(s => s.trim()).filter(Boolean);

  if (queryMode === "custom") {
    const prompts = getCustomPrompts();
    if (prompts.length === 0) { showError("프롬프트를 최소 1개 입력해주세요."); return; }
    body.custom_prompts = prompts;
    body.num_queries = prompts.length;
  } else {
    body.num_queries = parseInt(numQueriesSelect.value, 10);
  }

  setLoading(true);
  hideError();
  dashboard.hidden = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Server error (${res.status})`);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    showError(err.message || "Analysis failed.");
  } finally {
    setLoading(false);
  }
});

// ===== Helpers =====
function setLoading(on) {
  btn.disabled = on;
  input.disabled = on;
  btnText.hidden = on;
  btnLoading.hidden = !on;
}

function showError(msg) { errorMsg.textContent = msg; errorMsg.hidden = false; }
function hideError() { errorMsg.hidden = true; }
function esc(text) { const d = document.createElement("div"); d.textContent = text; return d.innerHTML; }
function avg(arr) { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }
function sentLabel(s) { return s > 0.15 ? "positive" : s < -0.15 ? "negative" : "neutral"; }
function posLabel(p) { return p < 0 ? "none" : p <= 33 ? "top" : p <= 66 ? "middle" : "bottom"; }

function destroyChart(key) { if (charts[key]) { charts[key].destroy(); charts[key] = null; } }

function scoreColor(score) {
  if (score >= 70) return "#34d399";
  if (score >= 40) return "#facc15";
  return "#f87171";
}

// ===== Render Dashboard =====
function renderDashboard(data) {
  heroSection.classList.add("compact");
  dashboard.hidden = false;
  resultDomain.textContent = data.target_domain;
  resultBrand.textContent = data.brand ? `Brand: ${data.brand}` : "";

  renderAEOScoreRing(data.global_aeo_score);
  renderKPICards(data.results, data.global_aeo_score);
  renderCitationChart(data.results);
  renderAEOScoreChart(data.results);
  renderSentimentChart(data.results);
  renderPositionChart(data.results);
  renderCategoryChart(data.results);
  renderCompetitorChart(data.results, data.target_domain);
  renderSOVChart(data.results);
  renderDepthChart(data.results);
  renderDomainChart(data.results);
  renderLLMCards(data.results, data.target_domain);

  dashboard.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ===== AEO Score Ring =====
function renderAEOScoreRing(score) {
  const container = document.getElementById("aeo-score-ring");
  const pct = Math.min(100, Math.max(0, score));
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (pct / 100) * circumference;
  const color = scoreColor(score);

  container.innerHTML = `
    <svg viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="42" fill="none" stroke="#252840" stroke-width="6"/>
      <circle cx="50" cy="50" r="42" fill="none" stroke="${color}" stroke-width="6"
        stroke-dasharray="${circumference}" stroke-dashoffset="${offset}" stroke-linecap="round"/>
    </svg>
    <div class="score-value">
      <span style="color:${color}">${score.toFixed(0)}</span>
      <span class="score-label">AEO Score</span>
    </div>
  `;
}

// ===== KPI Cards =====
function renderKPICards(results, globalAEO) {
  const src = results;
  const avgCite = avg(src.map(r => r.citation_rate));
  const avgMention = avg(src.map(r => r.mention_rate));
  const avgRec = avg(src.map(r => r.recommendation_rate));
  const avgSent = avg(src.map(r => r.avg_sentiment));
  const avgPos = avg(src.map(r => r.avg_position).filter(p => p >= 0));
  const avgDepth = avg(src.map(r => r.avg_depth));

  const sentText = sentLabel(avgSent);
  const sentColors = { positive: "var(--green)", neutral: "var(--muted)", negative: "var(--red)" };
  const posText = avgPos >= 0 ? posLabel(avgPos) : "N/A";
  const posColors = { top: "var(--green)", middle: "var(--yellow)", bottom: "var(--red)", none: "var(--muted)" };

  summaryMetrics.innerHTML = `
    <div class="kpi-card accent">
      <div class="kpi-value" style="color:var(--accent)">${avgCite.toFixed(1)}%</div>
      <div class="kpi-label">Citation Rate</div>
      <div class="kpi-sub">URL 인용 비율</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-value" style="color:var(--green)">${avgMention.toFixed(1)}%</div>
      <div class="kpi-label">Mention Rate</div>
      <div class="kpi-sub">브랜드 언급 비율</div>
    </div>
    <div class="kpi-card pink">
      <div class="kpi-value" style="color:var(--pink)">${avgRec.toFixed(1)}%</div>
      <div class="kpi-label">Recommendation</div>
      <div class="kpi-sub">추천 비율</div>
    </div>
    <div class="kpi-card blue">
      <div class="kpi-value" style="color:${sentColors[sentText]}">${sentText.charAt(0).toUpperCase() + sentText.slice(1)}</div>
      <div class="kpi-label">Sentiment</div>
      <div class="kpi-sub">감성 점수 ${avgSent.toFixed(2)}</div>
    </div>
    <div class="kpi-card yellow">
      <div class="kpi-value" style="color:${posColors[posText.toLowerCase()] || "var(--muted)"}">${posText}</div>
      <div class="kpi-label">Position</div>
      <div class="kpi-sub">${avgPos >= 0 ? `상위 ${avgPos.toFixed(0)}%` : "데이터 없음"}</div>
    </div>
    <div class="kpi-card orange">
      <div class="kpi-value" style="color:var(--orange)">${avgDepth.toFixed(1)}</div>
      <div class="kpi-label">Citation Depth</div>
      <div class="kpi-sub">인용 깊이 (0~4)</div>
    </div>
  `;
}

// ===== Citation Rate Chart =====
function renderCitationChart(results) {
  destroyChart("citation");
  const ctx = document.getElementById("citation-chart").getContext("2d");
  const labels = results.map(r => r.mode === "mock" ? `${r.llm} (Mock)` : r.llm);
  const colors = results.map(r => LLM_COLORS[r.llm] || "#6c63ff");

  charts.citation = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Citation Rate", data: results.map(r => r.citation_rate), backgroundColor: colors, borderRadius: 6, borderSkipped: false },
        { label: "Mention Rate", data: results.map(r => r.mention_rate), backgroundColor: colors.map(c => c + "66"), borderRadius: 6, borderSkipped: false },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: { legend: { labels: { color: "#8b8fa8", font: { size: 11 } } } },
      scales: {
        ...CHART_DEFAULTS.scales,
        y: { ...CHART_DEFAULTS.scales.y, max: 100, ticks: { ...CHART_DEFAULTS.scales.y.ticks, callback: v => v + "%" } },
      },
    },
  });
}

// ===== AEO Score Chart =====
function renderAEOScoreChart(results) {
  destroyChart("aeoScore");
  const ctx = document.getElementById("aeo-score-chart").getContext("2d");
  const labels = results.map(r => r.llm);
  const scores = results.map(r => r.aeo_score);
  const colors = scores.map(s => scoreColor(s));

  charts.aeoScore = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "AEO Score", data: scores, backgroundColor: colors, borderRadius: 6, borderSkipped: false }],
    },
    options: {
      ...CHART_DEFAULTS,
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8" } },
        y: { grid: { display: false }, ticks: { color: "#e4e6f0", font: { weight: "bold", size: 12 } } },
      },
    },
  });
}

// ===== Sentiment Chart =====
function renderSentimentChart(results) {
  destroyChart("sentiment");
  const ctx = document.getElementById("sentiment-chart").getContext("2d");

  charts.sentiment = new Chart(ctx, {
    type: "bar",
    data: {
      labels: results.map(r => r.llm),
      datasets: [
        { label: "Positive", data: results.map(r => r.sentiment_dist?.positive || 0), backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Neutral", data: results.map(r => r.sentiment_dist?.neutral || 0), backgroundColor: "#555870", borderRadius: 4 },
        { label: "Negative", data: results.map(r => r.sentiment_dist?.negative || 0), backgroundColor: "#f87171", borderRadius: 4 },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { stacked: true, beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8", stepSize: 1 } },
      },
    },
  });
}

// ===== Position Chart =====
function renderPositionChart(results) {
  destroyChart("position");
  const ctx = document.getElementById("position-chart").getContext("2d");

  charts.position = new Chart(ctx, {
    type: "bar",
    data: {
      labels: results.map(r => r.llm),
      datasets: [
        { label: "Top (상단)", data: results.map(r => r.position_dist?.top || 0), backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Middle (중간)", data: results.map(r => r.position_dist?.middle || 0), backgroundColor: "#facc15", borderRadius: 4 },
        { label: "Bottom (하단)", data: results.map(r => r.position_dist?.bottom || 0), backgroundColor: "#f87171", borderRadius: 4 },
        { label: "None (없음)", data: results.map(r => r.position_dist?.none || 0), backgroundColor: "#2a2d42", borderRadius: 4 },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { stacked: true, beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8", stepSize: 1 } },
      },
    },
  });
}

// ===== Category Performance Chart =====
function renderCategoryChart(results) {
  destroyChart("category");
  const ctx = document.getElementById("category-chart").getContext("2d");

  const allCats = new Map();
  results.forEach(r => {
    Object.entries(r.category_performance || {}).forEach(([key, val]) => {
      if (!allCats.has(key)) allCats.set(key, val.label);
    });
  });

  if (allCats.size === 0) {
    ctx.canvas.parentElement.hidden = true;
    return;
  }
  ctx.canvas.parentElement.hidden = false;

  const catKeys = [...allCats.keys()];
  const catLabels = catKeys.map(k => allCats.get(k));
  const colors = results.map(r => LLM_COLORS[r.llm] || "#6c63ff");

  const datasets = results.map((r, i) => ({
    label: r.llm,
    data: catKeys.map(k => r.category_performance?.[k]?.citation_rate || 0),
    backgroundColor: colors[i],
    borderRadius: 4,
  }));

  charts.category = new Chart(ctx, {
    type: "bar",
    data: { labels: catLabels, datasets },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { grid: { display: false }, ticks: { color: "#e4e6f0", font: { size: 11 } } },
        y: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8", callback: v => v + "%" } },
      },
    },
  });
}

// ===== Competitor Chart =====
function renderCompetitorChart(results, targetDomain) {
  destroyChart("competitor");
  const row = document.getElementById("competitive-row");
  const hasComp = results.some(r => Object.keys(r.competitor_rates || {}).length > 0);
  if (!hasComp) { row.hidden = true; return; }
  row.hidden = false;

  const ctx = document.getElementById("competitor-chart").getContext("2d");
  const competitors = new Set();
  results.forEach(r => Object.keys(r.competitor_rates || {}).forEach(c => competitors.add(c)));

  const allDomains = [targetDomain, ...competitors];
  const palette = ["#6c63ff", "#f472b6", "#facc15", "#60a5fa", "#fb923c", "#a78bfa"];

  const datasets = allDomains.map((domain, i) => ({
    label: domain,
    data: results.map(r => domain === targetDomain ? r.citation_rate : (r.competitor_rates?.[domain] || 0)),
    backgroundColor: palette[i % palette.length],
    borderRadius: 4,
  }));

  charts.competitor = new Chart(ctx, {
    type: "bar",
    data: { labels: results.map(r => r.llm), datasets },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8", callback: v => v + "%" } },
      },
    },
  });
}

// ===== Share of Voice Chart =====
function renderSOVChart(results) {
  destroyChart("sov");
  const row = document.getElementById("competitive-row");
  if (row.hidden) return;

  const ctx = document.getElementById("sov-chart").getContext("2d");
  const sovTotals = {};
  results.forEach(r => {
    Object.entries(r.share_of_voice || {}).forEach(([brand, share]) => {
      sovTotals[brand] = (sovTotals[brand] || 0) + share;
    });
  });

  const brands = Object.keys(sovTotals);
  if (brands.length === 0) return;

  const total = Object.values(sovTotals).reduce((a, b) => a + b, 0);
  const normalized = brands.map(b => total > 0 ? Math.round(sovTotals[b] / total * 100) : 0);
  const palette = ["#6c63ff", "#f472b6", "#facc15", "#60a5fa", "#fb923c", "#a78bfa"];

  charts.sov = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: brands,
      datasets: [{ data: normalized, backgroundColor: palette.slice(0, brands.length), borderWidth: 0 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { position: "bottom", labels: { color: "#8b8fa8", font: { size: 11 }, padding: 12 } },
        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed}%` } },
      },
    },
  });
}

// ===== Citation Depth Chart =====
function renderDepthChart(results) {
  destroyChart("depth");
  const ctx = document.getElementById("depth-chart").getContext("2d");

  charts.depth = new Chart(ctx, {
    type: "bar",
    data: {
      labels: results.map(r => r.llm),
      datasets: [
        { label: "Linked (링크포함)", data: results.map(r => r.depth_dist?.linked || 0), backgroundColor: "#6c63ff", borderRadius: 4 },
        { label: "Detailed (상세)", data: results.map(r => r.depth_dist?.detailed || 0), backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Surface (표면)", data: results.map(r => r.depth_dist?.surface || 0), backgroundColor: "#facc15", borderRadius: 4 },
        { label: "None (없음)", data: results.map(r => r.depth_dist?.none || 0), backgroundColor: "#2a2d42", borderRadius: 4 },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: "#e4e6f0" } },
        y: { stacked: true, beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8", stepSize: 1 } },
      },
    },
  });
}

// ===== Top Domains Chart =====
function renderDomainChart(results) {
  destroyChart("domain");
  const domainTotals = {};
  results.forEach(r => {
    for (const [d, c] of Object.entries(r.top_domains)) domainTotals[d] = (domainTotals[d] || 0) + c;
  });

  const sorted = Object.entries(domainTotals).sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (sorted.length === 0) return;

  const ctx = document.getElementById("domain-chart").getContext("2d");
  const palette = ["#6c63ff", "#f472b6", "#34d399", "#facc15", "#60a5fa", "#fb923c", "#a78bfa", "#e879f9"];

  charts.domain = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map(([d]) => d),
      datasets: [{ label: "Count", data: sorted.map(([, c]) => c), backgroundColor: sorted.map((_, i) => palette[i]), borderRadius: 5, borderSkipped: false }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#8b8fa8" } },
        y: { grid: { display: false }, ticks: { color: "#e4e6f0", font: { size: 11 } } },
      },
    },
  });
}

// ===== LLM Detail Cards =====
function renderLLMCards(results, targetDomain) {
  cardsContainer.innerHTML = "";

  results.forEach(r => {
    const color = LLM_COLORS[r.llm] || "#6c63ff";
    const modeClass = r.mode === "live" ? "live" : "mock";
    const modeLabel = r.mode === "live" ? "LIVE" : "MOCK";
    const details = r.query_details || [];

    let detailsHtml = "";
    details.forEach((d, i) => {
      const citedCls = d.cited ? "cited-yes" : "cited-no";
      const citedLbl = d.cited ? "CITED" : "NOT CITED";
      const errHtml = d.error ? `<div class="detail-error">Error: ${esc(d.error)}</div>` : "";

      let respHtml = esc(d.response);
      if (targetDomain) {
        const pat = new RegExp(`(https?://[^\\s)\\]}>,"']*${targetDomain.replace(/\./g, "\\.")}[^\\s)\\]}>,"']*)`, "gi");
        respHtml = respHtml.replace(pat, '<span class="highlight-url">$1</span>');
      }

      let urlsHtml = "";
      if (d.urls?.length) {
        const items = d.urls.map(u => {
          const isTgt = targetDomain && u.includes(targetDomain);
          return `<li class="${isTgt ? "target-url" : ""}">${esc(u)}</li>`;
        }).join("");
        urlsHtml = `<div class="detail-urls"><strong>URLs (${d.urls.length}):</strong><ul>${items}</ul></div>`;
      }

      const recBadge = d.recommendation?.recommended
        ? '<span class="rec-badge yes">RECOMMENDED</span>'
        : '';
      const depthBadge = d.citation_depth
        ? `<span class="depth-badge ${d.citation_depth.depth}">${d.citation_depth.depth}</span>`
        : '';
      const catBadge = d.category_label
        ? `<span class="category-badge">${d.category_label}</span>`
        : '';

      detailsHtml += `
        <div class="query-detail">
          <div class="detail-header">
            <span class="detail-index">Q${i + 1}</span>
            <span class="cited-badge ${citedCls}">${citedLbl}</span>
            ${d.brand_mentioned ? '<span class="cited-badge cited-yes">MENTIONED</span>' : ""}
            ${recBadge}
            ${d.sentiment ? `<span class="sentiment-badge ${d.sentiment.label}">${d.sentiment.label}</span>` : ""}
            ${d.position ? `<span class="position-badge ${d.position.section}">${d.position.section}</span>` : ""}
            ${depthBadge}
            ${catBadge}
          </div>
          <div class="detail-query"><strong>Query:</strong> ${esc(d.query)}</div>
          ${errHtml}
          <div class="detail-response"><strong>Response:</strong><div class="response-text">${respHtml}</div></div>
          ${urlsHtml}
        </div>
      `;
    });

    const card = document.createElement("div");
    card.className = "llm-card";
    card.innerHTML = `
      <div class="card-header">
        <span class="llm-name" style="color:${color}">
          ${r.llm}
          <span class="mode-badge ${modeClass}">${modeLabel}</span>
        </span>
        <span class="rate-badge" style="color:${color}">${r.citation_rate}%</span>
      </div>
      <div class="stat-row"><span>AEO Score</span><span style="color:${scoreColor(r.aeo_score)}">${r.aeo_score}</span></div>
      <div class="stat-row"><span>Citation Rate</span><span>${r.citation_rate}%</span></div>
      <div class="stat-row"><span>Mention Rate</span><span>${r.mention_rate}%</span></div>
      <div class="stat-row"><span>Recommendation</span><span>${r.recommendation_rate}%</span></div>
      <div class="stat-row"><span>Sentiment</span><span><span class="sentiment-badge ${sentLabel(r.avg_sentiment)}">${sentLabel(r.avg_sentiment)} (${r.avg_sentiment})</span></span></div>
      <div class="stat-row"><span>Position</span><span><span class="position-badge ${posLabel(r.avg_position)}">${posLabel(r.avg_position)}${r.avg_position >= 0 ? ` (${r.avg_position}%)` : ""}</span></span></div>
      <div class="stat-row"><span>Depth</span><span>${r.avg_depth.toFixed(1)} / 4</span></div>
      <div class="stat-row"><span>Queries</span><span>${r.successful_queries} / ${r.total_queries}</span></div>
      ${r.errors > 0 ? `<div class="stat-row"><span style="color:var(--red)">Errors</span><span style="color:var(--red)">${r.errors}</span></div>` : ""}
      <div class="bar-track">
        <div class="bar-fill" style="width:${r.aeo_score}%;background:${scoreColor(r.aeo_score)}"></div>
      </div>
      ${details.length > 0 ? `
        <button class="toggle-details" onclick="this.parentElement.querySelector('.query-details').classList.toggle('open'); this.textContent = this.textContent.includes('+') ? '- 상세 숨기기' : '+ 상세 보기'">
          + 상세 보기
        </button>
        <div class="query-details">${detailsHtml}</div>
      ` : ""}
    `;
    cardsContainer.appendChild(card);
  });
}
