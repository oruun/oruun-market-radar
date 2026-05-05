// ORUUN Market Radar — dashboard logic v0.2
// Reads ./data.json, refreshed weekly by GitHub Actions.

const CATEGORY_LABEL = {
  product_category: "Category",
  competitor_keyword: "Competitor product",
  feature_material: "Feature/Material",
  use_case_persona: "Use case/Persona",
  brand: "Brand",
};

const VERDICT_META = {
  Authentic: { emoji: "🚀", cls: "authentic" },
  Rising:    { emoji: "📈", cls: "rising" },
  Mixed:     { emoji: "🔀", cls: "mixed" },
  Mature:    { emoji: "📊", cls: "mature" },
  Saturated: { emoji: "🐢", cls: "saturated" },
  Unknown:   { emoji: "❓", cls: "unknown" },
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
  sovChart: null,
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
    (state.data.data_sources_active || []).join(" + ");
  renderKPIs();
  renderCrossSource();
  renderJourney();
  renderTable();
  renderOpportunities();
  renderAutocomplete();
  renderShareOfVoice();
  renderSentiment();
  renderPainPoints();
  toggleRedditSections();
}

function toggleRedditSections() {
  const hasReddit = (state.data.reddit_posts_analyzed || 0) > 0;
  document.getElementById("reddit-only").style.display = hasReddit ? "" : "none";
  document.getElementById("pain-card").style.display = hasReddit ? "" : "none";
}

// ---------- KPI strip ----------
function renderKPIs() {
  const kws = state.data.keywords || [];
  const climbing = kws.filter((k) => k.wow_change_pct > 5).length;
  const declining = kws.filter((k) => k.wow_change_pct < -5).length;
  const topOpp = kws.slice().sort((a, b) => b.opportunity_score - a.opportunity_score)[0];
  const cross = state.data.cross_source_validation || [];
  const authentic = cross.filter((c) => c.verdict === "Authentic" || c.verdict === "Rising").length;

  document.getElementById("kpis").innerHTML = [
    kpi("Keywords tracked", kws.length, ""),
    kpi("Trending up (WoW > 5%)", climbing, declining ? `↓ ${declining} declining` : "", climbing > declining ? "up" : "down"),
    kpi("Top opportunity", topOpp ? topOpp.term : "—", topOpp ? `score ${topOpp.opportunity_score}` : ""),
    kpi("Authentic + Rising brands", authentic, `of ${cross.length} tracked`, "up"),
  ].join("");
}
function kpi(label, value, delta = "", deltaClass = "") {
  return `<div class="kpi">
    <div class="label">${label}</div>
    <div class="value">${escapeHtml(String(value))}</div>
    <div class="delta ${deltaClass}">${escapeHtml(delta)}</div>
  </div>`;
}

// ---------- Cross-source validation ----------
function renderCrossSource() {
  const tbody = document.querySelector("#cross-table tbody");
  const rows = state.data.cross_source_validation || [];
  tbody.innerHTML = rows.map((r) => {
    const v = VERDICT_META[r.verdict] || VERDICT_META.Unknown;
    return `<tr>
      <td><b>${escapeHtml(r.brand)}</b></td>
      <td class="num ${pctCls(r.trends_yoy_pct)}">${pct(r.trends_yoy_pct)}</td>
      <td class="num ${pctCls(r.wiki_yoy_pct)}">${pct(r.wiki_yoy_pct)}</td>
      <td class="num ${pctCls(r.gdelt_yoy_pct)}">${pct(r.gdelt_yoy_pct)}</td>
      <td class="num ${pctCls(r.hn_yoy_pct)}">${pct(r.hn_yoy_pct)}</td>
      <td><span class="badge ${v.cls}">${v.emoji} ${r.verdict}</span></td>
    </tr>`;
  }).join("");
}
function pct(v) { return (v > 0 ? "+" : "") + (v ?? 0) + "%"; }
function pctCls(v) { return v > 5 ? "delta-pos" : v < -5 ? "delta-neg" : ""; }

// ---------- Buyer journey ----------
function renderJourney() {
  const journey = state.data.buyer_journey || [];
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
  let rows = (state.data.keywords || []).slice();
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
  let rows = (state.data.keywords || []).slice();
  if (state.filter.category !== "all") {
    rows = rows.filter((r) => r.category === state.filter.category);
  }
  rows.sort((a, b) => b.opportunity_score - a.opportunity_score);
  rows = rows.slice(0, 12);
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

// ---------- Autocomplete intent map ----------
function renderAutocomplete() {
  const rows = state.data.autocomplete || [];
  document.getElementById("autocomplete-grid").innerHTML = rows.map((r) => {
    const suggs = (r.suggestions || []).map((s) => {
      const meta = INTENT_META[s.intent] || INTENT_META.generic;
      return `<span class="ac-tag" style="border-color:${meta.color}; color:${meta.color}" title="${meta.label}">${escapeHtml(s.text)}</span>`;
    }).join("");
    return `<div class="ac-card">
      <div class="ac-head">
        <div class="term">${escapeHtml(r.term)}</div>
        <div class="cat-pill">${CATEGORY_LABEL[r.category] || r.category}</div>
      </div>
      <div class="ac-tags">${suggs || "<i>(no suggestions)</i>"}</div>
    </div>`;
  }).join("");
}

// ---------- Reddit sections ----------
function renderShareOfVoice() {
  const rows = (state.data.brand_share_of_voice || []).filter((r) => r.mentions > 0).slice(0, 12);
  if (!rows.length) return;
  const ctx = document.getElementById("sov-chart").getContext("2d");
  if (state.sovChart) state.sovChart.destroy();
  state.sovChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.brand),
      datasets: [{
        label: "Mentions",
        data: rows.map((r) => r.mentions),
        backgroundColor: rows.map((r) => r.brand === "oruun" ? "#d6ff5c" : "#3a4250"),
      }],
    },
    options: {
      responsive: true, indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.parsed.x} mentions  ·  ${rows[c.dataIndex].share_pct}%` } },
      },
      scales: {
        x: { ticks: { color: "#8b93a3" }, grid: { color: "#1f242c" } },
        y: { ticks: { color: "#e6e8ec" }, grid: { display: false } },
      },
    },
  });
}

function renderSentiment() {
  const sent = state.data.brand_sentiment || {};
  const items = Object.entries(sent)
    .map(([brand, s]) => ({ brand, ...s }))
    .filter((s) => s.n >= 3)
    .sort((a, b) => b.n - a.n).slice(0, 16);
  if (!items.length) return;
  document.getElementById("sentiment-grid").innerHTML = items.map((s) => {
    const pctV = Math.max(-100, Math.min(100, s.avg * 100));
    const w = Math.abs(pctV);
    const left = pctV >= 0 ? "50%" : `calc(50% - ${w}%)`;
    const cls = pctV >= 0 ? "" : "bad";
    return `<div class="sent-card">
      <div class="brand">${escapeHtml(s.brand)}</div>
      <div class="meter ${cls}"><span style="left:${left}; width:${w}%"></span></div>
      <div class="nums"><span>${s.n} sent.</span><span>${s.positive_pct}% pos · ${s.negative_pct}% neg</span></div>
    </div>`;
  }).join("");
}

function renderPainPoints() {
  if (!state.data.pain_points || !state.data.pain_points.length) return;
  const summary = state.data.pain_summary;
  const grid = document.getElementById("pain-summary");
  if (summary && summary.themes && summary.themes.length) {
    grid.innerHTML = summary.themes.map((t) => `
      <div class="pain-card">
        <h4>${escapeHtml(t.headline || "")}</h4>
        <p>${escapeHtml(t.description || "")}</p>
        <div class="idea"><b>Product idea →</b> ${escapeHtml(t.product_idea || "")}</div>
      </div>`).join("");
  } else {
    grid.innerHTML = `<div class="pain-card"><h4>AI summary unavailable</h4>
      <p>Set ANTHROPIC_API_KEY secret to enable theme clustering. Raw triggers below still work.</p></div>`;
  }
  document.getElementById("pain-triggers").innerHTML = (state.data.pain_triggers || [])
    .map((t) => `<span class="trigger-pill">${escapeHtml(t.trigger)} <b>${t.count}</b></span>`).join("");
  document.getElementById("pain-quotes").innerHTML = (state.data.pain_points || []).slice(0, 30).map((q) =>
    `<blockquote>${escapeHtml(q.text)}<cite>${escapeHtml(q.subreddit || "")} · <a href="${escapeAttr(q.url || "#")}" target="_blank" rel="noopener">view</a></cite></blockquote>`
  ).join("");
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
