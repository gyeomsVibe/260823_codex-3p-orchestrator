# 실시간 3P 연결과 비상 정족수 정본

상태: 2026-09-04 실기동 검증 완료. 기본은 3/3 만장일치이며, Claude 사용량 제한이 실증된 현재 저위험·가역 범위만 강등 정족수를 적용한다.

## 1. 결론부터

`MIA c3p 발동`은 이제 `.agent-swarm` 생성에 그치지 않는다. 프로젝트 루트의 브로커와 Claude·Antigravity 경량 어댑터를 시작하거나 재사용하고, 소켓 ROSTER와 하트비트를 모두 통과해야 `ready`를 반환한다. 실제 모델 작업은 TASK마다 별도 유계 프로세스로 실행하며 결과나 사용불가 증거를 JSONL 정본에 남긴다.

단, Codex PC 앱은 외부 로컬 서버가 임의로 새 모델 턴을 밀어 넣을 수 없다. 따라서 브로커와 두 어댑터는 백그라운드 상주가 가능하지만 Codex의 판단은 현재 사용자가 연 대화 턴에서 수행된다. 이것이 현재 플랫폼 경계이며 “세 모델이 24시간 동시에 사고한다”는 뜻이 아니다.

## 2. 실제 구조

```text
사용자
  ↕ 현재 대화 턴
Codex PC 앱 ─ dispatch / bounded await ─ CSC broker :8765
                                          ├─ Claude adapter ─ TASK마다 Claude CLI
                                          └─ Antigravity adapter ─ TASK마다 agy CLI
                                               ↕
                                      .agent-swarm JSONL SSOT
```

브로커는 알림과 live ROSTER를 담당한다. JSONL은 재시작·순간 단절에도 메시지를 잃지 않는 정본이다. 어댑터는 가벼운 Python 프로세스로 소켓 등록과 하트비트를 유지한다. 무거운 CLI 모델 프로세스는 요청이 있을 때만 생기며 120초 기본 제한과 Windows 자식 트리 정리를 적용한다.

## 3. 연결됨의 증명 조건

다음 네 조건이 동시에 참이어야 한다.

1. 브로커 `PING`이 `PONG`을 반환한다.
2. ROSTER에 `claude`, `antigravity`의 현재 소켓이 모두 있다.
3. 두 워커 메타데이터의 PID가 살아 있고 상태가 `ready`이며 하트비트가 최신이다.
4. 실제 TASK가 각 CLI에서 `RESULT` 또는 증거 있는 `BLOCKED`로 돌아온다.

프로세스 목록만 있거나 로그인 화면만 열린 상태는 연결 증명이 아니다. `BLOCKED/quota_exhausted`는 모델 이용 가능성 실패지만, 메시지 전달 경로가 실제로 작동했다는 증거다.

## 4. `MIA c3p 발동` 실행 절차

```powershell
python csc.py activate --timeout 15
python csc.py roster
python csc.py send --sender codex --recipient all --type TASK --body "검토 질문" --correlation-id <작업-ID>
python csc.py await --task-id <반환된-message-id> --agents claude antigravity --timeout 120
```

`activate`는 멱등을 목표로 한다. fresh 워커는 재사용하고 죽거나 stale인 워커만 정확한 PID 트리 단위로 교체한다. 처음 생성되는 워커 커서는 현재 큐 끝에서 시작하여 예전 TASK를 갑자기 실행하지 않는다.

## 5. 실시간의 두 시간축

- 전송 실시간성: 0.25초 poll, 최대 2초 재연결 backoff, ROSTER 조회 약 1초 이내.
- 사고 완료 시간: 외부 모델 추론 시간이며 기본 최대 120초.

카카오톡의 “까톡”에 해당하는 것은 상주 소켓 등록과 broker broadcast다. 알림을 받은 뒤 답을 만드는 시간은 별도다. 200ms 안에 LLM 답변까지 보장하는 주장은 하지 않는다.

## 6. 비상 정족수

| 조건 | 결정 |
|---|---|
| 모두 활성, 3/3 YES | `APPROVED_UNANIMOUS` |
| 정확히 1개 사용불가가 기계 증거로 확인되고, 활성 2개가 모두 YES이며, 저위험·가역 로컬 작업 | `APPROVED_DEGRADED` |
| 활성 에이전트가 NO | `BLOCKED_DISSENT` 또는 `BLOCKED_PENDING_USER` |
| 2개 이상 사용불가 | 변경 작업 `BLOCKED_NO_QUORUM` |
| 고위험·비가역·인증/계정·설치·commit/push·사용자 승인 경계 | `USER_APPROVAL_REQUIRED` |

사용불가 허용 코드는 다음으로 제한한다.

- `quota_exhausted`
- `credit_exhausted`
- `auth_unavailable`
- `binary_missing`
- `runtime_start_failed`

코드와 함께 CLI 원문 또는 실행 증거가 있어야 한다. 타임아웃만으로는 장애인지 느린 정상 처리인지 알 수 없으므로 사용불가가 아니다. 반대표·비판·침묵을 장애로 위장해서도 안 된다. 활성 2개가 갈리면 자동 타이브레이커 없이 사용자에게 올린다.

## 7. 생산적 비판 규칙

첫 답변은 자동 동의로 취급하지 않는다. 각 도구는 최소 하나의 고유 위험과 근거를 내야 한다. 주제 이탈, 근거 없는 완료, 실행하지 않은 검증 주장은 `CALL_OUT` 또는 `WHISTLEBLOW`로 공개 기록하고 자기교정을 요구한다. 수정 답변이 오기 전에는 해당 표를 세지 않는다.

이번 실험에서 Antigravity의 최초 답변은 프론트엔드 TTI로 주제를 벗어나 제외됐다. 자기교정 뒤 CSC 교착 위험을 제시했지만, 주 에이전트 단독 타이브레이커는 만장일치 원칙을 훼손하므로 Codex가 반대했다. 최종적으로 “2/2 불일치는 사용자 에스컬레이션”에 합의했다.

## 8. 장애 복구와 남은 한계

- Windows에서 상태 파일을 읽는 순간 원자 rename이 `WinError 5`를 낼 수 있다. `PermissionError`에만 최대 5회 짧게 재시도한다.
- 브로커가 순간 중단돼도 JSONL 큐가 정본이며 어댑터는 최대 2초 backoff로 재접속한다.
- CLI 로그인 세션은 각 공급자 정책에 종속된다. 비밀정보를 읽거나 저장해 연결을 흉내 내지 않는다.
- Codex 앱의 새 턴 자동 주입은 미지원이다. 향후 공식 이벤트/세션 API가 생기기 전에는 사용자의 현재 턴이 지휘 루프를 깨운다.
- Windows 로그인 후 자동 시작 서비스 등록은 시스템 변경이므로 별도 사용자 승인이 필요하다. 현재는 트리거가 실행될 때 시작한다.

## 9. 2026-09-04 증거 요약

- 브로커 PID 2544, 수정 후 Claude 어댑터 PID 9504, Antigravity 어댑터 PID 19932.
- 두 어댑터가 15초 후에도 ROSTER와 최신 하트비트 유지.
- 공용 TASK가 `realtime`으로 전달됨.
- Claude: 약 4초 뒤 `BLOCKED/quota_exhausted`, 04:20 Asia/Seoul 리셋 안내.
- Antigravity: 약 16초 뒤 RESULT, 공개 지적 후 자기교정, 최종 비상 정책 APPROVE.
- 구현 검증: unittest 38/38 통과 후 Windows 공유 위반 회귀 테스트 1개 추가. 최종 전수 재검증은 이 문서 저장 뒤 수행한다.
- commit·push: 수행하지 않음.
