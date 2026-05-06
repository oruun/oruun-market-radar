"""Seed data generator. Realistic placeholder data for first deploy."""
from __future__ import annotations
import json, random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(2026)
ROOT = Path(__file__).resolve().parents[1]

KW = [
    ("trail running shoes",      "product_category", 62, 0.6, 4),
    ("lightweight running shoes","product_category", 48, 1.2, 4),
    ("zero drop shoes",          "product_category", 28, 0.9, 3),
    ("daily trainer",            "product_category", 41, 0.4, 4),
    ("ultra running gear",       "product_category", 19, 1.4, 3),
    ("speed training shoes",     "product_category", 35, 0.7, 3),
    ("nike pegasus",             "competitor_keyword", 78, -0.2, 5),
    ("on cloudmonster",          "competitor_keyword", 42, 1.6, 4),
    ("hoka mach",                "competitor_keyword", 51, 0.9, 4),
    ("hoka clifton",             "competitor_keyword", 64, 0.5, 4),
    ("salomon speedcross",       "competitor_keyword", 38, 0.2, 4),
    ("asics novablast",          "competitor_keyword", 47, 1.1, 4),
    ("brooks ghost",             "competitor_keyword", 52, 0.3, 4),
    ("merino wool running",      "feature_material", 26, 1.3, 3),
    ("carbon plate shoes",       "feature_material", 58, 0.4, 4),
    ("breathable running shorts","feature_material", 39, 0.6, 3),
    ("seamless running top",     "feature_material", 18, 1.5, 3),
    ("recycled polyester activewear","feature_material", 22, 1.7, 3),
    ("anti chafe shorts",        "feature_material", 31, 0.8, 3),
    ("city run outfit",          "use_case_persona", 24, 1.2, 3),
    ("marathon training kit",    "use_case_persona", 33, 0.6, 3),
    ("half marathon prep",       "use_case_persona", 29, 0.7, 3),
    ("running commute",          "use_case_persona", 21, 1.1, 3),
    ("early morning run gear",   "use_case_persona", 18, 1.4, 3),
    ("hot weather running",      "use_case_persona", 36, 0.5, 4),
    ("oruun",                    "brand", 4, 1.8, 2),
    ("nike",                     "brand", 95, -0.1, 6),
    ("on",                       "brand", 68, 1.4, 5),
    ("hoka",                     "brand", 75, 0.9, 5),
    ("salomon",                  "brand", 54, 0.6, 4),
    ("asics",                    "brand", 71, 0.4, 5),
    ("tracksmith",               "brand", 18, 1.5, 2),
    ("bandit",                   "brand", 12, 2.1, 2),
    ("satisfy",                  "brand", 14, 1.9, 2),
    ("district vision",          "brand", 9, 1.6, 2),
]

RELATED = {
    "lightweight running shoes": {
        "top": ["nike lightweight", "best lightweight running shoes", "lightweight running shoes for women",
                "lightweight running shoes mens", "asics lightweight", "lightweight running shoes review"],
        "rising": ["lightweight zero drop running shoes", "carbon plate lightweight",
                   "lightweight running shoes wide feet", "best lightweight 2026"],
    },
    "trail running shoes": {
        "top": ["best trail running shoes", "hoka trail running shoes", "salomon trail running shoes",
                "trail running shoes review", "trail running shoes for women"],
        "rising": ["trail running shoes 2026", "carbon plate trail running shoes", "where to buy trail running shoes"],
    },
    "carbon plate shoes": {
        "top": ["best carbon plate shoes", "carbon plate shoes review", "vaporfly carbon plate",
                "carbon plate vs no plate", "carbon plate shoes amazon"],
        "rising": ["affordable carbon plate shoes", "carbon plate shoes alternative", "carbon plate shoes sale"],
    },
    "merino wool running": {
        "top": ["smartwool running", "merino wool running socks", "merino wool running shirt"],
        "rising": ["merino wool running tee", "merino blend running shirt"],
    },
    "marathon training kit": {
        "top": ["nyc marathon kit", "marathon training plan", "marathon training kit beginner"],
        "rising": ["marathon kit checklist", "where to buy marathon kit"],
    },
    "city run outfit": {
        "top": ["women's city run outfit", "men's city run outfit", "stylish running outfit"],
        "rising": ["city run outfit ideas", "running outfit street style"],
    },
}

WEEKS = 52
end = datetime.now(timezone.utc).date()
dates = [(end - timedelta(weeks=WEEKS - 1 - i)).isoformat() for i in range(WEEKS)]

def history(b, sl, n):
    return [{"date": dates[i], "value": int(round(min(100, max(0, b + sl*i + random.uniform(-n, n)))))} for i in range(WEEKS)]

def latest(h, w=4): return round(sum(x["value"] for x in h[-w:])/w, 1)
def wow(h, w=4):
    if len(h)<w*2: return 0.0
    r=sum(x["value"] for x in h[-w:])/w; p=sum(x["value"] for x in h[-2*w:-w])/w
    return round((r-p)/p*100, 1) if p>0.5 else 0.0
def yoy(h, hw=26):
    if len(h)<hw*2: return 0.0
    r=sum(x["value"] for x in h[-hw:])/hw; p=sum(x["value"] for x in h[-2*hw:-hw])/hw
    return round((r-p)/p*100, 1) if p>0.5 else 0.0

INFO=["what","how","why","guide","explain"]
COMM=["review","best","top","vs","alternative"]
TXN=["buy","where to buy","discount","sale","cheap","amazon","near me","size"]
BR={"nike","on","hoka","salomon","asics","brooks","saucony","adidas","lululemon",
    "tracksmith","satisfy","bandit","smartwool","vaporfly","speedcross"}

def classify(q):
    s=q.lower()
    for b in BR:
        if f" {b} " in f" {s} " or s.startswith(b+" ") or s==b: return "branded"
    if any(t in s for t in TXN): return "transactional"
    if any(t in s for t in COMM): return "commercial"
    if any(t in s for t in INFO): return "informational"
    return "generic"

keywords=[]
for term, cat, base, slope, noise in KW:
    h = history(base, slope, noise)
    vol = latest(h); g = wow(h); y = yoy(h)
    sat = 4 if term=="oruun" else max(0, int(random.gauss(base*0.2, 4)))
    gf = max(0.0, 1.0 + g/100.0)
    opp = round(vol*gf/(sat+1), 1) if vol>=5 else 0.0
    rel = RELATED.get(term)
    rt = [{"query":q,"value":random.randint(20,100)} for q in (rel["top"] if rel else [])]
    rr = [{"query":q,"value":random.choice([90,120,250,350,500])} for q in (rel["rising"] if rel else [])]
    ic = Counter()
    for q in (rel["top"] if rel else [])+(rel["rising"] if rel else []):
        ic[classify(q)] += 1
    keywords.append({
        "term":term,"category":cat,"volume_index":vol,"wow_change_pct":g,"yoy_change_pct":y,
        "reddit_mentions":sat,"opportunity_score":opp,"history":h,"last_date":dates[-1],
        "related_top":rt,"related_rising":rr,
        "intent_breakdown":[{"intent":k,"count":v} for k,v in ic.most_common()],
    })

cross = [
    ("satisfy",90,95,686,250,"Authentic"),("district vision",108,74,500,180,"Authentic"),
    ("bandit",68,81,462,100,"Authentic"),("tracksmith",58,35,63,22,"Rising"),
    ("on",13,30,49,15,"Rising"),("salomon",12,18,22,7,"Rising"),
    ("hoka",5,25,21,8,"Mature"),("lululemon",17,15,28,12,"Mature"),
    ("asics",4,6,8,3,"Mature"),("brooks",2,1,-3,0,"Mature"),
    ("adidas",9,-5,29,-2,"Mixed"),("nike",-3,-8,-12,-4,"Saturated"),
    ("oruun",0,0,0,0,"Unknown"),
]
cross_source = [{"brand":b,"trends_yoy_pct":t,"wiki_yoy_pct":w,"gdelt_yoy_pct":g,"hn_yoy_pct":h,
                 "verdict":v,"wiki_monthly":[],"gdelt_monthly":[],"hn_count_12m":0,
                 "hn_top_stories":[],"wiki_article":None}
                for b,t,w,g,h,v in cross]

journey=[]
# Brand category excluded from buyer journey — that's a consumer-search-intent
# concept, not a brand-awareness concept. Brand signals live in cross_source_validation.
for kw in [k for k in sorted(keywords, key=lambda r:(-r["opportunity_score"]))
           if (k["related_top"] or k["related_rising"]) and k["category"] != "brand"][:12]:
    counts={b["intent"]:b["count"] for b in kw["intent_breakdown"]}
    total=sum(counts.values()) or 1
    journey.append({
        "term":kw["term"],"category":kw["category"],"volume_index":kw["volume_index"],
        "intent_pct":{k:round(100.0*counts.get(k,0)/total,1)
                      for k in ("informational","commercial","transactional","branded","generic")},
        "rising_queries":[q["query"] for q in kw["related_rising"][:6]],
        "top_queries":[q["query"] for q in kw["related_top"][:6]],
    })

AUTO = {
    "lightweight running shoes": ["lightweight running shoes for women","lightweight running shoes for men",
        "lightweight running shoes for flat feet","lightweight running shoes review","lightweight running shoes 2026",
        "lightweight running shoes amazon","lightweight running shoes nike","lightweight running shoes wide","lightweight running shoes sale"],
    "trail running shoes": ["trail running shoes for women","trail running shoes mens","trail running shoes vs road",
        "trail running shoes review","trail running shoes wide feet","trail running shoes hoka","where to buy trail running shoes"],
    "merino wool running": ["merino wool running shirt","merino wool running socks","merino wool running base layer",
        "merino wool running pants","merino wool running review","best merino wool running"],
    "carbon plate shoes": ["carbon plate shoes for marathon","carbon plate shoes nike","carbon plate shoes vs no plate",
        "carbon plate shoes review","carbon plate shoes amazon","cheapest carbon plate shoes"],
    "city run outfit": ["city run outfit men","city run outfit women","stylish city run outfit","city run outfit aesthetic"],
    "marathon training kit": ["marathon training kit for beginners","marathon training kit checklist","marathon training kit gear"],
    "hot weather running": ["hot weather running clothes","hot weather running tips","hot weather running shirt","hot weather running gear"],
    "early morning run gear": ["early morning run gear winter","early morning run gear reflective","early morning run gear safety"],
}
auto_rows=[]
for term, suggs in AUTO.items():
    cat = next((kw["category"] for kw in keywords if kw["term"]==term), "product_category")
    ann, ic = [], Counter()
    for s in suggs:
        i=classify(s); ic[i]+=1
        ann.append({"text":s,"intent":i})
    auto_rows.append({"term":term,"category":cat,"suggestions":ann,
                      "intent_breakdown":[{"intent":k,"count":v} for k,v in ic.most_common()]})

now = datetime.now(timezone.utc).isoformat()
out = {
    "generated_at": now, "trends_fetched_at": now, "wiki_fetched_at": now,
    "gdelt_fetched_at": now, "hn_fetched_at": now, "autocomplete_fetched_at": now,
    "reddit_fetched_at": None, "reddit_posts_analyzed": 0, "timeframe": "today 12-m",
    "data_sources_active": ["Google Trends","Wikipedia","GDELT News","Hacker News","Autocomplete"],
    "keywords": sorted(keywords, key=lambda r:-r["opportunity_score"]),
    "cross_source_validation": cross_source,
    "buyer_journey": journey,
    "autocomplete": auto_rows,
    "intent_global": [], "brand_share_of_voice": [], "brand_sentiment": {},
    "pain_points": [], "pain_triggers": [], "pain_summary": None,
}
(ROOT/"docs").mkdir(exist_ok=True)
(ROOT/"data").mkdir(exist_ok=True)
(ROOT/"docs"/"data.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
(ROOT/"data"/"sample_data.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Wrote docs/data.json ({len(keywords)} keywords, {len(cross_source)} brands, {len(journey)} journey, {len(auto_rows)} autocomplete)")
