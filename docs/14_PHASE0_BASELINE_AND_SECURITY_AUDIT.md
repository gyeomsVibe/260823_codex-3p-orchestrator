# Phase 0 기준선 및 보안 감사

- 실행일: 2026-09-04
- 상태: `PHASE 0 DONE / PHASE 1 USER APPROVAL REQUIRED`
- 범위: 읽기 검사, 테스트, 런타임 실측, 문서 기록
- 수행하지 않음: 코드 수정, 인증 토큰 생성, ACL 변경, Git 인덱스 변경, commit, push, Windows 자동 시작

## 1. 결론

현재 CSC는 개발 세션에서 브로커와 두 워커를 유지하고 43개 자동 테스트를 통과한다. 그러나 “두 워커가 연결됨”은 “두 모델이 기한 내 의사결정 가능함”을 뜻하지 않는다. Claude Code는 사용량 소진으로 판단 불능이었고, Antigravity는 프로세스·하트비트가 정상인 상태에서 판단 TASK를 완료하지 못해 dead-letter가 생겼다.

상시 무인 운용과 신뢰 가능한 3자 표결은 아직 승인할 수 없다. 다음 구현은 브로커 세션 인증과 원문/추적 기록 분리다.

## 2. 자동 테스트 기준선

실행 명령:

```powershell
python -m unittest discover -s tests -v
```

결과:

- 실행: 43
- 통과: 43
- 실패: 0
- 오류: 0
- 실행 시간: 3.910초
- 종료 코드: 0

포함 범위는 CLI 실행 제한, 워커 하트비트, 브로커 프로토콜·ROSTER, 영속 큐, 비상 정족수, 런타임 활성화, 원자 쓰기 재시도, Ollama 벤치마크 안전 게이트다.

## 3. 물리 작업 트리 감사

실행:

```powershell
git status --short --untracked-files=all
git status --short --ignored --untracked-files=all
```

관찰:

- 상태 항목: 78
- staged-added 상태가 포함된 항목: 52
- modified 상태가 포함된 항목: 12
- untracked: 26
- deleted: 0
- ignored-only: 29

`AM` 항목은 added와 modified 양쪽 집계에 포함되므로 위 수치를 단순 합산하지 않는다. 대량의 사용자·기존 세션 변경이 섞여 있어 현재 상태는 commit 후보가 아니다. 이번 단계에서 stage 또는 untrack을 수행하지 않았다.

Git은 `C:\Users\<USER>\.config\git\ignore` 접근 거부 경고를 냈다. 상태 명령은 종료 코드 0이었지만 전역 ignore 파일을 읽지 못했다는 한계를 보존한다.

## 4. 비밀정보 후보 휴리스틱 검사

검사 범위:

- `.agent-swarm` 아래 Markdown, JSON, JSONL, log
- 일반적인 Anthropic/OpenAI형 키, Google형 키, 장문 Bearer, 장문 key/token/password 할당 패턴
- 값은 출력하지 않고 파일명만 탐지하도록 실행
- 런타임 상태와 워커 메타데이터 경로는 제외

결과:

- 후보 파일: 0

이 결과는 “비밀정보가 절대 없다”는 보증이 아니다. 알려지지 않은 형식, 짧은 토큰, 자연어 개인정보, 바이너리, Git 과거 이력은 탐지 범위 밖이다. 따라서 원문 기록을 Git에서 분리하고 commit 전 별도 스캐너를 두는 Phase 2는 여전히 필요하다.

## 5. 런타임 실측

실측 시점의 상태:

| 구성요소 | PID | 프로세스 | 프로토콜 상태 |
|---|---:|---|---|
| Broker | 17008 | alive | `127.0.0.1:8765` |
| Claude adapter | 8404 | alive | ROSTER 등록, worker `ready`, 최신 heartbeat |
| Antigravity adapter | 20344 | alive | ROSTER 등록, worker `ready`, 최신 heartbeat |

- ROSTER 등록: `claude`, `antigravity`, count 2
- `tasks/in_progress.jsonl`: 0줄
- `messages/queue.jsonl`: 56줄
- Antigravity dead-letter: 1줄
- 해당 dead-letter 원 작업: `MSG-20260904-035756-966548-793f4236-COD-ALL`

모델 가용성:

- Claude Code: `quota_exhausted`; 재설정 안내 17:10 KST
- Antigravity: 같은 TASK에 두 번 유계 대기했으나 RESULT/BLOCKED 없음; TASK는 dead-letter로 이동
- Codex: 사용자 활성 턴에서 정상

따라서 상태는 최소 네 축으로 분리해야 한다: 프로세스 생존, 소켓 등록, 하트비트, 모델 작업 응답성.

## 6. 점검 중 발생한 오류와 교정

첫 브로커 점검은 메타데이터를 `.agent-swarm/runtime/broker.json`에 있다고 잘못 가정했다. PowerShell 비종료 오류 때문에 셸 종료 코드는 0이었지만 결과는 무효로 처리했다.

코드에서 정본 경로를 확인한 뒤 `.agent-swarm/broker.json`으로 재검사했고 PID 17008의 실제 프로세스 생존과 포트 8765를 종료 코드 0으로 확인했다. 이후 점검 스크립트는 경로 부재를 종료 오류로 바꾸어야 한다.

## 7. Phase 0 판정

Phase 0의 목적은 기준선을 재현 가능하게 남기는 것이므로 `DONE`이다. 발견된 결함은 다음 단계의 입력이다.

1. 무인증 브로커에서는 표결 출처를 신뢰할 수 없다.
2. 원문과 Git 추적 감사 기록이 분리되지 않았다.
3. 하트비트 정상 상태에서도 모델 TASK가 실패할 수 있다.
4. 쿼터 소진 또는 무응답에 대한 결정 예산·회로 차단이 없다.
5. 작업 기한과 큐 지연을 보여주는 실질 건강도 텔레메트리가 없다.

다음 단계는 `12_SECURITY_AND_ALWAYS_ON_EXECUTION_PLAN.md`의 Phase 1이다. 임시 세션 비밀과 Windows ACL을 생성하는 인증 상태 변경이므로 사용자 명시 승인을 받은 뒤 시작한다.
