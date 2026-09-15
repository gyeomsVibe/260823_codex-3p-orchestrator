# C3P 협의체 해체·재편 결정 기록 (2026-09-15)

## 결정

- Codex = 지휘, Antigravity = `antigravity-bridge` MCP로 호출되는 작업자, Claude Code = 분리.
- 투표·정족수·상호 고발(CALL_OUT/WHISTLEBLOW)·소켓 브로커·세션 훅·예산절약/부재 모드를 제거한다.
- 전체 이전 상태는 태그 `c3p-v2-archive`(커밋 `5a363eb`)에 보존한다. 해체 시점의 미커밋 Codex 변경은 `archive/codex-uncommitted-20260915.patch`에 보존한다.

## 근거

1. **역할 구조가 바뀌면 합의 장치가 무의미하다.** 한 도구가 다른 도구의 작업자이면 표결 대상이 없다.
2. **규모 대비 가치.** 문서 62개, Python 약 8,000줄, 테스트 37개, 매 프롬프트·매 도구 호출마다 실행되는 훅 5종. 규칙이 운영 중 계속 개정됐다(보고 창구 단일화 → 정정 → 두 모드 계약 → 모드 종료).
3. **검증되지 않은 주장이 규칙에 들어갔다.** "입력 토큰 85% 이상 절감"이 규칙 본문에 있었으나 자체 벤치마크는 `EXPLORATORY_UNVERIFIED`였다.
4. **승인 상속 규칙의 충돌.** "Codex 1회 승인 시 나머지 도구 자동 승인"은 전역 규칙의 경계별 승인과 충돌했다.
5. **대체 수단의 등장.** Codex는 자체 하위 에이전트(MultiAgentV2, `max_threads`·`max_depth` 제어)와 MCP 위임을 지원한다. 멀티 에이전트는 단일 세션보다 토큰이 크게 늘고 검토 병목이 생기므로 작업자는 하나로 제한한다.

## 함께 정리한 전역 설정

- Codex: `approval_policy` never → on-request, `sandbox_mode` danger-full-access → workspace-write, 데스크톱 강제 푸시·PR 자동 병합 끔, 영구 `git push` 허용 규칙 제거.
- MCP: `vibe-clinic` 전면 제거, Codex `claude-code`·`local-agent-runtime` 제거. 유지: Codex `antigravity-bridge`, 각 도구 `notebooklm`.
- 스킬: Claude 중복 슬래시 별칭 스킬 10개, 모든 도구의 `vibe-check`, Antigravity 전역의 `codex-3p-orchestrator` 제거.
- 전역 규칙 v4.0.0: 127줄 → 약 40줄 경량본. C3P 명칭·원터치 진단·예산 거버넌스·저장소 조직 일반론을 제거하고 소통·안전·소유권·검증·보고 핵심만 유지.

## 참고 자료

- [CLAUDE.md Best Practices: What the Evidence Supports (2026)](https://www.alexdunlop.com/writing/claude-md-best-practices)
- [Stop Installing Every MCP Server: The Context Window Cost](https://metablogue.com/mcp-servers-context-window/)
- [Codex Sandbox](https://developers.openai.com/codex/concepts/sandboxing)
- [Multi-Agent Orchestration With Codex](https://www.firecrawl.dev/blog/codex-multi-agent-orchestration)
- [Codex CLI Custom Agent Definitions](https://codex.danielvaughan.com/2026/04/27/codex-cli-custom-agent-definitions-toml-specialised-subagents/)
- [vacnex/codex-antigravity-subagent](https://github.com/vacnex/codex-antigravity-subagent)