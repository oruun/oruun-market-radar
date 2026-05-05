# ORUUN Market Radar

A self-hosted, **zero-cost market research dashboard** for the ORUUN lightweight athletic wear brand.
Tracks search heat, week-over-week trends, blue-ocean opportunities, brand cross-source validation,
and buyer-journey intent across 5+ free public data sources.

Deploys to **GitHub Pages** for free. Data refreshes automatically every Monday via **GitHub Actions**.

---

## Data sources (all free, no auth required for the core 5)

| Source | Auth | Signal | Funnel stage |
|---|---|---|---|
| **Google Trends** (`pytrends`) — interest_over_time + related_queries | None | search heat, WoW & YoY, "rising" queries | full funnel |
| **Wikipedia Pageviews** (REST API) | None | brand-research depth, YoY pageview growth | consideration |
| **GDELT 2.0** (doc API) | None | global news mention volume per brand, monthly | awareness |
| **Hacker News** (Algolia search) | None | tech-savvy / quantified-self chatter | early adopter |
| **Google Autocomplete** (suggest API) | None | live "what users are typing" | exploration |
| Reddit (PRAW) — *optional* | client_id + client_secret | user pain points + brand sentiment | post-purchase |
| Anthropic Claude — *optional* | API key | LLM clusters Reddit complaints into product themes | strategy |

---

## What you see on the dashboard

1. **Cross-source validation** — for every brand, YoY change across Google / Wikipedia / News / HN.
   Verdict: 🚀 Authentic · 📈 Rising · 🔀 Mixed · 📊 Mature · 🐢 Saturated.
2. **Buyer journey map** — for the top 12 opportunity keywords, related queries are auto-classified
   into 4 intent buckets (Informational / Commercial / Transactional / Branded). High Transactional %
   = audience close to purchase.
3. **Search heat & trend explorer** — sortable table of every tracked keyword with WoW%, YoY%,
   opportunity score. Click any row to inspect 52-week trend chart + its top/rising related queries.
4. **Blue-ocean grid** — top 12 keywords by opportunity score (volume × growth ÷ saturation).
5. **Live autocomplete** — real-time Google suggestions per category, color-coded by intent.
6. **Reddit panels (if configured)** — competitor share of voice, brand sentiment meters,
   AI-clustered pain themes with concrete product ideas for ORUUN.

---

## Repo layout

```
oruun-market-radar/
├── keywords.yaml                 # ← edit to change what gets tracked
├── requirements.txt
├── scripts/
│   ├── fetch_trends.py           # Google Trends + related queries
│   ├── fetch_wikipedia.py        # Wikipedia pageviews
│   ├── fetch_gdelt.py            # Global news mentions
│   ├── fetch_hackernews.py       # Tech-savvy chatter
│   ├── fetch_autocomplete.py     # Live Google autocomplete
│   ├── fetch_reddit.py           # OPTIONAL — needs Reddit creds
│   ├── analyze.py                # Cross-source validator + intent classifier
│   ├── analyze_reddit_helpers.py # Imported lazily by analyze.py
│   ├── build_dashboard_data.py   # Copies analyzed.json → docs/data.json
│   └── generate_seed.py          # Generates placeholder data for first deploy
├── data/sample_data.json         # Seed so dashboard renders before first run
├── docs/                         # ← GitHub Pages serves this folder
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── data.json                 # rewritten weekly by Actions
├── .github/workflows/update.yml  # Weekly cron
└── README.md
```

---

## Deploy in 5 minutes

1. **Fork or push this repo** to your GitHub account.
2. **Settings → Pages → Source: `main` branch, `/docs` folder → Save.**
3. **Settings → Secrets and variables → Actions** — add *only what you have*:
   - `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` *(optional)* — only for pain-points module.
   - `ANTHROPIC_API_KEY` *(optional)* — only for AI clustering of complaints.
4. **Actions tab → Weekly Market Radar Update → Run workflow** (manual trigger).
5. Wait ~5 min, visit `https://<your-username>.github.io/<repo-name>/`.

The 5 core data sources need **zero secrets** — the dashboard is fully populated even
without Reddit/Anthropic. The Reddit-only sections of the dashboard auto-hide if those
secrets are absent.

---

## Tuning what gets tracked

Edit `keywords.yaml`:

- `categories.product_category / competitor_keyword / feature_material / use_case_persona`
  — your tracked keyword lists. ~5–8 each is the sweet spot.
- `brands` — for cross-source validation. Include ORUUN even if zero today;
  the dashboard plots its rise over time.
- `wikipedia_titles` — manual override map for ambiguous brand names
  (e.g. `on: "On (running brand)"` to avoid Wikipedia resolving "On" to a film).
- `geos` — Google Trends geographies, e.g. `US`, `GB`, `DE`, `FR`, `""` (worldwide).
- `timeframe` — Trends window, default `today 12-m`.

Push the change → next Actions run picks it up. No code edits needed.

---

## Cost

- GitHub Pages, GitHub Actions: **free** (well under 2,000 min/month)
- Google Trends, Wikipedia, GDELT, Hacker News, Google Autocomplete: **free public APIs**
- Reddit: **free** if you have an app (script-type)
- Anthropic Claude: pay-as-you-go, ~$0.01 per weekly run if enabled

---

## Limitations

- Google Trends gives **relative** interest, not absolute volume. The dashboard normalises to a 0–100 index.
- The "Authentic / Rising / Saturated" verdict is a heuristic combination of YoY signals — directional, not statistical proof.
- Wikipedia pageviews are skewed toward English-speaking research and often-name-collide brands.
  Always check the resolved article title in the workflow log; add an override in `keywords.yaml` if needed.
- GDELT covers English-language news; great for US/UK/AU/EU coverage, weaker on local-language press.
- Reddit signal (when enabled) is enthusiast-skewed; not a substitute for paid panel data.
- The opportunity score is a heuristic. Validate top picks with at least one paid tool
  (Ahrefs / SEMrush trial) before committing budget.
