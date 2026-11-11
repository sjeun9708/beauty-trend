"""순위 변동 분류: 신규 진입 / 급상승 / 상승 / 유지 / 하락."""
import config


def classify(today: list[dict], prev: list[dict]) -> list[dict]:
    prev_rank = {r["keyword"]: r["rank"] for r in prev}
    out = []
    for r in today:
        p = prev_rank.get(r["keyword"])
        if not prev:
            status, change = "UNKNOWN", None        # 비교할 전날 데이터가 없음
        elif p is None:
            status, change = "NEW", None
        else:
            change = p - r["rank"]                  # 양수 = 상승
            if change >= config.RISE_THRESHOLD:
                status = "SURGE"
            elif change > 0:
                status = "UP"
            elif change < 0:
                status = "DOWN"
            else:
                status = "SAME"
        out.append({**r, "prev_rank": p, "change": change, "status": status})
    return out


def is_hot(status: str) -> bool:
    """새로 원인 분석이 필요한 상태인지."""
    return status in ("NEW", "SURGE", "UNKNOWN")
