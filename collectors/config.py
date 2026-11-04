"""Static configuration: who RESCENE is, where to look, how often."""

ARTIST_NAMES = ["리센느", "RESCENE"]
MELON_ARTIST_ID = "3709231"

# 멤버: 표시 이름 → 제목에서 찾을 별칭
MEMBERS = {
    "원이": ["원이", "WONI", "WONEE"],
    "리브": ["리브", "LIV"],
    "미나미": ["미나미", "MINAMI"],
    "메이": ["메이", "MAY"],
    "제나": ["제나", "ZENA"],
}

DEBUT = {
    "date": "2024-03-26",
    "title": "데뷔 (싱글 'Re:Scene')",
    "sources": [
        "https://sports.khan.co.kr/article/202402181001003",
        "https://www.news1.kr/amp/entertain/music/5328092",
    ],
}

# group: official(공식) / wonee(원이 채널)
YOUTUBE_CHANNELS = [
    {"id": "UCtKtCiaWRz-d3EZn2xd1mdA", "name": "RESCENE", "group": "official"},
    {"id": "UCKoT9aB0axaxKum9sNXhZyg", "name": "RESCENE PLUS", "group": "official"},
    {"id": "UCWpY0eSJtyO-qNAPbKFRSSg", "name": "안녕하세요원이입니다잘부탁드립니다", "group": "wonee", "member": "원이"},
]
YOUTUBE_SEARCH_QUERIES = ["리센느", "RESCENE"]

NEWS_QUERIES = [
    "리센느",
    "RESCENE 리센느",
    "리센느 팝업",
    "리센느 콜라보",
    "리센느 음악방송",
    "리센느 투표",
    "리센느 광고",
    "리센느 포토카드",
]

# 실행 주기 (분). run.py가 15분마다 깨어나 due인 작업만 수행한다.
INTERVALS = {
    "youtube": 30,
    "appearances": 120,
    "melon_chart": 60,
    "melon_albums": 360,
    "melon_vote": 60,
    "events": 480,
    "archive": 7 * 24 * 60,  # 지난 팝업·콜라보·광고 이력, 주 1회
    "profile": 24 * 60,  # 빠진 생일이 없으면 LLM을 부르지 않음
    "theme": 360,
}
EVENTS_INTERVAL_OVER_BUDGET = 24 * 60

MODEL_EVENTS = "claude-sonnet-5-5"
MODEL_CLASSIFY = "claude-haiku-5-5"
MODEL_THEME = "claude-sonnet-5-5"

# USD per 1M tokens (input, output). 2026-11 기준 공식 단가.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.00, 20.00),
}
WEB_SEARCH_PRICE = 0.01  # per search
MONTHLY_BUDGET_SOFT = 20.0

DIGEST_HOURS_KST = {"morning": 9, "evening": 21}
FAILURES_BEFORE_ISSUE = 3

REPO = "hkseong/rescene-hub"
SITE_URL = "https://hkseong.github.io/rescene-hub/"
