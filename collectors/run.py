"""Entry point. Runs every job that is due, records health, then dispatches notifications.

python -m collectors.run                 # cron 모드
python -m collectors.run --only melon_chart --force --no-notify
python -m collectors.run --only melon_chart --smoke   # 수리 검증용: 임시 폴더에서 1회 실행, 실패 시 exit 1
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import traceback
from datetime import timedelta

from . import config, events, health, llm, melon, notify, profile, theme, youtube
from .common import iso, load, now, parse_iso, save

JOBS = {
    "melon_chart": melon.collect_chart,
    "melon_vote": melon.collect_vote,
    "melon_albums": melon.collect_albums,
    "theme": theme.collect_theme,
    "youtube": youtube.collect_youtube,
    "appearances": youtube.collect_appearances,
    "events": events.collect_events,
    "profile": profile.collect_profile,
}
LLM_JOBS = {"events", "profile", "theme", "appearances"}


def interval(job: str) -> int:
    if job == "events" and llm.over_budget():
        return config.EVENTS_INTERVAL_OVER_BUDGET
    return config.INTERVALS[job]


def is_due(job: str, state: dict) -> bool:
    last = state.get("last_run", {}).get(job)
    if not last:
        return True
    # cron이 몇 분 일찍 깨는 것을 감안해 5분 여유
    return now() - parse_iso(last) >= timedelta(minutes=interval(job) - 5)


def budget_guard(state: dict) -> None:
    month = now().strftime("%Y-%m")
    if llm.over_budget() and state.get("budget_alerted") != month:
        notify.admin("💸 이번 달 API 비용 $20 도달",
                     f"현재 ${llm.month_cost():.2f}. 일정 수집을 하루 1회로 줄였습니다.")
        state["budget_alerted"] = month


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    if args.smoke:
        # 실제 데이터 사본 위에서 실행 → 실데이터·알림에 영향 없음
        tmp = tempfile.mkdtemp()
        src = os.environ.get("DATA_DIR")
        if src and os.path.isdir(src):
            shutil.copytree(src, tmp, dirs_exist_ok=True)
        os.environ["DATA_DIR"] = tmp
        args.force, args.no_notify = True, True

    state = load("state.json", {})
    failed = []
    alerts = []
    for job, fn in JOBS.items():
        if args.only and job not in args.only:
            continue
        if not args.force and not is_due(job, state):
            continue
        if job in LLM_JOBS and not os.environ.get("ANTHROPIC_API_KEY"):
            print(f"[skip] {job}: ANTHROPIC_API_KEY 없음")
            continue
        print(f"[run] {job}")
        try:
            got = fn() or []
            alerts += got
            print(f"  ok, alerts={len(got)}")
            if not args.smoke:
                health.record(job, True)
        except Exception:
            err = traceback.format_exc()
            print(err, file=sys.stderr)
            failed.append(job)
            if not args.smoke:
                health.record(job, False, err)
        state = load("state.json", {})  # 작업이 state를 갱신했을 수 있음
        state.setdefault("last_run", {})[job] = iso()
        save("state.json", state)

    if not args.smoke:
        budget_guard(state)
        save("state.json", state)
    if not args.no_notify:
        evs = load("events.json", {"events": []})["events"]
        fresh = notify.register(alerts + notify.schedule_alerts(evs, now()))
        try:
            print("[notify]", notify.dispatch(fresh, now()))
        except Exception:
            traceback.print_exc()
    return 1 if (args.smoke and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
