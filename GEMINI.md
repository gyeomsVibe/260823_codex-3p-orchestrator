# Antigravity Project Rules — Codex 3P Orchestrator

## 물리 워크스페이스 불변 경계 (Canonical Physical Workspace)
- 이 프로젝트의 유일한 정본 물리 경로는 `D:\D_Workspace_NB\-agentic-ai-workspace\260823_codex-3p-orchestrator`입니다.
- 임시 앱 경로(`C:\Program Files\WindowsApps\...` 등)는 무효하며 워크스페이스로 취급하지 않습니다.
- 모든 도구 호출, 셸 실행(`Cwd`), 파일 조회/생성/수정은 반드시 이 정본 물리 루트를 기준으로 수행합니다.
- 거버넌스 및 3자 오케스트레이션 규약은 [AGENTS.md](file:///D:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/AGENTS.md)를 절대 기준으로 따릅니다.

## 사용자 우선 원칙 (User-First Principle) — 기본값
- 정본은 `.agent-swarm/USER_FIRST_PRINCIPLE.md` 이며 `AGENTS.md` 0.5절과 동일한 효력을 가집니다.
- 대상 사용자는 **"모르는 걸 모르는 사용자"** 입니다. 무엇을 물어야 할지 알 수 없는 위치에 있는 분입니다.
- 모든 사용자 대면 산출물은 **한국어 우선, 전문용어는 한국어(영어) 병기** 로 작성합니다.
- 모든 상태 표시에 **① 무엇이 ② 왜 그렇게 판단했는지 ③ 사용자가 무엇을 하면 되는지** 를 함께 적습니다.
- 나쁜 소식과 미검증 항목을 성공 항목보다 먼저 제시합니다.
- **오류수정은 3대 AI 도구 공통으로 동시 동기화**합니다. 공통 정본과 Codex·Claude Code·Antigravity 어댑터를 같은 변경 단위로 갱신하고, Antigravity 전용 오류는 다른 플랫폼에 복사하지 않고 해당 없음의 근거를 남깁니다.
- **C3P 발동 시 현재 프로젝트 전용 `.agent-swarm/dashboard.html`을 성공·실패 모두 생성합니다.** 실행마다 새 파일을 만들지 않고 같은 프로젝트 감시판을 갱신하며 상태 재계산 시각과 원문 경로를 표시합니다.
- 접두어 없는 **`c3p 발동`도 정식 호출문**이며 ASCII 영문 대소문자를 구분하지 않습니다. `c3p 발동`, `C3P 발동`, `C3p 발동`은 같은 절차입니다.
- 위반은 `CALL_OUT` 대상입니다.
