"""Parsers against saved pages. When a site changes, refresh the fixture and make these pass again."""
from pathlib import Path

import pytest

from collectors import melon, news
from collectors.common import CollectorError

FX = Path(__file__).parent / "fixtures"


def read(name):
    return (FX / name).read_text(encoding="utf-8")


def test_realtime_chart_has_rescene_rows():
    c = melon.parse_chart(read("melon_chart_realtime.html"))
    assert c["chart_date"] and c["chart_hour"]
    assert c["entries"], "리센느 곡이 차트에 있어야 하는 시점의 샘플"
    e = c["entries"][0]
    assert 1 <= e["rank"] <= 100 and e["title"] and e["song_id"].isdigit()
    assert [x["rank"] for x in c["entries"]] == sorted(x["rank"] for x in c["entries"])


def test_day_chart_parses():
    assert melon.parse_chart(read("melon_chart_day.html"))["entries"]


def test_chart_structure_change_is_detected():
    with pytest.raises(CollectorError):
        melon.parse_chart("<html><body>점검 중</body></html>")


def test_album_list():
    albums = melon.parse_album_list(read("melon_albums.html"))
    assert len(albums) >= 10
    a = albums[0]
    assert a["id"].isdigit() and a["title"] and a["date"][:2] == "20" and a["art"].startswith("https://")
    assert "\xa0" not in "".join(x["title"] for x in albums)


def test_album_detail_tracks():
    d = melon.parse_album_detail(read("melon_album_detail.html"))
    assert len(d["tracks"]) >= 1
    assert sum(t["is_title"] for t in d["tracks"]) >= 1
    assert not any(t["title"].startswith("Title") for t in d["tracks"])


def test_week_award():
    w = melon.parse_week_award(read("melon_weekaward.html"))
    assert w["total"] >= 3 and w["top"][0]["rank"] == 1
    assert all("song" in c and "artist" in c for c in w["top"])


def test_week_award_tallying():
    # 투표 마감 후 집계 중(월요일 15시 발표 전)에는 후보가 없다 → 오류 아님
    assert melon.parse_week_award(read("melon_weekaward_closed.html")) is None
    with pytest.raises(CollectorError):
        melon.parse_week_award("<html><body></body></html>")


def test_rss():
    items = news.parse_rss((FX / "news.xml").read_bytes())
    assert len(items) > 10
    a = items[0]
    assert a["id"].startswith("N") and a["title"] and a["publisher"] and a["published_at"][:2] == "20"
    assert not a["title"].endswith(" - " + a["publisher"])
    assert any(news.is_relevant(x) for x in items)
