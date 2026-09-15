# codex-3p-orchestrator

Codex가 지휘하고 Antigravity를 작업자로 쓰는 개인 AI 작업 체계의 설정 저장소다.

2026-09-15에 세 도구의 합의 체계였던 **C3P 협의체**를 해체하고 가볍게 재편했다. 이전 코드·문서·테스트 전체는 Git 태그 `c3p-v2-archive`에 그대로 남아 있다.

## 구조

| 역할 | 도구 | 하는 일 |
|---|---|---|
| 지휘 | Codex | 계획, 위임, 결과 검증, 사용자 보고 |
| 작업자 | Antigravity (`agy` CLI) | Codex가 맡긴 탐색·조사·테스트·화면 확인 |

## 연결 방식

- Codex 전역 MCP 서버 `antigravity-bridge`가 `agy` CLI를 도구로 노출한다: `antigravity_continue`, `antigravity_result`, `antigravity_jobs`, `antigravity_cancel`, `antigravity_cleanup`, `antigravity_models`, `antigravity_agents`, `antigravity_health` 등.
- 브리지 원본은 저장소 `260718_agentic-ai-platform-optimization`의 `mcp/antigravity-bridge`에 있다. 샌드박스를 켜고 자동 승인을 끈 보안 강화 포크다.
- Codex에서 쓰는 예: `antigravity-bridge로 docs 폴더의 깨진 링크를 조사시키고, 결과는 네가 직접 확인해서 보고해`

## 파일

| 파일 | 내용 |
|---|---|
| `AGENTS.md` | Codex 지휘·위임·승인 규칙 |
| `GEMINI.md` | Antigravity 작업자 규칙 |
| `docs/C3P_RETIREMENT_DECISION.md` | 해체 결정의 근거와 제거 목록 |

## 이전 체계 보기·복구

```bash
git show c3p-v2-archive --stat
```

```bash
git switch -c c3p-restore c3p-v2-archive
```