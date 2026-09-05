# Phase 1 로컬 통신 보안 딥리서치 및 구현 보고

- 대상: 윤겸스와 CSC 개발 세션
- 작성일: 2026-09-04
- 상태: `PHASE 1A AUTH CORE DONE / RUNTIME INTEGRATION NOT ACTIVE`
- 범위: 현재 설계 비판, 공개 구현·공식 문서 검증, 최소 인증 코어 구현

## 1. 핵심 결론

기존 계획의 “현재 사용자 전용 토큰 파일 + 루프백 HMAC”은 유용하지만 보안 범위를 과장했다. 같은 Windows 사용자로 이미 실행 중인 악성 프로세스는 같은 파일을 읽거나 JSONL을 직접 바꿀 수 있다. 따라서 Phase 1의 현실적 목표는 다음으로 한정한다.

> 세션 키가 노출되지 않은 협력적 단일 사용자 환경에서 우발적 주입, 다른 사용자 접근, 메시지 변조, 오래된 세션 재사용, 단순 재전송, 위조 표결을 탐지하고 fail-closed한다.

동일 사용자 계정이 완전히 침해된 상황까지 막으려면 별도 Windows 계정·권한 분리 또는 더 강한 프로세스 격리가 필요하며 현재 MVP 범위가 아니다.

## 2. 현재 단계 요약

1. Phase 0 기준선 감사 완료
2. 공개 자료 기반 Phase 1 설계 재검토 완료
3. `csc_auth.py` 순수 인증 코어 구현 완료
4. 인증 단위 테스트 10/10 통과
5. 전체 테스트 53/53 통과
6. 실제 세션 키 파일·ACL·브로커 통합은 미실행
7. commit·push 미실행

## 3. /CRITIC — 기존 계획의 오류

### BLOCKER 1: 브로커 인증만으로 JSONL 경로를 보호할 수 없다

`csc.py`는 브로커가 없으면 `csc_storage.persist_message()`로 직접 fallback한다. 워커의 RESULT/BLOCKED도 `csc_worker.py`가 JSONL에 직접 기록한다. 따라서 브로커 REGISTER에만 토큰을 붙이면 공격자는 브로커를 건너뛰어 queue 파일에 위조 메시지를 넣을 수 있다.

교정: 표결·작업 메시지는 저장된 envelope 자체를 서명하고, 소비자와 `await`가 검증한 메시지만 신뢰해야 한다. 인증 모드의 TASK/RESULT/BLOCKED/표결은 무서명 fallback을 금지한다.

### BLOCKER 2: 사용자 전용 ACL은 같은 사용자 악성 프로세스를 막지 못한다

Python 문서는 multiprocessing 인증도 같은 사용자 로컬 프로세스를 신뢰한다고 명시한다. Windows named pipe DACL은 사용자·로그온 세션을 제한할 수 있지만 동일 SID의 완전한 침해까지 분리하지 못한다.

교정: 위협 모델을 명시하고 “같은 사용자 malware 방어” 완료라고 주장하지 않는다. stronger isolation은 별도 계정/서비스 단계로 분리한다.

### IMPORTANT 1: 정적 토큰 전송은 인증이 아니라 비밀 노출 경로다

HashiCorp go-plugin의 공개 구현도 magic cookie를 보안 수단이 아닌 UX 확인으로 명시한다. 정적 값을 첫 프레임에 그대로 보내는 설계는 같은 수준의 한계를 가진다.

교정: 토큰 원문을 전송하지 않고 server nonce에 대한 HMAC challenge-response를 사용한다.

### IMPORTANT 2: 연결 인증과 메시지 출처 증명은 다르다

연결 직후에는 정당했더라도 저장 후 메시지가 수정될 수 있다. durable queue를 의사결정 증거로 쓸 경우 메시지 무결성, epoch, nonce, 시간창을 별도로 검증해야 한다.

### IMPORTANT 3: replay cache가 무한 집합이면 메모리 DoS가 된다

nonce를 영구 set에 쌓으면 장기 실행에서 메모리가 증가한다. 시간창과 연동한 TTL·최대 크기 캐시가 필요하다.

### MINOR: 포트 자체가 로컬 기본값으로 최선인지 재검토가 필요하다

공식 MCP Python SDK는 로컬 서버에 host가 자식을 직접 소유하는 stdio를 기본 권장한다. Python은 Windows named pipe `AF_PIPE`와 HMAC challenge도 제공한다. 다만 지금 즉시 transport 전체를 바꾸면 변경량과 회귀 위험이 커지므로 supervisor 단계의 대안으로 보류한다.

## 4. /REDTEAM — 반드시 통과할 공격 시험

| 공격/고장 | 기대 결과 |
|---|---|
| unsigned TASK를 queue에 직접 추가 | 워커가 실행하지 않고 격리·감사 |
| signed TASK body 한 글자 변경 | MAC 실패, 저장/실행 거부 |
| 다른 key로 서명 | 거부 |
| 이전 broker epoch 메시지 재사용 | 거부 |
| 같은 nonce 재전송 | 첫 1회만 수용 |
| 미래/오래된 timestamp | 시간창 밖 거부 |
| NaN/Infinity 시간창 설정 | 설정 자체 거부 |
| 잘못된 ACL 적용 | 활성화 fail-closed, 무인증 fallback 금지 |
| broker 재시작 중 기존 worker | key/epoch 재로드 후 재연결, 구 epoch 거부 |
| nonce flood | TTL·최대 크기 이후 메모리 상한 유지 |
| broker offline | REPORT 같은 비의결 로그만 제한 fallback, TASK/표결은 중단 |
| 동일 사용자 key 탈취 | 방어 범위 밖임을 탐지·보고; 안전하다고 오보고하지 않음 |

## 5. /OPTIMIZE — 정제된 Phase 1 순서

### Phase 1A — 순수 인증 코어: 완료

추가 파일:

- `csc_auth.py`
- `tests/test_csc_auth.py`

구현:

- OS CSPRNG 기반 256-bit key 생성 함수
- HMAC-SHA256 envelope 서명
- canonical JSON 직렬화
- `hmac.compare_digest` 검증
- epoch, timestamp, 128-bit nonce
- 변조, 오키, 구 epoch, stale/future, replay, NaN/Infinity 거부

검증:

- 인증 테스트 10개 통과
- 전체 테스트 53개 통과

### Phase 1B — 저장 메시지 신뢰 경계: 완료

- `csc_storage.py`가 인증 모드에서 서명된 envelope만 의결 큐에 기록
- `csc_worker.py`와 `csc.py await`가 서명·epoch·replay를 검증
- 과거 unsigned 로그는 보존하되 `legacy_untrusted`로 취급
- TASK/RESULT/BLOCKED/표결의 unsigned fallback 금지
- nonce cache는 TTL과 최대 항목 수를 갖춤

2026-09-04 구현·검증:

- `csc_auth.ReplayWindow`: TTL과 최대 항목 수를 가진 fail-closed replay 방어
- `csc_storage.prepare_envelope/persist_message`: 인증 모드의 의결 메시지 서명
- `csc_worker.QueueWorker`: unsigned/tampered TASK 실행 거부, 본문 없는 감사 메타데이터만 기록
- `csc.py wait_for_replies`: 인증 모드에서 unsigned/invalid RESULT·BLOCKED 무시
- unrelated signed history가 replay cache를 채우지 않도록 후보 필터 후 검증
- 보안 집중 테스트 8개와 전체 61개 테스트 exit 0
- 실제 session key/ACL과 runtime auth mode는 아직 비활성

### Phase 1C — 브로커 challenge-response

- server가 매 연결마다 새 challenge 생성
- client는 key 원문 대신 HMAC 응답 전송
- 인증 완료 전 REGISTER/ROSTER/PING/메시지 본문 처리 금지
- 인증 실패 내용은 business queue에 저장하지 않음

### Phase 1D — 실제 key lifecycle과 Windows ACL

- `.agent-swarm/runtime/session.key`는 Git 비추적
- activation마다 key와 epoch 회전
- ACL은 현재 사용자와 필요한 시스템 주체로 최소화
- ACL 검증 실패 시 runtime 시작 실패
- key, HMAC 원문, 인증 캐시는 로그에 기록하지 않음

이 단계는 실제 인증 상태와 ACL을 생성하므로 사용자 명시 승인 후 수행한다.

### Phase 1E — 실제 런타임 smoke/fault test

- 정상 Codex/Claude/Antigravity 등록·TASK·RESULT
- unsigned, wrong-key, replay, stale, old-epoch 공격
- broker 재시작과 worker 재연결
- 인증 실패 시 queue 무변경 확인

## 6. 공개 근거

- Python `secrets`: 암호학적 토큰과 32-byte 권고
  - https://docs.python.org/3/library/secrets.html
- Python `hmac`: HMAC과 timing attack 완화를 위한 `compare_digest`
  - https://docs.python.org/3/library/hmac.html
- Python multiprocessing: AF_PIPE, HMAC challenge, same-user trust 한계
  - https://docs.python.org/3/library/multiprocessing.html#module-multiprocessing.connection
- CPython 공개 구현: SHA-256 challenge와 `compare_digest`
  - https://github.com/python/cpython/blob/main/Lib/multiprocessing/connection.py
- Microsoft named pipe security: DACL과 logon SID 제한
  - https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- 공식 MCP Python SDK: 로컬 서버는 stdio, 포트는 배포형 transport
  - https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md
- MCP stdio 규격 공개 원문
  - https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/stdio.mdx
- HashiCorp go-plugin: magic cookie는 보안 수단이 아님
  - https://github.com/hashicorp/go-plugin/blob/main/server.go

## 7. 한계와 중단 조건

- 이번 코드는 아직 브로커·queue·worker에 연결되지 않아 현재 runtime을 보호하지 않는다.
- actual key/ACL을 만들지 않았으므로 실사용 인증은 비활성이다.
- 같은 사용자 권한 침해는 현재 보안 경계 밖이다.
- prompt가 CLI command line 인자로 노출되는 문제는 Phase 2 데이터 경계에서 별도 처리한다.
- 동일 원인 실패가 세 번 반복되면 구현을 중단하고 대안을 보고한다.

## 8. 다음 결정

다음 최소 단위는 Phase 1C broker challenge-response다. 이후 Phase 1D에서 실제 key 파일과 Windows ACL을 만들기 직전에 별도 사용자 승인이 필요하다.
