"""'왜 떴는지'의 근거 자료 수집: 네이버 검색 API(뉴스, 블로그).

네이버 개발자센터(developers.naver.com)에서 애플리케이션을 등록하고
'검색' API를 추가하면 Client ID / Secret을 받을 수 있습니다.
"""
import html
import re
import time
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

import config

if config.NAVER_API_MODE == "legacy":      # 예전 개발자센터 키
    NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
    BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
    HEADERS = {"X-Naver-Client-Id": config.NAVER_CLIENT_ID, "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET}
else:                                       # NAVER API HUB (네이버 클라우드 플랫폼)
    NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    BLOG_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"
    HEADERS = {"X-NCP-APIGW-API-KEY-ID": config.NAVER_CLIENT_ID, "X-NCP-APIGW-API-KEY": config.NAVER_CLIENT_SECRET}
_TAG = re.compile(r"<[^>]+>")
_cache: dict[tuple, list] = {}


def collect(keyword: str, d: str, days: int = config.EVIDENCE_DAYS, limit: int = 12, display: int = 20) -> list[dict]:
    """d 기준 최근 days일 안에 올라온 뉴스/블로그 글 목록."""
    if not config.HAS_SEARCH:
        return []
    key = (keyword, d, days, limit, display)
    if key in _cache:
        return _cache[key]

    end = date.fromisoformat(d)
    start = end - timedelta(days=days)
    items: list[dict] = []

    for it in _search(NEWS_URL, keyword, display):
        try:
            pub = parsedate_to_datetime(it["pubDate"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        if start <= pub <= end:
            items.append(_item("뉴스", it, pub, it.get("originallink") or it.get("link")))

    for it in _search(BLOG_URL, keyword, display):
        try:
            pub = datetime.strptime(it["postdate"], "%Y%m%d").date()
        except (KeyError, ValueError):
            continue
        if start <= pub <= end:
            items.append(_item("블로그", it, pub, it.get("link")))

    items = items[:limit + 8]   # 광고 글을 빼도 충분히 남도록 조금 더 받아 둠
    _cache[key] = items
    return items


def _item(kind, it, pub, link):
    text = f"{it.get('title', '')} {it.get('description', '')}"
    return {
        "ad": any(m in text for m in config.AD_MARKERS),
        "type": kind,
        "date": pub.isoformat(),
        "title": _clean(it.get("title", "")),
        "desc": _clean(it.get("description", ""))[:200],
        "link": link,
    }


def _search(url: str, query: str, display: int = 20) -> list[dict]:
    headers = HEADERS
    params = {"query": query, "display": display, "sort": "date"}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code == 429:          # 호출 한도 초과 → 잠시 대기
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(0.15)
            return r.json().get("items", [])
        except requests.RequestException:
            time.sleep(1 + attempt)
    return []


def _clean(text: str) -> str:
    return html.unescape(_TAG.sub("", text)).strip()
