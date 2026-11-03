from datetime import date, datetime

import pytest

from collectors import melon, notify, theme, verify, youtube
from collectors.common import KST, domain


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOW_OVERRIDE", "2026-11-03T08:30:00+09:00")


# ---- verify ----

ARTICLES = {
    "N1": {"link": "https://news.google.com/a1", "publisher": "연합뉴스", "publisher_domain": "yna.co.kr"},
    "N2": {"link": "https://news.google.com/a2", "publisher": "동아일보", "publisher_domain": "donga.com"},
    "N3": {"link": "https://news.google.com/a3", "publisher": "연합뉴스", "publisher_domain": "yna.co.kr"},
}
T = date(2026, 11, 3)


def ev(**kw):
    base = {"type": "broadcast", "title": "인기가요", "date": "2026-11-08", "end_date": None, "time": "15:20",
            "sources": []}
    base.update(kw)
    return base


def test_two_publishers_pass():
    ok, src, why = verify.verify(ev(sources=["N1", "N2"]), ARTICLES, set(), T)
    assert ok and len(src) == 2


def test_same_publisher_twice_fails():
    ok, _, why = verify.verify(ev(sources=["N1", "N3"]), ARTICLES, set(), T)
    assert not ok and "부족" in why


def test_invented_url_is_ignored():
    ok, src, _ = verify.verify(ev(sources=["N1", "https://made-up.example.com/x"]), ARTICLES, set(), T)
    assert not ok and len(src) == 1


def test_seen_url_counts_and_official_wins():
    url = "https://x.com/RESCENE_official/status/1"
    ok, _, why = verify.verify(ev(sources=[url]), ARTICLES, {url}, T)
    assert ok and why == "공식 출처"


def test_past_schedule_rejected_but_recent_collab_kept():
    assert not verify.verify(ev(date="2026-10-01", sources=["N1", "N2"]), ARTICLES, set(), T)[0]
    assert verify.verify(ev(type="collab", date="2026-10-20", time=None, sources=["N1", "N2"]), ARTICLES, set(), T)[0]
    assert not verify.verify(ev(type="collab", date="2026-09-01", time=None, sources=["N1", "N2"]), ARTICLES, set(), T)[0]


def test_bad_time_rejected():
    assert not verify.verify(ev(time="7pm", sources=["N1", "N2"]), ARTICLES, set(), T)[0]


def test_domain():
    assert domain("https://news.kbs.co.kr/a") == "kbs.co.kr"
    assert domain("https://m.blog.naver.com/x") == "naver.com"


# ---- chart alerts ----

def chart(*pairs):
    return {"entries": [{"song_id": s, "title": s, "rank": r} for s, r in pairs]}


def test_chart_alerts():
    prev = chart(("a", 2), ("b", 15))
    cur = chart(("a", 1), ("b", 9), ("c", 80))
    keys = {a["key"].split(":")[2] for a in melon.chart_alerts(prev, cur)}
    assert keys == {"1", "top10", "in"}
    assert melon.chart_alerts(None, cur) == []  # 첫 실행은 알림 없음


# ---- youtube ----

def test_detect_members():
    assert youtube.detect_members("[추석 특집] 제나의 트로트 메들리") == ["제나"]
    assert youtube.detect_members("메이크업 브이로그") == []
    assert set(youtube.detect_members("WONI & LIV dance")) == {"원이", "리브"}


def test_duration_and_milestone():
    assert youtube.parse_duration("PT1M5S") == 65
    pts = [["2026-10-27", 9_000_000], ["2026-11-03", 9_700_000]]
    m = youtube.milestone_eta(pts, 9_700_000)
    assert m["target"] == 10_000_000 and 2 < m["eta_days"] < 4


# ---- theme ----

def test_default_theme_passes_contrast():
    assert theme.problems(theme.DEFAULT["colors"]) == []


def test_bad_theme_rejected():
    c = dict(theme.DEFAULT["colors"], text="#EEEEEE")
    assert any("text/bg" in p for p in theme.problems(c))
    assert theme.problems(dict(c, bg="oops"))


# ---- notify ----

def test_schedule_alerts_window():
    t = datetime(2026, 11, 8, 14, 0, tzinfo=KST)
    events = [
        {"id": "x", "type": "broadcast", "title": "인기가요", "date": "2026-11-08", "time": "15:20", "sources": []},
        {"id": "y", "type": "broadcast", "title": "늦은 방송", "date": "2026-11-08", "time": "20:00", "sources": []},
        {"id": "v", "type": "vote", "title": "MMA 투표", "date": "2026-11-01", "end_date": "2026-11-08"},
    ]
    keys = {a["key"] for a in notify.schedule_alerts(events, t)}
    assert keys == {"soon:x", "deadline24:v"}


def test_register_dedupes():
    a = {"key": "k1", "cat": "video", "title": "t", "body": "b", "url": "u", "at": "2026-11-03T08:00:00+09:00"}
    assert len(notify.register([a])) == 1
    assert notify.register([a]) == []


def test_upcoming_days_and_digest():
    from collectors.common import save
    save("members.json", {"members": {"제나": {"birthday": "2008-11-27"}}})
    save("albums.json", {"albums": [{"type": "EP", "title": "PULSE", "date": "2025-11-05"}]})
    days = notify.upcoming_days(datetime(2026, 11, 3, 9, tzinfo=KST))
    titles = [d["title"] for d in days]
    assert "'PULSE' 발매 1주년" in titles and "제나 생일" in titles
    d = notify.build_digest("morning", datetime(2026, 11, 3, 9, tzinfo=KST))
    assert d["title"].startswith("☀️") and d["body"]
