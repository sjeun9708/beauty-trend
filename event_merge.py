"""홈페이지에 싣기 전에 팝업·행사를 정리해요.

- 같은 행사를 다룬 여러 기사·글을 하나로 합치고, 출처를 모두 남겨요(언론사·블로그 이름 포함).
- '총정리·TOP5·어디 갈까' 같은 정리 글은 행사에서 빼고 '최근 팝업 소식'으로 보내요.
- 제목에 뷰티 브랜드나 뷰티 단어가 없는 팝업은 빼요.
- 장소를 네이버 지도에서 찾을 검색어를 만들어요.
DB에 이미 쌓인 예전 기록에도 똑같이 적용돼서, 지난 중복도 함께 정리돼요.
"""
import re
from collections import Counter
from datetime import date
from urllib.parse import urlparse

import config

ROUNDUP = re.compile(r"총정리|정리\s*$|TOP\s*\d|탑\s*\d|BEST|베스트|어디\s*갈|가볼\s*만한|가\s*볼\s*만한|추천\s*코스|코스|지도|모음|리스트|"
                     r"일정\s*정리|팝업\s*정리|위클리|weekly|이번\s*주|주말\s*필수|\d+곳|\d+선", re.I)
BEAUTY_WORD = re.compile(r"뷰티|화장품|코스메틱|스킨케어|메이크업|향수|퍼퓸|립|쿠션|세럼|앰플|크림|헤어|바디|네일|색조|"
                         r"디바이스|올리브영|피부|선크림|패드|토너|에센스|마스크팩|클렌징|파운데이션|틴트|PDRN|에스테틱|프래그런스")
NOT_BEAUTY = re.compile(r"토이|TOYS|피규어|굿즈|캐릭터|빼빼로|과자|식품|푸드|음료|카페|디저트|패션|의류|신발|게임|웹툰|가구|리빙", re.I)

OUTLETS = {
    "blog.naver.com": "네이버 블로그", "m.blog.naver.com": "네이버 블로그", "cafe.naver.com": "네이버 카페",
    "tistory.com": "티스토리", "brunch.co.kr": "브런치", "newspim.com": "뉴스핌", "zdnet.co.kr": "지디넷코리아",
    "cosinkorea.com": "코스인코리아", "cosmorning.com": "코스모닝", "beautynury.com": "뷰티누리", "jangup.com": "장업신문",
    "fnnews.com": "파이낸셜뉴스", "mk.co.kr": "매일경제", "hankyung.com": "한국경제", "chosun.com": "조선일보",
    "donga.com": "동아일보", "joongang.co.kr": "중앙일보", "sedaily.com": "서울경제", "edaily.co.kr": "이데일리",
    "newsis.com": "뉴시스", "yna.co.kr": "연합뉴스", "news1.kr": "뉴스1", "asiae.co.kr": "아시아경제",
    "heraldcorp.com": "헤럴드경제", "mt.co.kr": "머니투데이", "etnews.com": "전자신문", "bizwatch.co.kr": "비즈워치",
    "insight.co.kr": "인사이트", "wikitree.co.kr": "위키트리", "topstarnews.net": "톱스타뉴스", "kmib.co.kr": "국민일보",
    "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "seoul.co.kr": "서울신문", "segye.com": "세계일보",
    "ajunews.com": "아주경제", "inews24.com": "아이뉴스24", "dailian.co.kr": "데일리안", "nocutnews.co.kr": "노컷뉴스",
    "mtn.co.kr": "머니투데이방송", "sportsseoul.com": "스포츠서울", "ilyo.co.kr": "일요신문", "thebell.co.kr": "더벨",
    "womaneconomy.co.kr": "여성경제신문", "fashionbiz.co.kr": "패션비즈", "apparelnews.co.kr": "어패럴뉴스",
}


def outlet(link: str | None) -> str:
    if not link:
        return "출처"
    host = (urlparse(link).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    for dom, name in OUTLETS.items():
        d = dom.removeprefix("m.")
        if host == d or host.endswith("." + d):
            return name
    return host or "출처"


def is_beauty_title(title: str) -> bool:
    """알려진 뷰티 브랜드가 제목에 있거나, 뷰티 단어가 있고 뷰티 아닌 단어가 없을 때만 뷰티 팝업으로 봄."""
    if config.brand_in_text(title):
        return True
    return bool(BEAUTY_WORD.search(title)) and not NOT_BEAUTY.search(title)


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (t or "").lower())


def _overlap(a, b, gap=2) -> bool:
    a1, a2 = date.fromisoformat(a["start"]), date.fromisoformat(a["end"] or a["start"])
    b1, b2 = date.fromisoformat(b["start"]), date.fromisoformat(b["end"] or b["start"])
    return (a1 - b2).days <= gap and (b1 - a2).days <= gap


def _map_query(place: str | None, area: str | None, brand: str | None) -> str | None:
    if place:
        m = re.search(r"\(([^)]*(?:로|길)\s?\d[^)]*)\)", place)      # 괄호 속 도로명 주소가 있으면 그걸로
        if m:
            return "서울 " + m.group(1)
        return re.sub(r"\s*\([^)]*\)", "", place).strip()
    if brand and area and area != "기타":
        return f"{area} {brand} 팝업"
    return None


_LEAD = re.compile(r"^(?:\[[^\]]{1,12}\]\s*)?[\"'‘“]?([A-Za-z0-9가-힣&.]{2,12})[\"'’”]?\s*[,·]")
_STOP_LEAD = {"성수", "여의도", "강남", "명동", "잠실", "홍대", "서울", "올리브영", "더현대", "현대백화점", "신세계", "롯데", "단독", "현장", "포토"}


def _lead_brand(title: str):
    """기사 제목 관례 '브랜드, ~' 에서 브랜드 추정 (예: '오키뷰티, 더현대 서울 팝업 운영')."""
    m = _LEAD.match(title.strip())
    if m and m.group(1) not in _STOP_LEAD and not BEAUTY_WORD.fullmatch(m.group(1)):
        return m.group(1)
    return None


def build(rows: list[dict]) -> list[dict]:
    """DB의 행사 행들 → 홈페이지용 목록 (행사 + '최근 소식')."""
    events, news, seen_links = [], [], set()
    # 1차: 제목에서 브랜드 후보 모으기 (알려진 브랜드 + '브랜드, ~' 형태)
    guessed = {g for r in rows if (g := _lead_brand(r.get("source_title") or ""))}

    def brand_of(title):
        b = config.brand_in_text(title)
        if b:
            return b
        t = _norm(title)
        hits = [g for g in guessed if _norm(g) and _norm(g) in t]
        return max(hits, key=len) if hits else None

    for r in rows:
        title = (r.get("source_title") or r.get("name") or "").strip()
        link = r.get("source_link")
        if not title:
            continue
        roundup = bool(ROUNDUP.search(title))
        if not roundup and not is_beauty_title(title):
            continue                                    # 뷰티 아닌 팝업
        src = [title, link, outlet(link)]
        if roundup or r.get("undated"):
            if link and link in seen_links:
                continue
            seen_links.add(link)
            news.append({"n": title, "b": None if roundup else brand_of(title), "a": r.get("area") or "기타",
                         "s": r["start"], "e": None, "u": 1, "k": "정리 글" if roundup else "소식", "src": [src]})
            continue
        r = {**r, "brand": brand_of(title)}   # 브랜드는 '제목'에서만 판단
        key = r["brand"] or _norm(title)[:10]
        for c in events:
            if c["key"] == key and _overlap(c["rows"][0], r):
                c["rows"].append(r)
                if link not in {s[1] for s in c["src"]}:
                    c["src"].append(src)
                break
        else:
            events.append({"key": key, "rows": [r], "src": [src]})

    out = []
    for c in events:
        rs = c["rows"]
        pick = lambda k: (Counter(x[k] for x in rs if x.get(k)).most_common(1) or [(None, 0)])[0][0]
        brand, place, area = rs[0]["brand"], pick("place"), pick("area") or "기타"
        start, end = pick("start"), pick("end")
        heads = sorted({s[0] for s in c["src"]}, key=len)
        name = f"{brand} 팝업스토어" if brand else heads[0]
        out.append({
            "n": name, "hl": heads[0] if brand else None, "b": brand, "p": place, "a": area,
            "s": start, "e": end, "bk": pick("booking"), "sm": pick("summary"),
            "src": sorted(c["src"], key=lambda s: s[2] == "네이버 블로그"),   # 뉴스를 먼저
            "map": _map_query(place, area, brand), "u": 0,
        })
    return out + news
