# C3P 예산절약 모드 사용자 부재 중 협의 결과보고서

> 작성일: 2026-09-09  
> 범위: 예산절약 모드 발동문과 쿼터 관측 라우팅의 구현·검토·검증  
> 원문 정본: `.agent-swarm/messages/queue.jsonl`

## 먼저 알아야 할 상태

**예산절약 모드 발동문은 구현·테스트·Antigravity 최종 동의까지 완료됐습니다.**
반면, 쿼터 관측 라우팅에는 소진 상태 차단을 우회할 수 있는 미해결 결함이 보고되어,
전체 예산절약 모드를 최종 완료로 선언할 수는 없습니다.

사용자가 지금 하실 일은 없습니다. 다음 구현 단계에서 아래의 `남은 위험` 두 건을
수정하고 회귀 검증한 뒤에만 커밋 승인 여부를 판단하면 됩니다.

## 1. 무엇을 했는가

| 작업 | 결과 | 근거 |
|---|---|---|
| 쿼터 관측 분리 | `QuotaObservation`, `RuntimeMode`, 정책 래퍼와 전용 테스트 추가 | `model_runtime_routing/observation.py`, `tests/test_model_runtime_observation.py` |
| 예산절약 발동문 | 정확 일치·공백 정리·ASCII 대소문자 비구분·NFC 한글 정규화 구현 | `c3p_trigger.py`, `csc.py trigger` |
| 오발동 방어 | 설명 문장과 기존 `c3p 발동`을 새 발동문으로 오인하지 않음 | `tests/test_c3p_trigger.py` |
| 도구 간 규칙 이식 | Codex·Claude Code·Antigravity 어댑터와 C3P 스킬에 같은 호출 계약 반영 | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.agents/skills/codex-3p-orchestrator/SKILL.md` |
| 교차검토 | Antigravity가 발동문  ㅍ구현을 읽기 전용으로 검토하고 최종 `AGREE` 제출 | 원문 `RESULT-aae33e3971087c719ee61297`, `RESULT-6d8f4473d69644ff68d82487` |

## 2. 왜 이렇게 판단했는가

발동문은 닫힌 집합(closed set, 미리 정한 문구만 허용하는 방식)으로 처리했다.
따라서 `예산절약 모드의 설계를 검토한다` 같은 설명은 활성화하지 않고,
`C3P 예산절약 모드` 같은 정확한 호출만 기존 `activate --budget-saving` 경로로 보낸다.
이는 자연어 일부 일치에 따른 무단 워커 기동을 막기 위한 선택이다.

검증은 `python -m unittest discover -s tests`로 수행했고 **288개 통과, 1개 건너뜀**이었다.
실제 워커 재기동은 앞선 `PARTIAL_READY` 이력 때문에 반복 실행하지 않았다. 따라서
CLI 분기와 단위 테스트는 검증됐지만, 이번 변경 후의 실제 2/2 워커 등록은 미검증이다.

Claude Code에는 사용량 한도 소진(`quota_exhausted`) 원문 응답이 있어 능동 구현을 맡기지
않았다. Antigravity도 읽기 전용 하네스라 코드 작성 대신 설계·교차검토를 맡았다.

## 3. 남은 위험 — 완료 전 반드시 수정

| 심각도 | 재현 조건 | 영향 | 필요한 수정 |
|---|---|---|---|
| 높음 | `QuotaObservation(state="exhausted")`와 `policy_disabled=True`로 `route_with_observation` 호출 | 소진 상태가 `normal`로 덮여 기존 `BLOCKED` 판정을 우회할 수 있음 | 소진 관측은 정책 비활성화 여부와 무관하게 항상 `exhausted`로 전달하고 회귀 테스트 추가 |
| 중간 | 서로 다른 두 도구가 같은 `in_reply_to`, `correlation_id`, 본문을 제출 | 논리 중복 집계가 발신자를 구분하지 않아 독립 표결 하나를 버릴 수 있음 | 집계 키에 `sender`를 추가하고 서로 다른 발신자·같은 본문 테스트 추가 |

위 두 위험은 Antigravity의 읽기 전용 보고 `RESULT-347f1912253c0e82aaf7fd64`에 근거한다.
해당 보고는 테스트 실행 증거가 없는 설계 검토이므로, 수정 후 Codex의 실제 회귀 테스트가
필요하다.

## 4. 권한·운영 상태

- 코드 변경은 사용자 요청 범위의 가역적 로컬 수정으로만 수행했다.
- 외부 패키지 설치, 삭제, 자격증명 변경, 커밋, 푸시는 하지 않았다.
- 귀가 전 협의용 자동 감시(heartbeat, 주기적으로 상태를 확인하는 장치)는 목적 달성 후 삭제했다.
- 원문 메시지 큐를 직접 편집하지 않았다.

## 5. 다음 단계

1. 위 두 남은 위험을 최소 수정으로 해결한다.
2. 관련 단위 테스트와 전체 테스트를 다시 실행한다.
3. 실제 `python csc.py trigger "C3P 예산절약 모드"`의 워커 등록 결과를 한 번만 확인한다.
4. 결과가 모두 통과하면 변경 범위와 diff를 검토한 뒤 사용자에게 커밋 승인 여부를 묻는다.
