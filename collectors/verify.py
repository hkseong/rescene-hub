"""Strict publication rule for LLM-extracted facts. The LLM proposes; this code decides.

An item is published only if it has
  - at least one official source, or
  - at least two different publishers,
where a source counts only if Claude actually saw it: an article id from our own
news fetch, or a URL that appeared in Claude's web search results.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .common import domain

OFFICIAL_URL_PATTERNS = [
    r"(^|\.)melon\.com/",
    r"(x|twitter)\.com/RESCENE_official",
    r"instagram\.com/rescene_official",
    r"youtube\.com/@RESCENE",
    r"themuse",
]

# 팬 커뮤니티는 실마리로만 쓰고 출처 개수에는 넣지 않는다
COMMUNITY_DOMAINS = {"dcinside.com", "theqoo.net", "instiz.net", "fmkorea.com", "namu.wiki", "ruliweb.com",
                     "inven.co.kr", "clien.net", "ppomppu.co.kr"}

UPCOMING_TYPES = {"broadcast", "event", "popup", "collab", "goods", "vote", "release", "ad"}
# 종료일 없이 시작일만 알려진 진행형 소식(콜라보 제품 출시, 광고 등)은 30일간 유효
ONGOING_TYPES = {"popup", "collab", "goods", "ad"}
HISTORY_START = date(2024, 1, 1)  # 데뷔 전 프리데뷔 활동까지


def is_official(url: str) -> bool:
    return any(re.search(p, url, flags=re.I) for p in OFFICIAL_URL_PATTERNS)


def resolve_sources(raw: list[str], articles: dict, seen_urls: set[str]) -> list[dict]:
    out, keys = [], set()
    for s in raw:
        s = s.strip()
        if s in articles:
            a = articles[s]
            src = {"ref": s, "url": a["link"], "publisher": a["publisher"] or a["publisher_domain"],
                   "key": a["publisher_domain"] or a["publisher"], "official": False}
        elif s.startswith("http") and _seen(s, seen_urls):
            if domain(s) in COMMUNITY_DOMAINS:
                continue
            src = {"ref": s, "url": s, "publisher": domain(s), "key": domain(s), "official": is_official(s)}
        else:
            continue  # 모델이 지어낸 출처는 버린다
        if src["url"] in keys:
            continue
        keys.add(src["url"])
        out.append(src)
    return out


def _seen(url: str, seen_urls: set[str]) -> bool:
    u = url.rstrip("/")
    return any(u == x.rstrip("/") for x in seen_urls)


def check_date(item: dict, today: date, history: bool = False) -> str | None:
    """history=True(지난 이력 수집)면 과거 날짜를 허용하고 형식과 범위만 본다."""
    try:
        d = date.fromisoformat(item["date"])
        end = date.fromisoformat(item["end_date"]) if item.get("end_date") else d
    except (TypeError, ValueError):
        return "날짜 형식 오류"
    if end < d:
        return "종료일이 시작일보다 빠름"
    if history:
        if d < HISTORY_START or d > today + timedelta(days=400):
            return "이력 범위 밖 날짜"
        return _time_error(item)
    if abs((d - today).days) > 400:
        return "날짜가 1년 이상 차이남"
    if item["type"] in ONGOING_TYPES and not item.get("end_date"):
        if d < today - timedelta(days=30):
            return "30일 이상 지난 소식"
    elif item["type"] in UPCOMING_TYPES and end < today - timedelta(days=1):
        return "이미 지난 일정"
    if item["type"] == "award" and not (today - timedelta(days=60) <= d <= today):
        return "수상일이 최근 60일 밖"
    return _time_error(item)


def _time_error(item: dict) -> str | None:
    if item.get("time") and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", item["time"]):
        return "시간 형식 오류"
    return None


def verify(item: dict, articles: dict, seen_urls: set[str], today: date,
           history: bool = False) -> tuple[bool, list[dict], str]:
    sources = resolve_sources(item.get("sources", []), articles, seen_urls)
    bad_date = check_date(item, today, history)
    if bad_date:
        return False, sources, bad_date
    if any(s["official"] for s in sources):
        return True, sources, "공식 출처"
    publishers = {s["key"] for s in sources if s["key"]}
    if len(publishers) >= 2:
        return True, sources, f"독립 출처 {len(publishers)}곳"
    return False, sources, f"출처 부족 ({len(publishers)}곳)"
