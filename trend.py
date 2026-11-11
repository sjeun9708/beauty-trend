"""관심 브랜드의 '관심도 추이' (순위와 무관).

인기검색어 100위 안에 못 들어도, 네이버 쇼핑인사이트 API로
'메디큐브' 같은 키워드의 검색 클릭 추이를 연령별로 받아 와요.
관심 브랜드(최대 5개)를 한 번에 요청해서, 같은 기준(가장 높은 값=100)으로 비교할 수 있어요.

- NAVER API HUB 의 쇼핑인사이트(키워드별 트렌드)를 Application 에 추가해 둬야 해요.
- 하루 7번(전체 + 연령 6개)만 호출해요.
"""
import json
from datetime import date, timedelta

import requests

import config

if config.NAVER_API_MODE == "legacy":
    URL = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"
    HEADERS = {"X-Naver-Client-Id": config.NAVER_CLIENT_ID, "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET}
else:
    URL = "https://naverapihub.apigw.ntruss.com/shopping/v1/category/keywords"
    HEADERS = {"X-NCP-APIGW-API-KEY-ID": config.NAVER_CLIENT_ID, "X-NCP-APIGW-API-KEY": config.NAVER_CLIENT_SECRET}

DAYS = 30


def fetch(brands: list[str], end: str, age: str | None) -> dict | None:
    """age=None 이면 전 연령. 반환: {"dates": [...], "series": {브랜드: [ratio...]}}"""
    start = (date.fromisoformat(end) - timedelta(days=DAYS - 1)).isoformat()
    body = {
        "startDate": start, "endDate": end, "timeUnit": "date",
        "category": config.BEAUTY_CID,
        "keyword": [{"name": b, "param": [b]} for b in brands[:5]],
    }
    if config.GENDER:
        body["gender"] = config.GENDER
    if age:
        body["ages"] = [age]
    try:
        r = requests.post(URL, headers={**HEADERS, "Content-Type": "application/json"},
                          data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=15)
        r.raise_for_status()
        res = r.json().get("results", [])
    except (requests.RequestException, ValueError) as e:
        print(f"  ! 관심도 추이 실패({age or '전체'}): {e}")
        return None
    dates = [(date.fromisoformat(start) + timedelta(days=i)).isoformat() for i in range(DAYS)]
    series = {}
    for item in res:
        vals = {p["period"]: p["ratio"] for p in item.get("data", [])}
        series[item["title"]] = [round(vals.get(d, 0), 1) for d in dates]
    return {"dates": dates, "series": series}


def update(conn, d: str, demo: bool = False) -> int:
    brands = config.WATCH_BRANDS[:5]
    if not brands:
        return 0
    if not demo and not config.HAS_SEARCH:
        return 0
    conn.execute("CREATE TABLE IF NOT EXISTS brand_trend (age TEXT PRIMARY KEY, fetched TEXT, data TEXT)")
    n = 0
    for age in ["all"] + list(config.AGE_GROUPS):
        snap = _demo(brands, d, age) if demo else fetch(brands, d, None if age == "all" else age)
        if snap:
            conn.execute("INSERT OR REPLACE INTO brand_trend (age, fetched, data) VALUES (?,?,?)",
                         (age, d, json.dumps(snap, ensure_ascii=False)))
            n += 1
    conn.commit()
    return n


def load(conn) -> dict:
    try:
        rows = conn.execute("SELECT age, fetched, data FROM brand_trend").fetchall()
    except Exception:
        return {}
    return {r["age"]: {**json.loads(r["data"]), "fetched": r["fetched"]} for r in rows}


def _demo(brands, d, age):
    import math
    import random
    dates = [(date.fromisoformat(d) - timedelta(days=DAYS - 1 - i)).isoformat() for i in range(DAYS)]
    series = {}
    for j, b in enumerate(brands):
        rng = random.Random(f"{b}-{age}")
        base = rng.uniform(15, 70) * (1.4 if j == 0 else 1)
        series[b] = [round(max(1, base + 12 * math.sin(i / 4 + j) + rng.uniform(-6, 6)), 1) for i in range(DAYS)]
    mx = max(max(v) for v in series.values())
    return {"dates": dates, "series": {b: [round(x * 100 / mx, 1) for x in v] for b, v in series.items()}}
