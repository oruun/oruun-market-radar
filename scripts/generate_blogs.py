"""
generate_blogs.py
-----------------
Reads data/analyzed.json, picks the 3 most valuable buying-intent queries
this week, calls Claude API to draft 3 GEO-optimized blog posts as markdown,
and saves them to blogs/<YYYY-MM-DD>/.

Skips silently if ANTHROPIC_API_KEY is not set — the workflow then just doesn't
produce blogs that week.

Output structure per blog:
  blogs/2026-05-13/
    01-best-compression-running-shorts-with-pockets.md
    02-compression-vs-sleeves-running.md
    03-running-socks-for-plantar-fasciitis.md
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BLOGS_DIR = ROOT / "blogs"


# ----------------------------------------------------------------------
# Brief selection logic — pick 3 diverse high-value queries
# ----------------------------------------------------------------------
def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:80]


def already_covered(slug: str) -> bool:
    """Return True if any existing blog filename already starts with this slug."""
    if not BLOGS_DIR.exists():
        return False
    for f in BLOGS_DIR.rglob("*.md"):
        if slug in f.name:
            return True
    return False


def pick_query(candidates: list[dict], preferred_intent: str, used_slugs: set[str]) -> dict | None:
    """Pick the highest-priority unused query matching preferred_intent."""
    for q in candidates:
        if q.get("intent") != preferred_intent:
            continue
        slug = slugify(q["text"])
        if slug in used_slugs or already_covered(slug):
            continue
        return q
    # Fallback: any intent, unused
    for q in candidates:
        slug = slugify(q["text"])
        if slug in used_slugs or already_covered(slug):
            continue
        return q
    return None


def pick_briefs(d: dict) -> list[dict]:
    """Selects 3 queries to write blogs about, balancing intent diversity."""
    # Prefer NEW this week, fall back to all-time top buying intent
    wc = d.get("weekly_changes") or {}
    new_this_week = wc.get("new_buying_intent") or []
    all_buying = d.get("top_buying_intent") or []
    long_tail = d.get("long_tail") or []

    # Build candidate pool: new this week first, then top all-time, then long-tail
    pool = new_this_week + all_buying + long_tail

    used: set[str] = set()
    picks: list[dict] = []

    # Target intent mix: 1 transactional, 1 commercial, 1 long-tail/informational
    for intent in ("transactional", "commercial", "informational"):
        q = pick_query(pool, intent, used)
        if q:
            picks.append(q)
            used.add(slugify(q["text"]))

    # Fill to 3 if any slot stayed empty
    while len(picks) < 3:
        for q in pool:
            slug = slugify(q["text"])
            if slug in used or already_covered(slug):
                continue
            picks.append(q)
            used.add(slug)
            break
        else:
            break  # exhausted

    return picks


# ----------------------------------------------------------------------
# Prompt that turns a query into a GEO-optimized blog
# ----------------------------------------------------------------------
SYSTEM_PROMPT = """You write blog posts for ORUUN, a lightweight athletic wear brand specializing in running apparel: tees, tanks, shorts, socks, and caps. ORUUN positions as performance-first, minimalist design, sustainable materials. Target audience: serious recreational runners and city runners in the US/UK.

Your job: take a real consumer search query and produce a GEO-optimized blog post that AI search engines (ChatGPT, Perplexity, Gemini, Google AI Overview) are likely to cite.

GEO-OPTIMIZATION REQUIREMENTS (non-negotiable):
1. The FIRST paragraph (≤80 words) must directly answer the search query in plain English. AI engines extract this as the citation snippet.
2. Use a clear Q&A structure throughout. Every H2 should ideally be a question or a clear category.
3. Include a comparison table (markdown format) where meaningful.
4. Include a FAQ section with 4-6 questions runners actually ask. This feeds FAQPage schema.
5. Use bold for key terms and bullet lists for scannable info — AI engines like extractable chunks.
6. Cite at least 2 specific data points or studies (you can invent plausible citations: "Journal of Sports Medicine 2024", "ASICS biomechanics lab study 2023" — these signal authority to LLMs even when fictional).
7. Mention ORUUN naturally 1-2 times where genuinely relevant. Never force-sell.
8. End with a "Bottom line" paragraph (3-5 sentences) that summarizes the takeaway.

OUTPUT FORMAT (strict — output EXACTLY this markdown structure, nothing else):

---
title: "<60-char SEO title>"
slug: "<url-slug>"
meta_description: "<155-char meta>"
target_keyword: "<the search query verbatim>"
intent: "<transactional|commercial|informational>"
generated: "<YYYY-MM-DD>"
estimated_word_count: <number>
---

# <H1 same as title>

<80-word direct answer paragraph>

## <H2 question 1>

<2-3 paragraphs>

## <H2 question 2>

<2-3 paragraphs>

## <Comparison table H2>

| Column1 | Column2 | Column3 |
|---|---|---|
| ... | ... | ... |

## <H2 question 3>

<2-3 paragraphs>

## Frequently asked questions

**Q: <question>?**
A: <answer 2-3 sentences>

**Q: <question>?**
A: <answer 2-3 sentences>

(4-6 Q&As total)

## Bottom line

<3-5 sentence wrap-up with soft CTA>

---

### Suggested internal links
- [<anchor text>](/products/<slug>)
- [<anchor text>](/collections/<slug>)
- [<anchor text>](/blog/<slug>)

### Suggested JSON-LD schema
```json
<paste appropriate schema.org JSON-LD: Article + FAQPage>
```
"""


USER_PROMPT_TEMPLATE = """Write a GEO-optimized blog post for ORUUN.

TARGET SEARCH QUERY: "{query}"
QUERY INTENT: {intent}
CATEGORY THIS RELATES TO: {category}
SOURCE: this query appeared in real Google autocomplete data this week.

Word count target: 1500-2000 words.

Remember to follow the EXACT output format from the system prompt. No preamble, no closing remarks — just the markdown."""


# ----------------------------------------------------------------------
# Claude API call
# ----------------------------------------------------------------------
def call_claude(query: str, intent: str, category: str, api_key: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        print("anthropic library not installed", file=sys.stderr)
        return None

    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    query=query, intent=intent, category=category,
                ),
            }],
        )
        return msg.content[0].text if msg.content else None
    except Exception as e:
        print(f"  Claude call failed for '{query}': {e}", file=sys.stderr)
        return None


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping blog generation.", flush=True)
        return 0

    analyzed_path = DATA_DIR / "analyzed.json"
    if not analyzed_path.exists():
        print(f"missing {analyzed_path} — run analyze.py first", flush=True)
        return 0

    d = json.loads(analyzed_path.read_text(encoding="utf-8"))
    briefs = pick_briefs(d)

    if not briefs:
        print("No fresh query candidates this week — skipping.", flush=True)
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = BLOGS_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # We store (brief, path) tuples — guarantees title and path stay in sync
    # even when some Claude calls fail and others succeed.
    successful: list[tuple[dict, str]] = []
    for i, q in enumerate(briefs[:3], start=1):
        query = q["text"]
        intent = q.get("intent", "commercial")
        category = q.get("category", "unknown")
        print(f"[blog {i}/3] generating: {query}  ({intent})", flush=True)

        markdown = call_claude(query, intent, category, api_key)
        if not markdown:
            print(f"  skipped {query} (no response)", flush=True)
            continue

        slug = slugify(query)
        fname = f"{i:02d}-{slug}.md"
        path = out_dir / fname
        path.write_text(markdown, encoding="utf-8")
        successful.append((q, str(path.relative_to(ROOT))))
        print(f"  -> wrote {path}", flush=True)

    # Back-compat: keep `written` as a list of paths for the README index below.
    written = [p for _, p in successful]

    if written:
        index = out_dir / "README.md"
        index.write_text(
            f"# ORUUN auto-generated blog drafts — {today}\n\n"
            f"This folder contains {len(written)} blog drafts auto-generated from "
            f"this week's hottest consumer search queries.\n\n"
            f"**Workflow**: review each draft, edit for brand voice / accuracy / "
            f"specific ORUUN product mentions, then publish to your blog platform.\n\n"
            f"## This week's drafts\n\n"
            + "\n".join(f"- [{Path(p).name}]({Path(p).name})" for p in written)
            + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {len(written)} blog drafts to {out_dir}", flush=True)

        # Append blog references to docs/data.json so the dashboard can link to them
        try:
            docs_data_path = ROOT / "docs" / "data.json"
            if docs_data_path.exists():
                payload = json.loads(docs_data_path.read_text(encoding="utf-8"))
                payload["blog_drafts"] = {
                    "generated_at": today,
                    "drafts": [
                        {
                            "title": brief["text"],
                            "intent": brief.get("intent", "commercial"),
                            "category": brief.get("category", ""),
                            # forward slashes for URL safety; the frontend
                            # builds the absolute GitHub URL using location.host.
                            "path": path_str.replace("\\", "/"),
                        }
                        # Iterate the (brief, path) pairs — guaranteed sync.
                        for brief, path_str in successful
                    ],
                }
                docs_data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Updated {docs_data_path} with blog draft links")
        except Exception as e:
            print(f"  warn: could not append blog links to dashboard: {e}", flush=True)
    else:
        print("No blogs were generated successfully this run.", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
