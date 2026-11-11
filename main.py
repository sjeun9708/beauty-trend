"""연령별 뷰티 검색 트렌드 분석 파이프라인.

사용법:
    python main.py                                  # 어제 날짜 기준, 전 연령 (매일 자동 실행용)
    python main.py --date 2026-11-10                # 특정 날짜
    python main.py --from 2026-11-01 --to 2026-11-10  # 기간 한꺼번에 채우기
    python main.py --rebuild                        # 저장된 모든 날짜의 리포트를 다시 그리기 (API 호출 없음)
    python main.py --demo                           # API 키 없이 가짜 데이터로 흐름 확인

결과:
    site/index.html           홈페이지 (최근 30일, 여기서 시작)
    reports/index.html        날짜별 리포트 목록 (전체 기간)
    reports/YYYY-MM-DD.html   날짜별 리포트 (전날/다음날 이동 가능)
    reports/YYYY-MM-DD.json   날짜별 원본 데이터
    beauty_trend.db           모든 날짜의 순위·분석 누적 저장소
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import config
import brands
import db
import events
import report
import homepage
import trends

KST = timezone(timedelta(hours=9))


def _prev(d: str) -> str:
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


# ---------- 1. 수집 + 분석 (API 사용, 결과는 DB에 누적) ----------

def collect_and_analyze(conn, d: str, ages: list[str], demo: bool):
    import collector, evidence, demo_data, rules  # noqa: E401
    brain = rules if config.ANALYZER == "free" else __import__("analyzer")

    for age in ages:
        for day in (_prev(d), d):
            if db.has_ranks(conn, day, age):
                continue
            label = f"{day} {config.AGE_GROUPS[age]}"
            try:
                rows = demo_data.ranks(day, age) if demo else collector.fetch_top_keywords(day, age)
            except RuntimeError as e:
                print(f"  ! 수집 실패 {label}: {e}")
                continue
            db.save_ranks(conn, day, age, rows)
            print(f"  수집 {label}: {len(rows)}개")

    by_age = _classified(conn, d, ages)
    if not by_age:
        print(f"  ! {d} 순위 데이터가 없어 건너뜁니다.")
        return False

    appearances = defaultdict(list)
    for age, rows in by_age.items():
        for r in rows:
            appearances[r["keyword"]].append({**r, "age": age})

    counts = {"new": 0, "reused": 0, "cached": 0}
    for kw, apps in appearances.items():
        if db.get_analysis(conn, d, kw):
            counts["cached"] += 1
            continue
        if not any(trends.is_hot(a["status"]) for a in apps):
            prior = db.get_recent_analysis(conn, kw, d, config.REUSE_DAYS)
            if prior:
                db.save_analysis(conn, d, kw, prior, reused=True)
                counts["reused"] += 1
                continue
        if demo:
            result = demo_data.analysis(kw)
        elif not config.HAS_SEARCH:
            result = {"category": "원인 불명확", "confidence": "low", "sources": [],
                      "reason": "근거 검색이 꺼져 있어요(네이버 API 키 없음). 순위 변화를 보고 노트에 직접 해석을 남겨 보세요."}
        else:
            result = brain.analyze_keyword(kw, d, apps, evidence.collect(kw, d))
        db.save_analysis(conn, d, kw, result)
        counts["new"] += 1
    print(f"  원인 분석: 신규 {counts['new']} / 재사용 {counts['reused']} / 기존 {counts['cached']}")

    _attach_analyses(conn, d, by_age)
    for age, rows in by_age.items():
        if not db.get_insights(conn, d, age):
            items = rules.age_insights(age, d, rows, by_age) if demo else brain.age_insights(age, d, rows, by_age)
            db.save_insights(conn, d, age, items)
    return True


# ---------- 2. 리포트 그리기 (DB만 읽음, API 호출 없음) ----------

def render(conn, d: str, ages: list[str], dates: list[str]) -> str | None:
    by_age = _classified(conn, d, ages)
    if not by_age:
        return None
    _attach_analyses(conn, d, by_age)
    if any(r["analysis"] is None for rows in by_age.values() for r in rows):
        return None
    insights = {age: db.get_insights(conn, d, age) for age in by_age}

    seen = defaultdict(list)
    for age, rows in by_age.items():
        for r in rows:
            seen[r["keyword"]].append(age)
    common = sorted(
        ({"keyword": k, "age_count": len(v), "ages": v} for k, v in seen.items() if len(v) >= config.COMMON_MIN_AGES),
        key=lambda x: -x["age_count"],
    )

    i = dates.index(d) if d in dates else -1
    prev_d = dates[i - 1] if i > 0 else None
    next_d = dates[i + 1] if 0 <= i < len(dates) - 1 else None
    _, html_path = report.build(d, by_age, insights, common, prev_d, next_d)
    return html_path


def render_index(conn, ages: list[str], dates: list[str]) -> str:
    entries = []
    for d in reversed(dates):
        tops, rising = {}, 0
        for age, rows in _classified(conn, d, ages).items():
            if rows:
                tops[age] = rows[0]["keyword"]
            rising += sum(1 for r in rows if r["status"] in ("NEW", "SURGE"))
        entries.append({"date": d, "tops": tops, "rising": rising})
    return report.build_index(entries, ages)


# ---------- 공통 ----------

def _classified(conn, d, ages, limit=config.TOP_N):
    """순위 변동은 500위 전체로 계산하고(예: 120위→40위는 NEW가 아니라 ▲80), 상위 limit개만 돌려줌."""
    out = {}
    for age in ages:
        today = db.get_ranks(conn, d, age)
        if today:
            out[age] = trends.classify(today, db.get_ranks(conn, _prev(d), age))[:limit]
    return out


def _attach_analyses(conn, d, by_age):
    for rows in by_age.values():
        for r in rows:
            r["analysis"] = db.get_analysis(conn, d, r["keyword"])


def _date_range(start: str, end: str) -> list[str]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s > e:
        raise SystemExit("--from 이 --to 보다 늦습니다.")
    return [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]


def _check_keys():
    if config.ANALYZER == "claude" and not config.ANTHROPIC_API_KEY:
        raise SystemExit(".env 에 ANTHROPIC_API_KEY 를 넣거나 ANALYZER=free 로 바꿔 주세요.")
    if not config.HAS_SEARCH:
        print("ℹ️  네이버 검색 API 키가 없어 '키 없이 쓰기' 모드로 실행해요.")
        print("    순위·품목·브랜드·주간 흐름은 그대로 쌓이고, 원인 근거와 팝업·행사 수집만 꺼져요.\n")


def self_test(d: str):
    """설치 직후 연결 점검: 데이터랩 수집, 네이버 검색, 쇼핑(브랜드) 검색이 되는지 확인."""
    import collector, evidence, brands as br
    ok = True
    print("1) 네이버 데이터랩 인기검색어 (20대, 20개만)")
    try:
        rows = collector.fetch_top_keywords(d, "20", top_n=20)
        print("   ✅ 성공:", ", ".join(r["keyword"] for r in rows[:5]), "…" if rows else "(결과 없음)")
        ok &= bool(rows)
    except Exception as e:
        ok = False
        print("   ❌ 실패:", e, "\n   → collector.py 안내대로 데이터랩 주소·파라미터를 확인해야 해요.")
    print(f"2) 네이버 검색 API (뉴스) · 방식: {config.NAVER_API_MODE}")
    if not config.HAS_SEARCH:
        print("   ⏸️  키가 없어 건너뜀 → '키 없이 쓰기' 모드 (순위·품목·브랜드·주간 흐름은 정상, 원인 근거·행사만 꺼짐)")
    else:
        items = evidence._search(evidence.NEWS_URL, "선크림", display=5)
        print(f"   {'✅ 성공' if items else '❌ 실패'}: 뉴스 {len(items)}건")
        ok &= bool(items)
        if not items:
            print("   → 키 값, 그리고 .env 의 NAVER_API_MODE(hub/legacy)가 키를 받은 곳과 맞는지 확인하세요.")
        if config.NAVER_API_MODE == "legacy":
            b = br.lookup("메디큐브 마스크팩")
            print(f"3) 네이버 쇼핑 검색 (브랜드 판별)\n   {'✅ 성공' if b else '⚠️ 판별 못 함'}: 메디큐브 마스크팩 → {b}")
    print("\n모두 통과! 이제 python main.py 로 실행하세요." if ok else "\n❌ 표시된 부분을 해결한 뒤 다시 python main.py --test 를 실행하세요.")


def set_keys():
    """메모장 없이 키 넣기: 검은 창에 붙여넣기만 하면 .env 에 저장하고 바로 연결 점검까지 해요."""
    import subprocess
    import sys
    env = config.BASE_DIR / ".env"
    example = config.BASE_DIR / ".env.example"
    lines = (env if env.exists() else example).read_text(encoding="utf-8").splitlines()

    print("네이버 클라우드 [인증 정보] 창에서 값을 복사해 오세요.")
    print("붙여넣기: 마우스 오른쪽 클릭 또는 Ctrl+V\n")
    cid = input("① Client ID 붙여넣고 Enter: ").strip().strip('"').strip("'")
    sec = input("② Client Secret 붙여넣고 Enter: ").strip().strip('"').strip("'")
    if not cid or not sec:
        print("\n값이 비어 있어요. 다시 python main.py --setkey 를 실행해 주세요.")
        return
    values = {"NAVER_API_MODE": "hub", "NAVER_CLIENT_ID": cid, "NAVER_CLIENT_SECRET": sec}
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen]
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n✅ 저장했어요. (이 화면은 키가 보이니 캡처해서 공유하지 마세요)\n바로 연결 점검을 할게요...\n")
    subprocess.run([sys.executable, str(config.BASE_DIR / "main.py"), "--test"])


def check(conn, d: str, ages: list[str]):
    """오늘 검색어의 품목·브랜드 분류를 엑셀로 열 수 있는 CSV로 저장 (틀린 건 config.py 에서 고치기)."""
    import csv
    import homepage
    dates = db.report_dates(conn)
    if d not in dates and dates:
        d = dates[-1]
    best = {}
    for age in ages:
        for r in db.get_ranks(conn, d, age)[: config.COLLECT_N]:
            k = r["keyword"]
            if k not in best or r["rank"] < best[k][0]:
                best[k] = (r["rank"], config.AGE_GROUPS[age])
    brand = db.get_brands(conn, best)
    brand.update({k: v for k, v in config.BRAND_OVERRIDES.items() if k in best})
    path = config.BASE_DIR / f"check_{d}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["검색어", "최고 순위", "연령", "품목", "브랜드"])
        for k, (rk, age) in sorted(best.items(), key=lambda x: x[1][0]):
            w.writerow([k, rk, age, homepage.product_category(k), brand.get(k) or ""])
    etc = [k for k in best if homepage.product_category(k) == "기타"]
    print(f"{d} 검색어 {len(best)}개 분류 결과를 저장했어요: {path}")
    print(f"품목이 '기타'인 검색어 {len(etc)}개: {', '.join(etc[:15])}{' …' if len(etc) > 15 else ''}")
    print("틀린 곳은 config.py 의 CATEGORY_OVERRIDES / BRAND_OVERRIDES 에 적고 python main.py --rebuild 하세요.")


def main():
    yesterday = (datetime.now(KST).date() - timedelta(days=1)).isoformat()
    p = argparse.ArgumentParser(description="연령별 뷰티 검색 트렌드 분석")
    p.add_argument("--date", default=yesterday, help="기준일 YYYY-MM-DD (기본: 어제)")
    p.add_argument("--from", dest="start", help="기간 시작일 (--to 와 함께)")
    p.add_argument("--to", dest="end", help="기간 종료일")
    p.add_argument("--ages", nargs="+", default=list(config.AGE_GROUPS), choices=list(config.AGE_GROUPS))
    p.add_argument("--rebuild", action="store_true", help="저장된 모든 날짜의 리포트만 다시 그리기")
    p.add_argument("--demo", action="store_true", help="가짜 데이터로 실행")
    p.add_argument("--test", action="store_true", help="설치 후 연결 점검")
    p.add_argument("--setkey", action="store_true", help="네이버 API 키를 검은 창에서 바로 넣기")
    p.add_argument("--reanalyze", action="store_true", help="이미 분석한 날짜의 이유·인사이트를 지우고 다시 분석")
    p.add_argument("--check", action="store_true", help="품목·브랜드 분류 결과를 CSV로 확인")
    args = p.parse_args()

    if args.setkey:
        return set_keys()
    if args.test:
        return self_test(args.date)
    conn = db.connect()
    ages = args.ages
    if args.check:
        return check(conn, args.date, ages)

    if args.rebuild:
        targets = db.report_dates(conn)
    else:
        if not args.demo:
            _check_keys()
        targets = _date_range(args.start, args.end or args.start) if args.start else [args.date]
        if args.reanalyze:
            for d in targets:
                conn.execute("DELETE FROM analyses WHERE date=?", (d,))
                conn.execute("DELETE FROM insights WHERE date=?", (d,))
            conn.commit()
            print("이유·인사이트를 지우고 다시 분석해요 (순위 기록은 그대로).")
        for d in targets:
            print(f"[{d}] {', '.join(config.AGE_GROUPS[a] for a in ages)}")
            collect_and_analyze(conn, d, ages, args.demo)
            print(f"  팝업·행사: {events.collect(conn, d, args.demo)}건 확인")
            print(f"  브랜드 판별: 새 검색어 {brands.update(conn, d, ages, args.demo)}개")

    dates = db.report_dates(conn)
    # 새 날짜가 생기면 바로 앞 날짜의 '다음날' 링크도 갱신해야 하므로 함께 다시 그림
    to_render = set(targets)
    for d in targets:
        if d in dates and dates.index(d) > 0:
            to_render.add(dates[dates.index(d) - 1])
    for d in sorted(to_render):
        if render(conn, d, ages, dates):
            print(f"  리포트 {d}.html")
    index = render_index(conn, ages, dates)
    home = homepage.build_site(conn, ages, demo=args.demo)
    print(f"\n홈페이지: {home}")
    print(f"날짜별 리포트 목록: {index}  (저장된 날짜 {len(dates)}일)")


if __name__ == "__main__":
    main()
