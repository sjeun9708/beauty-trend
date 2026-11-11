"""홈페이지(site/index.html) 만들기.

최근 SITE_DAYS일치 데이터를 페이지 안에 넣어서, 서버 없이 파일을 더블클릭해도 열리고
GitHub Pages 같은 곳에 그대로 올려도 동작합니다. 그보다 오래된 날짜는 reports/ 폴더에 남아 있습니다.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import config
import db
import trends
import trend

SITE_DIR = config.BASE_DIR / "site"
TEMPLATE = config.BASE_DIR / "site_template.html"
KST = timezone(timedelta(hours=9))


def _prev(d):
    from datetime import date
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


def _day_payload(conn, d: str, ages: list[str]) -> dict | None:
    out_ages, analyses, seen = {}, {}, defaultdict(list)
    for age in ages:
        today = db.get_ranks(conn, d, age)
        if not today:
            continue
        full = trends.classify(today, db.get_ranks(conn, _prev(d), age))
        rows, tail = full[: config.TOP_N], full[config.TOP_N:]
        out_ages[age] = {
            "ins": db.get_insights(conn, d, age),
            "rows": [{"rk": r["rank"], "kw": r["keyword"], "st": r["status"], "ch": r["change"], "pv": r["prev_rank"]}
                     for r in rows],
            "tail": [r["keyword"] for r in tail],   # 51위~500위: 검색용으로 키워드만 순서대로
        }
        for r in rows:
            seen[r["keyword"]].append(age)
            if r["keyword"] not in analyses:
                a = db.get_analysis(conn, d, r["keyword"])
                if a:
                    analyses[r["keyword"]] = {
                        "c": a["category"], "r": a["reason"], "f": a["confidence"],
                        "s": [[s.get("title", "출처"), s.get("link")] for s in a["sources"]],
                        "u": 1 if a["reused"] else 0,
                    }
    if not out_ages:
        return None
    common = sorted(([k, v] for k, v in seen.items() if len(v) >= config.COMMON_MIN_AGES), key=lambda x: -len(x[1]))
    return {"ages": out_ages, "an": analyses, "common": common}


def build_site(conn, ages: list[str], demo: bool = False) -> str:
    dates = db.report_dates(conn)[-config.SITE_DAYS:]
    days = {}
    for d in dates:
        p = _day_payload(conn, d, ages)
        if p:
            days[d] = p
    evs = []
    if dates:
        last = (datetime.fromisoformat(dates[-1]) + timedelta(days=30)).date().isoformat()
        for e in db.get_events(conn, dates[0], last):
            evs.append({"n": e["name"], "b": e["brand"], "p": e["place"], "a": e["area"] or "기타",
                        "s": e["start"], "e": e["end"], "bk": e["booking"], "sm": e["summary"],
                        "src": [e["source_title"] or "출처", e["source_link"]] if e["source_link"] else None,
                        "u": e.get("undated") or 0})
    all_kws = set()
    for p in days.values():
        for g in p["ages"].values():
            all_kws.update(r["kw"] for r in g["rows"])
            all_kws.update(g["tail"])
    brands_all = db.get_brands(conn, all_kws)
    for k in all_kws:
        b = config.alias_brand(k) or config.known_brand(k) or brands_all.get(k)
        if b:
            brands_all[k] = b
    brands_all.update({k: v for k, v in config.BRAND_OVERRIDES.items() if k in all_kws})
    brand_map = {k: b for k, b in brands_all.items() if b}
    cat_names = [c for c, _ in config.PRODUCT_CATEGORIES] + ["기타"]
    pcat = {k: product_category(k) for k in all_kws}
    data = {
        "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "demo": demo,
        "target": config.GENDER_LABEL,
        "mode": config.ANALYZER,
        "collect": config.COLLECT_N,
        "dates": list(days),
        "days": days,
        "events": evs,
        "brands": brand_map,
        "pcats": cat_names,
        "pcat": {k: cat_names.index(c) for k, c in pcat.items()},
        "notes": read_notes(demo, dates),
        "btrend": trend.load(conn),
        "watch": config.WATCH_BRANDS,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/", f"window.SITE_DATA={blob};", 1)
    SITE_DIR.mkdir(exist_ok=True)
    path = SITE_DIR / "index.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


def product_category(keyword: str) -> str:
    if keyword in config.CATEGORY_OVERRIDES:
        return config.CATEGORY_OVERRIDES[keyword]
    k = keyword.replace(" ", "").lower() + " "
    for name, terms in config.PRODUCT_CATEGORIES:
        if any(t.replace(" ", "").lower() in k for t in terms):
            return name
    return "기타"


NOTES_FILE = config.BASE_DIR / "notes.md"


def read_notes(demo: bool, dates: list[str]) -> dict:
    """notes.md 의 '## YYYY-MM-DD' 아래에 쓴 글을 날짜별 마케터 노트로 홈페이지에 싣습니다."""
    notes, cur = {}, None
    if NOTES_FILE.exists():
        for line in NOTES_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^##\s*(\d{4}-\d{2}-\d{2})\s*$", line)
            if m:
                cur = m.group(1)
                notes[cur] = []
            elif cur and not line.startswith("<!--"):
                notes[cur].append(line)
    notes = {d: "\n".join(v).strip() for d, v in notes.items() if "\n".join(v).strip()}
    if demo and not notes and dates:
        notes[dates[-1]] = ("(예시 노트) 20대·30대 여성에서 스킨케어 비중이 높고, 40대 이상은 탄력·주름 키워드가 꾸준해요. "
                            "연말 할인 시즌이라 할인/행사로 분류된 키워드가 많은 편이라, 다음 주 세일 종료 후 순위가 유지되는지 지켜볼 것.")
    return notes
