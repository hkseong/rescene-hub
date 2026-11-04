from datetime import date

import pytest

from collectors import events, news, verify

T = date(2026, 11, 4)
SEEN = {"https://popga.co.kr/popup/1", "https://www.newsis.com/view/1", "https://gall.dcinside.com/mgallery/board/view/?id=rescene&no=1",
        "https://theqoo.net/square/1"}


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOW_OVERRIDE", "2026-11-04T10:00:00+09:00")


def raw(**kw):
    base = {"same_as": None, "type": "popup", "title": "더현대 팝업 'Scent Archive'", "date": "2025-09-15",
            "end_date": "2025-09-23", "time": None, "place": "더현대 서울", "members": [], "summary": "팝업",
            "perk": None, "link": None, "sources": ["https://popga.co.kr/popup/1", "https://www.newsis.com/view/1"]}
    base.update(kw)
    return base


def test_history_mode_accepts_past_items_daily_mode_rejects():
    assert verify.verify(raw(), {}, SEEN, T, history=True)[0]
    assert not verify.verify(raw(), {}, SEEN, T)[0]
    ok, _, why = verify.verify(raw(date="2023-05-01", end_date=None), {}, SEEN, T, history=True)
    assert not ok and "범위" in why


def test_community_posts_are_leads_not_sources():
    ok, src, why = verify.verify(raw(sources=["https://popga.co.kr/popup/1",
                                               "https://gall.dcinside.com/mgallery/board/view/?id=rescene&no=1",
                                               "https://theqoo.net/square/1"]), {}, SEEN, T, history=True)
    assert not ok and len(src) == 1 and "1곳" in why


def test_merge_keeps_history_and_alerts_only_for_live_items():
    store = {"events": [], "pending": []}
    live = raw(title="CU 올림픽광장점 팝업", date="2026-11-01", end_date="2026-11-30", perk="2만원 구매 시 포카 증정")
    alerts = events.merge(store, [raw(), live], {}, SEEN, T, notify=True, history=True)
    assert len(store["events"]) == 2
    assert [a["title"] for a in alerts] == ["🏬 [팝업] CU 올림픽광장점 팝업"]
    assert "포카" in alerts[0]["body"]
    # 같은 항목을 same_as로 다시 보내면 합쳐지고 알림은 없다
    again = raw(same_as=store["events"][0]["id"])
    assert events.merge(store, [again], {}, SEEN, T, notify=True, history=True) == []
    assert len(store["events"]) == 2


def test_history_rejects_do_not_pile_up_in_pending():
    store = {"events": [], "pending": []}
    events.merge(store, [raw(sources=["https://popga.co.kr/popup/1"])], {}, SEEN, T, notify=True, history=True)
    assert store["events"] == [] and store["pending"] == []


def test_apply_stories_groups_and_fills_gaps():
    arts = [{"id": "A", "published_at": "2026-11-04T10:00"}, {"id": "B", "published_at": "2026-11-04T11:00"},
            {"id": "C", "published_at": "2026-11-04T09:00"}]
    news.apply_stories(arts, [["A", "B", "Z"], ["A"]])
    assert [a["story"] for a in arts] == ["B", "B", "C"]
