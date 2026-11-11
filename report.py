"""날짜별 결과를 JSON과 HTML 리포트로 저장합니다.

디자인 콘셉트: '립 컬러 스와치'
- 연령대 6개를 한 립 라인의 6가지 셰이드(누드 → 딥 베리)로 표현해, 상단 스와치를 눌러 연령을 고릅니다.
- 원인 분류마다 고유한 색 칩을 줘서, 순위표와 원인 분포 막대에서 같은 색으로 읽히게 했습니다.
"""
import json
from collections import Counter
from datetime import date
from html import escape

import config

# 연령 셰이드: 밝은 누드 → 딥 베리 (글자색은 대비를 위해 셰이드별로 지정)
AGE_SHADES = {
    "10": ("#F4C7D0", "#4A1E2B"),
    "20": ("#EA98AC", "#4A1E2B"),
    "30": ("#D86784", "#FFFFFF"),
    "40": ("#B9445F", "#FFFFFF"),
    "50": ("#8F2F49", "#FFFFFF"),
    "60": ("#5E1E31", "#FFFFFF"),
}

CATEGORY_COLORS = {
    "셀럽/광고": "#D9577A",
    "시즌/날씨": "#5B8DB8",
    "할인/행사": "#D9A13B",
    "성분/기술 트렌드": "#4F9A78",
    "SNS 바이럴": "#8A5CC2",
    "신제품 출시": "#2E9AA0",
    "스테디셀러": "#A08C7A",
    "원인 불명확": "#B3ADB6",
}

WEEKDAYS = "월화수목금토일"


def build(d: str, by_age: dict, insights: dict, common: list[dict],
          prev_d: str | None = None, next_d: str | None = None) -> tuple[str, str]:
    config.REPORT_DIR.mkdir(exist_ok=True)
    json_path = config.REPORT_DIR / f"{d}.json"
    html_path = config.REPORT_DIR / f"{d}.html"

    payload = {
        "date": d,
        "common_keywords": common,
        "ages": {
            config.AGE_GROUPS[age]: {"insights": insights.get(age, []), "keywords": rows}
            for age, rows in by_age.items()
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_page(d, by_age, insights, common, prev_d, next_d), encoding="utf-8")
    return str(json_path), str(html_path)


# ---------- 조각들 ----------

def _is_rising(r) -> bool:
    return r["status"] in ("NEW", "SURGE")


def _change(r) -> str:
    s, c = r["status"], abs(r["change"] or 0)
    if s == "NEW":
        return '<span class="chg new">NEW</span>'
    if s in ("SURGE", "UP"):
        return f'<span class="chg up{" surge" if s == "SURGE" else ""}" title="전일 {r["prev_rank"]}위">▲{c}</span>'
    if s == "DOWN":
        return f'<span class="chg down" title="전일 {r["prev_rank"]}위">▼{c}</span>'
    return '<span class="chg same" title="전일과 같은 순위">–</span>'


def _cat_chip(cat: str) -> str:
    color = CATEGORY_COLORS.get(cat, "#B3ADB6")
    return f'<span class="cat"><i style="background:{color}"></i>{escape(cat)}</span>'


def _swatch(age: str, rows: list[dict], first: bool) -> str:
    bg, fg = AGE_SHADES[age]
    top = rows[0]["keyword"] if rows else "-"
    rising = sum(1 for r in rows if _is_rising(r))
    return (
        f'<button class="sw" role="tab" aria-selected="{str(first).lower()}" data-age="{age}" '
        f'style="--sw:{bg};--swfg:{fg}">'
        f'<span class="sw-age">{config.AGE_GROUPS[age]}</span>'
        f'<span class="sw-top">{escape(top)}</span>'
        f'<span class="sw-meta">새로 뜬 {rising}개</span></button>'
    )


def _distribution(rows: list[dict]) -> str:
    counts = Counter(r["analysis"]["category"] for r in rows)
    total = sum(counts.values()) or 1
    order = [c for c in CATEGORY_COLORS if counts.get(c)]
    bar = "".join(
        f'<span style="flex:{counts[c]};background:{CATEGORY_COLORS[c]}" title="{escape(c)} {counts[c]}개"></span>'
        for c in order
    )
    legend = "".join(
        f'<li><i style="background:{CATEGORY_COLORS[c]}"></i>{escape(c)}<b>{round(counts[c] * 100 / total)}%</b></li>'
        for c in order
    )
    return f'<div class="dist"><div class="bar">{bar}</div><ul class="legend">{legend}</ul></div>'


def _row(r: dict) -> str:
    a = r["analysis"]
    srcs = "".join(
        f'<a href="{escape(s.get("link") or "#")}" target="_blank" rel="noopener">{escape(_short(s.get("title", "출처"), 28))}</a>'
        for s in a.get("sources", [])
    )
    note = '<span class="note">지난 분석 유지</span>' if a.get("reused") else ""
    low = " low" if a.get("confidence") == "low" else ""
    top = " top" if r["rank"] <= 3 else ""
    return (
        f'<li class="row{top}" data-rising="{int(_is_rising(r))}">'
        f'<span class="rk">{r["rank"]}</span>'
        f'<div class="kwcol"><span class="kw">{escape(r["keyword"])}</span>{_change(r)}</div>'
        f'<div class="why">{_cat_chip(a["category"])}'
        f'<p class="reason{low}">{escape(a["reason"])}</p>'
        f'{("<div class=src>" + srcs + "</div>") if srcs else ""}{note}</div></li>'
    )


def _panel(age: str, rows: list[dict], ins: list[str], first: bool) -> str:
    bg, _ = AGE_SHADES[age]
    ins_html = "".join(f"<li>{escape(x)}</li>" for x in ins) or "<li>오늘은 인사이트를 만들지 못했습니다.</li>"
    rising = sum(1 for r in rows if _is_rising(r))
    return f"""
<section class="panel" role="tabpanel" data-age="{age}" style="--shade:{bg}"{"" if first else " hidden"}>
  <div class="summary">
    <div class="ins">
      <h2>{config.AGE_GROUPS[age]} {config.GENDER_LABEL}은 오늘 이걸 찾았어요</h2>
      <ul>{ins_html}</ul>
    </div>
    <div class="mix">
      <h3>검색이 늘어난 이유</h3>
      {_distribution(rows)}
    </div>
  </div>
  <div class="listhead">
    <h3>인기 검색어 1–{len(rows)}위</h3>
    <div class="filter" role="group" aria-label="보기">
      <button aria-pressed="true" data-f="all">전체</button>
      <button aria-pressed="false" data-f="rising">새로 뜬 키워드 {rising}</button>
    </div>
  </div>
  <ol class="rank">{"".join(_row(r) for r in rows)}</ol>
  <p class="empty" hidden>오늘은 새로 진입했거나 급상승한 키워드가 없습니다.</p>
</section>"""


def _common(common: list[dict], ages: list[str]) -> str:
    if not common:
        return ""
    items = []
    for c in common:
        dots = "".join(
            f'<i style="background:{AGE_SHADES[a][0] if a in c.get("ages", []) else "transparent"}" '
            f'title="{config.AGE_GROUPS[a]}"></i>'
            for a in ages
        )
        items.append(f'<li><span>{escape(c["keyword"])}</span><span class="dots">{dots}</span></li>')
    return f"""
<section class="common">
  <h3>세대를 가리지 않고 찾은 키워드</h3>
  <p class="sub">{config.COMMON_MIN_AGES}개 이상 연령대의 50위 안에 동시에 오른 키워드예요. 점은 10대부터 60대 이상 순서입니다.</p>
  <ul>{"".join(items)}</ul>
</section>"""


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _date_label(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {WEEKDAYS[dt.weekday()]}요일"


# ---------- 페이지 ----------

def _datenav(prev_d, next_d) -> str:
    prev = (f'<a class="dn" href="{prev_d}.html" rel="prev">‹ {_short_date(prev_d)}</a>'
            if prev_d else '<span class="dn off">‹ 이전 없음</span>')
    nxt = (f'<a class="dn" href="{next_d}.html" rel="next">{_short_date(next_d)} ›</a>'
           if next_d else '<span class="dn off">최신</span>')
    return f'<nav class="datenav" aria-label="날짜 이동">{prev}<a class="dn all" href="index.html">날짜 목록</a>{nxt}</nav>'


def _short_date(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.month}/{dt.day} ({WEEKDAYS[dt.weekday()]})"


def _page(d, by_age, insights, common, prev_d=None, next_d=None):
    ages = list(by_age.keys())
    swatches = "".join(_swatch(a, by_age[a], i == 0) for i, a in enumerate(ages))
    panels = "".join(_panel(a, by_age[a], insights.get(a, []), i == 0) for i, a in enumerate(ages))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{_date_label(d)} 뷰티 검색 트렌드</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style></head>
<body>
<main class="wrap">
  {_datenav(prev_d, next_d)}
  <header class="head">
    <p class="date">{_date_label(d)}</p>
    <h1>{config.GENDER_LABEL + " " if config.GENDER_LABEL else ""}연령별 뷰티 검색 트렌드</h1>
    <p class="src-note">네이버 쇼핑 화장품/미용 인기 검색어를 {config.GENDER_LABEL + " " if config.GENDER_LABEL else ""}연령대별로 모으고, 최근 뉴스와 블로그를 근거로 이유를 정리했어요.</p>
  </header>
  <nav class="swatches" role="tablist" aria-label="연령대 선택">{swatches}</nav>
  {panels}
  {_common(common, ages)}
  <footer>순위는 네이버 로그인 사용자 기준 상대 지표입니다. 이유는 AI가 수집된 기사·글만 근거로 작성했으며, 흐린 글씨는 근거가 약한 분석입니다.</footer>
</main>
<script>{JS}</script>
</body></html>"""


CSS = """
:root{
  --bg:#F5F3F7; --paper:#FFFFFF; --ink:#2B1F2E; --soft:#6F6474; --line:#E5DEE9;
  --up:#C23A62; --down:#4E78A6; --new:#FFFFFF; --newbg:#2B1F2E; --focus:#8A5CC2;
  --font:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark; --bg:#171219; --paper:#211A24; --ink:#F1EAF3; --soft:#A79CAC; --line:#372D3B;
  --up:#F07D9C; --down:#8FB4DD; --new:#171219; --newbg:#F1EAF3; --focus:#B996E8;
}}
:root[data-theme="dark"]{color-scheme:dark; --bg:#171219; --paper:#211A24; --ink:#F1EAF3; --soft:#A79CAC;
  --line:#372D3B; --up:#F07D9C; --down:#8FB4DD; --new:#171219; --newbg:#F1EAF3; --focus:#B996E8;}
:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*,*::before,*::after{box-sizing:inherit}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:15px;line-height:1.6;
  -webkit-font-smoothing:antialiased;word-break:keep-all}
button{font:inherit;color:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--focus);outline-offset:3px;border-radius:6px}
.wrap{max-width:1080px;margin:0 auto;padding:40px 20px 64px}
h1,h2,h3{margin:0;letter-spacing:-.02em}

/* 날짜 이동 */
.datenav{display:flex;gap:8px;align-items:center;margin-bottom:28px;flex-wrap:wrap}
.dn{font-size:13px;font-weight:600;color:var(--ink);text-decoration:none;padding:6px 12px;
  border:1px solid var(--line);border-radius:999px;background:var(--paper)}
a.dn:hover{border-color:var(--soft)}
.dn.all{margin:0 auto}
.dn.off{color:var(--soft);background:transparent}

/* 헤더 */
.date{margin:0 0 6px;color:var(--soft);font-weight:500}
h1{font-size:clamp(28px,4.2vw,40px);font-weight:800;line-height:1.2}
.src-note{margin:10px 0 0;color:var(--soft);max-width:56ch}

/* 스와치: 페이지의 주인공 */
.swatches{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin:32px 0 36px;
  border-radius:0 0 20px 20px;overflow:hidden}
.sw{position:relative;display:flex;flex-direction:column;justify-content:flex-end;gap:2px;text-align:left;
  min-height:168px;padding:16px 14px;border:0;border-radius:16px 16px 0 0;background:var(--sw);color:var(--swfg);
  transition:flex-grow .25s ease, min-height .25s ease}
.sw-age{font-weight:700;font-size:14px;opacity:.85}
.sw-top{font-weight:800;font-size:clamp(16px,1.9vw,22px);line-height:1.25;letter-spacing:-.03em}
.sw-meta{font-size:12px;opacity:.8}
.sw[aria-selected="true"]{min-height:196px}
.sw[aria-selected="true"]::after{content:"";position:absolute;left:14px;right:14px;top:14px;height:3px;
  border-radius:3px;background:currentColor;opacity:.9}
.sw:hover .sw-top{text-decoration:underline;text-underline-offset:4px}
.swatches{align-items:end}

/* 요약 */
.summary{display:grid;grid-template-columns:1.35fr 1fr;gap:28px;padding:28px;background:var(--paper);
  border-radius:16px;border-top:6px solid var(--shade)}
.ins h2{font-size:22px;font-weight:800;margin-bottom:12px}
.ins ul{margin:0;padding:0;list-style:none;display:grid;gap:10px}
.ins li{padding-left:18px;position:relative}
.ins li::before{content:"";position:absolute;left:0;top:.62em;width:8px;height:8px;border-radius:50%;background:var(--shade)}
.mix h3,.listhead h3,.common h3{font-size:15px;font-weight:700;margin-bottom:12px}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;gap:2px;background:var(--line)}
.legend{list-style:none;margin:14px 0 0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;font-size:13px}
.legend li{display:flex;align-items:center;gap:8px}
.legend i,.cat i{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none}
.legend b{margin-left:auto;font-weight:600;color:var(--soft);font-variant-numeric:tabular-nums}

/* 순위 리스트 */
.listhead{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:36px 0 8px;flex-wrap:wrap}
.listhead h3{margin:0}
.filter{display:flex;background:var(--paper);border:1px solid var(--line);border-radius:999px;padding:3px}
.filter button{border:0;background:transparent;padding:6px 14px;border-radius:999px;font-size:13px;font-weight:600;color:var(--soft)}
.filter button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.rank{list-style:none;margin:0;padding:0}
.row{display:grid;grid-template-columns:44px minmax(150px,220px) 1fr;gap:16px;align-items:start;
  padding:16px 4px;border-bottom:1px solid var(--line)}
.rk{font-weight:800;font-size:17px;font-variant-numeric:tabular-nums;color:var(--soft);padding-top:1px}
.kwcol{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.kw{font-weight:700;font-size:16px;letter-spacing:-.02em}
.row.top .rk{color:var(--ink)}
.row.top .kw{font-size:19px;font-weight:800}
.chg{font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.chg.up{color:var(--up)} .chg.down{color:var(--down)} .chg.same{color:var(--soft)}
.chg.new{background:var(--newbg);color:var(--new);padding:1px 7px;border-radius:999px;font-size:11px}
.chg.surge{background:color-mix(in srgb,var(--up) 14%,transparent);padding:1px 7px;border-radius:999px}
.cat{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--soft)}
.reason{margin:4px 0 0;max-width:62ch}
.reason.low{color:var(--soft)}
.src{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.src a{font-size:12px;color:var(--ink);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:2px 10px;background:var(--paper)}
.src a:hover{border-color:var(--soft)}
.note{display:inline-block;margin-top:6px;font-size:12px;color:var(--soft)}
.empty{color:var(--soft);padding:24px 4px}

/* 공통 키워드 */
.common{margin-top:56px;padding-top:28px;border-top:2px solid var(--ink)}
.common .sub{margin:-6px 0 16px;color:var(--soft);font-size:13px}
.common ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:4px 28px}
.common li{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-weight:600}
.dots{display:flex;gap:4px}
.dots i{width:9px;height:9px;border-radius:50%;border:1px solid var(--line)}
footer{margin-top:48px;color:var(--soft);font-size:12px;max-width:70ch}

@media (max-width:760px){
  .wrap{padding:28px 16px 48px}
  .swatches{grid-template-columns:repeat(3,1fr);border-radius:16px}
  .sw{border-radius:0}
  .sw,.sw[aria-selected="true"]{min-height:112px}
  .summary{grid-template-columns:1fr;padding:20px}
  .row{grid-template-columns:36px 1fr;gap:4px 12px}
  .why{grid-column:2}
}
@media (prefers-reduced-motion:reduce){.sw{transition:none}}
"""

JS = """
document.addEventListener('keydown',e=>{
  if(e.target.closest('.sw,input,textarea')||e.altKey||e.metaKey||e.ctrlKey) return;
  const a=document.querySelector(e.key==='ArrowLeft'?'a[rel=prev]':e.key==='ArrowRight'?'a[rel=next]':null);
  if(a) location.href=a.href;
});
const sws=[...document.querySelectorAll('.sw')], panels=[...document.querySelectorAll('.panel')];
function show(age, focus){
  sws.forEach(s=>{const on=s.dataset.age===age; s.setAttribute('aria-selected',on); s.tabIndex=on?0:-1; if(on&&focus) s.focus();});
  panels.forEach(p=>p.hidden=p.dataset.age!==age);
}
sws.forEach((s,i)=>{
  s.addEventListener('click',()=>show(s.dataset.age));
  s.addEventListener('keydown',e=>{
    const d={ArrowRight:1,ArrowLeft:-1}[e.key]; if(!d) return;
    e.preventDefault(); show(sws[(i+d+sws.length)%sws.length].dataset.age,true);
  });
  s.tabIndex=s.getAttribute('aria-selected')==='true'?0:-1;
});
panels.forEach(p=>{
  const btns=p.querySelectorAll('.filter button'), rows=p.querySelectorAll('.row'), empty=p.querySelector('.empty');
  btns.forEach(b=>b.addEventListener('click',()=>{
    btns.forEach(x=>x.setAttribute('aria-pressed',x===b));
    const only=b.dataset.f==='rising'; let n=0;
    rows.forEach(r=>{const v=!only||r.dataset.rising==='1'; r.hidden=!v; if(v) n++;});
    empty.hidden=n>0;
  }));
});
"""


def build_index(entries: list[dict], ages: list[str]) -> str:
    """entries: [{"date", "tops": {age: keyword}, "rising": int}] (최신순)."""
    config.REPORT_DIR.mkdir(exist_ok=True)
    path = config.REPORT_DIR / "index.html"

    legend = "".join(
        f'<li><i style="background:{AGE_SHADES[a][0]}"></i>{config.AGE_GROUPS[a]}</li>' for a in ages
    )
    months: dict[str, list[str]] = {}
    for e in entries:
        dt = date.fromisoformat(e["date"])
        bars = "".join(
            f'<span class="mini" style="background:{AGE_SHADES[a][0]};color:{AGE_SHADES[a][1]}" '
            f'title="{config.AGE_GROUPS[a]} 1위">{escape(e["tops"].get(a, "-"))}</span>'
            for a in ages
        )
        months.setdefault(f"{dt.year}년 {dt.month}월", []).append(
            f'<li><a class="day" href="{e["date"]}.html">'
            f'<span class="d"><b>{dt.day}일</b> {WEEKDAYS[dt.weekday()]}요일'
            f'<em>새로 뜬 키워드 전 연령 합계 {e["rising"]}개</em></span>'
            f'<span class="minis">{bars}</span></a></li>'
        )
    body = "".join(
        f'<section><h2>{m}</h2><ul class="days">{"".join(items)}</ul></section>' for m, items in months.items()
    ) or '<p class="empty">아직 저장된 리포트가 없습니다. python main.py 를 실행하면 첫 리포트가 생깁니다.</p>'

    latest = (f'<a class="latest" href="{entries[0]["date"]}.html">최신 리포트 보기 ({_short_date(entries[0]["date"])})</a>'
              if entries else "")

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>뷰티 검색 트렌드 날짜 목록</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}{INDEX_CSS}</style></head>
<body><main class="wrap">
  <header class="head">
    <h1>{config.GENDER_LABEL + " " if config.GENDER_LABEL else ""}뷰티 검색 트렌드 기록</h1>
    <p class="src-note">날짜를 누르면 그날의 연령별 1~50위와 이유를 볼 수 있어요. 색 막대는 각 연령대의 그날 1위 키워드입니다.</p>
    {latest}
  </header>
  <ul class="agelegend">{legend}</ul>
  {body}
</main></body></html>"""
    path.write_text(html, encoding="utf-8")
    return str(path)


INDEX_CSS = """
.latest{display:inline-block;margin-top:18px;font-weight:700;color:var(--bg);background:var(--ink);
  text-decoration:none;padding:10px 18px;border-radius:999px}
.agelegend{list-style:none;padding:0;margin:28px 0 8px;display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--soft)}
.agelegend li{display:flex;align-items:center;gap:6px}
.agelegend i{width:12px;height:12px;border-radius:4px}
section h2{font-size:18px;font-weight:800;margin:32px 0 8px}
.days{list-style:none;margin:0;padding:0}
.day{display:grid;grid-template-columns:150px 1fr;gap:16px;align-items:center;padding:12px 4px;
  border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none}
.day:hover .d b{text-decoration:underline;text-underline-offset:4px}
.d{display:flex;flex-direction:column;font-size:13px;color:var(--soft)}
.d b{font-size:17px;color:var(--ink);font-weight:800}
.d em{font-style:normal;font-size:12px}
.minis{display:grid;grid-template-columns:repeat(6,1fr);border-radius:10px;overflow:hidden}
.mini{font-size:12px;font-weight:700;padding:8px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media (max-width:760px){
  .day{grid-template-columns:1fr;gap:8px}
  .minis{grid-template-columns:repeat(3,1fr)}
}
"""
