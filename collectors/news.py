"""Google News RSS search (no API key)."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from . import config, llm
from .common import KST, CollectorError, domain, http_get, iso, load, norm_title, now, save

RSS = "https://news.google.com/rss/search?q={}+when:7d&hl=ko&gl=KR&ceid=KR:ko"


def article_id(link: str) -> str:
    return "N" + hashlib.sha1(link.encode()).hexdigest()[:8]


def parse_rss(xml_bytes: bytes) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise CollectorError(f"뉴스 RSS 파싱 실패: {e}")
    out = []
    for it in root.findall(".//item"):
        src = it.find("source")
        title = it.findtext("title") or ""
        publisher = src.text if src is not None else ""
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3]
        link = it.findtext("link") or ""
        out.append({
            "id": article_id(link),
            "title": title.strip(),
            "link": link,
            "publisher": publisher,
            "publisher_domain": domain(src.get("url", "")) if src is not None else "",
            "published_at": iso(parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)),
        })
    return out


def is_relevant(a: dict) -> bool:
    return any(n.lower() in a["title"].lower() for n in config.ARTIST_NAMES)


def collect_news() -> list[dict]:
    """Updates news.json; returns articles that are new since the last run."""
    data = load("news.json", {"articles": []})
    known = {a["id"]: a for a in data["articles"]}
    titles = {norm_title(a["title"]) for a in known.values()}
    new = []
    for q in config.NEWS_QUERIES:
        for a in parse_rss(http_get(RSS.format(quote(q))).content):
            if a["id"] in known or not is_relevant(a):
                continue
            key = norm_title(a["title"])
            known[a["id"]] = a
            if key in titles:
                a["dup"] = True  # 같은 제목 재전송은 출처 집계에 쓰되 목록엔 숨김
            titles.add(key)
            new.append(a)
    cutoff = iso(now() - timedelta(days=14))
    data["articles"] = sorted((a for a in known.values() if a["published_at"] >= cutoff),
                              key=lambda a: a["published_at"], reverse=True)
    if not data["articles"]:
        raise CollectorError("뉴스 RSS에서 리센느 기사를 하나도 찾지 못했습니다")
    data["updated"] = iso()
    save("news.json", data)
    return new


STORY_WINDOW_HOURS = 72
STORY_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
    "required": ["groups"],
    "additionalProperties": False,
}
STORY_SYSTEM = """리센느 관련 뉴스 제목 목록을 같은 사건·소식끼리 묶어라.
- 같은 발표·행사·기록을 다룬 기사는 언론사나 표현이 달라도 한 묶음이다 (예: 디즈니 콜라보 발탁 기사 여러 건).
- 주제만 비슷하고 사건이 다르면 나눈다 (예: 음원차트 1위 기사와 음악방송 1위 기사).
- 혼자인 기사는 1개짜리 묶음으로. 모든 id가 정확히 한 번씩 나와야 한다."""


def cluster_stories() -> None:
    """최근 72시간 기사를 같은 소식끼리 묶어 story(대표 기사 id)를 붙인다. 화면에선 묶음당 한 줄."""
    data = load("news.json", {"articles": []})
    since = iso(now() - timedelta(hours=STORY_WINDOW_HOURS))
    recent = [a for a in data["articles"] if not a.get("dup") and a["published_at"] >= since][:200]
    if len(recent) < 2:
        return
    lines = "\n".join(f"{a['id']} | {a['title']}" for a in recent)
    out, _ = llm.ask_json(model=config.MODEL_CLASSIFY, system=STORY_SYSTEM, content=lines,
                          schema=STORY_SCHEMA, purpose="news_stories", effort="low", max_tokens=8000)
    apply_stories(recent, out["groups"])
    save("news.json", data)


def apply_stories(recent: list[dict], groups: list[list[str]]) -> None:
    by_id = {a["id"]: a for a in recent}
    for a in recent:
        a.pop("story", None)
    for g in groups:
        members = [by_id[i] for i in dict.fromkeys(g) if i in by_id and "story" not in by_id[i]]
        if not members:
            continue
        head = max(members, key=lambda a: a["published_at"])["id"]  # 최신 기사가 대표
        for a in members:
            a["story"] = head
    for a in recent:
        a.setdefault("story", a["id"])  # 모델이 빠뜨린 기사는 단독으로
