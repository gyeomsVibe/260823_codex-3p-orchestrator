# C3P 인증 실패 통보·Claude 턴 제한·Antigravity 헤드리스 권한 연구

> 작성일: 2026-09-07  
> 대상: `csc_worker.py`, `csc_agent_worker.py`, `csc.py`, `csc_storage.py`  
> 절차: MIA 전략 검증 + 공식 문서·GitHub 공개 이슈·Reddit 사례 조사 + 현재 설치본 실측  
> 판정: **PIVOT 후 GO — 서명된 `BLOCKED`를 정본 결과로 발행하고 DLQ는 진단 보관소로 유지**

## 1. 바로 답하기

세 문제는 한꺼번에 권한을 넓히거나 제한을 없애서 풀면 안 된다.

1. **인증 모드의 빠른 실패**: 배달 실패함(DLQ, 반복 처리에 실패한 작업의 진단 보관소)을 직접 신뢰하지 않는다. 워커가 최종 실패를 확정하는 순간 기존 HMAC 인증 경로로 서명된 `BLOCKED`를 정본 `queue.jsonl`에 먼저 기록한다. `await`는 이 서명된 결과를 검증한 뒤 즉시 종료한다.
2. **Claude Code 턴 제한**: `--max-turns`를 없애지 않는다. 텍스트 오류를 추측하지 말고 `--output-format json`의 `subtype`, `is_error`, `terminal_reason`, `errors`, `permission_denials`를 읽는다. `error_max_turns`는 같은 요청을 세 번 반복하지 않고 `task_scope_exceeded`로 즉시 보고해 Codex가 작업을 나누게 한다.
3. **Antigravity 권한 실패**: `--dangerously-skip-permissions`는 사용하지 않는다. `--sandbox --output-format json`을 사용하고 `status`, `error`, `denied_actions`를 해석한다. Git·테스트처럼 샌드박스 탈출 가능성이 있는 실측은 Codex가 결정론적으로 실행해 결과를 제공하고, Antigravity는 작업공간 내장 읽기와 판단에 집중한다.

이 안은 브로커를 폐기하지 않으며, 전역 권한 설정이나 인증 정보를 바꾸지 않고도 코드 단위 검증부터 시작할 수 있다.

## 2. 문제를 다시 정의한 결과

### 2.1 서명되지 않은 DLQ는 원인이 아니라 신뢰 경계의 혼합이다

현재 `RESULT`와 `BLOCKED`는 `persist_message(..., signing_key=...)`로 서명할 수 있다. 일반 예외만 `_dead_letter()`에서 `append_once()`로 별도 파일에 기록되어 인증 모드의 `await`가 신뢰할 수 없다.

여기서 필요한 것은 “DLQ 전체를 의사결정 메시지로 바꾸기”가 아니다.

- 정본 업무 결과: 서명된 `RESULT` 또는 서명된 `BLOCKED`
- 진단 자료: DLQ의 재시도 횟수, 오류 종류, 원래 작업 식별자
- 시간 만료 관찰: 워커가 아니라 Codex가 자기 신원으로 기록하는 `TASK_DEADLINE_EXCEEDED`

워커가 죽었을 때 Codex가 워커인 척 실패를 서명하면 발신자 귀속이 깨진다. Codex는 “워커가 실패했다”가 아니라 “마감까지 인증된 결과를 받지 못했다”만 자기 이름으로 서명해야 한다.

Python은 외부 MAC 비교에 `hmac.compare_digest()` 사용을 권고한다. 현재 `csc_auth.py`는 이미 이 방식을 사용한다. 새 암호 방식을 추가할 이유가 없다.  
근거: [Python `hmac` 공식 문서](https://docs.python.org/3/library/hmac.html), [RFC 2104 HMAC](https://www.rfc-editor.org/rfc/rfc2104)

AWS SQS도 DLQ를 처리 실패 원인 분석과 재처리용으로 설명하며, 재시도 횟수는 충분히 크게 잡으라고 경고한다. 이는 DLQ가 정상 응답 채널을 대신하기보다 실패 격리·진단 역할을 맡아야 한다는 비교 근거다.  
근거: [Amazon SQS DLQ 공식 문서](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)

### 2.2 Claude의 6턴 실패는 브로커 오류가 아니다

Claude Code 공식 CLI 문서는 `--max-turns`가 비대화식 실행의 턴 수를 제한하며, 한도에 도달하면 오류로 끝나고 기본값은 무제한이라고 명시한다. 현재 CSC는 6으로 고정했고 실제 다중 파일 검토가 `Reached max turns (6)`로 끝났다.  
근거: [Claude Code CLI 공식 문서](https://code.claude.com/docs/en/cli-usage)

현재 설치된 Claude Code 2.1.259를 직접 실행한 결과:

- 무도구 `--max-turns 1`: 성공, `subtype=success`, `num_turns=1`
- `Read` 도구가 필요한 `--max-turns 1`: 종료 코드 1, `subtype=error_max_turns`, `terminal_reason=max_turns`, `is_error=true`, 오류 원문 포함

즉 텍스트의 `Reached max turns`를 검색하는 대신 JSON 상태를 읽으면 안정적으로 분류할 수 있다. 공개 GitHub 사례도 `error_max_turns` 결과에 `num_turns`, `errors`, `terminal_reason`이 남는다는 점을 보여준다. 다만 큰 값에서 제한이 일관되게 적용되지 않았다는 공개 사례도 있어 `--max-turns` 하나를 유일한 안전장치로 믿으면 안 된다.  
근거: [Claude Code 공개 이슈 #83823](https://github.com/anthropics/claude-code/issues/83823), [Claude Code Action 공개 이슈 #1577](https://github.com/anthropics/claude-code-action/issues/1577)

### 2.3 Antigravity는 현재 버전의 JSON 오류 계약을 사용해야 한다

Antigravity 공식 문서는 헤드리스 모드가 성공 시 0, 응답 실패 시 비영 종료 코드와 JSON `status`·`error`를 제공한다고 설명한다. 1.1.27 변경 기록은 허용되지 않은 도구 동작을 `denied_actions`에 넣도록 수정했다고 밝힌다.  
근거: [Antigravity 헤드리스 공식 문서](https://antigravity.google/docs/cli/headless/), [Antigravity CLI 변경 기록](https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md)

현재 설치본 1.1.27 직접 실측:

- 무도구 샌드박스 요청: 3.41초, `SUCCESS`
- 작업공간 내장 파일 읽기: 34.74초, `SUCCESS`
- 샌드박스 안의 `git status`: 60초 안에 결과를 만들지 못해 `ERROR`, `timeout waiting for response`

따라서 Antigravity가 전혀 동작하지 않는 것이 아니다. **내장 읽기는 되고, 호스트 상태를 요구하는 Git 경로가 불안정하다.** `command(*)`나 `--dangerously-skip-permissions`로 전체 권한을 여는 것은 문제보다 위험이 크다.

과거 1.1.3 Windows 공개 이슈는 헤드리스가 `permissions.allow`를 무시했다고 보고한다. 1.1.4 변경 기록은 이 동작을 수정했다고 밝히며 현재 설치본은 1.1.27이다. 과거 결함을 현재 사실로 단정할 수는 없지만 Windows 권한 경로의 회귀 시험이 필요하다는 근거는 된다.  
근거: [Antigravity 공개 이슈 #548](https://github.com/google-antigravity/antigravity-cli/issues/548), [Antigravity 권한 공식 문서](https://antigravity.google/docs/cli/permissions/)

Reddit 사례에서는 “읽기 전용” 프롬프트가 실제 쓰기를 막지 못했다는 보고와, 전역 전체 허용보다 좁은 권한 규칙을 쓰라는 사용자 조언이 확인됐다. 이는 공식 보장이 아니라 현장 위험 신호로만 사용한다.  
근거: [Claude·Antigravity 위임 경험](https://www.reddit.com/r/ClaudeAI/comments/1vu1636/anyone_got_claude_code_antigravity_cli_agy/), [Antigravity plan 모드 권한 토론](https://www.reddit.com/r/google_antigravity/comments/1w5eax0/autoapprove_bash_in_plan_mode/)

## 3. 대안 평가

| 대안 | 가치 | 실현 가능성 | 지속 가능성 | 핵심 위험 | 판정 |
|---|---:|---:|---:|---|---|
| A. DLQ 파일 자체만 서명해 `await`가 읽음 | 중간 | 높음 | 낮음 | 정상 결과와 진단 보관소의 역할 혼합 | No-Go |
| B. 서명된 `BLOCKED`를 정본 큐에 발행하고 DLQ는 보관 | 높음 | 높음 | 높음 | 워커 급사 때 결과 발행 불가 | **Go** |
| C. Codex가 모든 워커 실패를 대신 서명 | 중간 | 높음 | 낮음 | 발신자 사칭과 원인 과장 | No-Go |
| D. Claude 턴 제한 제거 | 단기 높음 | 높음 | 낮음 | 비용·무한 루프 방어 약화 | No-Go |
| E. JSON 상태 분류 + 작업 분할 + 외부 시간 제한 | 높음 | 높음 | 높음 | 초기 임계값 조정 필요 | **Go** |
| F. Antigravity 전체 권한 우회 | 단기 높음 | 높음 | 매우 낮음 | 프롬프트 주입 시 쓰기·명령 무제한 | No-Go |
| G. 샌드박스 JSON + 내장 읽기 + Codex 실측 공급 | 높음 | 높음 | 높음 | 역할 분담 인터페이스 필요 | **Go** |

## 4. 정제된 구현 계획

### 단계 1 — 실패 분류를 메시지 계약으로 고정

다음 두 필드를 분리한다.

- `availability_code`: `quota_exhausted`, `credit_exhausted`, `auth_unavailable`, `binary_missing`, `runtime_start_failed`처럼 도구 자체가 기계적으로 사용 불가능한 경우만 사용
- `failure_code`: `task_scope_exceeded`, `permission_denied`, `process_timeout`, `nonzero_exit`, `malformed_output`, `retry_exhausted`

`permission_denied`나 `task_scope_exceeded`는 비상 정족수에서 부재표로 바꾸지 않는다. 활성 도구의 `BLOCKED`로 남긴다.

### 단계 2 — 최종 실패의 서명된 정본 결과 발행

`QueueWorker._handle_failure()`가 최대 재시도에 도달하면 다음 순서를 지킨다.

1. 결정적 오류를 안전한 길이로 정규화한다.
2. `persist_message()`로 `type=BLOCKED`, `failure_code=retry_exhausted`를 정본 큐와 Codex inbox에 기록한다.
3. 인증 모드에서는 기존 `signing_key`와 `auth_epoch`로 같은 경로에서 서명한다.
4. DLQ에는 진단 보관용 레코드를 남긴다. 원문 전체 대신 작업 ID, 상관관계 ID, 오류 종류, 시도 횟수와 정본 `BLOCKED` ID를 우선 저장한다.
5. `await`는 이미 구현된 `BLOCKED` 서명 검증을 통과한 결과만 즉시 반환한다. 비인증 DLQ 직접 검색은 과거 레코드 호환용으로만 남긴다.

워커가 메시지를 남기지 못하고 죽으면 `await`의 기존 데드라인이 종료한다. Codex가 필요하면 자기 신원으로 `TASK_DEADLINE_EXCEEDED` 관찰을 기록하되 워커의 실패 결과처럼 표결하지 않는다.

### 단계 3 — Claude Code 실행기를 JSON 기반으로 변경

1. `--output-format json` 사용.
2. 종료 코드만 보지 않고 JSON을 먼저 파싱.
3. `subtype=success`이고 `is_error=false`일 때만 `result`를 채택.
4. `error_max_turns`는 즉시 서명된 `BLOCKED(failure_code=task_scope_exceeded)`로 변환. 같은 프롬프트 3회 반복 금지.
5. `permission_denials`가 있으면 `permission_denied`로 변환.
6. API·네트워크 오류만 기존 제한 내에서 재시도.
7. 작업 프로필을 최소 둘로 분리:
   - 무도구 판단: 1턴
   - 다중 파일 읽기 검토: 초기 후보 12턴
8. 외부 프로세스 시간 제한을 별도로 유지한다. 현재 클래스 기본 600초와 CLI 파서 기본 120초가 충돌하므로 하나의 설정값으로 통일한다.

12턴은 확정 상수가 아니라 시험 시작값이다. 대표 다중 파일 작업 3회가 모두 끝나지 않으면 한도를 계속 올리지 말고 작업을 분할한다.

### 단계 4 — Antigravity 실행기를 샌드박스 JSON 기반으로 변경

1. `--sandbox --output-format json --print-timeout <bounded>` 사용.
2. 현재 경고를 만드는 `--mode plan`과 `--disable-slash-commands` 조합을 제거하거나 호환성을 별도 시험한다.
3. `status=SUCCESS`와 비어 있지 않은 `response`만 성공으로 채택.
4. `denied_actions` 또는 권한 거부 문구는 비재시도 `BLOCKED(failure_code=permission_denied)`로 변환.
5. `status=ERROR`와 timeout은 오류 원문을 보존해 제한 재시도 또는 `process_timeout`으로 종결.
6. Git 상태·테스트 결과는 Codex가 실행한 종료 코드와 출력을 입력 자료로 제공한다.
7. Antigravity의 작업공간 내장 읽기는 유지한다. 파일 쓰기·명령 실행 확대는 별도 사용자 승인과 정확한 경로·명령 규칙이 있을 때만 다룬다.

### 단계 5 — 인증 런타임 전환 전제 확인

현재 저장소는 HMAC 코어와 주입형 인증 단위 검사를 갖췄지만, 상주 워커 기동에서 세션 키를 안전하게 전달하는 전체 런타임은 별도 검증 대상이다. 키를 명령행, Git, 로그에 두지 않는다. 런타임 인증 전환은 다음을 따로 통과해야 한다.

- 프로세스별 키·epoch 전달 경로
- Windows 사용자 전용 접근 통제
- 재시작 시 epoch 교체
- 이전 epoch 메시지 거부
- 비밀값을 출력하지 않는 doctor

이 단계가 끝나기 전에는 “인증 모드가 운영 중”이라고 표시하지 않는다.

## 5. 반증 시험과 완료 기준

1. 일반 예외가 3회 실패하면 서명된 `BLOCKED`와 DLQ 진단 레코드가 모두 생긴다.
2. 서명된 `BLOCKED`를 변조하면 인증 `await`가 거부한다.
3. 잘못된 키·epoch·재사용 nonce를 거부한다.
4. 워커 급사 시 타임아웃 관찰이 워커 발신 결과로 위조되지 않는다.
5. `task_scope_exceeded`와 `permission_denied`는 비상 정족수의 사용불가 코드가 아니다.
6. Claude 1턴 Read 시험은 `error_max_turns`로 즉시 분류되고 동일 작업을 세 번 실행하지 않는다.
7. Claude 다중 파일 대표 작업 3회가 12턴 또는 더 작은 분할 작업으로 종결된다.
8. Antigravity 무도구와 내장 Read는 `SUCCESS`; Git sandbox 실패는 `ERROR` 또는 `denied_actions` 원문으로 종결된다.
9. `--dangerously-skip-permissions`가 실행 명령에 포함되지 않는다.
10. 전체 unittest, `csc_sync.py`, 실제 Claude·Antigravity `RESULT/BLOCKED` 왕복이 모두 종료 코드 0 기준을 충족한다.

## 6. 3자 반증 결과

- Claude Code: A안은 서명 주체 분리와 deadline 관찰을 보강하는 조건부 Go, B안은 작업 분할을 조건으로 Go, C안은 권한 거부와 실행 역할을 분리하는 방향에 동의.
- Antigravity: 워커 급사 시 별도 관찰자가 필요하다는 반론, 턴 초과의 동일 재시도 대신 범위 조정 필요, 작업공간 내장 읽기는 유지해야 한다는 반론을 제출.
- Codex 통합 판정: 두 반론을 수용하되 Codex가 워커를 사칭해 서명하는 안과 권한 거부를 부재표로 바꾸는 안은 거부. **PIVOT 후 GO**.

## 7. 남은 불확실성

- Antigravity `git status` 실측은 `denied_actions`가 아니라 60초 timeout으로 끝났다. 이 한 건만으로 권한 엔진과 모델 지연 중 어느 쪽이 직접 원인인지 확정할 수 없다.
- Claude 다중 파일 작업의 적정 턴 수는 아직 분포 측정이 없다. 12턴은 실험 후보일 뿐 보장값이 아니다.
- Reddit 사례는 재현 가능한 공식 보장이 아니라 위험 탐색용 참고자료다.
- 라이브 세션 키 전달과 Windows 접근 통제는 이번 조사에서 구현·검증하지 않았다.

## 8. 다음 실행 단위

가장 작은 다음 변경은 **`QueueWorker`가 재시도 소진 시 기존 인증 경로로 서명된 `BLOCKED`를 정본 큐에 기록하는 단계 2**다. 이 변경이 인증 빠른 실패를 직접 해결하며 Claude·Antigravity 실행기 개편과 독립적으로 시험할 수 있다. 그 뒤 Claude JSON 파싱, Antigravity JSON 파싱을 각각 별도 변경 단위로 진행한다.
