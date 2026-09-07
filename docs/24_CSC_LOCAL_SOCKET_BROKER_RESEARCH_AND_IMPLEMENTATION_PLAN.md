# CSC 로컬 소켓 브로커 실측·공개 구현 연구 및 보강 계획

> **작성일**: 2026-09-06  
> **대상**: `csc_broker.py`, `csc.py`, `csc_runtime.py`, `csc_agent_worker.py`  
> **절차**: MIA 전략 검증 → `/DEEPDIVE` 공개 근거 조사 → `/SELFREFINE` 반증·정제  
> **판정**: **파일·기본 구현은 존재, 런타임 상태는 변동·현재 오프라인, 기존 브로커 보강(Go), 외부 브로커 교체(No-Go)**

## 1. 먼저 바로잡아야 할 상태

Antigravity가 전달한 “`csc_broker.py`가 미설치·미실행이라 협업하지 못했다”는 설명은 두 주장으로 나눠야 한다. **미설치 주장은 틀렸다.** 파일과 테스트된 구현이 정본 워크스페이스에 있다. **미실행 주장은 시점에 따라 달라졌다.** 첫 검사에서는 브로커와 두 워커가 살아 있었지만 연구 종료 전 재검사에서는 브로커가 꺼지고 낡은 `broker.json`만 남아 있었다.

정확한 판정은 **`구현됨 + 기본 통신 검증됨 + 상시 실행은 보장되지 않음 + 운영 안전성 미완성`**이다. 따라서 이번 과제는 새 소켓 서버를 처음 만드는 일이 아니라, 기존 서버의 생존 여부를 정확히 진단하고 잘못된 프로젝트·위조된 로컬 클라이언트·느린 수신자·중복 메시지·프로세스 재시작을 견디도록 보강하는 일이다.

### 1.1 실측 근거

| 무엇을 확인했나 | 관측 결과 | 뜻 | 사용자가 할 일 |
|---|---|---|---|
| `csc_broker.py` 파일 | 정본 루트에 존재, 16,584바이트 | “미설치”가 아님 | 없음 |
| 첫 `python csc_broker.py --test-ping` | 종료 코드 0, `PONG` | 그 시점에는 소켓 왕복 통신이 됨 | 실행 상태에는 검사 시각을 함께 기록 |
| 첫 `python csc.py status`와 `roster` | 브로커 `127.0.0.1:8765`, PID 2004, 두 워커 2/2 `LIVE`; roster는 `antigravity`, `claude` | 그 시점에는 브로커와 두 worker가 연결됨 | 없음 |
| 종료 전 `--test-ping`과 `roster` 재검사 | ping 종료 코드 1과 JSONL fallback; roster 종료 코드 1과 timeout | 상시 실행이 아니며 짧은 시간 안에도 상태가 바뀔 수 있음 | `doctor` 구현 전에는 ping·roster·status를 함께 확인 |
| 종료 전 `python csc.py status` | 종료 코드 0이지만 화면은 broker inactive, 0/2 worker live; `broker.json`은 PID 2004와 `RUNNING`을 계속 주장 | 명령 종료 코드, 메타데이터, 실제 준비 상태가 서로 어긋남 | 현재 복구가 필요하면 `python csc.py activate` 실행 |
| 브로커·명단·전달·런타임·워커 테스트 | 16개 실행, 모두 통과 | 현재 기본 계약의 회귀는 없음 | 없음 |

Antigravity 발언의 정확한 발생 원인은 대화만으로 확정할 수 없다. 가능한 원인은 다른 작업 폴더에서 실행, 오래된 상태 정보 사용, 브로커 파일 존재와 실행 상태를 한 표현으로 섞음, 또는 “이 작업에 필요하지 않음”을 “서버가 없음”으로 잘못 표현한 경우다. 직접 OS 프로세스 목록을 읽는 추가 검사는 권한 거부로 완료하지 못했다. 다만 `status`의 소켓·PID 검사와 ping·roster 실패는 현재 브로커가 준비되지 않았다는 같은 결론을 낸다. 이를 추측으로 끝내지 않도록 첫 구현 단계에 기계 판독 가능한 `doctor` 진단을 둔다.

## 2. 현재 구현에서 확인한 강점과 맹점

### 2.1 유지할 강점

- 외부 패키지 없이 Python `asyncio` TCP와 줄 단위 JSON(NDJSON)을 사용한다.
- 외부 네트워크가 아닌 `127.0.0.1`에만 바인딩한다.
- 소켓 전송 전에 `csc_storage.persist_message()`로 JSONL 정본에 저장한다.
- `message_id` 멱등성(idempotency), 파일 잠금, `flush`와 `fsync`, 수신자별 inbox, 워커 cursor와 dead-letter queue가 이미 있다.
- 브로커가 꺼졌을 때 JSONL 경로로 돌아가는 기본 복구 경로가 있다.

### 2.2 보강해야 할 맹점

| 우선순위 | 맹점 | 현재 증거 | 실제 위험 |
|---|---|---|---|
| P0 | 진단 결과가 모호함 | `status`와 `roster`는 있으나 원인을 분류하는 `doctor`가 없음 | 다른 폴더·죽은 프로세스·낡은 메타데이터를 “미설치”로 오판 |
| P0 | 상태와 종료 코드가 불일치 | broker inactive·0/2 worker인데 `csc.py status`는 종료 코드 0 | 자동화가 실패 상태를 성공으로 오판 |
| P0 | 등록 전 업무 메시지 허용 | 연결 기본 이름이 `unknown`; `REGISTER` 완료 여부 검사 없음 | 미등록 프로세스가 큐에 기록 가능 |
| P0 | 발신자 위조 가능 | 메시지에 `sender`가 있으면 연결 신원으로 덮어쓰지 않음 | 로컬 프로세스가 다른 에이전트 행세 가능 |
| P0 | 프로젝트 신원 없음 | `REGISTER`에 agent 이름만 있음 | 다른 프로젝트 브로커로 잘못 연결해도 탐지 불가 |
| P1 | 수신자 격리 없음 | 업무 메시지를 모든 subscriber에 broadcast | 특정 수신자 메시지가 불필요한 클라이언트에도 노출 |
| P1 | 중복 등록 정책 없음 | 같은 agent 키를 새 writer로 덮어씀 | 이전 연결이 subscriber에 남아 명단과 실제 연결이 어긋날 수 있음 |
| P1 | 느린 수신자 격리 없음 | 각 writer에 순차 `await writer.drain()` | 한 클라이언트가 해당 broadcast 작업을 지연 |
| P1 | 프레임 크기 계약 없음 | 기본 `StreamReader` 제한에 의존 | 큰 메시지가 구조화된 오류 없이 연결 종료로 이어질 수 있음 |
| P1 | 멱등 메시지도 재방송 | 저장 중복 여부와 무관하게 broadcast 실행 | 재전송된 동일 메시지를 실시간 수신자가 두 번 처리할 수 있음 |
| P2 | 전달 단계가 한 ACK에 섞임 | sender ACK는 “저장 완료”만 의미 | 저장·라우팅·표시·처리를 사용자가 구분하지 못함 |
| P2 | 포트 선택 경쟁 조건 | 빈 포트를 먼저 찾고 나중에 `start_server()` | 두 프로세스가 같은 포트를 골라 한쪽 시작 실패 가능 |
| P2 | 메타데이터 원자성 부족 | `broker.json`을 직접 덮어씀 | 중간 종료 시 불완전 JSON 또는 낡은 상태 가능 |
| P2 | 문서의 보장 범위 과장 | 모듈 설명에 “at-least-once delivery 보장” | 소켓 subscriber 처리 확인까지 보장하는 것으로 오해 가능 |

`asyncio.start_server()`의 기본 reader limit은 65,536바이트이며, 구분자를 제한 안에서 찾지 못하면 `LimitOverrunError`가 발생할 수 있다. `drain()`은 쓰기 버퍼가 낮은 임계값으로 내려갈 때까지 기다리는 흐름 제어다. 현재처럼 수신자를 순차 처리하면 느린 연결을 별도 정책으로 다루어야 한다. 근거: [Python asyncio streams 공식 문서](https://docs.python.org/3/library/asyncio-stream.html).

## 3. 공개 Git 저장소·공식 문서에서 가져올 설계 원칙

공개 구현은 복사 대상이 아니라 반례와 설계 패턴의 근거로 사용했다. 각 프로젝트의 보안성·유지보수성 전체를 검증했다는 뜻은 아니다.

| 공개 자료 | 확인한 패턴 | CSC에 가져올 것 | 그대로 채택하지 않을 것 |
|---|---|---|---|
| [hcom](https://github.com/aannoo/hcom) | 로컬 SQLite 이벤트 기록, agent identity/status/inbox, worktree별 `HCOM_DIR`, 충돌 알림 | 프로젝트별 저장소 격리, 명시적 신원·상태·이벤트 기록 | 현재 JSONL 정본을 SQLite로 즉시 교체 |
| [open-agent-bridge](https://github.com/kevinArgueta96/open-agent-bridge) | project+identity scope, `doctor`, conversation/reply 관계, queued→displayed→answered 전달 상태 | 진단 명령, 프로젝트 지문, 상관관계 ID, 전달 상태 분리 | localhost라는 이유만으로 인증을 생략하는 선택 |
| [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail) | project key 격리, 명시적 ACK, inbox filter, TTL reservation, audit | 프로젝트 키와 수신자 격리, 감사 추적 | 파일 첨부 경로처럼 불필요한 파일 읽기 기능 |
| [agent-bridge architecture v2](https://github.com/creatornader/agent-bridge/blob/main/docs/architecture-v2.md) | health와 readiness 분리, delivery lease의 동시성 테스트 | “프로세스 생존”과 “작업 가능”을 다른 판정으로 표시 | 전체 아키텍처 이식 |
| [mcp-agent-switchboard](https://github.com/FutureisinPast/mcp-agent-switchboard) | CLI 설치·서버·전달·reply path를 나눠 검사하는 `doctor` | 실패 지점별 상태 코드와 자가 전송 검사 | MCP 의존 구조로 전환 |
| [agent-bus](https://github.com/atongrun/agent-bus) | config·server health·token scope 검사, 저장과 ACK를 확인하는 send-test | `doctor --send-test`의 비파괴 왕복 검사 | 제품 전체 도입 |
| [NATS JetStream consumer 문서](https://github.com/nats-io/nats.docs/blob/master/nats-concepts/jetstream/consumers.md) | 소비자별 전달·ACK 추적, 재전송, 최대 시도, advisories | 저장 ACK와 소비자 처리 ACK 분리, 재시도 횟수와 DLQ | 현재 규모에 NATS 서버 설치 |
| [NATS JetStream 개요](https://github.com/nats-io/nats.docs/blob/master/nats-concepts/jetstream/README.md) | 저장·재생과 at-least-once에서도 중복 가능성을 명시 | “최소 한 번”의 범위와 중복 처리 의무를 정확히 문서화 | exactly-once처럼 보이는 홍보 문구 |
| [NATS 인증 공식 문서](https://docs.nats.io/learn/security/authentication-basics) | 공유 토큰의 한계, 비밀을 Git·URL·프로세스 인수에 두지 말라는 지침 | 로컬 인증 자료를 커밋·명령행에 노출하지 않는 원칙 | 공유 토큰 하나를 최종 신원 모델로 사용 |

### 3.1 대안 가치평가

| 대안 | 가치 | 실현 가능성 | 지속 가능성 | 위험 | 판정 |
|---|---:|---:|---:|---:|---|
| A. 현재 CSC 브로커를 단계적으로 보강 | 높음 | 높음 | 높음 | 중간→낮음 | **Go, 권고안** |
| B. hcom 또는 open-agent-bridge를 파일럿 도입 | 중간 | 중간 | 미확인 | 중간 | 연구용 비교군만 유지 |
| C. NATS JetStream으로 교체 | 현재 규모에서 낮음 | 낮음 | 운영 부담 큼 | 설치·설정·이중 정본 위험 | **현재 No-Go** |

기존 CSC를 보강하면 현재 JSONL 정본, 테스트, P2 승인 체계와 대시보드를 보존할 수 있다. 외부 브로커 도입은 패키지 설치 승인, 프로세스 운영, 데이터 이관, 새 인증 설정이 필요하지만 지금 확인된 결함을 해결하는 데 필수는 아니다.

## 4. 정제된 구현 계획

각 단계는 이전 단계의 자동 검사가 모두 통과한 뒤 진행한다. 실패하면 다음 단계로 넘어가지 않고 원인과 보존 상태를 기록한다.

### 단계 0 — 사실 기반 진단기와 용어 수정

**구현**

- `python csc.py doctor --json`과 사람이 읽는 기본 출력을 추가한다.
- 상태 코드를 `FILE_MISSING`, `WRONG_PROJECT`, `META_INVALID`, `BROKER_STOPPED`, `SOCKET_REFUSED`, `BROKER_LIVE`, `ROSTER_MISSING`, `WORKER_STALE`, `READY`, `PARTIAL_READY`로 고정한다.
- 사람이 읽는 상태와 프로세스 종료 코드를 맞춘다. `READY`만 0, 부분·실패 상태는 문서화된 비영(非零) 코드로 반환한다.
- 정본 경로, 브로커 파일, 메타데이터, PID, PING, ROSTER, 두 worker heartbeat, 필요한 CLI 존재를 순서대로 검사한다.
- `doctor --send-test`는 별도 옵션으로 두고 테스트 메시지의 저장 ACK와 회수 가능성만 확인한다.
- `docs/07_3P_COMMUNICATION_AND_BROKER_SPEC.md`와 모듈 설명의 10ms·저위험·at-least-once 표현을 측정 범위에 맞게 고친다.

**통과 기준**

- 잘못된 cwd에서도 정본 루트를 찾아 동일 결과를 낸다.
- 파일 없음, 메타데이터만 남음, 포트 거절, roster 누락, worker stale을 서로 다른 코드로 재현한다.
- 비밀값이나 환경변수 내용을 출력하지 않는다.

### 단계 1 — 연결 신원과 프로젝트 격리

**구현**

- REGISTER v2 필드: `protocol_version`, `project_id`, `broker_instance_id`, `client_instance_id`, `role`, `capabilities`.
- 등록 완료 전 업무 메시지를 거부한다.
- 업무 메시지의 `sender`는 클라이언트 입력을 신뢰하지 않고 등록된 연결 신원으로 설정한다.
- 정본 경로에서 생성한 안정적인 `project_id`와 broker 시작마다 바뀌는 `broker_instance_id`를 구분한다.
- 동일 role·client 충돌 정책을 “기존 연결 종료 후 교체” 또는 “새 연결 거부” 중 하나로 정하고 감사 로그에 남긴다. 기본 권고는 새 연결 거부다.
- localhost를 보안 경계로 오해하지 않도록 OS 사용자 범위에서 읽을 수 있는 임시 challenge/response 또는 동등한 로컬 신원 증명을 설계한다. 비밀은 저장소·프로세스 인수·로그에 두지 않는다.

**통과 기준**

- 미등록 전송, 발신자 위조, 잘못된 project, 오래된 broker instance, 중복 등록을 모두 명시적 오류로 거부한다.
- Codex·Claude Code·Antigravity 어댑터가 같은 v2 계약으로 동기화된다.

### 단계 2 — 수신자 라우팅, 크기 제한, 느린 클라이언트 격리

**구현**

- `recipient=all`만 전체 전송하고 특정 recipient는 해당 연결에만 전달한다.
- `MAX_FRAME_BYTES`를 명시하고 `start_server(limit=...)`와 동일하게 맞춘다. 초기 후보는 256KiB이며 실제 대화 메시지 분포를 측정한 뒤 확정한다.
- 잘못된 UTF-8, JSON, 너무 큰 프레임을 구조화된 오류로 반환하고 감사 로그에는 내용 대신 크기·오류 코드만 기록한다.
- 클라이언트별 크기가 제한된 `asyncio.Queue`, writer task, `drain()` 제한 시간을 둔다.
- queue가 차거나 제한 시간을 넘긴 느린 클라이언트는 다른 수신자를 막지 않도록 연결을 해제하고 `SLOW_CONSUMER`를 기록한다.

**통과 기준**

- 특정 수신자 메시지가 제3 클라이언트에 도달하지 않는다.
- 느린 수신자 하나가 정상 수신자의 전달 시간을 설정된 한계 이상 늦추지 않는다.
- 큰 입력과 잘못된 입력이 브로커 전체를 중단시키지 않는다.

### 단계 3 — 전달 의미와 재시작 복구

**구현**

- 상태를 최소 `PERSISTED`, `ROUTED`, `DELIVERED_TO_CLIENT`, `PROCESSED`로 분리한다.
- sender가 받는 첫 ACK는 `PERSISTED`라는 사실만 뜻하도록 필드와 문서를 맞춘다.
- subscriber ACK와 cursor를 도입하고, 재연결 시 JSONL 정본에서 미처리 메시지를 재생한다.
- 멱등 저장으로 판정된 중복 메시지는 명시적 replay 요청이 아닌 한 live broadcast하지 않는다.
- 최대 재시도 후 DLQ로 이동하고 사용자 감시판에 원인과 다음 조치를 표시한다.

**통과 기준**

- 저장 직후 ACK 전 종료, ACK 직후 broadcast 전 종료, client 수신 직후 처리 ACK 전 종료를 각각 재현해 메시지가 사라지지 않는다.
- 재전송으로 같은 `message_id`가 들어와도 업무 처리는 한 번만 일어난다.
- 문서가 exactly-once를 주장하지 않는다.

### 단계 4 — 라이프사이클과 메타데이터 원자성

**구현**

- 포트를 미리 검사한 뒤 다시 바인딩하는 경쟁 조건을 제거한다. OS가 고른 포트(`port=0`) 사용 또는 `start_server` 바인딩 자체를 제한된 범위에서 재시도한다.
- `broker.json`은 같은 디렉터리의 임시 파일에 쓰고 flush/fsync 후 `os.replace()`한다.
- 메타데이터에 project·protocol·instance ID를 넣고, 종료 시 자신이 만든 instance일 때만 제거한다.
- SIGINT/SIGTERM과 Windows 종료 경로에서 server close, client close, `wait_closed()`를 검증한다.

**통과 기준**

- 두 브로커 동시 시작, 시작 중 강제 종료, 낡은 metadata, Windows 재시작 시나리오에서 잘못된 `RUNNING` 판정을 남기지 않는다.

### 단계 5 — 감시판과 3대 도구 동시 동기화

**구현**

- 프로젝트 감시판에 broker health, readiness, protocol version, project ID, 연결된 role, 마지막 heartbeat, queue 지연, DLQ 수를 표시한다.
- 원문 JSONL 경로와 파생 화면의 생성 시각을 함께 보여준다.
- 공통 정본과 Codex·Claude Code·Antigravity 어댑터를 같은 변경 단위로 수정하고 `python csc_sync.py`로 검증한다.

**통과 기준**

- 두 별도 테스트 프로젝트를 동시에 실행해 메시지·metadata·dashboard가 섞이지 않는다.
- 한 플랫폼을 끈 상태는 `부분 준비(PARTIAL_READY)`로 표시하며 초록불을 주지 않는다.

## 5. 필수 반증 테스트 목록

1. REGISTER 전 업무 이벤트 거부
2. 입력 `sender` 위조 거부 또는 연결 신원으로 강제 교체
3. 다른 `project_id`와 오래된 `broker_instance_id` 거부
4. 동일 agent·instance 중복 등록의 결정적 처리
5. 특정 recipient 메시지의 제3자 비수신
6. 느린 subscriber와 가득 찬 queue가 정상 subscriber를 막지 않음
7. 프레임 한계 직전·직후, 잘못된 UTF-8, 잘못된 JSON의 구조화된 응답
8. 중복 `message_id`가 다시 live broadcast되지 않음
9. persistence 후 ACK 전 crash와 restart replay
10. subscriber 수신 후 처리 ACK 전 crash와 재전송 멱등성
11. 손상·낡은 `broker.json`, 포트 경쟁, Windows 종료 복구
12. 두 프로젝트 동시 실행의 완전한 격리
13. Antigravity가 다른 cwd에서 실행해도 `WRONG_PROJECT` 또는 정본 경로를 정확히 보고
14. 기존 JSONL fallback, worker cursor, DLQ, dashboard 회귀 없음

## 6. 범위 밖과 완료 정의

이번 보강의 범위에는 인터넷 공개 서버, 외부 패키지 설치, NATS·Redis·RabbitMQ 도입, 자격증명 변경, exactly-once 주장, 원격 다중 사용자 권한 시스템이 포함되지 않는다.

구현 완료는 파일이 생긴 시점이 아니다. 다음 조건이 모두 참일 때만 완료다.

- 위 단계별 자동 테스트와 전체 회귀 테스트가 종료 코드 0이다.
- `doctor`가 정상·부분·실패 상태와 근거·사용자 조치를 함께 표시한다.
- 3대 도구의 공통 정본과 어댑터가 동기화되며 어느 하나도 미검증 상태가 아니다.
- 감시판의 파생 상태가 JSONL 원문 및 실제 PING/ROSTER와 일치한다.
- 문서가 저장 ACK, client 전달, 업무 처리의 차이를 구분한다.
- 설치·비밀 변경 없이 기존 브로커로 되돌릴 수 있는 커밋 단위가 유지된다.

## 7. 다음 실행 단위

권고하는 다음 작업은 **단계 0 하나만 구현**하는 것이다. 이 단계가 Antigravity의 잘못된 “미설치” 진단을 직접 막고 이후 보강의 측정 기준을 만든다. 단계 0의 코드·테스트·문서가 모두 통과한 뒤 단계 1로 넘어간다. 외부 패키지 설치는 필요하지 않다.
