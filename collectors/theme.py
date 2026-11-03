"""Site palette from the latest album art. Applied only if it passes WCAG AA contrast checks."""
from __future__ import annotations

import base64
import re

from . import config, llm
from .common import http_get, iso, load, save

DEFAULT = {
    "album_id": None,
    "album": "default",
    "mood": "RESCENE",
    "colors": {
        "bg": "#FBF7F4", "surface": "#FFFFFF", "text": "#1F1A24", "muted": "#6B6170",
        "primary": "#7A4E9C", "on_primary": "#FFFFFF", "accent": "#E58FB0",
        "grad_from": "#F3E3F0", "grad_to": "#E6E9FB",
    },
}
KEYS = list(DEFAULT["colors"])
HEX = {"type": "string", "description": "#RRGGBB"}
SCHEMA = {
    "type": "object",
    "properties": {"mood": {"type": "string"}, "colors": {
        "type": "object", "properties": {k: HEX for k in KEYS}, "required": KEYS, "additionalProperties": False}},
    "required": ["mood", "colors"],
    "additionalProperties": False,
}
SYSTEM = """너는 팬 사이트의 UI 컬러 디자이너다. 앨범 커버의 컨셉과 무드를 살려 '라이트 모드' 웹앱 팔레트를 만든다.
- bg: 아주 밝은 배경(명도 높음), surface: 카드 배경(흰색에 가까움), text: 본문(진함), muted: 보조 텍스트
- primary: 버튼·강조색(앨범의 대표색), on_primary: primary 위 글자색, accent: 포인트색
- grad_from/grad_to: 헤더 배경 그라데이션(옅은 톤)
- 대비 조건(WCAG AA 4.5:1): text/bg, text/surface, muted/bg, muted/surface, on_primary/primary, primary/surface(3:1)
mood에는 앨범 컨셉을 한 줄(한국어, 20자 이내)로 적는다."""


def _lum(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def problems(c: dict) -> list[str]:
    bad = [k for k in KEYS if not re.fullmatch(r"#[0-9A-Fa-f]{6}", c.get(k, ""))]
    if bad:
        return [f"색상 형식 오류: {', '.join(bad)}"]
    rules = [("text", "bg", 4.5), ("text", "surface", 4.5), ("muted", "bg", 4.5), ("muted", "surface", 4.5),
             ("on_primary", "primary", 4.5), ("primary", "surface", 3.0)]
    out = [f"{a}/{b} 대비 {contrast(c[a], c[b]):.2f} < {m}" for a, b, m in rules if contrast(c[a], c[b]) < m]
    if _lum(c["bg"]) < 0.75:
        out.append("bg가 라이트 모드로 보기에 너무 어두움")
    return out


def collect_theme() -> list[dict]:
    albums = load("albums.json", {"albums": []})["albums"]
    cur = load("theme.json", DEFAULT)
    main = [a for a in albums if a.get("type") in ("EP", "정규", "싱글") and a.get("art")]
    if not main or cur.get("album_id") == main[0]["id"]:
        if "updated" not in cur:
            save("theme.json", dict(DEFAULT, updated=iso()))
        return []
    album = main[0]
    if cur.get("rejected", {}).get("album_id") == album["id"]:
        return []
    img = http_get(re.sub(r"_\d+\.jpg$", "_500.jpg", album["art"]))
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                      "data": base64.standard_b64encode(img.content).decode()}},
        {"type": "text", "text": f"리센느 '{album['title']}' ({album['date']}) 앨범 커버야. 팔레트를 만들어줘."},
    ]
    feedback = ""
    for _ in range(2):
        out, _ = llm.ask_json(model=config.MODEL_THEME, system=SYSTEM, schema=SCHEMA, purpose="theme",
                              content=content + ([{"type": "text", "text": feedback}] if feedback else []),
                              effort="low", max_tokens=4000)
        issues = problems(out["colors"])
        if not issues:
            save("theme.json", {"album_id": album["id"], "album": album["title"], "mood": out["mood"],
                                "colors": out["colors"], "art": album["art"], "updated": iso()})
            return []
        feedback = "이전 팔레트가 대비 검사에 실패했어. 고쳐줘: " + "; ".join(issues)
    # 두 번 다 실패하면 이전 테마를 그대로 둔다.
    cur["rejected"] = {"album_id": album["id"], "issues": issues, "at": iso()}
    save("theme.json", cur)
    return []
