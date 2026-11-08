"""Melon: realtime/day/week chart, discography, weekly award vote."""
from __future__ import annotations

import re
from datetime import timedelta

from bs4 import BeautifulSoup

from . import config
from .common import CollectorError, http_get, iso, load, now, parse_iso, save, today

CHART_URLS = {
    "realtime": "https://www.melon.com/chart/index.htm",
    "day": "https://www.melon.com/chart/day/index.htm",
    "week": "https://www.melon.com/chart/week/index.htm",
}
ALBUM_LIST_URL = ("https://www.melon.com/artist/albumPaging.htm?startIndex={}&pageSize=15&listType=0"
                  "&orderBy=ISSUE_DATE&artistId={}")
ALBUM_DETAIL_URL = "https://www.melon.com/album/detail.htm?albumId={}"
WEEK_AWARD_URL = "https://www.melon.com/melonaward/weekAward.htm"
SONG_URL = "https://www.melon.com/song/detail.htm?songId={}"
ALBUM_URL = "https://www.melon.com/album/detail.htm?albumId={}"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def is_rescene(text: str) -> bool:
    return any(n.lower() in text.lower() for n in config.ARTIST_NAMES)


def parse_chart(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser")
    rows = s.select("tr.lst50, tr.lst100")
    if len(rows) < 50:
        raise CollectorError(f"멜론 차트 행이 {len(rows)}개뿐입니다 (페이지 구조 변경 의심)")
    year = s.select_one("span.year")
    hour = s.select_one("span.hour")
    entries = []
    for tr in rows:
        rank = tr.select_one("span.rank")
        title = tr.select_one("div.ellipsis.rank01 a")
        artist = tr.select_one("div.ellipsis.rank02 a")
        album = tr.select_one("div.ellipsis.rank03 a")
        if not (rank and title and artist):
            raise CollectorError("멜론 차트 행에서 순위/제목/아티스트를 찾지 못했습니다")
        if not is_rescene(artist.get_text()):
            continue
        album_id = re.findall(r"goAlbumDetail\('(\d+)'\)", str(album)) if album else []
        entries.append({
            "rank": int(rank.get_text(strip=True)),
            "title": clean(title.get_text()),
            "song_id": tr.get("data-song-no"),
            "album": album.get_text(strip=True) if album else "",
            "album_id": album_id[0] if album_id else None,
        })
    return {
        "chart_date": year.get_text(strip=True) if year else None,
        "chart_hour": hour.get_text(strip=True) if hour else None,
        "entries": entries,
    }


def _rank_map(chart: dict | None) -> dict:
    return {e["song_id"]: e["rank"] for e in (chart or {}).get("entries", [])}


def chart_alerts(prev: dict | None, cur: dict) -> list[dict]:
    """New entry to TOP100 / TOP10 / #1 compared with the previous realtime chart."""
    if not prev:
        return []
    before = _rank_map(prev)
    alerts = []
    day = today()
    for e in cur["entries"]:
        old = before.get(e["song_id"])
        url = SONG_URL.format(e["song_id"])
        if e["rank"] == 1 and old != 1:
            alerts.append(_alert(f"chart:{e['song_id']}:1:{day}", f"🥇 멜론 실시간 1위! '{e['title']}'",
                                 f"'{e['title']}'이(가) 멜론 TOP100 1위에 올랐어요.", url))
        elif e["rank"] <= 10 and (old is None or old > 10):
            alerts.append(_alert(f"chart:{e['song_id']}:top10:{day}", f"📈 '{e['title']}' TOP10 진입",
                                 f"멜론 실시간 {e['rank']}위 ({'차트 밖' if old is None else str(old) + '위'} → {e['rank']}위)", url))
        elif old is None:
            alerts.append(_alert(f"chart:{e['song_id']}:in:{day}", f"🎵 '{e['title']}' 멜론 TOP100 진입",
                                 f"멜론 실시간 {e['rank']}위로 진입했어요.", url))
    return alerts


def _alert(key, title, body, url, cat="chart"):
    return {"key": key, "cat": cat, "title": title, "body": body, "url": url, "at": iso()}


def collect_chart() -> list[dict]:
    data = load("chart.json", {"history": {}, "best": {}})
    prev_realtime = data.get("realtime")
    stamp = iso()
    for kind, url in CHART_URLS.items():
        parsed = parse_chart(http_get(url).text)
        parsed["fetched_at"] = stamp
        data[kind] = parsed
    alerts = chart_alerts(prev_realtime, data["realtime"])

    # 실시간 순위 히스토리 (7일)
    cutoff = now() - timedelta(days=7)
    hist = data.setdefault("history", {})
    for e in data["realtime"]["entries"]:
        hist.setdefault(e["song_id"], {"title": e["title"], "points": []})
        pts = hist[e["song_id"]]["points"]
        if not pts or pts[-1][0][:13] != stamp[:13]:
            pts.append([stamp, e["rank"]])
    for sid in list(hist):
        hist[sid]["points"] = [p for p in hist[sid]["points"] if parse_iso(p[0]) >= cutoff]
        if not hist[sid]["points"]:
            del hist[sid]

    # 최고 순위
    best = data.setdefault("best", {})
    for kind in CHART_URLS:
        for e in data[kind]["entries"]:
            b = best.setdefault(e["song_id"], {"title": e["title"]})
            if kind not in b or e["rank"] < b[kind]["rank"]:
                b[kind] = {"rank": e["rank"], "date": today()}
    data["updated"] = stamp
    save("chart.json", data)
    return alerts


def parse_album_list(html: str) -> list[dict]:
    s = BeautifulSoup(html, "html.parser")
    items = s.select("li.album11_li")
    if not items:
        raise CollectorError("멜론 앨범 목록이 비어 있습니다 (페이지 구조 변경 의심)")
    albums = []
    for li in items:
        name = li.select_one("a.ellipsis")
        ids = re.findall(r"goAlbumDetail\('(\d+)'\)", str(li))
        date = li.select_one("span.cnt_view")
        kind = li.select_one("span.vdo_name")
        img = li.select_one("a.thumb img")
        if not (name and ids and date):
            raise CollectorError("멜론 앨범 항목에서 이름/ID/발매일을 찾지 못했습니다")
        art = img.get("src", "").split("?")[0] if img else ""
        albums.append({
            "id": ids[0],
            "title": clean(name.get_text()),
            "type": (kind.get_text(strip=True).strip("[]") if kind else ""),
            "date": date.get_text(strip=True).replace(".", "-"),
            "art": art,
            "url": ALBUM_URL.format(ids[0]),
        })
    return albums


def parse_album_detail(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser")
    rows = s.select("form#frm tbody tr")
    tracks = []
    for tr in rows:
        cb = tr.select_one("input[name=input_check]")
        a = tr.select_one(".wrap_song_info .ellipsis a")
        if not (cb and a):
            continue
        tracks.append({
            "song_id": cb.get("value"),
            "title": clean(a.get_text()),
            "is_title": bool(tr.select_one(".bullet_icons.title")),
        })
    if not tracks:
        raise CollectorError("멜론 앨범 상세에서 수록곡을 찾지 못했습니다")
    info = {}
    dl = s.select_one("dl.list")
    if dl:
        for dt in dl.select("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                info[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
    return {"tracks": tracks, "genre": info.get("장르", ""), "label": info.get("기획사", "")}


def collect_albums() -> list[dict]:
    data = load("albums.json", {"albums": []})
    known = {a["id"]: a for a in data["albums"]}
    first_run = not known
    alerts = []
    listed = []
    for start in range(1, 200, 15):
        page = parse_album_list(http_get(ALBUM_LIST_URL.format(start, config.MELON_ARTIST_ID)).text)
        listed += page
        if len(page) < 15:
            break
    for a in listed:
        old = known.get(a["id"])
        if old and old.get("tracks"):
            old.update({k: a[k] for k in ("title", "type", "date", "art")})
            continue
        a.update(parse_album_detail(http_get(ALBUM_DETAIL_URL.format(a["id"])).text))
        known[a["id"]] = a
        if not first_run:
            alerts.append(_alert(f"album:{a['id']}", f"💿 새 앨범 '{a['title']}'",
                                 f"{a['date']} 발매 · {len(a['tracks'])}곡", a["url"], cat="video"))
    data["albums"] = sorted(known.values(), key=lambda x: x["date"], reverse=True)
    data["updated"] = iso()
    save("albums.json", data)
    return alerts


def parse_week_award(html: str) -> dict | None:
    """None = 투표 마감 후 집계 중(매주 월요일 15시 결과 발표 전까지 후보 목록이 없음)."""
    s = BeautifulSoup(html, "html.parser")
    seen, cands = set(), []
    for el in s.select("[data-vote-rank]"):
        vid = el.get("data-vote-id")
        if vid in seen:
            continue
        seen.add(vid)
        cands.append({
            "rank": int(el.get("data-vote-rank")),
            "song": el.get("data-vote-nm", ""),
            "artist": el.get("data-artist-nm", ""),
        })
    if not cands:
        tally = s.select_one(".chart-result-time")
        if tally and "집계 중" in str(tally):
            return None
        raise CollectorError("멜론 주간 인기상 후보를 찾지 못했습니다")
    cands.sort(key=lambda c: c["rank"])
    return {
        "top": cands[:5],
        "total": len(cands),
        "rescene": [c for c in cands if is_rescene(c["artist"])],
        "url": WEEK_AWARD_URL,
    }


def collect_vote() -> list[dict]:
    data = load("votes.json", {})
    prev = data.get("melon_week")
    cur = parse_week_award(http_get(WEEK_AWARD_URL).text)
    if cur is None:  # 집계 중: 직전 데이터 유지
        return []
    cur["fetched_at"] = iso()
    alerts = []
    if prev is not None:
        before = {c["song"]: c["rank"] for c in prev.get("rescene", [])}
        for c in cur["rescene"]:
            old = before.get(c["song"])
            if old != c["rank"]:
                what = "후보 등장" if old is None else f"{old}위 → {c['rank']}위"
                alerts.append(_alert(f"vote:melonweek:{c['song']}:{c['rank']}:{today()}",
                                     f"🗳️ 멜론 주간 인기상 '{c['song']}' {c['rank']}위",
                                     f"{what}. 지금 투표하러 가요!", WEEK_AWARD_URL, cat="vote"))
    data["melon_week"] = cur
    data["updated"] = iso()
    save("votes.json", data)
    return alerts
