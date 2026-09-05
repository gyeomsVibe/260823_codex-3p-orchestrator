# Antigravity 백그라운드 CLI 가치평가

## 판정

**조건부 Go.** Antigravity의 기본 인프라는 Bridge가 아니라 Claude Code와 같은 **백그라운드 CLI**로 맞출 가치가 있다. 다만 현재 호스트의 `agy`가 로그인되지 않았고 샌드박스에서 사용자 로그 경로 쓰기가 거부되므로, 이번 변경에서는 목표 구조와 영구 규칙만 확정한다. 인증·권한·취소·재시작 실험을 통과하기 전에는 현재 워커를 교체하지 않는다.

## 관찰한 사실

- 로컬 `agy --version`은 `1.1.27`이다.
- 로컬 도움말은 `--print`, `--input-format stream-json`, `--output-format stream-json`, `--conversation`, `--continue`, `--sandbox`를 제공한다.
- `agy remote-control status`는 데몬이 등록되지 않았다고 보고했다.
- `agy models`는 로그인되지 않았다는 오류와 종료 코드 1로 끝났다. 샌드박스에서는 `.gemini/antigravity-cli` 로그·크래시 경로 쓰기도 거부됐다.
- 현재 `csc_agent_worker.py`는 Antigravity 작업마다 `agy --print` 자식 프로세스를 새로 실행한다. 경량 Python 워커는 상주하지만 모델 CLI 세션은 상주하지 않는다.
- Google 공식 Headless 문서는 `stream-json` 입력으로 한 프로세스에서 여러 턴을 처리하고 예열된 대화를 재사용할 수 있다고 설명한다: <https://antigravity.google/docs/cli/headless/>.
- Google 공식 Remote Control 문서는 Windows 데몬 설치에 관리자 권한과 별도 로그인이 필요하며, 용도는 웹 브라우저에서 Antigravity 인스턴스를 원격 조종하는 것이라고 설명한다: <https://antigravity.google/docs/remote-control/>.

## Claude Code 대화 원문에서 반영한 증거

사용자가 지정한 대화창 `2608023_3대 AI 병렬 협업 시스템 구축_claude code`에서 추출된 로컬 공개 협업 기록을 직접 대조했다. 전체 원문을 다시 복제하지 않고 다음 근거를 설계 조건으로 반영했다.

| 원문 | 확인한 사실 | 이번 판단에 반영한 내용 |
|---|---|---|
| `.agent-swarm/chat/sessions/claude-code-6c.md` 1405~1460행 | 백그라운드 알림은 모델의 자발적 폴링이 아니라 하네스·실행 계층의 감시 기능으로 두어야 하며, Antigravity의 동등 수단은 실측이 필요하다고 결론냈다 | 장기 CLI를 Python CSC supervisor가 감시하고, 모델 자체의 항시성을 가정하지 않는다 |
| 같은 파일 1589~1604행 | 숨김 실행기에서 `agy.exe`를 호출해 구조화 응답을 받는 실사용 구조가 기록돼 있다 | 백그라운드 CLI 방식은 개념상 가능하다는 보조 증거로 사용하되, 이 저장소에서 성공한 것으로 확대 해석하지 않는다 |
| 같은 파일 2502~2530행 | Antigravity CLI 무출력 실패가 3회 재시도 뒤 데드레터 큐(DLQ)에 보존됐다 | 무출력·중단을 정상 결과로 취급하지 않고 제한 재시도, 실패 보존, 재시작 검증을 필수 조건으로 둔다 |

이 대화 기록은 당시 참가자의 관찰과 판단이다. 현재 CLI 기능과 제품 용도는 로컬 `--help` 실측과 Google 공식 문서를 우선 근거로 삼았다.

## 세 가지 대안

| 대안 | 방식 | 가치 | 위험·비용 | 판정 |
|---|---|---|---|---|
| A. 작업마다 한 번 실행 | 현재처럼 `agy --print`를 TASK마다 시작·종료 | 단순하고 고착된 세션을 격리하기 쉽다 | 시작 비용이 반복되고 대화 문맥·실시간 진행 이벤트가 약하다 | 안전한 기준선으로 유지 |
| B. 장기 백그라운드 CLI | CSC supervisor가 `agy --input-format stream-json --output-format stream-json` 한 프로세스를 유지 | Claude 방식과 운영 모델이 같아지고, 시작 비용 감소·연속 문맥·진행 이벤트 수집이 가능하다 | 인증 만료, 멈춘 턴, 누적 문맥 오염, 권한 요청, 프로세스 재시작을 관리해야 한다 | **추천: 격리 파일럿 후 기본값** |
| C. Bridge 또는 Remote Control | MCP Bridge나 Antigravity 원격제어 데몬을 사용 | 브라우저·외부 도구·원격 사용자 제어에는 유용하다 | CSC의 작업 큐·정족수·감사를 대신하지 못한다. Windows 데몬은 관리자 설치와 별도 로그인이 필요하다 | 선택적 보조 수단 |

## 4대 렌즈 평가

| 기준 | 평가 | 근거 |
|---|---|---|
| 가치성(Value) | 높음 | Claude와 Antigravity의 실행·상태·재시작 모델을 하나로 맞춰 사용자가 이해하기 쉬워진다. |
| 실현 가능성(Feasibility) | 중상 | 공식 CLI가 필요한 스트리밍 표면을 제공한다. 현재 인증 상태 때문에 실제 응답 시험은 아직 못 했다. |
| 지속 가능성(Viability) | 중상 | 별도 Bridge 공급망과 관리자 데몬 없이 기존 Python CSC 안에서 구현할 수 있다. supervisor 복잡도는 늘어난다. |
| 위험(Risk) | 중간 | 장기 세션의 문맥 오염과 권한 대기를 막으려면 턴 제한·타임아웃·취소·재시작·출력 검증이 필요하다. |

## 권고 구조

```text
Codex App
   ↕
Python CSC broker + durable queue + supervisor
   ├─ Claude Code CLI (background stream/session)
   └─ Antigravity CLI (background stream-json)
          └─ Bridge는 브라우저·외부 도구가 필요한 작업에서만 선택
```

Remote Control 데몬은 CSC 내부 통신망으로 사용하지 않는다. 이것은 사용자가 다른 기기에서 Antigravity를 조종하기 위한 제품 기능이며, CSC의 로컬 작업 배달·표결·감사 기능과 목적이 다르다.

## 파일럿 통과 조건

1. 사용자가 Antigravity CLI 로그인을 명시적으로 수행하거나 승인한다.
2. 샌드박스 안에서 로그 경로 쓰기와 읽기 전용 작업이 정상 동작한다.
3. 한 프로세스에 두 개의 순차 프롬프트를 보내 같은 `conversation_id`와 각 턴의 `result`를 확인한다.
4. 턴 타임아웃, 표준입력 종료, 강제 중단, 재시작 후 큐 재처리를 검증한다.
5. 권한 요청이 필요한 도구는 자동 승인하지 않고 명시적 거부 결과를 CSC에 전달한다.
6. 대화 누적 상한 또는 작업 단위 세션 회전 정책을 둔다.
7. Claude Code와 Antigravity 어댑터가 같은 상태 이름과 오류 계약을 사용하고 `python csc_sync.py`와 전체 테스트를 통과한다.

## 사용자가 할 일

현재는 아무 설정도 바꿀 필요가 없다. 실제 파일럿 단계에서만 Antigravity CLI 로그인과 제한된 테스트 실행 승인을 요청한다. 관리자 권한이 필요한 Remote Control 데몬 설치는 권고안에 포함하지 않는다.
