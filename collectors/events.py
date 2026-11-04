"""Schedules, pop-ups, collabs, goods, music-show wins, votes — extracted by Claude, published by verify.py."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from . import config, llm, news
from .common import iso, load, norm_title, now, parse_iso, save, today
from .verify import verify

TYPES = ["broadcast", "event", "popup", "collab", "goods", "ad", "award", "vote", "release"]
TYPE_LABEL = {
    "broadcast": "방송 출연", "event": "행사", "popup": "팝업", "collab": "콜라보", "goods": "굿즈", "ad": "광고",
    "award": "1위·수상", "vote": "투표", "release": "발매",
}
ALERT_CAT = {"popup": "popup", "collab": "popup", "goods": "popup", "ad": "popup", "award": "award", "vote": "vote",
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
                    "perk": {"type": ["string", "null"]},
                    "link": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["same_as", "type", "title", "date", "end_date", "time", "place", "members",
                             "summary", "perk", "link", "sources"],
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
- collab: 브랜드 협업 제품 출시·콜라보 (예: 편의점 도시락·빵, 애니메이션 OST 협업) (date=출시/시작일)
- goods: 굿즈·앨범 MD 판매 (date=판매 시작일)
- ad: 광고 모델 발탁·새 광고 공개 (date=발탁/공개일, title에 브랜드명)
- award: 음악방송 1위·시상식 수상 (date=수상일, 이미 일어난 일만)
- vote: 진행 중이거나 예정된 팬 투표 (date=시작일, end_date=마감일, link=투표 페이지)
- release: 앨범·음원 발매 예정

규칙:
- sources에는 근거를 넣는다. 뉴스 목록 항목은 그 id(예: N1a2b3c4d)를, 웹검색 결과는 URL을 그대로 넣는다. 본 적 없는 URL을 만들어내지 마라.
- 같은 사실을 다룬 서로 다른 언론사 기사가 있으면 모두 sources에 넣어라. 공식 SNS·소속사·방송사 공지를 웹검색으로 찾으면 가장 좋다.
- 날짜는 YYYY-MM-DD, 시간은 한국시간 HH:MM. 기사에 시간이 없으면 time=null. 추측하지 마라.
- 기존 일정과 같은 사실이면 same_as에 그 id를 넣고, 새로 알게 된 출처를 sources에 넣어라.
- 최근 30일 안에 시작해 아직 진행 중인 팝업·콜라보·굿즈도 넣어라(종료일을 모르면 end_date=null).
- 디시인사이드 리센느 갤러리 같은 팬 커뮤니티 글은 실마리로만 써라. 거기서 본 소식은 공식 공지·언론 기사를 웹검색으로 찾아 그 URL을 sources에 넣어라(커뮤니티 URL은 출처로 인정되지 않는다).
- 리센느와 무관하거나 날짜를 확정할 수 없는 내용, 루머, 차트 순위 자체는 넣지 마라.
- perk: 팬 혜택이 있으면 한 줄로 (예: "2만원 이상 구매 시 미공개 포토카드 1종 랜덤 증정", "팝업 방문 미션 완료 시 한정 엽서"). 기간이 있으면 date/end_date를 그 기간으로. 없으면 null.
- 같은 콜라보·광고·팝업을 여러 항목으로 쪼개지 마라. 기존 일정에 이미 있으면 반드시 same_as를 써라.
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
    if new_articles:
        try:
            news.cluster_stories()
        except Exception as e:  # 묶기는 보기 좋게 하는 용도라 실패해도 일정 수집은 계속
            print(f"  [news] 같은 소식 묶기 실패: {e}")
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

    alerts = merge(store, out["events"], articles, seen_urls, t, notify=not first_run)
    store["updated"] = iso()
    store["events_last_llm"] = iso()
    save("events.json", store)
    return alerts


def merge(store: dict, proposed: list[dict], articles: dict, seen_urls: set[str], t: date, *,
          notify: bool, history: bool = False) -> list[dict]:
    """LLM 제안을 검증해 store에 합친다. 새로 확인된 것 중 지나지 않은 것만 알림으로 돌려준다."""
    verified = {e["id"]: e for e in store["events"]}
    pending = {e["id"]: e for e in store["pending"]}
    alerts = []
    for raw in proposed:
        eid = raw["same_as"] if raw["same_as"] in verified or raw["same_as"] in pending else event_id(raw)
        prev = verified.get(eid) or pending.get(eid)
        if prev:  # 이전 출처와 합쳐서 판정
            raw["sources"] = list(dict.fromkeys(raw["sources"] + [s["ref"] for s in prev.get("sources", [])]))
            seen_urls = seen_urls | {s["url"] for s in prev.get("sources", []) if s["ref"].startswith("http")}
        ok, sources, why = verify(raw, articles, seen_urls, t, history=history)
        ev = {k: raw.get(k) for k in ("type", "title", "date", "end_date", "time", "place", "members", "summary",
                                      "perk", "link")}
        ev.update(id=eid, sources=sources, verdict=why, checked_at=iso())
        ev["first_seen"] = (prev or {}).get("first_seen", iso())
        if ok:
            was_verified = eid in verified
            pending.pop(eid, None)
            verified[eid] = ev
            still_on = (ev.get("end_date") or ev["date"]) >= t.isoformat()
            if not was_verified and notify and still_on:
                alerts.append({
                    "key": f"event:{eid}", "cat": ALERT_CAT[ev["type"]],
                    "title": f"{_emoji(ev['type'])} [{TYPE_LABEL[ev['type']]}] {ev['title']}",
                    "body": f"{_span(ev)} · {ev['summary']}" + (f" 🎁 {ev['perk']}" if ev.get("perk") else ""),
                    "url": ev.get("link") or sources[0]["url"], "at": iso(),
                })
        elif eid not in verified and not history:
            pending[eid] = ev  # 이력 수집에서 떨어진 건 보류함을 어지럽히지 않게 버린다

    limit = iso(now() - timedelta(days=PENDING_DAYS))
    store["pending"] = [e for e in pending.values() if e["first_seen"] >= limit]
    store["events"] = sorted(verified.values(), key=lambda e: e["date"])  # 지난 이력도 모두 보관
    return alerts


def _emoji(t: str) -> str:
    return {"broadcast": "📺", "event": "🎤", "popup": "🏬", "collab": "🤝", "goods": "🛍️",
            "ad": "📢", "award": "🏆", "vote": "🗳️", "release": "💿"}[t]


def _span(e: dict) -> str:
    s = e["date"][5:].replace("-", "/")
    if e.get("end_date") and e["end_date"] != e["date"]:
        s += "~" + e["end_date"][5:].replace("-", "/")
    if e.get("time"):
        s += " " + e["time"]
    return s
