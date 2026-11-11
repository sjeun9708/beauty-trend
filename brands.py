"""검색어 → 브랜드 자동 판별.

판별 순서: ① config 의 BRAND_OVERRIDES ② BRAND_ALIASES(대표 제품명) ③ 예전 개발자센터 키가 있으면 쇼핑 검색
④ 그 밖에는 '추정 규칙': 여러 검색어의 첫 단어로 반복해서 나오는 이름(예: 메디큐브 크림, 메디큐브 패드)을 브랜드로 봄.
NAVER API HUB 에는 쇼핑 검색이 없어서 ③ 대신 ④를 써요. 키가 하나도 없어도 ④는 돌아가요.


'에이지알 부스터프로'처럼 브랜드 이름이 안 들어간 검색어도 브랜드로 묶을 수 있게,
네이버 쇼핑 검색 API(무료, 검색 API 키 그대로 사용)로 그 검색어의 상품들을 보고
'화장품/미용' 상품의 절반 이상이 한 브랜드면 그 브랜드로 정합니다.
'선크림'처럼 여러 브랜드가 섞인 일반 검색어는 브랜드 없음으로 둡니다.
한 번 판별한 검색어는 DB에 저장해 다시 묻지 않으므로, 첫날 이후에는 호출이 적어요.
"""
import re
import time
from collections import Counter

import requests

import config
import db

SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
_TAG = re.compile(r"<[^>]+>")


def update(conn, d: str, ages: list[str], demo: bool = False) -> int:
    kws = set()
    for age in ages:
        kws.update(r["keyword"] for r in db.get_ranks(conn, d, age))
    known = db.get_brands(conn, kws)
    for k, b in config.BRAND_OVERRIDES.items():       # 직접 고친 값이 항상 우선
        if k in kws:
            db.save_brand(conn, k, b, d)
            known[k] = b
    for k in kws:                                       # 대표 제품명 별칭
        b = config.alias_brand(k)
        if b and known.get(k) != b and k not in config.BRAND_OVERRIDES:
            db.save_brand(conn, k, b, d)
            known[k] = b
    for k in kws:                                       # 알려진 브랜드 이름으로 시작 (예: vdl틴트 → VDL)
        if k in known or k in config.BRAND_OVERRIDES:
            continue
        b = config.alias_brand(k) or config.known_brand(k)
        if b:
            db.save_brand(conn, k, b, d)
            known[k] = b
    todo = [k for k in kws if k not in known]
    if demo:
        import demo_data
        table = demo_data.brands()
        for k in todo:
            db.save_brand(conn, k, table.get(k), d)
        return len(todo)
    if config.HAS_SEARCH and config.NAVER_API_MODE == "legacy":
        for k in todo:
            db.save_brand(conn, k, lookup(k), d)
            time.sleep(0.12)
        return len(todo)
    # 추정 규칙: 최근 7일 검색어 전체에서 첫 단어 반복을 셈 (브랜드로 판단된 것만 저장, 아니면 다음 날 다시 판단)
    found = guess(conn, d, ages)
    n = 0
    for k in todo:
        if found.get(k):
            db.save_brand(conn, k, found[k], d)
            n += 1
    return n


def guess(conn, d: str, ages: list[str]) -> dict:
    from datetime import date, timedelta
    import homepage
    pool = set()
    for i in range(7):
        day = (date.fromisoformat(d) - timedelta(days=i)).isoformat()
        for age in ages:
            pool.update(r["keyword"] for r in db.get_ranks(conn, day, age))
    first = Counter(k.split()[0] for k in pool if len(k.split()) >= 2)
    stop = set(config.BRAND_STOPWORDS)
    out = {}
    for k in pool:
        parts = k.split()
        w = parts[0]
        if len(parts) >= 2 and len(w) >= 2 and first[w] >= 2 and w not in stop and homepage.product_category(w) == "기타":
            out[k] = w
    return out


def lookup(keyword: str) -> str | None:
    headers = {"X-Naver-Client-Id": config.NAVER_CLIENT_ID, "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET}
    for attempt in range(3):
        try:
            r = requests.get(SHOP_URL, headers=headers, params={"query": keyword, "display": 20, "sort": "sim"}, timeout=10)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            items = r.json().get("items", [])
            break
        except requests.RequestException:
            time.sleep(1 + attempt)
    else:
        return None

    beauty = [it for it in items if it.get("category1") == "화장품/미용"]
    names = Counter()
    for it in beauty:
        name = _clean(it.get("brand") or it.get("maker") or "")
        if name:
            names[name] += 1
    if len(beauty) < 3 or not names:
        return None
    name, n = names.most_common(1)[0]
    return name if n / len(beauty) >= 0.5 else None


def _clean(s: str) -> str:
    return _TAG.sub("", s).strip()
