"""LLM(Claude)으로 원인 분석과 연령별 인사이트 생성.

핵심 원칙: LLM은 '수집한 근거 안에서만' 이유를 말하게 합니다.
근거가 없으면 LLM을 부르지 않고 '원인 불명확'으로 남깁니다(환각 방지 + 비용 절감).
"""
import json
import re

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


TARGET = f"{config.GENDER_LABEL} " if config.GENDER_LABEL else ""

KEYWORD_SYSTEM = f"""너는 한국 뷰티 마케팅 트렌드 애널리스트다.
네이버 쇼핑 '화장품/미용' 분야에서 {TARGET}소비자가 많이 검색한 키워드가 왜 많이 검색됐는지 분석한다.
타깃 고객은 {TARGET or '전체 '}소비자이며, 이 관점에서 마케터에게 의미 있는 이유를 쓴다.

규칙:
1. 반드시 사용자가 준 [근거 자료] 안의 내용만 근거로 삼는다. 근거에 없는 사건, 인물, 수치를 지어내지 않는다.
2. 근거가 키워드와 관련이 약하거나 원인을 특정할 수 없으면 category를 "원인 불명확"으로 하고 confidence를 "low"로 한다.
3. category는 다음 중 하나만 고른다: {", ".join(config.CATEGORIES)}
4. reason은 마케터가 바로 쓸 수 있게 한국어 1~2문장으로 쓴다.
5. JSON 외의 다른 텍스트(설명, 마크다운 코드블록)는 출력하지 않는다.

출력 형식:
{{"category": "...", "reason": "...", "confidence": "high|medium|low", "evidence_ids": [1, 3]}}"""

INSIGHT_SYSTEM = f"""너는 한국 뷰티 마케팅 트렌드 애널리스트다.
{TARGET}소비자 중 한 연령대의 하루치 화장품/미용 인기검색어 1~50위와 각 키워드의 순위 변동, 원인 분류를 보고
마케터에게 쓸모 있는 핵심 인사이트 3개를 뽑는다.
주어진 데이터에 없는 사실은 지어내지 않는다.
JSON 배열(문자열 3개)만 출력한다. 예: ["...", "...", "..."]"""


def analyze_keyword(keyword: str, d: str, appearances: list[dict], evidence: list[dict]) -> dict:
    evidence = [e for e in evidence if not e.get("ad")][:12]
    if not evidence:
        return {
            "category": "원인 불명확",
            "reason": f"최근 {config.EVIDENCE_DAYS}일 안에 관련 뉴스나 블로그 근거를 찾지 못했습니다.",
            "confidence": "low",
            "sources": [],
        }

    ages_text = "\n".join(
        f"- {config.AGE_GROUPS[a['age']]} {config.GENDER_LABEL}: {a['rank']}위 ({_status_text(a)})" for a in appearances
    )
    ev_text = "\n".join(
        f"[{i}] ({e['type']}, {e['date']}) {e['title']} — {e['desc']}" for i, e in enumerate(evidence, 1)
    )
    prompt = f"""기준일: {d}
키워드: {keyword}

[연령별 순위]
{ages_text}

[근거 자료]
{ev_text}"""

    raw = _call(KEYWORD_SYSTEM, prompt, max_tokens=600)
    data = _parse_json(raw, default={})

    category = data.get("category")
    if category not in config.CATEGORIES:
        category = "원인 불명확"
    ids = [i for i in data.get("evidence_ids", []) if isinstance(i, int) and 1 <= i <= len(evidence)]
    return {
        "category": category,
        "reason": str(data.get("reason", "")).strip() or "분석 결과를 해석하지 못했습니다.",
        "confidence": data.get("confidence", "low") if data.get("confidence") in ("high", "medium", "low") else "low",
        "sources": [{"title": evidence[i - 1]["title"], "link": evidence[i - 1]["link"]} for i in ids[:3]],
    }


def age_insights(age: str, d: str, rows: list[dict], by_age: dict | None = None) -> list[str]:
    lines = "\n".join(
        f"{r['rank']}. {r['keyword']} | {_status_text(r)} | {r['analysis']['category']}" for r in rows
    )
    prompt = f"기준일: {d}\n연령대: {config.AGE_GROUPS[age]} {config.GENDER_LABEL}\n\n{lines}"
    raw = _call(INSIGHT_SYSTEM, prompt, max_tokens=700)
    items = _parse_json(raw, default=[])
    return [str(x) for x in items][:3] if isinstance(items, list) else []


def _call(system: str, prompt: str, max_tokens: int) -> str:
    resp = _get_client().messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _parse_json(text: str, default):
    text = re.sub(r"```(?:json)?", "", text).strip()
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = text.find(open_c), text.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    return default


def _status_text(r: dict) -> str:
    return {
        "NEW": "신규 진입",
        "SURGE": f"급상승 ▲{r.get('change')}",
        "UP": f"상승 ▲{r.get('change')}",
        "DOWN": f"하락 ▼{abs(r.get('change') or 0)}",
        "SAME": "유지",
        "UNKNOWN": "전일 데이터 없음",
    }.get(r.get("status"), "")


EVENT_SYSTEM = """너는 한국 뷰티 업계 행사 정보를 정리하는 에디터다.
주어진 [기사·글] 목록에서 화장품·뷰티 브랜드의 오프라인 팝업스토어, 체험 행사, 할인 행사를 찾아 정리한다.

규칙:
1. 글에 날짜와 장소가 명시된 행사만 넣는다. 날짜나 장소를 추측하지 않는다.
2. 뷰티(화장품, 향수, 헤어, 바디, 네일)와 관련 없는 행사는 뺀다.
3. 같은 행사가 여러 글에 나오면 하나로 합친다.
4. 연도가 없으면 기준일에 가장 가까운 연도로 본다.
5. summary는 무엇을 체험하거나 받을 수 있는지 한국어 한 문장으로, 원문 문장을 그대로 옮기지 말고 새로 쓴다.
6. JSON 배열만 출력한다. 행사가 없으면 [] 를 출력한다.

각 항목 형식:
{"name": "행사 이름", "brand": "브랜드", "place": "장소(건물·주소)", "area": "성수|여의도|강남|홍대|명동|잠실|기타 중 하나",
 "start": "YYYY-MM-DD", "end": "YYYY-MM-DD 또는 null", "booking": "현장방문|사전예약|사전예약·현장방문|null",
 "summary": "...", "source_id": 3}"""


def extract_events(d: str, items: list[dict]) -> list[dict]:
    if not items:
        return []
    text = "\n".join(f"[{i}] ({e['type']}, {e['date']}) {e['title']} — {e['desc']}" for i, e in enumerate(items, 1))
    raw = _call(EVENT_SYSTEM, f"기준일: {d}\n\n[기사·글]\n{text}", max_tokens=3000)
    data = _parse_json(raw, default=[])
    if not isinstance(data, list):
        return []
    out = []
    for e in data:
        if not isinstance(e, dict) or not e.get("name") or not _is_date(e.get("start")):
            continue
        sid = e.get("source_id")
        src = items[sid - 1] if isinstance(sid, int) and 1 <= sid <= len(items) else None
        out.append({
            "name": str(e["name"]).strip(), "brand": e.get("brand"), "place": e.get("place"),
            "area": e.get("area") or "기타", "start": e["start"],
            "end": e["end"] if _is_date(e.get("end")) else None,
            "booking": e.get("booking"), "summary": e.get("summary"),
            "source_title": src["title"] if src else None, "source_link": src["link"] if src else None,
        })
    return out


def _is_date(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) is not None
