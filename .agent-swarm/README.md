# Agent Swarm Control Plane

이 폴더는 `D:\D_Workspace_NB\-agentic-ai-workspace\260823_codex-3p-orchestrator`에서 Codex, Claude Code, Antigravity가 협업하는 유일한 로컬 제어면(control plane)이다.

`D:\D_Workspace_NB\-agentic-ai-workspace\260823_week3`는 폐기된 경로다. 해당 경로에 `.agent-swarm`, 문서 또는 소스 복사본을 만들지 않는다. CLI 실행 위치가 달라도 `csc.py`가 있는 이 정본 루트를 `project-root`와 자식 프로세스 `cwd`로 사용한다.

## 기본 원칙

- Codex가 유일한 오케스트레이터이자 외부효과 승인 경계다.
- Claude Code와 Antigravity는 한 번에 하나의 명확한 작업만 받는다.
- 기본 권한은 읽기 전용이다. 파일 수정은 에이전트별 `tasks/` 카드에 지정된 경로만 허용한다.
- `commit`, `push`, 배포, 계정·권한 변경, 패키지·모델 설치는 하위 에이전트가 수행하지 않는다.
- Antigravity는 `auto_approve:false`, `sandbox:true`를 유지한다.
- 메시지는 Codex가 전달하고 `messages/relay-log.md`에 요약한다.
- 실행 결과는 주장으로 끝내지 않고 재현 가능한 검증 결과와 함께 보고한다.

## 구조

- `registry.md`: 활성 세션과 역할의 사람이 읽을 수 있는 정본
- `protocol.md`: 통신·소유권·승인·실패 처리 규약
- `tasks/`: 에이전트별 현재 작업 카드
- `messages/relay-log.md`: Codex가 중계한 요청·응답·결정 로그
- `chat/ROOM.md`: 사용자와 세 도구가 함께 읽는 실시간 통합 채팅 타임라인
- `chat/<agent>.md`: 각 에이전트가 자기 발언만 추가하는 전용 채널
- `results/`: 에이전트가 제출한 결과 문서

## 운영 흐름

1. Codex가 `docs/00_PROJECT_INDEX.md`와 현재 작업 카드를 읽는다.
2. 독립적인 읽기 작업만 병렬 위임한다.
3. 각 에이전트는 관찰 사실, 가설, 위험, 제안을 분리해서 답한다.
4. Codex가 충돌을 해소하고 사용자 결정을 요청한다.
5. 승인된 구현만 단일 소유자로 직렬 실행한다.
6. Codex가 테스트와 전체 상태를 재검증하고 `docs`와 relay log를 갱신한다.

## 채팅방 바로가기

업무 대화는 `chat/ROOM.md`를 기준으로 한다. 에이전트별 원문 발언은 각자 전용 파일에 남기고 Codex가 ROOM에 중계한다.
