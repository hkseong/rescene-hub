# rescene-hub

리센느(RESCENE) 활동 정보를 **사람 손 없이** 자동 수집해 보여 주는 팬 패널.

- 사이트: https://hkseong.github.io/rescene-hub/
- 기획서: [SPEC.md](SPEC.md) · 작업 보고: [REPORT.md](REPORT.md)

## 구조

| 경로 | 내용 |
|---|---|
| `collectors/` | Python 수집기 (멜론·유튜브·뉴스·Claude). `python -m collectors.run` |
| `tests/` | 파서·검증 규칙 테스트 (`python -m pytest -q`), 저장된 원본 페이지 `fixtures/` |
| `site/` | 정적 PWA (GitHub Pages) |
| `worker/` | Cloudflare Worker: 푸시 구독 저장, 카카오 챗봇 스킬 |
| `.github/workflows/` | `collect`(15분 cron) · `pages` · `test` · `repair`(`/fix` 자가 수리) |

수집 결과는 `data` 브랜치에 JSON으로 덮어쓰기 저장되고, 사이트는 이를 직접 읽습니다.
