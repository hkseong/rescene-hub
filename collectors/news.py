"""Google News RSS search (no API key)."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from . import config
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
