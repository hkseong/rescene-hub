"""Web push end to end without a browser: encrypt with pywebpush, decrypt as the browser would."""
import base64
import json

import http_ece
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from collectors import notify


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def browser():
    key = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    sub = {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": b64(pub), "auth": b64(auth)}}
    return key, auth, sub


@pytest.fixture
def vapid(monkeypatch):
    k = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("VAPID_PRIVATE_KEY", b64(k.private_numbers().private_value.to_bytes(32, "big")))


class Resp:
    def __init__(self, code):
        self.status_code = code
        self.text = ""
        self.headers = {}
        self.reason = "Gone" if code == 410 else "Created"


def test_payload_decrypts_in_browser(browser, vapid, monkeypatch):
    key, auth, sub = browser
    sent = {}

    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        sent.update(url=url, data=data, headers=headers)
        return Resp(201)

    monkeypatch.setattr("requests.post", fake_post)
    payload = {"title": "📺 리센느 출연 영상 떴어요!", "body": "본문", "url": "https://youtu.be/x", "tag": "k"}
    assert notify.send({"id": "1", "subscription": sub}, payload) is True
    assert sent["url"] == sub["endpoint"]
    assert sent["headers"]["Authorization"].startswith("vapid t=")
    assert sent["headers"]["Content-Encoding"] == "aes128gcm"
    plain = http_ece.decrypt(sent["data"], private_key=key, auth_secret=auth, version="aes128gcm")
    assert json.loads(plain) == payload


def test_gone_subscription_reported(browser, vapid, monkeypatch):
    _, _, sub = browser
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(410))
    assert notify.send({"id": "1", "subscription": sub}, {"title": "t"}) is False


def test_dispatch_respects_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from datetime import datetime
    from collectors.common import KST
    subs = [
        {"id": "a", "prefs": {"digest_morning": True, "digest_evening": True, "realtime": {"video": True}}},
        {"id": "b", "prefs": {"digest_morning": False, "digest_evening": True, "realtime": {}}},
    ]
    got = []
    monkeypatch.setattr(notify, "subscribers", lambda: subs)
    monkeypatch.setattr(notify, "send", lambda s, p: got.append((s["id"], p["tag"])) or True)
    monkeypatch.setattr(notify, "_remove", lambda ids: None)
    alerts = [{"key": "video:1", "cat": "video", "title": "t", "body": "b", "url": "u", "at": "x"},
              {"key": "chart:1", "cat": "chart", "title": "t", "body": "b", "url": "u", "at": "x"}]
    stats = notify.dispatch(alerts, datetime(2026, 11, 4, 9, 5, tzinfo=KST))
    assert stats["digests"] == ["morning"]
    assert sorted(got) == [("a", "digest-morning"), ("a", "video:1")]
    # 같은 슬롯에서는 다이제스트를 다시 보내지 않는다
    got.clear()
    notify.dispatch([], datetime(2026, 11, 4, 9, 20, tzinfo=KST))
    assert got == []
