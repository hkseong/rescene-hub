"""Alerts → web push. Realtime per-category opt-in, morning/evening digests, admin messages."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta

import requests

from . import config
from .common import KST, iso, load, now, parse_iso, save, today

CATEGORIES = ["broadcast", "vote", "award", "video", "appearance", "chart", "popup"]
MAX_PER_RUN = 4
VAPID_SUB = "https://hkseong.github.io"  # 푸시 서비스에 알리는 연락처 (호스트만 허용됨)


# ---------- alert bookkeeping ----------

def schedule_alerts(events: list[dict], t: datetime) -> list[dict]:
    """Time-driven alerts: broadcasts starting within 2h, vote deadlines within 24h / 3h."""
    out = []
    for e in events:
        if e["type"] in ("broadcast", "event") and e.get("time"):
            start = datetime.fromisoformat(f"{e['date']}T{e['time']}:00+09:00")
            if timedelta(0) <= start - t <= timedelta(hours=2):
                out.append({"key": f"soon:{e['id']}", "cat": "broadcast",
                            "title": f"⏰ 오늘 {e['time']} {e['title']}",
                            "body": f"곧 시작해요! {e.get('summary', '')}".strip(),
                            "url": e.get("link") or (e["sources"][0]["url"] if e.get("sources") else config.SITE_URL),
                            "at": iso(t)})
        if e["type"] == "vote" and e.get("end_date"):
            end = datetime.fromisoformat(f"{e['end_date']}T23:59:00+09:00")
            left = end - t
            for hours in (3, 24):
                if timedelta(0) <= left <= timedelta(hours=hours):
                    out.append({"key": f"deadline{hours}:{e['id']}", "cat": "vote",
                                "title": f"🗳️ {e['title']} 마감 {hours}시간 전!",
                                "body": "얼른 투표하러 가요!",
                                "url": e.get("link") or config.SITE_URL, "at": iso(t)})
                    break
    return out


def register(alerts: list[dict]) -> list[dict]:
    """Drop already-sent keys, append to alerts.json history. Returns the fresh ones."""
    log = load("alerts.json", {"items": [], "keys": []})
    keys = set(log["keys"])
    fresh = []
    for a in alerts:
        if a["key"] in keys:
            continue
        keys.add(a["key"])
        fresh.append(a)
    log["items"] = (fresh[::-1] + log["items"])[:300]
    log["keys"] = (log["keys"] + [a["key"] for a in fresh])[-5000:]  # 오래된 것부터 버림
    log["updated"] = iso()
    save("alerts.json", log)
    return fresh


# ---------- digest ----------

def _events_on(events, day):
    return [e for e in events if e["date"] <= day <= (e.get("end_date") or e["date"])]


def build_digest(kind: str, t: datetime) -> dict | None:
    day = t.strftime("%Y-%m-%d")
    events = load("events.json", {"events": []})["events"]
    chart = load("chart.json", {})
    lines = []
    if kind == "morning":
        todays = _events_on(events, day)
        for e in sorted(todays, key=lambda e: e.get("time") or "99"):
            lines.append(f"• {e.get('time') or ''} {e['title']}".replace("•  ", "• "))
        for d in upcoming_days(t, within=0):
            lines.append(f"• 🎂 {d['title']}")
        rt = (chart.get("realtime") or {}).get("entries", [])
        if rt:
            top = min(rt, key=lambda e: e["rank"])
            lines.append(f"• 멜론 실시간 최고 {top['rank']}위 '{top['title']}' (TOP100에 {len(rt)}곡)")
        soon = [e for e in events if e["type"] == "vote" and e.get("end_date", "") >= day]
        for e in soon[:2]:
            lines.append(f"• 🗳️ {e['title']} (~{e['end_date'][5:]})")
        title = f"☀️ 오늘의 리센느 ({t.month}/{t.day})"
    else:
        since = iso(t - timedelta(hours=14))
        items = [a for a in load("alerts.json", {"items": []})["items"] if a["at"] >= since]
        counts = {}
        for a in items:
            counts[a["cat"]] = counts.get(a["cat"], 0) + 1
        label = {"video": "새 영상", "appearance": "출연 영상", "award": "1위·수상", "chart": "차트 소식",
                 "popup": "팝업·콜라보", "vote": "투표 소식", "broadcast": "일정"}
        for cat, n in counts.items():
            lines.append(f"• {label.get(cat, cat)} {n}건")
        for a in [a for a in items if a["cat"] in ("award", "popup")][:3]:
            lines.append(f"• {a['title']}")
        tomorrow = (t + timedelta(days=1)).strftime("%Y-%m-%d")
        for e in _events_on(events, tomorrow)[:3]:
            lines.append(f"• 내일: {e['title']}")
        title = f"🌙 오늘 있었던 리센느 ({t.month}/{t.day})"
    if not lines:
        lines = ["오늘은 새 소식이 없어요. 사이트에서 차트와 영상을 확인해 보세요!"]
    return {"title": title, "body": "\n".join(lines[:6]), "url": config.SITE_URL, "tag": f"digest-{kind}"}


def upcoming_days(t: datetime, within: int = 30) -> list[dict]:
    """Anniversaries (debut, birthdays, album releases) within N days."""
    members = load("members.json", {"members": {}})
    albums = load("albums.json", {"albums": []})["albums"]
    base = []
    debut = config.DEBUT["date"]
    base.append((debut, "리센느 데뷔 {n}주년", True))
    for name, m in members.get("members", {}).items():
        if m.get("birthday"):
            base.append((m["birthday"], f"{name} 생일", False))
    for a in albums:
        if a.get("type") in ("EP", "정규", "싱글"):
            base.append((a["date"], f"'{a['title']}' 발매 {{n}}주년", True))
    out = []
    d0 = t.date()
    for src, label, needs_year in base:
        y, mo, da = (int(x) for x in src.split("-"))
        for year in (d0.year, d0.year + 1):
            try:
                occ = date(year, mo, da)
            except ValueError:
                continue
            n = year - y
            if 0 <= (occ - d0).days <= within and n >= 1:
                out.append({"date": occ.isoformat(), "title": label.format(n=n), "days": (occ - d0).days})
                break
    return sorted(out, key=lambda x: x["days"])


# ---------- delivery ----------

def subscribers() -> list[dict]:
    url, token = os.environ.get("WORKER_URL"), os.environ.get("WORKER_ADMIN_TOKEN")
    if not (url and token):
        return []
    r = requests.get(url.rstrip("/") + "/api/admin/subscribers", headers={"Authorization": f"Bearer {token}"},
                     timeout=20)
    r.raise_for_status()
    return r.json()["subscribers"]


def _remove(ids: list[str]) -> None:
    if not ids:
        return
    requests.post(os.environ["WORKER_URL"].rstrip("/") + "/api/admin/remove", json={"ids": ids},
                  headers={"Authorization": f"Bearer {os.environ['WORKER_ADMIN_TOKEN']}"}, timeout=20)


def send(sub: dict, payload: dict) -> bool:
    """Returns False if the subscription is gone and should be deleted."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(subscription_info=sub["subscription"], data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600)
    except WebPushException as e:
        code = e.response.status_code if e.response is not None else None
        if code in (404, 410):
            return False
        print(f"push failed ({code}): {e}", file=sys.stderr)
    return True


def ntfy(title: str, body: str, url: str | None = None) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        headers = {"Title": title.encode("utf-8"), "Tags": "rotating_light"}
        if url:
            headers["Click"] = url
        requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), headers=headers, timeout=15)


def admin(title: str, body: str, url: str | None = None) -> None:
    """Message for the site owner: push to admin subscribers + ntfy fallback."""
    payload = {"title": title, "body": body, "url": url or config.SITE_URL, "tag": "admin"}
    try:
        for s in subscribers():
            if s.get("admin"):
                send(s, payload)
    except Exception as e:  # 알림 실패가 수집을 막지 않게
        print(f"admin push failed: {e}", file=sys.stderr)
    try:
        ntfy(title, body, url)
    except Exception as e:
        print(f"ntfy failed: {e}", file=sys.stderr)


def dispatch(fresh: list[dict], t: datetime, dry_run: bool = False) -> dict:
    state = load("state.json", {})
    digests = []
    for kind, hour in config.DIGEST_HOURS_KST.items():
        slot = t.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot <= t <= slot + timedelta(hours=3) and state.get(f"digest_{kind}") != today():
            digests.append((kind, build_digest(kind, t)))
            state[f"digest_{kind}"] = today()
    stats = {"alerts": len(fresh), "digests": [k for k, _ in digests], "sent": 0}
    if dry_run:
        stats["preview"] = {"alerts": fresh, "digests": digests}
        return stats
    subs = subscribers()
    gone = []
    for s in subs:
        prefs = s.get("prefs", {})
        msgs = [d for k, d in digests if prefs.get(f"digest_{k}", True)]
        mine = [a for a in fresh if prefs.get("realtime", {}).get(a["cat"], False)]
        if len(mine) > MAX_PER_RUN:
            msgs.append({"title": f"리센느 새 소식 {len(mine)}건", "body": "\n".join(a["title"] for a in mine[:6]),
                         "url": config.SITE_URL, "tag": "bundle"})
        else:
            msgs += [{"title": a["title"], "body": a["body"], "url": a["url"], "tag": a["key"]} for a in mine]
        for m in msgs:
            if not send(s, m):
                gone.append(s["id"])
                break
            stats["sent"] += 1
    _remove(gone)
    save("state.json", state)
    return stats


if __name__ == "__main__":
    # python -m collectors.notify --admin "제목" "본문" [url]
    if len(sys.argv) >= 4 and sys.argv[1] == "--admin":
        admin(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
