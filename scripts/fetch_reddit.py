"""
fetch_reddit.py
---------------
Pulls recent posts + top comments from running/athleisure subreddits.
Used downstream to compute (a) competitor share of voice and
(b) sentiment + pain-point clusters.

Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars
(set as GitHub Actions secrets).

Output: data/reddit_raw.json
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
import praw

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_client() -> praw.Reddit:
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not csec:
        print("WARNING: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set. "
              "Writing empty reddit_raw.json so the rest of the pipeline still runs.",
              flush=True)
        return None  # type: ignore
    return praw.Reddit(
        client_id=cid,
        client_secret=csec,
        user_agent="oruun-market-radar/0.1 by ORUUN",
    )


def main() -> None:
    cfg = load_config()
    subs = cfg.get("subreddits", [])
    post_limit = int(cfg.get("reddit_post_limit", 75))
    comment_limit = int(cfg.get("reddit_comment_limit", 25))

    client = make_client()
    posts_out: list[dict] = []

    if client is None:
        out = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "posts": [],
        }
        (DATA_DIR / "reddit_raw.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        return

    for sub in subs:
        print(f"[reddit] r/{sub}", flush=True)
        try:
            subreddit = client.subreddit(sub)
            for post in subreddit.new(limit=post_limit):
                comments_text: list[str] = []
                try:
                    post.comments.replace_more(limit=0)
                    for c in post.comments[:comment_limit]:
                        if hasattr(c, "body"):
                            comments_text.append(c.body)
                except Exception as e:
                    print(f"  comments err on {post.id}: {e}", flush=True)
                posts_out.append({
                    "id": post.id,
                    "subreddit": sub,
                    "created_utc": int(post.created_utc),
                    "title": post.title,
                    "selftext": (post.selftext or "")[:2000],
                    "score": int(post.score),
                    "num_comments": int(post.num_comments),
                    "comments": comments_text,
                    "url": f"https://reddit.com{post.permalink}",
                })
        except Exception as e:
            print(f"  failed r/{sub}: {e}", flush=True)

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "skipped": False,
        "posts": posts_out,
    }
    target = DATA_DIR / "reddit_raw.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {target}  ({len(posts_out)} posts)")


if __name__ == "__main__":
    sys.exit(main())
