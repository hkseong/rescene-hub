"""YouTube: official/원이 channel uploads, view tracking, third-party appearances."""
from __future__ import annotations

import os
import re
from datetime import timedelta, timezone

import requests

from . import config, llm
from .common import CollectorError, iso, load, now, parse_iso, save

API = "https://www.googleapis.com/youtube/v3/"
MILESTONES = [10**5, 5 * 10**5, 10**6, 5 * 10**6, 10**7, 2 * 10**7, 5 * 10**7, 10**8, 2 * 10**8, 5 * 10**8, 10**9]


def yt(endpoint: str, **params) -> dict:
    params["key"] = os.environ["YOUTUBE_API_KEY"]
    r = requests.get(API + endpoint, params=params, timeout=25)
    if r.status_code != 200:
        raise CollectorError(f"YouTube {endpoint} {r.status_code}: {r.text[:300]}")
    return r.json()


KO_PARTICLES = "의|가|이|는|은|를|을|와|과|랑|이랑|도|만|에게|한테|님|네|표|씨|도요|까지|부터|처럼|와의|과의|로|으로"


def detect_members(text: str) -> list[str]:
    found = []
    for name, aliases in config.MEMBERS.items():
        for a in aliases:
            # 영문은 단어 경계, 한글은 뒤에 조사만 허용 ('제나의'는 O, '메이크업'은 X)
            if a.isascii():
                pat = r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])"
            else:
                pat = r"(?<![가-힣])" + re.escape(a) + r"(?:" + KO_PARTICLES + r")?(?![가-힣])"
            if re.search(pat, text, flags=re.I):
                found.append(name)
                break
    return found


def parse_duration(iso_dur: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def video_details(ids: list[str]) -> dict:
    out = {}
    for i in range(0, len(ids), 50):
        res = yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]), maxResults=50)
        for v in res.get("items", []):
            out[v["id"]] = v
    return out


def _item_from(v: dict, group: str, members: list[str]) -> dict:
    sn, st = v["snippet"], v.get("statistics", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {
        "id": v["id"],
        "title": sn["title"],
        "channel_id": sn["channelId"],
        "channel": sn["channelTitle"],
        "published_at": sn["publishedAt"],
        "thumb": thumb,
        "views": int(st.get("viewCount", 0)),
        "likes": int(st.get("likeCount", 0)) if "likeCount" in st else None,
        "short": parse_duration(v.get("contentDetails", {}).get("duration", "")) <= 60,
        "group": group,
        "members": members,
    }


def next_milestone(views: int) -> int | None:
    return next((m for m in MILESTONES if m > views), None)


def milestone_eta(points: list, views: int) -> dict | None:
    """points: [[date, views], ...] daily. Linear rate over up to the last 7 days."""
    target = next_milestone(views)
    if not target or len(points) < 2:
        return None
    window = points[-8:]
    days = (parse_iso(window[-1][0] + "T00:00:00+09:00") - parse_iso(window[0][0] + "T00:00:00+09:00")).days
    gained = window[-1][1] - window[0][1]
    if days <= 0 or gained <= 0:
        return None
    rate = gained / days
    eta = (target - views) / rate
    if eta > 365:
        return None
    return {"target": target, "eta_days": round(eta, 1), "per_day": int(rate)}


def fmt_count(n: int) -> str:
    if n >= 10**8:
        return f"{n / 10**8:g}억"
    if n >= 10**4:
        return f"{n / 10**4:g}만"
    return str(n)


def collect_youtube() -> list[dict]:
    data = load("videos.json", {"items": []})
    items = {v["id"]: v for v in data["items"]}
    alerts = []
    for ch in config.YOUTUBE_CHANNELS:
        playlist = "UU" + ch["id"][2:]
        have_any = any(v["channel_id"] == ch["id"] for v in items.values())
        ids, token = [], None
        for _ in range(20 if not have_any else 1):
            res = yt("playlistItems", part="contentDetails", playlistId=playlist, maxResults=50 if not have_any else 15,
                     **({"pageToken": token} if token else {}))
            ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
            token = res.get("nextPageToken")
            if not token:
                break
        new_ids = [i for i in ids if i not in items]
        for vid, v in video_details(new_ids).items():
            members = detect_members(v["snippet"]["title"])
            if ch.get("member") and ch["member"] not in members:
                members.insert(0, ch["member"])
            items[vid] = _item_from(v, ch["group"], members)
            if have_any:
                label = "원이 채널" if ch["group"] == "wonee" else ch["name"]
                alerts.append({"key": f"video:{vid}", "cat": "video", "title": f"🎬 {label} 새 영상",
                               "body": v["snippet"]["title"], "url": f"https://youtu.be/{vid}", "at": iso()})

    # 통계 갱신 (전체, 50개씩 1 unit)
    fresh = video_details(list(items))
    for vid, v in fresh.items():
        st = v.get("statistics", {})
        items[vid]["views"] = int(st.get("viewCount", items[vid]["views"]))
        if "likeCount" in st:
            items[vid]["likes"] = int(st["likeCount"])
        items[vid]["title"] = v["snippet"]["title"]
        if items[vid]["group"] in ("official", "wonee"):
            members = detect_members(items[vid]["title"])
            if items[vid]["group"] == "wonee" and "원이" not in members:
                members.insert(0, "원이")
            items[vid]["members"] = members
    for vid in [i for i in items if i not in fresh]:  # 비공개/삭제
        del items[vid]

    alerts += _track_views(items)
    data["items"] = sorted(items.values(), key=lambda x: x["published_at"], reverse=True)
    data["updated"] = iso()
    save("videos.json", data)
    return alerts


def _track_views(items: dict) -> list[dict]:
    hist = load("views_history.json", {})
    day = now().strftime("%Y-%m-%d")
    cutoff = (now() - timedelta(days=60)).strftime("%Y-%m-%d")
    recent = (now() - timedelta(days=30)).isoformat()
    alerts = []
    for vid, v in items.items():
        if v["group"] not in ("official", "wonee") or v["short"]:
            continue
        if v["views"] < 10**5 and v["published_at"] < recent:
            continue
        pts = hist.setdefault(vid, [])
        prev_views = pts[-1][1] if pts else None
        if pts and pts[-1][0] == day:
            pts[-1][1] = v["views"]
        else:
            pts.append([day, v["views"]])
        hist[vid] = [p for p in pts if p[0] >= cutoff]
        if prev_views is not None:
            crossed = [m for m in MILESTONES if prev_views < m <= v["views"] and m >= 10**6]
            if crossed:
                m = crossed[-1]
                alerts.append({"key": f"milestone:{vid}:{m}", "cat": "video",
                               "title": f"🎉 조회수 {fmt_count(m)} 돌파!", "body": v["title"],
                               "url": f"https://youtu.be/{vid}", "at": iso()})
        v["milestone"] = milestone_eta(hist[vid], v["views"])
    for vid in [k for k in hist if k not in items]:
        del hist[vid]
    save("views_history.json", hist)
    return alerts


CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["appearance", "stage", "reject"]},
                    "members": {"type": "array", "items": {"type": "string", "enum": list(config.MEMBERS)}},
                },
                "required": ["id", "kind", "members"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = """너는 K팝 걸그룹 리센느(RESCENE; 멤버 원이, 리브, 미나미, 메이, 제나) 팬 사이트의 영상 분류기다.
각 유튜브 영상이 리센느(또는 멤버)가 실제로 출연한 '공식 콘텐츠'인지 판정한다.
- appearance: 방송사·제작사·브랜드·다른 아티스트 등의 공식 채널 예능/웹예능/인터뷰/라디오/광고/챌린지 등에 리센느 또는 멤버가 직접 출연
- stage: 음악방송·페스티벌·시상식 무대 영상, 방송사/공식 직캠
- reject: 팬 편집·리액션·커버·뉴스 요약·쇼츠 짜깁기·이름만 언급·다른 그룹 영상·확신이 서지 않는 경우
확실하지 않으면 reject. members에는 영상에 출연한 멤버만 넣고 그룹 전체면 5명 모두 넣는다."""


def collect_appearances() -> list[dict]:
    data = load("videos.json", {"items": []})
    items = {v["id"]: v for v in data["items"]}
    if not items:
        raise CollectorError("videos.json이 비어 있어 공식 채널 수집 후 실행해야 합니다")
    seen = load("appearances_seen.json", {})
    first_run = not seen
    own = {c["id"] for c in config.YOUTUBE_CHANNELS}
    after = (now() - timedelta(days=3 if seen else 14)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cand_ids = []
    for q in config.YOUTUBE_SEARCH_QUERIES:
        res = yt("search", part="snippet", q=q, type="video", order="date", maxResults=50,
                 publishedAfter=after, regionCode="KR", relevanceLanguage="ko")
        for it in res.get("items", []):
            vid = it["id"]["videoId"]
            if it["snippet"]["channelId"] in own or vid in items or vid in seen or vid in cand_ids:
                continue
            cand_ids.append(vid)
    alerts = []
    if cand_ids:
        details = video_details(cand_ids)
        lines = []
        for vid, v in details.items():
            sn = v["snippet"]
            desc = re.sub(r"\s+", " ", sn.get("description", ""))[:300]
            lines.append(f"- id={vid} | 채널={sn['channelTitle']} | 제목={sn['title']} | 설명={desc}")
        verdicts = {}
        for i in range(0, len(lines), 40):
            out, _ = llm.ask_json(model=config.MODEL_CLASSIFY, system=CLASSIFY_SYSTEM, schema=CLASSIFY_SCHEMA,
                                  content="다음 영상들을 분류해.\n" + "\n".join(lines[i:i + 40]),
                                  purpose="classify_videos", effort="low", max_tokens=8000)
            verdicts.update({r["id"]: r for r in out["results"]})
        for vid, v in details.items():
            r = verdicts.get(vid, {"kind": "reject", "members": []})
            seen[vid] = r["kind"]
            if r["kind"] == "reject":
                continue
            items[vid] = _item_from(v, r["kind"], r["members"])
            if not first_run:
                label = "무대 영상" if r["kind"] == "stage" else "출연 영상"
                who = ", ".join(r["members"]) if 0 < len(r["members"]) < 5 else "리센느"
                alerts.append({"key": f"video:{vid}", "cat": "appearance",
                               "title": f"📺 {who} {label} 떴어요!",
                               "body": f"{v['snippet']['channelTitle']} · {v['snippet']['title']}",
                               "url": f"https://youtu.be/{vid}", "at": iso()})
    # 오래된 seen 정리 (최대 3000개)
    if len(seen) > 3000:
        seen = dict(list(seen.items())[-3000:])
    save("appearances_seen.json", seen)
    data["items"] = sorted(items.values(), key=lambda x: x["published_at"], reverse=True)
    data["updated"] = iso()
    save("videos.json", data)
    return alerts
