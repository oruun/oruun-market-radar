"""
Reddit-specific helpers, kept separate so analyze.py imports them lazily —
the rest of the pipeline runs even when Reddit creds are absent.
"""
from __future__ import annotations
import json
import os
import re
from collections import Counter, defaultdict
import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

PAIN_TRIGGERS = [
    "blister", "blisters", "chafe", "chafing", "rub", "rubs", "rubbed",
    "uncomfortable", "uncomfy", "hurt", "hurts", "hurting", "painful",
    "too tight", "too loose", "fall apart", "wore out", "worn out",
    "fell apart", "broke", "ripped", "tear", "torn", "stink", "stinks", "smelly",
    "overpriced", "too expensive", "not worth", "waste of money",
    "didn't last", "didnt last", "size down", "size up", "runs small", "runs large",
    "narrow", "wide foot", "no support", "no cushion", "too soft", "too firm",
    "slip", "slips", "slipping",
]


def brand_mentions(posts, brands):
    norm = [b.lower().strip() for b in brands]
    counts = {b: 0 for b in norm}
    for post in posts:
        blob = " ".join([
            post.get("title", ""),
            post.get("selftext", ""),
            *post.get("comments", []),
        ]).lower()
        for b in norm:
            if not b:
                continue
            counts[b] += len(re.findall(r"\b" + re.escape(b) + r"\b", blob))
    return counts


def brand_sentiment(posts, brands):
    sia = SentimentIntensityAnalyzer()
    scores = defaultdict(list)
    sentence_split = re.compile(r"(?<=[.!?])\s+")
    for post in posts:
        blob = " ".join([
            post.get("title", ""),
            post.get("selftext", ""),
            *post.get("comments", []),
        ])
        for sent in sentence_split.split(blob):
            sl = sent.lower()
            for b in brands:
                bl = b.lower().strip()
                if bl and re.search(r"\b" + re.escape(bl) + r"\b", sl):
                    scores[bl].append(sia.polarity_scores(sent)["compound"])
    out = {}
    for b, vals in scores.items():
        if not vals:
            continue
        out[b] = {
            "avg": round(float(np.mean(vals)), 3),
            "n": len(vals),
            "positive_pct": round(100.0 * sum(1 for v in vals if v > 0.2) / len(vals), 1),
            "negative_pct": round(100.0 * sum(1 for v in vals if v < -0.2) / len(vals), 1),
        }
    return out


def extract_pain_points(posts, top_n=30):
    sentence_split = re.compile(r"(?<=[.!?])\s+")
    hits = []
    for post in posts:
        blob = " ".join([post.get("title", ""), post.get("selftext", ""), *post.get("comments", [])])
        for sent in sentence_split.split(blob):
            sl = sent.lower()
            triggers = [t for t in PAIN_TRIGGERS if t in sl]
            if triggers:
                hits.append({
                    "text": sent.strip()[:300],
                    "triggers": triggers[:3],
                    "subreddit": post.get("subreddit"),
                    "url": post.get("url"),
                })
    seen, uniq = set(), []
    for h in hits:
        k = h["text"][:120]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    uniq.sort(key=lambda h: (-len(h["triggers"]), -len(h["text"])))
    return uniq[:top_n]


def trigger_frequency(pain_points):
    c = Counter()
    for p in pain_points:
        for t in p["triggers"]:
            c[t] += 1
    return [{"trigger": k, "count": v} for k, v in c.most_common(20)]


def claude_summary(pain_points):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not pain_points:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=api_key)
    excerpts = "\n".join(f"- {p['text']} ({p['subreddit']})" for p in pain_points[:60])
    prompt = (
        "You are a market research analyst for ORUUN, a lightweight athletic wear brand.\n"
        "Below are real Reddit complaints from runners.\n"
        "Cluster them into 4-6 pain themes. For each give: 4-word headline, "
        "1-sentence description, and a concrete product feature ORUUN could ship to solve it.\n"
        "Return strict JSON: {\"themes\": [{\"headline\":\"...\",\"description\":\"...\",\"product_idea\":\"...\"}]}.\n\n"
        f"COMPLAINTS:\n{excerpts}"
    )
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text if msg.content else ""
        a, b = raw.find("{"), raw.rfind("}")
        if a >= 0 and b > a:
            return json.loads(raw[a:b + 1])
    except Exception as e:
        print(f"  Claude summary failed: {e}", flush=True)
    return None
