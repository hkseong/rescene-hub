"""Per-job health: consecutive failures open a GitHub issue and ask the owner for /fix approval."""
from __future__ import annotations

import os
import sys

import requests

from . import config, notify
from .common import iso, load, save

LABEL = "collector-broken"
JOB_LABEL = {
    "youtube": "유튜브 공식 채널", "appearances": "유튜브 출연 영상", "melon_chart": "멜론 차트",
    "melon_albums": "멜론 앨범", "melon_vote": "멜론 주간 인기상", "events": "일정·뉴스(LLM)",
    "profile": "멤버 프로필", "theme": "자동 테마",
}


def _gh(method: str, path: str, **kw):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    r = requests.request(method, f"https://api.github.com/repos/{config.REPO}{path}", timeout=20,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()
    return r.json()


def record(job: str, ok: bool, error: str | None = None) -> None:
    status = load("status.json", {"jobs": {}})
    j = status["jobs"].setdefault(job, {"consecutive_failures": 0})
    j["interval_min"] = config.INTERVALS[job]
    j["last_run"] = iso()
    if ok:
        if j.get("issue"):
            _resolve(job, j)
        j.update(last_success=iso(), consecutive_failures=0, error=None)
    else:
        j["consecutive_failures"] += 1
        j["error"] = (error or "")[-3000:]
        if j["consecutive_failures"] >= config.FAILURES_BEFORE_ISSUE and not j.get("issue"):
            _open_issue(job, j)
    status["updated"] = iso()
    save("status.json", status)


def _open_issue(job: str, j: dict) -> None:
    name = JOB_LABEL.get(job, job)
    body = (
        f"`{job}` 수집기가 {j['consecutive_failures']}회 연속 실패했습니다.\n\n"
        f"마지막 정상 데이터는 그대로 유지되고, 사이트에는 '업데이트 지연'이 표시됩니다.\n\n"
        f"**수리를 승인하려면 이 이슈에 `/fix` 라고 댓글을 달아 주세요.** "
        f"Claude가 원인을 고치고 테스트·실제 수집이 통과하면 자동으로 반영합니다.\n\n"
        f"<details><summary>오류 로그</summary>\n\n```\n{j['error']}\n```\n</details>\n\n"
        f"<!-- job:{job} -->"
    )
    try:
        issue = _gh("POST", "/issues", json={"title": f"[수집기 고장] {name} ({job})", "body": body,
                                              "labels": [LABEL]})
    except Exception as e:
        print(f"issue create failed: {e}", file=sys.stderr)
        issue = None
    url = issue["html_url"] if issue else f"https://github.com/{config.REPO}/actions"
    j["issue"] = issue["number"] if issue else -1
    notify.admin(f"🔧 {name} 수집기 고장, 고칠까요?", "이슈에 /fix 댓글을 달면 Claude가 수리합니다.", url)


def _resolve(job: str, j: dict) -> None:
    num = j.pop("issue")
    if num and num > 0:
        try:
            _gh("POST", f"/issues/{num}/comments", json={"body": "수집이 다시 정상 동작해서 자동으로 닫습니다. ✅"})
            _gh("PATCH", f"/issues/{num}", json={"state": "closed"})
        except Exception as e:
            print(f"issue close failed: {e}", file=sys.stderr)
    notify.admin(f"✅ {JOB_LABEL.get(job, job)} 수집 복구", "정상 동작을 확인했습니다.")
