"""무료 분석기: AI(유료 API) 없이 규칙으로 원인 분류·인사이트·행사 정리를 합니다.

- 원인: 최근 뉴스·블로그 제목과 요약에 자주 나온 단어로 분류합니다.
- 인사이트: 순위 변동과 연령대 비교를 계산해 문장으로 만듭니다.
- 행사: 글 제목·요약에서 '11월 4일부터 11일까지', '10/28~11/12' 같은 기간과 장소를 찾아냅니다.
AI만큼 자연스럽진 않지만, 비용이 들지 않고 근거가 투명합니다.
"""
import re
from collections import Counter
from datetime import date

import config

CATEGORY_TERMS = {
    "할인/행사": ["할인", "세일", "특가", "증정", "쿠폰", "블랙프라이데이", "기획전", "1+1", "페스타", "럭키드로우", "최저가"],
    "셀럽/광고": ["모델", "앰배서더", "뮤즈", "화보", "광고", "발탁", "아이돌", "배우", "착용", "협업", "콜라보"],
    "SNS 바이럴": ["틱톡", "숏폼", "릴스", "유튜브", "인스타", "바이럴", "입소문", "챌린지", "품절", "대란", "SNS"],
    "신제품 출시": ["출시", "신제품", "론칭", "런칭", "선보", "신상", "리뉴얼", "첫선"],
    "성분/기술 트렌드": ["성분", "PDRN", "레티놀", "펩타이드", "콜라겐", "엑소좀", "비타민", "시카", "특허", "임상", "더마"],
    "시즌/날씨": ["건조", "환절기", "겨울", "추위", "보습", "자외선", "미세먼지", "장마", "여름", "연말", "크리스마스", "선물"],
}


# ---------- 원인 분류 ----------

def analyze_keyword(keyword: str, d: str, appearances: list[dict], evidence: list[dict]) -> dict:
    ads = [e for e in evidence if e.get("ad")]
    evidence = [e for e in evidence if not e.get("ad")]
    # 관련성: 제목·요약에 키워드(띄어쓰기 무시)나 그 브랜드 이름이 실제로 나오는 글만 근거로 씀
    #   예) '웨이크메이크파데' 검색 결과 중 다른 브랜드 신상 소개 글은 제외
    total = len(evidence)
    evidence = [e for e in evidence if _relevant(keyword, e)]
    off = total - len(evidence)
    notes = [f"광고·체험단 글 {len(ads)}건" if ads else "", f"관련 없는 글 {off}건" if off else ""]
    ad_note = f" ({' · '.join(x for x in notes if x)} 제외)" if any(notes) else ""
    if not evidence and (ads or off):
        return {"category": "원인 불명확", "confidence": "low", "sources": [],
                "reason": f"관련 글은 있었지만 키워드를 직접 다룬 글이 없었어요{ad_note}."}
    if not evidence:
        why = (f"관련 글 {len(ads)}건이 모두 광고·체험단 글이라 근거에서 뺐어요." if ads
               else f"최근 {config.EVIDENCE_DAYS}일 안에 관련 뉴스나 블로그 글을 찾지 못했어요.")
        return {"category": "원인 불명확", "confidence": "low", "sources": [], "reason": why}

    hits = {c: [] for c in CATEGORY_TERMS}
    terms_found = {c: Counter() for c in CATEGORY_TERMS}
    score = Counter()
    for i, e in enumerate(evidence):
        text = f"{e['title']} {e['desc']}"
        for cat, terms in CATEGORY_TERMS.items():
            matched = [t for t in terms if t.lower() in text.lower()]
            if matched:
                hits[cat].append(i)
                terms_found[cat].update(matched)
                score[cat] += 2 if e["type"] == "뉴스" else 1      # 뉴스는 블로그보다 무겁게

    if not score:
        return {"category": "원인 불명확", "confidence": "low", "sources": [_src(evidence[0])],
                "reason": f"관련 글 {len(evidence)}건{ad_note}이 있지만 뚜렷한 이유를 찾지 못했어요. 출처를 직접 확인해 보세요."}

    best = max(CATEGORY_TERMS, key=lambda c: (score[c], len(hits[c])))
    idx = sorted(hits[best], key=lambda i: evidence[i]["type"] != "뉴스")   # 뉴스를 먼저 보여 줌
    n, news = len(idx), sum(1 for i in idx if evidence[i]["type"] == "뉴스")
    words = ", ".join(f"‘{w}’" for w, _ in terms_found[best].most_common(2))
    where = " · ".join(x for x in [f"뉴스 {news}건" if news else "", f"블로그 {n - news}건" if n - news else ""] if x)
    conf = "high" if news >= 1 and n >= 3 else "medium" if news >= 1 or n >= 3 else "low"
    return {
        "category": best,
        "confidence": conf,
        "reason": f"{where}에서 {words} 이야기가 나왔어요{ad_note}. 대표 근거: {evidence[idx[0]]['title']}",
        "sources": [_src(evidence[i]) for i in idx[:3]],
    }


def _relevant(keyword: str, e: dict) -> bool:
    text = (e["title"] + e["desc"]).replace(" ", "").lower()
    k = keyword.replace(" ", "").lower()
    if k in text:
        return True
    brand = config.alias_brand(keyword) or config.known_brand(keyword)
    if brand:
        rest = k[len(brand.replace(" ", "").lower()):] if k.startswith(brand.replace(" ", "").lower()) else ""
        b = brand.replace(" ", "").lower()
        # 브랜드 이름과 제품명 일부(2글자 이상)가 함께 나오면 관련 글로 인정
        return b in text and (not rest or rest[:2] in text)
    # 띄어 쓴 검색어는 모든 단어가 나오면 인정
    words = [w.lower() for w in keyword.split() if len(w) >= 2]
    return len(words) >= 2 and all(w in text for w in words)


def _src(e):
    return {"title": e["title"], "link": e["link"]}


# ---------- 연령별 인사이트 ----------

def _has_batchim(word: str) -> bool:
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isalnum():
            return ch.lower() in "lmnr0136789"   # 영문·숫자는 읽는 소리 기준 대략 판정
    return False


def _josa(word: str, with_b: str, without_b: str) -> str:
    return word + (with_b if _has_batchim(word) else without_b)


def age_insights(age: str, d: str, rows: list[dict], by_age: dict | None = None) -> list[str]:
    name = config.AGE_GROUPS[age] + (f" {config.GENDER_LABEL}" if config.GENDER_LABEL else "")
    out = []

    rising = [r for r in rows if r["status"] in ("NEW", "SURGE")]
    if rising:
        top = max(rising, key=lambda r: (51 - r["rank"]) if r["status"] == "NEW" else r["change"])
        how = "새로 진입" if top["status"] == "NEW" else f"{top['change']}계단 상승"
        kw = top["keyword"]
        out.append(f"새로 들어왔거나 크게 오른 키워드가 {len(rising)}개예요. 가장 눈에 띄는 건 {kw}({top['rank']}위, {how}){'이에요' if _has_batchim(kw) else '예요'}.")
    else:
        out.append(f"순위 변동이 적은 하루였어요. 상위권은 {_josa(', '.join(r['keyword'] for r in rows[:3]), '이', '가')} 지켰어요.")

    cats = Counter(r["analysis"]["category"] for r in rows if r.get("analysis"))
    for skip in ("원인 불명확", "스테디셀러"):
        cats.pop(skip, None)
    if cats:
        c, n = cats.most_common(1)[0]
        ex = [r["keyword"] for r in rows if r.get("analysis") and r["analysis"]["category"] == c][:2]
        out.append(f"검색이 늘어난 이유로는 {_josa(c, '이', '가')} {n}개로 가장 많아요. ({', '.join(ex)} 등)")
    else:
        out.append("이유가 뚜렷하게 잡힌 키워드가 적어요. 관련 기사나 글이 아직 많지 않은 시기일 수 있어요.")

    if by_age:
        others = set()
        for a, rs in by_age.items():
            if a != age:
                others.update(r["keyword"] for r in rs)
        only = [r["keyword"] for r in rows[:20] if r["keyword"] not in others]
        if only:
            out.append(f"다른 연령대 50위 안에는 없고 {name}만 상위 20위 안에서 찾은 키워드: {', '.join(only[:4])}.")
        else:
            shared = sum(1 for r in rows[:10] if all(r["keyword"] in {x['keyword'] for x in rs} for rs in by_age.values()))
            out.append(f"상위 10위 중 {shared}개는 모든 연령대가 함께 찾은 키워드예요.")
    return out


# ---------- 팝업·행사 ----------

VENUES = [
    ("더현대 서울", "여의도"), ("여의도", "여의도"), ("올리브영N 성수", "성수"), ("무신사 뷰티", "성수"),
    ("성수", "성수"), ("연무장", "성수"), ("신세계 강남", "강남"), ("강남", "강남"), ("압구정", "강남"),
    ("가로수길", "강남"), ("홍대", "홍대"), ("연남", "홍대"), ("명동", "명동"), ("롯데월드몰", "잠실"),
    ("잠실", "잠실"), ("판교", "기타"), ("용산", "기타"), ("한남", "기타"),
]
_RANGE_KR = re.compile(r"(\d{1,2})월\s*(\d{1,2})일\s*(?:\([^)]*\))?\s*(?:부터|~|-)\s*(?:(\d{1,2})월\s*)?(\d{1,2})일")
_RANGE_NUM = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})\s*[~\-–]\s*(?:(\d{1,2})[./])?(\d{1,2})(?![\d./])")
_POPUP = re.compile(r"팝업|팝업스토어|체험존|라운지|쇼룸")


def extract_events(d: str, items: list[dict]) -> list[dict]:
    base = date.fromisoformat(d)
    found = {}
    for it in items:
        text = f"{it['title']} {it['desc']}"
        if not _POPUP.search(text):
            continue
        m = _RANGE_KR.search(text) or _RANGE_NUM.search(text)
        if not m:
            continue
        sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(1)), int(m.group(4))
        try:
            start = _nearest(base, sm, sd)
            end = _nearest(start, em, ed, after=True)
        except ValueError:
            continue
        place, area = next(((v, a) for v, a in VENUES if v in text), (None, "기타"))
        title = re.sub(r"\s+", " ", it["title"]).strip()
        key = (title[:12], start)
        if key in found:
            continue
        found[key] = {
            "name": title[:60], "brand": None, "place": place, "area": area,
            "start": start.isoformat(), "end": end.isoformat(),
            "booking": "사전예약" if "사전예약" in text else None,
            "summary": None, "source_title": title, "source_link": it["link"],
        }
    return list(found.values())


def _nearest(base: date, m: int, d: int, after: bool = False) -> date:
    """연도가 없는 날짜를 기준일에 가장 가까운 연도로 해석."""
    cands = [date(base.year + k, m, d) for k in (-1, 0, 1)]
    if after:
        cands = [c for c in cands if c >= base] or cands
    return min(cands, key=lambda c: abs((c - base).days))
