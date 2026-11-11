"""관심 브랜드의 '관심도 추이' (순위와 무관). 관심 브랜드(최대 5개)를 한 번에 요청해 같은 기준(최고=100)으로 비교.

세 가지 보기
  brand  : 브랜드 전체 화제성 — 네이버 통합검색(검색어트렌드). 브랜드명 + 대표 제품명(에이지알, 제로모공패드 등)을 묶어서 봄.
           디바이스·화장품 구분 없이 '그 브랜드를 얼마나 찾나'.
  beauty : 화장품 구매 관심 — 쇼핑인사이트, 화장품/미용 분야에서 브랜드명을 검색해 상품을 클릭한 양
  device : 디바이스 구매 관심 — 쇼핑인사이트, 디지털/가전 분야(뷰티 디바이스가 여기에 속함)
하루 21번(3가지 × 전체+연령 6개)만 호출해요.
"""
import json
from datetime import date, timedelta

import requests

import config

if config.NAVER_API_MODE == "legacy":
    SHOP_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"
    SEARCH_URL = "https://openapi.naver.com/v1/datalab/search"
    HEADERS = {"X-Naver-Client-Id": config.NAVER_CLIENT_ID, "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET}
else:
    SHOP_URL = "https://naverapihub.apigw.ntruss.com/shopping/v1/category/keywords"
    SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
    HEADERS = {"X-NCP-APIGW-API-KEY-ID": config.NAVER_CLIENT_ID, "X-NCP-APIGW-API-KEY": config.NAVER_CLIENT_SECRET}

DAYS = 30
DEVICE_CID = "50000003"   # 디지털/가전 (뷰티 디바이스가 속한 분야)
# 검색어트렌드는 연령 구간이 더 잘게 나뉘어 있어서 묶어서 요청
SEARCH_AGES = {"10": ["2"], "20": ["3", "4"], "30": ["5", "6"], "40": ["7", "8"], "50": ["9", "10"], "60": ["11"]}
VIEWS = ["brand", "beauty", "device"]


def _post(url, body):
    r = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"},
                      data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=15)
    r.raise_for_status()
    return r.json().get("results", [])


def _brand_terms(b: str) -> list[str]:
    words = [b] + [w for w in config.BRAND_ALIASES.get(b, []) if len(w) >= 3]
    return list(dict.fromkeys(words))[:20]


def fetch(view: str, brands: list[str], end: str, age: str | None) -> dict | None:
    start = (date.fromisoformat(end) - timedelta(days=DAYS - 1)).isoformat()
    body = {"startDate": start, "endDate": end, "timeUnit": "date"}
    if config.GENDER:
        body["gender"] = config.GENDER
    try:
        if view == "brand":
            body["keywordGroups"] = [{"groupName": b, "keywords": _brand_terms(b)} for b in brands[:5]]
            if age:
                body["ages"] = SEARCH_AGES[age]
            res = _post(SEARCH_URL, body)
        else:
            body["category"] = config.BEAUTY_CID if view == "beauty" else DEVICE_CID
            body["keyword"] = [{"name": b, "param": [config.DEVICE_TERMS.get(b, b) if view == "device" else b]}
                               for b in brands[:5]]
            if age:
                body["ages"] = [age]
            res = _post(SHOP_URL, body)
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"  ! 관심도({view}, {age or '전체'}) 실패: {e}")
        return None
    dates = [(date.fromisoformat(start) + timedelta(days=i)).isoformat() for i in range(DAYS)]
    series = {}
    for item in res:
        vals = {p["period"]: p["ratio"] for p in item.get("data", [])}
        series[item["title"]] = [round(vals.get(d, 0), 1) for d in dates]
    return {"dates": dates, "series": series}


def update(conn, d: str, demo: bool = False) -> int:
    brands = config.WATCH_BRANDS[:5]
    if not brands or (not demo and not config.HAS_SEARCH):
        return 0
    conn.execute("CREATE TABLE IF NOT EXISTS brand_trend2 (view TEXT, age TEXT, fetched TEXT, data TEXT, PRIMARY KEY (view, age))")
    n = 0
    for view in VIEWS:
        for age in ["all"] + list(config.AGE_GROUPS):
            snap = _demo(view, brands, d, age) if demo else fetch(view, brands, d, None if age == "all" else age)
            if snap and snap["series"]:
                conn.execute("INSERT OR REPLACE INTO brand_trend2 (view, age, fetched, data) VALUES (?,?,?,?)",
                             (view, age, d, json.dumps(snap, ensure_ascii=False)))
                n += 1
    conn.commit()
    return n


def load(conn) -> dict:
    try:
        rows = conn.execute("SELECT view, age, fetched, data FROM brand_trend2").fetchall()
    except Exception:
        return {}
    out = {}
    for r in rows:
        out.setdefault(r["view"], {})[r["age"]] = {**json.loads(r["data"]), "fetched": r["fetched"]}
    return out


def _demo(view, brands, d, age):
    import math
    import random
    dates = [(date.fromisoformat(d) - timedelta(days=DAYS - 1 - i)).isoformat() for i in range(DAYS)]
    series = {}
    for j, b in enumerate(brands):
        rng = random.Random(f"{view}-{b}-{age}")
        base = rng.uniform(10, 70) * (1.6 if (j == 0 and view != "beauty") else 1)
        series[b] = [round(max(1, base + 12 * math.sin(i / 4 + j) + rng.uniform(-6, 6)), 1) for i in range(DAYS)]
    mx = max(max(v) for v in series.values())
    return {"dates": dates, "series": {b: [round(x * 100 / mx, 1) for x in v] for b, v in series.items()}}
