from collectors import health


def test_issue_after_three_failures_then_auto_close(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    calls, admin = [], []
    monkeypatch.setattr(health, "_gh", lambda m, p, **kw: calls.append((m, p, kw.get("json"))) or
                        {"number": 7, "html_url": "https://github.com/x/issues/7"})
    monkeypatch.setattr(health.notify, "admin", lambda t, b, u=None: admin.append(t))

    for _ in range(2):
        health.record("melon_chart", False, "boom")
    assert calls == []
    health.record("melon_chart", False, "boom")
    assert calls[0][0] == "POST" and calls[0][1] == "/issues"
    assert "job:melon_chart" in calls[0][2]["body"] and calls[0][2]["labels"] == [health.LABEL]
    assert "고칠까요" in admin[0]

    health.record("melon_chart", False, "boom")  # 이슈는 한 번만
    assert len(calls) == 1

    health.record("melon_chart", True)
    assert ("PATCH", "/issues/7", {"state": "closed"}) in calls
    assert "복구" in admin[-1]
    st = health.load("status.json")["jobs"]["melon_chart"]
    assert st["consecutive_failures"] == 0 and "issue" not in st
