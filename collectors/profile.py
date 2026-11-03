"""Member birthdays, found by web search and published only with two independent sources."""
from __future__ import annotations

from datetime import date

from . import config, llm
from .common import domain, iso, load, save

SCHEMA = {
    "type": "object",
    "properties": {
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": list(config.MEMBERS)},
                    "birthday": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "birthday", "sources"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["members"],
    "additionalProperties": False,
}

SYSTEM = """걸그룹 리센느(RESCENE, 소속사 더뮤즈엔터테인먼트) 멤버 원이, 리브, 미나미, 메이, 제나의 생년월일을 웹검색으로 찾는다.
가족·동명이인의 생일과 헷갈리지 마라. 확인되지 않으면 birthday=null.
sources에는 그 생일이 실제로 적힌 웹검색 결과 URL을 그대로 넣는다(가능하면 서로 다른 사이트 2곳 이상). 본 적 없는 URL은 만들지 마라."""


def missing(members: dict) -> list[str]:
    return [m for m in config.MEMBERS if not members.get(m, {}).get("birthday")]


def accept(entry: dict, seen_urls: set[str]) -> list[str] | None:
    try:
        date.fromisoformat(entry["birthday"] or "")
    except ValueError:
        return None
    urls = [u for u in entry["sources"] if u.rstrip("/") in {s.rstrip("/") for s in seen_urls}]
    return urls if len({domain(u) for u in urls}) >= 2 else None


def collect_profile() -> list[dict]:
    data = load("members.json", {"members": {}})
    todo = missing(data["members"])
    data["checked_at"] = iso()
    if todo:
        out, seen = llm.ask_json(model=config.MODEL_EVENTS, system=SYSTEM, schema=SCHEMA, purpose="profile",
                                 content=f"생일을 찾을 멤버: {', '.join(todo)}", web_search=5, effort="medium")
        for e in out["members"]:
            if e["name"] not in todo:
                continue
            urls = accept(e, set(seen))
            if urls:
                data["members"][e["name"]] = {"birthday": e["birthday"], "sources": urls, "verified_at": iso()}
    data["debut"] = config.DEBUT
    save("members.json", data)
    return []
