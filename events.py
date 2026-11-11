"""뷰티 팝업스토어·행사 수집.

네이버 뉴스·블로그에서 팝업 관련 글을 모으고, AI가 글에 적힌 행사만 골라
이름·브랜드·장소·기간·예약 방법을 정리해 DB에 쌓습니다.
"""
import config
import db


def collect(conn, d: str, demo: bool = False) -> int:
    if not demo and not config.HAS_SEARCH:
        return 0                      # 키 없이 쓰기 모드: 행사 수집은 건너뜀
    if demo:
        import demo_data
        found = demo_data.events()
    else:
        import evidence
        brain = __import__("rules" if config.ANALYZER == "free" else "analyzer")
        items, seen = [], set()
        queries = config.EVENT_QUERIES + [f"{b} 팝업" for b in config.WATCH_BRANDS[:5]]
        for q in queries:
            for it in evidence.collect(q, d, days=config.EVENT_DAYS, limit=100, display=100):
                if it["link"] not in seen:
                    seen.add(it["link"])
                    items.append(it)
        found = brain.extract_events(d, items if config.ANALYZER == "free" else items[: config.EVENT_MAX_SOURCES])
    for e in found:
        db.save_event(conn, e, d)
    return len(found)
