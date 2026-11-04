"""Weekly backfill of pop-ups, collabs, goods and ads since debut, so past and long-running ones show up.

The daily events job only reads the last 7 days of news. Pop-ups are often announced on
pop-up listing sites and run for weeks, and ad deals are announced once, so this job asks
Claude to search the web for the whole history. The same strict rule applies (verify.py).
"""
from __future__ import annotations

from datetime import date

from . import config, events, llm
from .common import iso, load, save, today

GROUPS = [
    ("popup", "goods"),
    ("collab", "ad"),
]

GUIDE = {
    "popup": "팝업스토어 (예: 백화점·성수·편의점 매장 팝업, 브랜드 콜라보 팝업). date=시작일, end_date=종료일",
    "goods": "공식 굿즈·MD 판매, 편의점·브랜드 한정 상품 (date=판매 시작일)",
    "collab": "브랜드 협업 제품 출시·콜라보 (편의점 빵·도시락, 애니메이션·게임 협업 등)",
    "ad": "광고 모델 발탁·새 광고 공개 (title에 브랜드명, 구매 혜택은 perk)",
}

SYSTEM = events.SYSTEM + """

지금은 '지난 이력 정리' 모드다. 데뷔(2024-03-26) 이후 지금까지와 예정된 것 중 요청한 종류만 빠짐없이 모아라.
- 웹검색을 적극적으로 써라. 팝업 정보 사이트, 브랜드 공식 공지, 뉴스 기사 모두 좋다.
- 디시인사이드 리센느 갤러리 같은 팬 커뮤니티에서 '리센느 팝업', '포카 증정', '콜라보' 정리 글을 찾아 빠진 항목의 실마리로 써라. 단, 그 항목의 sources는 공식·언론·팝업 정보 사이트 URL로 채워야 한다.
- 이미 끝난 것도 넣는다. 날짜를 확정할 수 없으면 넣지 마라.
- 각 항목의 sources에는 실제로 본 웹검색 결과 URL을 모두 넣어라. 서로 다른 사이트 2곳 이상이면 가장 좋다."""


def collect_archive() -> list[dict]:
    store = load("events.json", {"events": [], "pending": []})
    articles = {a["id"]: a for a in load("news.json", {"articles": []})["articles"]}
    t = date.fromisoformat(today())
    first_run = "archive_updated" not in store
    alerts = []
    for types in GROUPS:
        known = [e for e in store["events"] if e["type"] in ("popup", "goods", "collab", "ad")]
        content = (
            f"오늘은 {today()}이다.\n\n"
            f"[모을 종류]\n" + "\n".join(f"- {k}: {GUIDE[k]}" for k in types) + "\n\n"
            f"[참고: 이미 확인된 항목 — 이 목록은 불완전하다. 같은 것을 다시 찾으면 same_as로 id를 쓰고 새 출처·혜택을 보태라]\n"
            + ("\n".join(events._compact(e) for e in known) or "(없음)") + "\n\n"
            "웹검색을 여러 번 해서(연도별·장소별·브랜드별로 나눠서) 위 목록에 없는 항목을 찾아라. "
            "검색 없이 답하지 마라."
        )
        out, seen = llm.ask_json(model=config.MODEL_EVENTS, system=SYSTEM, content=content,
                                 schema=events.SCHEMA, purpose=f"archive_{'_'.join(types)}",
                                 web_search=6, effort="high")
        proposed = [e for e in out["events"] if e["type"] in types]
        alerts += events.merge(store, proposed, articles, set(seen), t, notify=not first_run, history=True)
    store["archive_updated"] = iso()
    save("events.json", store)
    return alerts
