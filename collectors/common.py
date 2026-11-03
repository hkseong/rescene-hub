"""Shared helpers: data dir, JSON IO, time, HTTP."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

KST = timezone(timedelta(hours=9))
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def data_dir() -> Path:
    d = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(name: str, default=None):
    p = data_dir() / name
    if not p.exists():
        return {} if default is None else default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(name: str, obj) -> None:
    p = data_dir() / name
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
    tmp.replace(p)


def now() -> datetime:
    override = os.environ.get("NOW_OVERRIDE")
    if override:
        return datetime.fromisoformat(override)
    return datetime.now(KST)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(KST).isoformat(timespec="seconds")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST)


def today() -> str:
    return now().strftime("%Y-%m-%d")


def http_get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    headers.update(kw.pop("headers", {}))
    r = requests.get(url, headers=headers, timeout=kw.pop("timeout", 25), **kw)
    r.raise_for_status()
    return r


def domain(url: str) -> str:
    """Registrable-ish domain: news.kbs.co.kr -> kbs.co.kr, m.blog.naver.com -> naver.com."""
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 3 and parts[-1] == "kr" and parts[-2] in {"co", "or", "go", "ne", "re", "ac"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def norm_title(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


class CollectorError(Exception):
    """Raised when a source answers but its content no longer looks right."""
