// ORUUN Market Radar — dashboard logic v0.3
// Focus: CONSUMER SEARCH TERMS only. Brand tracking removed by design.

const CATEGORY_LABEL = {
  product_category:   "Category",
  competitor_keyword: "Competitor product",
  feature_material:   "Feature/Material",
  use_case_persona:   "Use case/Persona",
};

const INTENT_META = {
  transactional: { color: "#d6ff5c", label: "Transactional",  short: "TXN" },
  commercial:    { color: "#6affb1", label: "Commercial",     short: "COM" },
  informational: { color: "#5cb8ff", label: "Informational",  short: "INFO" },
  branded:       { color: "#c19bff", label: "Branded",        short: "BRAND" },
  generic:       { color: "#3a4250", label: "Generic",        short: "GEN" },
};

const state = {
  data: null,
  filter: { category: "all", sortBy: "opportunity_score", search: "" },
  selectedTerm: null,
  trendChart: null,
};

async function load() {
  try {
    const r = await fetch("data.json", { cache: "no-store" });
    if (!r.ok) throw new Error("data.json not found");
    state.data = await r.json();
  } catch (e) {
    document.getElementById("kpis").innerHTML =
      `<div class="kpi"><div class="label">Status</div><div class="value">⚠ No data yet</div>
       <div class="delta">Trigger the GitHub Action to populate. ${e.message}</div></div>`;
    return;
  }
  bindFilters();
  render();
  setRepoLink();
}

function setRepoLink() {
  const host = location.host;
  if (!host.endsWith(".github.io")) return;
  const user = host.split(".")[0];
  const path = location.pathname.split("/").filter(Boolean)[0] || "oruun-market-radar";
  document.getElementById("repo-link").href = `https://github.com/${user}/${path}`;
}

function bindFilters() {
  document.getElementById("cat-filter").addEventListener("change", (e) => {
    state.filter.category = e.target.value;
    renderTable();
    renderOpportunities();
  });
  document.getElementById("sort-by").addEventListener("change", (e) => {
    state.filter.sortBy = e.target.value;
    renderTable();
  });
  document.getElementById("search").addEventListener("input", (e) => {
    state.filter.search = e.target.value.toLowerCase();
    renderTable();
  });
}

function render() {
  document.getElementById("generated-at").textContent =
    "Updated " + niceDate(state.data.generated_at);
  document.getElementById("data-sources").textContent =
    (state.data.data_sources_active || []).join(" + ") || "no data";
  renderKPIs();
  renderAutocomplete();      // Front and center — the most reliable section
  renderJourney();
  renderTable();
  renderOpportunities();
}

// ---------- KPI strip ----------
function renderKPIs() {
  const kws = (state.data.keywords || []).filter((k) => k.category !== "brand");
  const climbing = kws.filter((k) => k.wow_change_pct > 5).length;
  const declining = kws.filter((k) => k.wow_change_pct < -5).length;
  const topOpp = kws.slice().sort((a, b) => b.opportunity_score - a.opportunity_score)[0];

  // Aggregate autocomplete suggestions
  const acRows = state.data.autocomplete || [];
  const totalSuggs = acRows.reduce((n, r) => n + (r.suggestions || []).length, 0);
  const txnCount = acRows.reduce((n, r) =>
    n + (r.suggestions || []).filter((s) => s.intent === "transactional").length, 0);

  document.getElementById("kpis").innerHTML = [
    kpi("Search terms tracked", kws.length, "consumer queries"),
    kpi("Trending up (WoW > 5%)", climbing,
        declining ? `↓ ${declining} declining` : "",
        climbing > declining ? "up" : "down"),
    kpi("Top opportunity term", topOpp ? topOpp.term : "—",
        topOpp ? `score ${topOpp.opportunity_score}` : ""),
    kpi("Live autocomplete suggestions", totalSuggs,
        `${txnCount} buy-intent`, "up"),
  ].join("");
}
function kpi(label, value, delta = "", deltaClass = "") {
  return `<div class="kpi">
    <div class="label">${label}</div>
    <div class="value">${escapeHtml(String(value))}</div>
    <div class="delta ${deltaClass}">${escapeHtml(delta)}</div>
  </div>`;
}

function pct(v) {
  if (v === null || v === undefined) return "—";
  return (v > 0 ? "+" : "") + v + "%";
}
function pctCls(v) {
  if (v === null || v === undefined) return "muted";
  return v > 5 ? "delta-pos" : v < -5 ? "delta-neg" : "";
}

// ---------- Buyer journey ----------
function renderJourney() {
  const journey = state.data.buyer_journey || [];
  if (journey.length === 0) {
    document.getElementById("journey-grid").innerHTML = `<div class="empty-state">
      <b>No journey data this run.</b><br>
      Buyer journey uses Google Trends related queries.
      Will populate once a Trends run completes successfully (Trends is sometimes
      rate-limited from GitHub Actions).
    </div>`;
    return;
  }
  document.getElementById("journey-grid").innerHTML = journey.map((j) => {
    const stages = ["transactional", "commercial", "informational", "branded", "generic"];
    const total = stages.reduce((s, k) => s + (j.intent_pct[k] || 0), 0) || 1;
    const bar = stages.map((k) => {
      const w = (j.intent_pct[k] || 0) / total * 100;
      if (w < 0.5) return "";
      const meta = INTENT_META[k];
      return `<span class="bar-seg" style="width:${w}%; background:${meta.color}" title="${meta.label}: ${j.intent_pct[k]}%"></span>`;
    }).join("");
    const rising = (j.rising_queries || []).slice(0, 4).map((q) => `<span class="rising-q">↑ ${escapeHtml(q)}</span>`).join("");
    const top = (j.top_queries || []).slice(0, 4).map((q) => `<span class="top-q">${escapeHtml(q)}</span>`).join("");
    return `<div class="journey-card">
      <div class="journey-head">
        <div class="term">${escapeHtml(j.term)}</div>
        <div class="cat-pill">${CATEGORY_LABEL[j.category] || j.category}</div>
      </div>
      <div class="intent-bar">${bar}</div>
      <div class="intent-legend">
        ${stages.map((k) => j.intent_pct[k] >= 5 ? `<span><i style="background:${INTENT_META[k].color}"></i>${INTENT_META[k].short} ${j.intent_pct[k]}%</span>` : "").join("")}
      </div>
      ${rising ? `<div class="qsection"><div class="qhead">Rising queries</div><div class="qlist">${rising}</div></div>` : ""}
      ${top ? `<div class="qsection"><div class="qhead">Top queries</div><div class="qlist">${top}</div></div>` : ""}
    </div>`;
  }).join("");
}

// ---------- Keyword table ----------
function renderTable() {
  const tbody = document.querySelector("#kw-table tbody");
  let rows = (state.data.keywords || []).filter((r) => r.category !== "brand");

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">
      <b>No keyword data this run.</b><br>
      Google Trends is the source for this section and is rate-limited from GitHub Actions.
      <br>Live autocomplete suggestions above are unaffected.
    </td></tr>`;
    document.getElementById("chart-title").textContent = "(no keyword data)";
    if (state.trendChart) { state.trendChart.destroy(); state.trendChart = null; }
    document.getElementById("related-queries").innerHTML = "";
    return;
  }

  if (state.filter.category !== "all") {
    rows = rows.filter((r) => r.category === state.filter.category);
  }
  if (state.filter.search) {
    rows = rows.filter((r) => r.term.toLowerCase().includes(state.filter.search));
  }
  rows.sort((a, b) => (b[state.filter.sortBy] || 0) - (a[state.filter.sortBy] || 0));
  tbody.innerHTML = rows
    .map((r) => `<tr data-term="${escapeAttr(r.term)}" class="${state.selectedTerm === r.term ? "selected" : ""}">
        <td>${escapeHtml(r.term)}</td>
        <td><span class="pill">${CATEGORY_LABEL[r.category] || r.category}</span></td>
        <td class="num">${r.volume_index}</td>
        <td class="num ${pctCls(r.wow_change_pct)}">${pct(r.wow_change_pct)}</td>
        <td class="num ${pctCls(r.yoy_change_pct)}">${pct(r.yoy_change_pct)}</td>
        <td class="num"><b>${r.opportunity_score}</b></td>
      </tr>`)
    .join("");
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => selectTerm(tr.dataset.term));
  });
  if (!state.selectedTerm && rows[0]) selectTerm(rows[0].term);
}

function selectTerm(term) {
  state.selectedTerm = term;
  document.querySelectorAll("#kw-table tbody tr").forEach((tr) => {
    tr.classList.toggle("selected", tr.dataset.term === term);
  });
  const row = (state.data.keywords || []).find((r) => r.term === term);
  if (!row) return;
  document.getElementById("chart-title").textContent =
    `${row.term}  ·  ${CATEGORY_LABEL[row.category] || row.category}`;
  drawTrendChart(row);
  renderRelatedFor(row);
}

function drawTrendChart(row) {
  const labels = row.history.map((h) => h.date);
  const values = row.history.map((h) => h.value);
  const ctx = document.getElementById("trend-chart").getContext("2d");
  if (state.trendChart) state.trendChart.destroy();
  state.trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: row.term,
        data: values,
        borderColor: "#d6ff5c",
        backgroundColor: "rgba(214,255,92,0.12)",
        fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8b93a3", maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { color: "#1f242c" } },
        y: { ticks: { color: "#8b93a3" }, grid: { color: "#1f242c" }, beginAtZero: true },
      },
    },
  });
}

function renderRelatedFor(row) {
  const top = row.related_top || [];
  const rising = row.related_rising || [];
  if (!top.length && !rising.length) {
    document.getElementById("related-queries").innerHTML = "";
    return;
  }
  document.getElementById("related-queries").innerHTML = `
    ${rising.length ? `<div class="qsection">
      <div class="qhead">↑ Rising related queries</div>
      <div class="qlist">${rising.slice(0, 10).map((q) => `<span class="rising-q">${escapeHtml(q.query)} <b>+${q.value}%</b></span>`).join("")}</div>
    </div>` : ""}
    ${top.length ? `<div class="qsection">
      <div class="qhead">Top related queries</div>
      <div class="qlist">${top.slice(0, 10).map((q) => `<span class="top-q">${escapeHtml(q.query)}</span>`).join("")}</div>
    </div>` : ""}
  `;
}

// ---------- Opportunities ----------
function renderOpportunities() {
  let rows = (state.data.keywords || []).filter((r) => r.category !== "brand");
  if (state.filter.category !== "all") {
    rows = rows.filter((r) => r.category === state.filter.category);
  }
  rows.sort((a, b) => b.opportunity_score - a.opportunity_score);
  rows = rows.slice(0, 12);
  if (rows.length === 0) {
    document.getElementById("opp-grid").innerHTML = `<div class="empty-state">
      <b>No opportunity data this run.</b><br>
      Opportunity scoring uses Google Trends search-volume data.
    </div>`;
    return;
  }
  document.getElementById("opp-grid").innerHTML = rows.map((r) => `
    <div class="opp-card">
      <div class="term">${escapeHtml(r.term)}</div>
      <div class="stats">
        <span>vol ${r.volume_index}</span>
        <span class="${pctCls(r.wow_change_pct)}">${pct(r.wow_change_pct)} WoW</span>
        <span class="${pctCls(r.yoy_change_pct)}">${pct(r.yoy_change_pct)} YoY</span>
      </div>
      <div class="score">${r.opportunity_score}</div>
    </div>
  `).join("");
}

// ---------- Autocomplete (the centerpiece) ----------
function renderAutocomplete() {
  const rows = state.data.autocomplete || [];
  if (rows.length === 0) {
    document.getElementById("autocomplete-grid").innerHTML = `<div class="empty-state">
      <b>No autocomplete data this run.</b><br>
      Will populate on the next scheduled run.
    </div>`;
    return;
  }
  document.getElementById("autocomplete-grid").innerHTML = rows.map((r) => {
    const suggs = (r.suggestions || []).map((s) => {
      const meta = INTENT_META[s.intent] || INTENT_META.generic;
      return `<span class="ac-tag" style="border-color:${meta.color}; color:${meta.color}" title="${meta.label}">${escapeHtml(s.text)}</span>`;
    }).join("");
    const breakdown = (r.intent_breakdown || []).map((b) =>
      `<span class="ac-stat" style="color:${(INTENT_META[b.intent] || INTENT_META.generic).color}">${(INTENT_META[b.intent] || INTENT_META.generic).short} ${b.count}</span>`
    ).join("");
    return `<div class="ac-card">
      <div class="ac-head">
        <div class="term">${escapeHtml(r.term)}</div>
        <div class="cat-pill">${CATEGORY_LABEL[r.category] || r.category}</div>
      </div>
      <div class="ac-breakdown">${breakdown}</div>
      <div class="ac-tags">${suggs || "<i>(no suggestions)</i>"}</div>
    </div>`;
  }).join("");
}

// ---------- helpers ----------
function niceDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}
function escapeAttr(s) { return escapeHtml(s).replaceAll("'", "&#39;"); }

load();
