"""Schedules, pop-ups, collabs, goods, music-show wins, votes — extracted by Claude, published by verify.py."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from . import config, llm, news
from .common import iso, load, norm_title, now, parse_iso, save, today
from .verify import verify

TYPES = ["broadcast", "event", "popup", "collab", "goods", "award", "vote", "release"]
TYPE_LABEL = {
    "broadcast": "방송 출연", "event": "행사", "popup": "팝업", "collab": "콜라보", "goods": "굿즈",
    "award": "1위·수상", "vote": "투표", "release": "발매",
}
ALERT_CAT = {"popup": "popup", "collab": "popup", "goods": "popup", "award": "award", "vote": "vote",
             "broadcast": "broadcast", "event": "broadcast", "release": "broadcast"}
PENDING_DAYS = 7

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "same_as": {"type": ["string", "null"]},
                    "type": {"type": "string", "enum": TYPES},
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "end_date": {"type": ["string", "null"]},
                    "time": {"type": ["string", "null"]},
                    "place": {"type": ["string", "null"]},
                    "members": {"type": "array", "items": {"type": "string", "enum": list(config.MEMBERS)}},
                    "summary": {"type": "string"},
                    "link": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["same_as", "type", "title", "date", "end_date", "time", "place", "members",
                             "summary", "link", "sources"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

SYSTEM = """너는 걸그룹 리센느(RESCENE; 멤버 원이, 리브, 미나미, 메이, 제나, 소속사 더뮤즈엔터테인먼트) 팬 사이트의 일정 수집기다.
주어진 뉴스 목록과 웹검색으로 리센느 관련 '날짜가 있는 사실'만 뽑는다.

type:
- broadcast: 음악방송·예능·라디오 등 방송 출연 (방송일)
- event: 팬사인회·공연·페스티벌·시상식 참석·쇼케이스 등 오프라인 행사
- popup: 팝업스토어 (date=시작일, end_date=종료일)
- collab: 브랜드 협업·광고 캠페인·제품 출시 (date=출시/시작일)
- goods: 굿즈·앨범 MD 판매 (date=판매 시작일)
- award: 음악방송 1위·시상식 수상 (date=수상일, 이미 일어난 일만)
- vote: 진행 중이거나 예정된 팬 투표 (date=시작일, end_date=마감일, link=투표 페이지)
- release: 앨범·음원 발매 예정

규칙:
- sources에는 근거를 넣는다. 뉴스 목록 항목은 그 id(예: N1a2b3c4d)를, 웹검색 결과는 URL을 그대로 넣는다. 본 적 없는 URL을 만들어내지 마라.
- 같은 사실을 다룬 서로 다른 언론사 기사가 있으면 모두 sources에 넣어라. 공식 SNS·소속사·방송사 공지를 웹검색으로 찾으면 가장 좋다.
- 날짜는 YYYY-MM-DD, 시간은 한국시간 HH:MM. 기사에 시간이 없으면 time=null. 추측하지 마라.
- 기존 일정과 같은 사실이면 same_as에 그 id를 넣고, 새로 알게 된 출처를 sources에 넣어라.
- 최근 30일 안에 시작해 아직 진행 중인 팝업·콜라보·굿즈도 넣어라(종료일을 모르면 end_date=null).
- 리센느와 무관하거나 날짜를 확정할 수 없는 내용, 루머, 차트 순위 자체는 넣지 마라.
- title은 짧게(예: "SBS 인기가요 출연", "성수 팝업스토어 'PULSE'"), summary는 한 문장.
- members는 해당 멤버만, 그룹 전체면 5명 모두."""


def event_id(e: dict) -> str:
    return "e" + hashlib.sha1(f"{e['type']}|{e['date']}|{norm_title(e['title'])}".encode()).hexdigest()[:10]


def _compact(e: dict) -> str:
    span = e["date"] + (f"~{e['end_date']}" if e.get("end_date") else "") + (f" {e['time']}" if e.get("time") else "")
    return f"- id={e['id']} | {e['type']} | {span} | {e['title']}"


def should_run(state: dict, new_articles: list) -> bool:
    last = state.get("events_last_llm")
    if new_articles:
        return True
    return not last or now() - parse_iso(last) > timedelta(hours=24)


def collect_events() -> list[dict]:
    new_articles = news.collect_news()
    store = load("events.json", {"events": [], "pending": []})
    first_run = "updated" not in store
    if not should_run(store, new_articles):
        return []

    articles = {a["id"]: a for a in load("news.json")["articles"]}
    week = iso(now() - timedelta(days=7))
    recent = [a for a in articles.values() if not a.get("dup") and a["published_at"] >= week][:300]
    horizon = (now() - timedelta(days=30)).strftime("%Y-%m-%d")
    existing = [e for e in store["events"] if (e.get("end_date") or e["date"]) >= horizon]
    lines = [f"- id={a['id']} | {a['published_at'][:16]} | {a['publisher']} | {a['title']}" for a in recent]
    content = (
        f"오늘은 {today()} (한국시간 {now().strftime('%H:%M')})이다.\n\n"
        f"[기존 확인된 일정]\n" + ("\n".join(_compact(e) for e in existing) or "(없음)") + "\n\n"
        f"[출처가 부족해 보류 중인 일정 — 추가 출처를 찾아봐]\n"
        + ("\n".join(_compact(e) for e in store["pending"]) or "(없음)") + "\n\n"
        f"[최근 7일 뉴스]\n" + "\n".join(lines)
    )
    out, seen = llm.ask_json(model=config.MODEL_EVENTS, system=SYSTEM, content=content, schema=SCHEMA,
                             purpose="events", web_search=2 if store["pending"] else 1, effort="low")
    seen_urls = set(seen)
    t = date.fromisoformat(today())

    verified = {e["id"]: e for e in store["events"]}
    pending = {e["id"]: e for e in store["pending"]}
    alerts = []
    for raw in out["events"]:
        eid = raw["same_as"] if raw["same_as"] in verified or raw["same_as"] in pending else event_id(raw)
        prev = verified.get(eid) or pending.get(eid)
        if prev:  # 이전 출처와 합쳐서 판정
            raw["sources"] = list(dict.fromkeys(raw["sources"] + [s["ref"] for s in prev.get("sources", [])]))
            seen_urls |= {s["url"] for s in prev.get("sources", []) if s["ref"].startswith("http")}
        ok, sources, why = verify(raw, articles, seen_urls, t)
        ev = {k: raw[k] for k in ("type", "title", "date", "end_date", "time", "place", "members", "summary", "link")}
        ev.update(id=eid, sources=sources, verdict=why, checked_at=iso())
        ev["first_seen"] = (prev or {}).get("first_seen", iso())
        if ok:
            was_verified = eid in verified
            pending.pop(eid, None)
            verified[eid] = ev
            if not was_verified and not first_run:
                alerts.append({
                    "key": f"event:{eid}", "cat": ALERT_CAT[ev["type"]],
                    "title": f"{_emoji(ev['type'])} [{TYPE_LABEL[ev['type']]}] {ev['title']}",
                    "body": f"{_span(ev)} · {ev['summary']}",
                    "url": ev.get("link") or sources[0]["url"], "at": iso(),
                })
        elif eid not in verified:
            pending[eid] = ev

    limit = iso(now() - timedelta(days=PENDING_DAYS))
    store["pending"] = [e for e in pending.values() if e["first_seen"] >= limit]
    keep = (now() - timedelta(days=400)).strftime("%Y-%m-%d")
    store["events"] = sorted((e for e in verified.values() if e["date"] >= keep), key=lambda e: e["date"])
    store["updated"] = iso()
    store["events_last_llm"] = iso()
    save("events.json", store)
    return alerts


def _emoji(t: str) -> str:
    return {"broadcast": "📺", "event": "🎤", "popup": "🏬", "collab": "🤝", "goods": "🛍️",
            "award": "🏆", "vote": "🗳️", "release": "💿"}[t]


def _span(e: dict) -> str:
    s = e["date"][5:].replace("-", "/")
    if e.get("end_date") and e["end_date"] != e["date"]:
        s += "~" + e["end_date"][5:].replace("-", "/")
    if e.get("time"):
        s += " " + e["time"]
    return s
