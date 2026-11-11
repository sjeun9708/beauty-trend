"""SQLite 저장소. 순위, 키워드 분석, 연령별 인사이트를 날짜별로 보관합니다."""
import json
import sqlite3
from datetime import date, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranks (
    date TEXT, age TEXT, rank INTEGER, keyword TEXT,
    PRIMARY KEY (date, age, rank)
);
CREATE TABLE IF NOT EXISTS analyses (
    date TEXT, keyword TEXT, category TEXT, reason TEXT,
    confidence TEXT, sources TEXT, reused INTEGER DEFAULT 0,
    PRIMARY KEY (date, keyword)
);
CREATE TABLE IF NOT EXISTS events (
    key TEXT PRIMARY KEY, name TEXT, brand TEXT, place TEXT, area TEXT,
    start TEXT, end TEXT, booking TEXT, summary TEXT,
    source_title TEXT, source_link TEXT, first_seen TEXT
);
CREATE TABLE IF NOT EXISTS brands (
    keyword TEXT PRIMARY KEY, brand TEXT, checked TEXT
);
CREATE TABLE IF NOT EXISTS insights (
    date TEXT, age TEXT, content TEXT,
    PRIMARY KEY (date, age)
);
"""


def connect(path=config.DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def has_ranks(conn, d: str, age: str) -> bool:
    row = conn.execute("SELECT 1 FROM ranks WHERE date=? AND age=? LIMIT 1", (d, age)).fetchone()
    return row is not None


def save_ranks(conn, d: str, age: str, rows: list[dict]):
    conn.executemany(
        "INSERT OR REPLACE INTO ranks (date, age, rank, keyword) VALUES (?,?,?,?)",
        [(d, age, r["rank"], r["keyword"]) for r in rows],
    )
    conn.commit()


def get_ranks(conn, d: str, age: str) -> list[dict]:
    cur = conn.execute("SELECT rank, keyword FROM ranks WHERE date=? AND age=? ORDER BY rank", (d, age))
    return [dict(r) for r in cur.fetchall()]


def get_analysis(conn, d: str, keyword: str):
    row = conn.execute("SELECT * FROM analyses WHERE date=? AND keyword=?", (d, keyword)).fetchone()
    return _row_to_analysis(row)


def get_recent_analysis(conn, keyword: str, before: str, days: int):
    start = (date.fromisoformat(before) - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT * FROM analyses WHERE keyword=? AND date>=? AND date<? AND reused=0 "
        "ORDER BY date DESC LIMIT 1",
        (keyword, start, before),
    ).fetchone()
    return _row_to_analysis(row)


def save_analysis(conn, d: str, keyword: str, a: dict, reused: bool = False):
    conn.execute(
        "INSERT OR REPLACE INTO analyses (date, keyword, category, reason, confidence, sources, reused) "
        "VALUES (?,?,?,?,?,?,?)",
        (d, keyword, a["category"], a["reason"], a.get("confidence", "low"),
         json.dumps(a.get("sources", []), ensure_ascii=False), int(reused)),
    )
    conn.commit()


def save_insights(conn, d: str, age: str, items: list[str]):
    conn.execute("INSERT OR REPLACE INTO insights (date, age, content) VALUES (?,?,?)",
                 (d, age, json.dumps(items, ensure_ascii=False)))
    conn.commit()


def get_insights(conn, d: str, age: str) -> list[str]:
    row = conn.execute("SELECT content FROM insights WHERE date=? AND age=?", (d, age)).fetchone()
    return json.loads(row["content"]) if row else []


def _row_to_analysis(row):
    if row is None:
        return None
    a = dict(row)
    a["sources"] = json.loads(a["sources"] or "[]")
    a["reused"] = bool(a["reused"])
    return a


def report_dates(conn) -> list[str]:
    """분석까지 끝난(리포트를 만들 수 있는) 날짜 목록, 오래된 순."""
    cur = conn.execute("SELECT DISTINCT date FROM insights ORDER BY date")
    return [r["date"] for r in cur.fetchall()]


def save_event(conn, e: dict, seen: str):
    """같은 브랜드·장소·시작일이면 한 행사로 보고 최신 정보로 덮어씁니다."""
    key = f"{e.get('brand','')}|{e.get('place','')}|{e['start']}"
    old = conn.execute("SELECT first_seen FROM events WHERE key=?", (key,)).fetchone()
    conn.execute(
        "INSERT OR REPLACE INTO events (key,name,brand,place,area,start,end,booking,summary,source_title,source_link,first_seen) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (key, e["name"], e.get("brand"), e.get("place"), e.get("area"), e["start"], e.get("end"),
         e.get("booking"), e.get("summary"), e.get("source_title"), e.get("source_link"),
         old["first_seen"] if old else seen),
    )
    conn.commit()


def get_events(conn, start: str, end: str) -> list[dict]:
    """start~end 기간과 하루라도 겹치는 행사."""
    cur = conn.execute(
        "SELECT * FROM events WHERE start <= ? AND (end IS NULL OR end >= ?) ORDER BY start",
        (end, start),
    )
    return [dict(r) for r in cur.fetchall()]


def get_brands(conn, keywords) -> dict:
    """판별해 둔 검색어 → 브랜드 (브랜드 없음으로 판별된 것은 None)."""
    out = {}
    kws = list(keywords)
    for i in range(0, len(kws), 500):
        part = kws[i:i + 500]
        cur = conn.execute(f"SELECT keyword, brand FROM brands WHERE keyword IN ({','.join('?' * len(part))})", part)
        out.update({r["keyword"]: r["brand"] for r in cur.fetchall()})
    return out


def save_brand(conn, keyword: str, brand, checked: str):
    conn.execute("INSERT OR REPLACE INTO brands (keyword, brand, checked) VALUES (?,?,?)", (keyword, brand, checked))
    conn.commit()
