"""네이버 데이터랩 쇼핑인사이트 > 화장품/미용 > 인기검색어 수집.

주의: 이 엔드포인트는 데이터랩 웹 화면이 내부적으로 쓰는 비공식 주소입니다.
- 네이버가 언제든 바꿀 수 있으므로 오류가 나면 브라우저 개발자도구(Network 탭)에서
  쇼핑인사이트 화면의 인기검색어 요청을 확인해 URL/파라미터를 맞춰 주세요.
- 상업적으로 쓰기 전에 네이버 이용약관(자동 수집 관련)을 반드시 확인하세요.
- 요청 간격(time.sleep)을 줄이지 마세요.
"""
import time
import requests

import config

URL = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
PAGE_SIZE = 20  # 데이터랩은 한 페이지에 20개씩 반환


def fetch_top_keywords(date: str, age: str, top_n: int = config.COLLECT_N,
                       cid: str = config.BEAUTY_CID) -> list[dict]:
    """date(YYYY-MM-DD) 하루 동안 해당 연령대의 인기검색어 1~top_n위."""
    results: list[dict] = []
    page = 1
    while len(results) < top_n:
        payload = {
            "cid": cid,
            "timeUnit": "date",
            "startDate": date,
            "endDate": date,
            "age": age,       # "10","20",... 빈 문자열이면 전체
            "gender": config.GENDER,  # config.py 에서 지정 ("f" = 여성)
            "device": "",     # "pc" / "mo" 로 기기 필터 가능
            "page": page,
            "count": PAGE_SIZE,
        }
        resp = _post_with_retry(payload)
        ranks = resp.get("ranks", [])
        if not ranks:
            break
        for item in ranks:
            results.append({"rank": int(item["rank"]), "keyword": item["keyword"].strip()})
        page += 1
        time.sleep(1.5)
    return results[:top_n]


def _post_with_retry(payload: dict, retries: int = 3) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(URL, data=payload, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"데이터랩 수집 실패: {last_err}")
