# C3P 협의체 해체·재편 결정 기록 (2026-09-15)

## 결정

- Codex = 지휘, Antigravity = `antigravity-bridge` MCP로 호출되는 작업자.
- 투표·정족수·상호 고발(CALL_OUT/WHISTLEBLOW)·소켓 브로커·세션 훅·예산절약/부재 모드를 제거한다.
- 이전 상태 전체는 태그 `c3p-v2-archive`(커밋 `5a363eb`)에 있다.

## 근거

1. **역할 구조가 바뀌면 합의 장치가 무의미하다.** 한 도구가 다른 도구의 작업자이면 표결 대상이 없다.
2. **규모 대비 가치.** 문서 62개, Python 약 8,000줄, 테스트 37개, 매 호출마다 실행되는 훅. 규칙이 운영 중 계속 개정됐다.
3. **검증되지 않은 주장이 규칙에 들어갔다.** "입력 토큰 85% 이상 절감"이 규칙 본문에 있었으나 자체 벤치마크는 `EXPLORATORY_UNVERIFIED`였다.
4. **승인 상속 규칙의 충돌.** "Codex 1회 승인 시 나머지 도구 자동 승인"은 경계별 승인 원칙과 충돌했다.
5. **대체 수단.** Codex는 자체 하위 에이전트와 MCP 위임을 지원한다. 멀티 에이전트는 토큰과 검토 부담이 크므로 작업자는 하나로 제한한다.

## 함께 정리한 전역 설정

- Codex: `approval_policy` on-request, `sandbox_mode` workspace-write, 데스크톱 강제 푸시·PR 자동 병합 끔, 영구 `git push` 허용 규칙 제거.
- MCP: 유지 `antigravity-bridge`, `notebooklm`. 그 외 제거.
- 전역 규칙: Antigravity·Codex 두 도구용 경량본(v4.1.0).

## 참고 자료

- [Stop Installing Every MCP Server: The Context Window Cost](https://metablogue.com/mcp-servers-context-window/)
- [Codex Sandbox](https://developers.openai.com/codex/concepts/sandboxing)
- [Multi-Agent Orchestration With Codex](https://www.firecrawl.dev/blog/codex-multi-agent-orchestration)
- [Codex CLI Custom Agent Definitions](https://codex.danielvaughan.com/2026/04/27/codex-cli-custom-agent-definitions-toml-specialised-subagents/)
- [vacnex/codex-antigravity-subagent](https://github.com/vacnex/codex-antigravity-subagent)