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
const cardsContainer = document.getElementById("llm-cards");

// Chart instances (destroy before re-creating)
let citationChart = null;
let domainChart = null;

// LLM color mapping
const LLM_COLORS = {
  ChatGPT: "#10a37f",
  Perplexity: "#20b8cd",
  Claude: "#d97706",
  Gemini: "#4285f4",
  Copilot: "#9333ea",
};

const LLM_COLORS_ALPHA = {
  ChatGPT: "rgba(16,163,127,0.15)",
  Perplexity: "rgba(32,184,205,0.15)",
  Claude: "rgba(217,119,6,0.15)",
  Gemini: "rgba(66,133,244,0.15)",
  Copilot: "rgba(147,51,234,0.15)",
};

// ===== Form Submit =====
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!url) return;

  setLoading(true);
  hideError();
  resultsSection.hidden = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, num_queries: 10 }),
    });

    if (!res.ok) throw new Error(`서버 오류 (${res.status})`);

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    showError(err.message || "분석 중 오류가 발생했습니다.");
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

// ===== Render Results =====
function renderResults(data) {
  heroSection.classList.add("compact");
  resultsSection.hidden = false;
  resultDomain.textContent = data.target_domain;

  renderCitationChart(data.results);
  renderLLMCards(data.results);
  renderDomainChart(data.results);

  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ===== 1. Main Bar Chart: Citation Rate per LLM =====
function renderCitationChart(results) {
  const ctx = document.getElementById("citation-chart").getContext("2d");
  if (citationChart) citationChart.destroy();

  const labels = results.map((r) => r.llm);
  const rates = results.map((r) => r.citation_rate);
  const colors = labels.map((l) => LLM_COLORS[l] || "#6c63ff");
  const bgColors = labels.map((l) => LLM_COLORS_ALPHA[l] || "rgba(108,99,255,0.15)");

  citationChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "인용율 (%)",
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
            label: (ctx) => `인용율: ${ctx.parsed.y}%`,
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

// ===== 2. LLM Detail Cards =====
function renderLLMCards(results) {
  cardsContainer.innerHTML = "";

  results.forEach((r) => {
    const color = LLM_COLORS[r.llm] || "#6c63ff";
    const card = document.createElement("div");
    card.className = "llm-card";
    card.innerHTML = `
      <div class="card-header">
        <span class="llm-name" style="color:${color}">${r.llm}</span>
        <span class="rate-badge" style="color:${color}">${r.citation_rate}%</span>
      </div>
      <div class="stat-row"><span>총 쿼리 수</span><span>${r.total_queries}</span></div>
      <div class="stat-row"><span>인용 횟수</span><span>${r.cited_count} / ${r.total_queries}</span></div>
      <div class="stat-row"><span>인용 URL 수</span><span>${r.target_domain_urls.length}</span></div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${r.citation_rate}%;background:${color}"></div>
      </div>
    `;
    cardsContainer.appendChild(card);
  });
}

// ===== 3. Top Domains Horizontal Bar Chart =====
function renderDomainChart(results) {
  // Aggregate top domains across all LLMs
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
          label: "인용 횟수",
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
