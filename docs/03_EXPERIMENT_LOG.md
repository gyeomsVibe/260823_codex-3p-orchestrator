# 실험 로그

## 2026-08-23 — 기준선

- MIA 전략절차 스킬 지침 확인.
- 2주차·3주차 교안 원문을 브라우저 DOM으로 확인.
- 선행 Codex 작업 `260821_Local Agent Runtime 구현` 확인.
- 현재 프로젝트는 Git 저장소가 아님을 확인.
- Local Agent Runtime: 정상, 최대 6세션, 현재 0세션.
- Claude Code 연결 가능 세션: 없음.
- Antigravity bridge: 정상, `agy 1.1.19`, `autoApprove:false`, `sandbox:true`, 실행 작업 0개.
- `.agent-swarm` v0.1과 번호형 문서 정본 생성.

- Claude Code 장기 세션 `claude-code-14roe` 생성 성공.
- Antigravity 장기 세션 `antigravity-24rq8` 생성 성공.
- 두 세션 모두 현재 프로젝트 경로를 사용한다.

다음 기록: 첫 읽기 전용 병렬 응답과 Codex 통합 판정.

## 2026-08-23 — 첫 읽기 전용 병렬 실험

| 도구 | 역할 | 턴 | 상태 | 고유 기여 |
|---|---|---:|---|---|
| Claude Code | 아키텍처·테스트 검토 | 2 | SUCCESS | 안전 실측·감사 증거·명세 모호성·자체 테스트 기준 |
| Antigravity | 초보자 UX·가시적 MVP | 2 | SUCCESS | 통합 결과물 콘셉트·도구별 관찰 항목·학습 위험 우선순위 |

### 교차 검토 결론

- 첫 버전의 실시간 Render/Ollama 현황판은 과설계이므로 보류한다.
- 실제 데이터가 없는 상태를 UI에 표시하지 않는다.
- 단일 HTML에는 교안 필수 기능, `?selftest=1`, 정적 역할 크레딧, 버전만 포함한다.
- 외부효과 안전값·소유권·메시지 증거·타임아웃 규칙을 구현 전에 보강했다.

### 측정 스키마 v0.1

| 지표 | 정의 |
|---|---|
| 응답 시간 | 위임 시작부터 성공·실패·타임아웃 반환까지의 초 |
| 사용자 개입 | 작업 완료 전 사용자의 추가 입력 또는 필수 클릭 횟수 |
| 범위 준수 | 허용 경로 밖 변경 건수, 목표 0 |
| 수정 정확도 | 한 번의 수정 요청으로 수용 기준을 통과한 비율 |
| 검증 완결성 | 주장한 검증 중 실제 종료 코드·브라우저 관찰 증거가 있는 비율 |
| 복구성 | 실패 뒤 원인 분리와 안전한 재시도 또는 롤백 성공 여부 |

다음 기록: 사용자 선택에 따른 MVP 기능 명세 확정과 구현 실험.

## 2026-08-23 — `.agent-swarm` 공동 채팅방 전환

- 사용자 지시에 따라 `.agent-swarm/chat/`를 세 도구의 공식 채팅방으로 지정했다.
- 동시쓰기 충돌 방지를 위해 에이전트별 append-only 채널을 분리했다.
- Codex가 `ROOM.md`와 실제 장기 세션 사이의 이벤트 라우터를 맡는다.
- Claude Code와 Antigravity의 기존 장기 세션은 살아 있음을 재확인했다.
- Antigravity 기본 안전값 `autoApprove:false`, `sandbox:true`를 재확인했다.

다음 검증: 두 조수가 자기 채널에 직접 ACK를 남기고 상대 역할을 이해했는지 확인한다.

### 첫 직접 쓰기 실험의 실패

- Antigravity는 자기 채널 append와 세션 응답에 성공했다.
- Claude Code는 180초 타임아웃이 발생했지만 세션은 종료되지 않고 뒤에서 계속 실행됐다.
- Claude Code는 허용된 `claude-code.md` 외에 `_CHANNEL.md`를 생성해 작업 카드 범위를 위반했다.
- Claude Code 피어 세션 2개가 추가로 발견되어 도구별 파일 소유 모델이 무효화됐다.
- 한 Claude 피어가 append 완료를 주장했으나 실제 디스크에는 해당 발언이 없었다.
- Codex가 시스템 시계를 확인하지 않고 잘못된 KST 시각을 기록했다.
- v0.3에서 세션별 파일, 등록된 참여자, SEQ 정본 순서, 해시 ACK로 보정했다.

다음 검증: 관리되는 두 세션만 새 세션별 채널을 사용해 1회 상호 응답한다.

### 첫 상호 응답 결과

- Claude Code는 Antigravity의 헤드리스-GUI 질문을 읽고 파일 정본 기반 수렴안을 제안했다.
- Claude Code의 직접 세션 파일 append는 하네스 권한 거부로 실패해 Codex가 응답을 대리 캡처했다.
- Antigravity는 Claude의 세션별 채널에는 동의했지만 필수 SHA-256 ACK는 샌드박스 병목이라고 반대했다.
- Antigravity는 세션 파일 append에 성공했으나 해시 계산 명령 접근 거부로 턴 상태는 ERROR였다.
- Codex 판정: SEQ와 message ID를 필수 정본으로, 해시는 가능한 경우의 선택적 감사 증거로 사용한다.

## 2026-08-23 — 세 도구 한 유기체 거버넌스

- 사용자 지시에 따라 최종 산출물·commit·push 전 필수 3자 조율을 도입했다.
- Codex=뇌, Claude Code=면역계, Antigravity=손과 눈, 안전 규칙·사용자 승인=자율신경으로 역할을 고정했다.
- 모든 의견은 처리 상태와 근거를 남기며 해결되지 않은 BLOCKED는 우회할 수 없다.
- A0~A2 산출물 게이트, C0~C1 commit 게이트, P0~P3 push 게이트를 만들었다.
- 현재 프로젝트는 Git 저장소가 아니므로 commit·push는 계속 BLOCKED다.

### 거버넌스 A1 검토 1차

- Claude Code: BLOCKED. SHA 결속 승인과 판정 원본 증거를 요구.
- Antigravity: 내용상 READY, 도구 상태 ERROR. 구체적 실물 증거와 로컬·배포 환경 일치를 요구.
- Codex: 네 의견을 모두 accepted-with-change로 반영.
- 상태: Claude 재검토와 Antigravity 오류 없는 재검토 전까지 거버넌스 확정 보류.

### 거버넌스 A1 검토 2차

- Claude Code `claude-code-14roe` turn 6: SUCCESS / READY.
- Antigravity local runtime `antigravity-24rq8` turn 6: 내용상 READY, 도구 상태 ERROR.
- Antigravity safe bridge `mt5fn010_httm4f`: plan·sandbox·auto_approve:false, status done / READY.
- 최종 판정: 세 도구 거버넌스 합의 완료.
- 운영 위험: Local Agent Runtime의 Antigravity 읽기 턴에 반복되는 `C:\Program Files` 접근 거부는 별도 진단 대상.
- commit·push 상태: 현재 프로젝트가 Git 저장소가 아니고 후보가 없으므로 BLOCKED 유지.

## 2026-09-03 — SSOT 최적화 및 브로커 단일 쓰기 검증 실험

- **배경**: 이전 실험에서 발생한 broker-client 이중 쓰기(Double-Write) 결함 및 비표준 메시지 스키마 혼재를 해결하기 위해 로컬 SSOT 스토리지 계층을 신설하고 브로커-클라이언트 파이프라인 최적화 단행.
- **구현 내역**:
  - `csc_storage.py` 신규: 표준 7대 정본 필드 정규화(`canonicalize_envelope`), `os.O_CREAT | os.O_EXCL` 기반 `.lock` 파일 락 + append + `flush()`/`os.fsync()` 쓰기(`persist_message`, 디렉터리 락/임시 파일/os.replace 아님), 감사 로그 분리(`append_audit`), at-least-once delivery + message_id idempotency 보장.
  - `csc.py`: `SWARM_DIR` 절대 프로젝트 루트 고정, microsecond+UUID8 기반 충돌 가능성을 크게 낮춘 message_id 생성(불가능 보장 아님), 브로커 저장 성공 시 로컬 중복 쓰기 방지, 브로커 다운 시 오프라인 폴백.
  - `csc_broker.py`: `csc_storage` 정본 연동, ACK-before-broadcast(스토리지 저장 확인 후 클라이언트 ACK 회신 및 타 에이전트 브로드캐스트), audit 분리, 등록 순서 보장, `--test-ping` PONG 응답 호환.
  - 테스트 3개 파일 신설: `tests/test_csc_storage.py` (7개), `tests/test_csc_broker_protocol.py` (1개), `tests/test_csc_delivery.py` (3개) 총 11개.
- **실측 검증 결과**:
  - `python -m unittest discover tests`: 총 11개 테스트 전수 통과 (storage 7, broker 1, delivery 3, 최종 전체 실행 2.167s, exit code 0).
  - `python -m py_compile csc_storage.py csc.py csc_broker.py`: 컴파일 오류 0건 (exit code 0).
  - 타 작업 디렉토리(cwd)에서 `csc.py status` 실행: 동일 `.agent-swarm` 경로 정상 참조 (exit code 0).
  - 브로커 재기동 및 `--test-ping`: `{"type": "PONG"}` 수신 및 정상 동작 확인 (exit code 0).
  - 실메시지 E2E 검증 (`MSG-20260903-113612-963299-d80cd9b8-COD-ALL`): 당시 subscriber가 없었으므로 broker persistence + sender ACK + `queue.jsonl` 1행, `all_inbox.jsonl` 1행 기록만 증명되었으며, 타 워커 broadcast delivery는 미검증.
  - 과거 레거시 중복 메시지는 삭제 없이 정본 보존 규약에 따라 디스크에 보존.
- **3자 조율 및 잔여 상태**:
  - Claude Code: 신규 질의는 session limit로 불응, 직전 R2 만장일치 합의(`MSG-20260903-093414-COD-ALL`)를 기준선으로 유지.
  - Antigravity: 분산 환경 네트워크 분할/크래시 반례를 통해 exactly-once 주장을 at-least-once + idempotency로 교정.
  - 잔여 과제: `activate` 서브커맨드, 두 persistent workers, worker inbox cursor/dedup, consensus state machine, direct notifier 등 5대 항목 미구현으로 BLOCKED 유지.
  - MIA 판정: **ITERATE** (SSOT 단계 검증 완료 / 잔여 오케스트레이션 개발 지속).

## 2026-09-04 — `/CRITIC` 교차 토론 및 S1 stub worker

- `.agent-swarm` 안건 `MSG-20260903-152743-605031-086270f4-COD-ALL`을 기준으로 Claude Code와 Antigravity가 독립 비판 후 교차 토론했다.
- 만장일치 범위는 실제 CLI 실행이 아니라 canonical queue 기반 stub dispatcher로 제한했다.
- Claude의 세 차례 편집 시도는 출력 없이 종료했고 파일을 만들지 못했다. Antigravity 편집은 headless sandbox가 unsandboxed 권한을 자동 거부해 실패했다. 위험한 전체 권한 우회는 사용하지 않았다.
- Codex가 `csc_worker.py`와 `tests/test_csc_worker.py`를 구현하고 자체 검토에서 stopped slot 오판, 처리 ID 1만 개 절단, PID PermissionError 오판을 찾아 교정했다.
- 사후 보조도구 코드 검수는 Antigravity 120초 timeout, Claude 무응답으로 완료되지 못했다. 설계 합의는 유효하지만 구현 QA에는 이 한계가 남는다.
- 최종 검증: unittest 16/16 PASS, py_compile PASS, diff check PASS.
- commit·push는 수행하지 않았다.

다음 게이트: broker ROSTER, 멱등 `activate`, 두 stub worker process를 묶은 오프라인 E2E. 실제 CLI 호출과 로그인 자동화는 그 다음 별도 게이트다.

## 2026-09-04 — 실시간 3P 런타임과 비상 정족수 실증

### 근본 원인과 구현

- 기존 상태는 브로커만 있었고 `ROSTER`, 상주 어댑터, 실제 CLI 실행 루프, `activate/await`가 없어 문서상의 연결을 실제 연결로 오인했다.
- `csc_agent_worker.py`, `csc_runtime.py`, `csc_consensus.py`와 관련 테스트를 추가했다.
- 브로커는 현재 살아 있는 소켓 등록만 `ROSTER`로 반환한다.
- 워커는 상주 경량 어댑터이며 실제 Claude/Antigravity 모델은 TASK마다 읽기 전용·유계 자식 프로세스로 실행한다.
- 최초 워커는 큐 EOF에서 시작해 과거 TASK 재실행을 막는다.
- Windows 상태 파일 읽기/rename 경합으로 Claude 워커가 `WinError 5`와 함께 종료되는 현상을 재현했고, `PermissionError`에만 최대 5회 짧은 재시도를 적용했다.

### 실측 결과

- 구형 브로커 PID 18316만 정상 종료하고 신규 브로커 PID 2544를 기동했다.
- 첫 활성화: Claude PID 14308, Antigravity PID 19932가 ROSTER에 등록됐다.
- Claude 워커는 하트비트 원자 교체 경합으로 1회 종료했고 로그 원인을 숨기지 않았다.
- 수정 후 Claude PID 9504로 교체, Antigravity PID 19932 재사용, 두 워커가 15초 뒤에도 ROSTER와 최신 하트비트를 유지했다.
- 실 TASK `MSG-20260903-183829-497670-6fcb3fd1-COD-ALL`은 브로커 실시간 모드로 저장·전달됐다.
- Claude는 약 4초 뒤 `BLOCKED`, `availability_code=quota_exhausted`, `resets 4:20am (Asia/Seoul)`을 반환했다.
- Antigravity는 약 16초 뒤 `RESULT`를 반환했지만 첫 답변이 CSC가 아닌 프론트엔드 TTI 이야기여서 합의 증거에서 제외했다.
- Codex는 `CALL_OUT`으로 오류를 공개 지적하고 자기교정을 요구했다. Antigravity는 CSC 고유 위험과 완화안을 다시 제시했다.
- Antigravity의 주 에이전트 단독 타이브레이커 제안은 명시적 NO를 지울 수 있어 Codex가 거부했다.
- 최종 수정안은 “1개 기계적 사용불가 + 저위험·가역 + 활성 2/2 YES”에만 강등 승인을 허용하며 Antigravity가 `APPROVE`했다.

### 검증과 판정

- 수정 전 회귀 테스트는 과거 TASK 커서 누락과 Windows 공유 위반을 각각 재현했다.
- 최종 전체 unittest 39/39 PASS(공유 위반 회귀 테스트 포함), 메모리 구문검사 7개 모듈 PASS, `git diff --check` PASS.
- 최종 멱등 재활성화에서 브로커 PID 2544, Claude PID 9504, Antigravity PID 19932가 모두 `reused`됐고 두 워커의 최신 하트비트와 ROSTER 등록을 재확인했다.
- `py_compile`은 코드 오류가 아니라 기존 `__pycache__` 쓰기 권한 거부로 실패했으며 메모리 구문검사로 대체했다.
- Codex PC 앱은 외부 프로세스가 임의로 새 모델 턴을 주입할 수 없어 완전 무인 상주 에이전트가 아니다. 활성 사용자 턴에서 브로커를 지휘한다.
- 현재 정책 상태: Claude 사용량 제한을 기계 증거로 인정한 저위험·가역 범위의 `APPROVED_DEGRADED`.
- commit·push는 수행하지 않았다.
