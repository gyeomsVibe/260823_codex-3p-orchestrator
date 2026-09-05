# 3대 AI 브리지·진보형 통신·PC 영구 프로필 딥리서치

- 대상: 윤겸스
- 작성일: 2026-09-04 (Asia/Seoul)
- 상태: `RESEARCH COMPLETE / PHASE 1B VERIFIED / BRIDGE DECISION PROVISIONAL`
- 범위: Codex PC 앱을 사용자 단일 창구로 두고 Claude Code CLI와 Antigravity CLI를 Python 로컬 서버의 백그라운드 워커로 연결하는 방법
- 제외: 계정·로그인·자격증명 변경, MCP 등록, 패키지 설치, Windows 자동 시작, commit·push

## 1. 직접 답

사용자 구상은 **타당하며 구현 가치가 높다.** 다만 “PC 전체를 세 AI가 항상 로그인되고 무엇이든 자동 승인하는 상태로 영구 고정”하면 장애·쿼터 소진·프롬프트 주입도 함께 영구화된다. 권장안은 다음과 같다.

1. Python CSC 로컬 서버를 중앙 제어 평면(control plane)으로 유지한다.
2. `.agent-swarm`은 서명된 작업·결과·감사 기록의 데이터 평면(data plane)으로 유지한다.
3. Antigravity는 공식 `stream-json` 장기 프로세스, Claude Code는 공식 `stream-json` 또는 세션 resume를 사용하는 어댑터로 개선한다.
4. MCP Bridge는 에이전트 채팅망이 아니라 Codex/Claude가 상대 CLI를 **도구처럼 호출하는 선택적 어댑터 표면**으로만 둔다.
5. A2A의 Task/Artifact/상태/스트리밍 의미론은 차용하되, 현 단계에서 A2A 서버 전체나 NATS JetStream을 설치하지 않는다.
6. PC 영구화는 전역 고정이 아니라 프로젝트별 선언형 프로필과 제한된 supervisor로 만든다. Phase 1~4 통과 후 Windows 로그인 자동 시작을 별도 승인받는다.

판정은 **Python CSC 하이브리드 구조 GO**, **MCP 전면 대체 NO-GO**, **MCP 보조 브리지 PILOT**, **PC 전역 무인 고정 NO-GO**, **프로젝트별 복구형 영구 프로필 GO-after-gates**다.

## 2. 실측된 현재 상태

- `claude 2.1.259`는 로컬 도움말에서 `claude mcp serve`를 제공한다.
- `agy`는 로컬 도움말에서 `--input-format stream-json`, `--output-format stream-json`, 대화 resume 및 `remote-control`을 제공한다.
- 현재 Codex의 `codex mcp list` 결과는 `No MCP servers configured yet`이다. 과거 프로젝트의 Antigravity MCP fork는 이 프로젝트/현재 Codex 설정에 등록된 상태가 아니다.
- CSC 8765 브로커는 작업 중 한 차례 사라졌고 `roster`와 `--test-ping`이 실패했다. `activate`로 브로커 PID 12916, Claude adapter PID 18020, Antigravity adapter PID 8816을 다시 시작했고 두 adapter의 ROSTER 등록을 확인했다.
- Claude는 TASK를 받았으나 `quota_exhausted`로 차단됐고 17:10 Asia/Seoul 초기화 정보를 반환했다.
- Antigravity 1차 응답은 하이브리드 구조에 GO했으나 미측정 지연 수치와 과장된 RCE 단정이 있었다. 교정·웹근거 재심 TASK는 3회 무출력 후 dead-letter가 됐다. heartbeat `ready`와 모델 응답 가능성은 동일하지 않다.

이 증거는 “확실한 연결”을 네 단계로 나눠야 함을 보여준다.

`프로세스 생존 → 소켓 등록 → 실제 TASK 수신 → 유효한 모델 RESULT`

앞 단계 성공만으로 뒷 단계를 주장하면 안 된다.

## 3. /CRITIC — 현재 생각의 잘못된 전제

### MCP가 곧 실시간 에이전트 채팅이라는 오해

MCP는 host가 client를 만들고 각 client가 한 server와 1:1 세션을 유지하는 도구·컨텍스트 연결 구조다. server 간 대화와 3자 합의는 host가 조정해야 한다. 따라서 Claude/Antigravity MCP 서버를 Codex에 연결해도 `.agent-swarm`의 정족수, 재시도, 감사, 사용자 승인 규칙이 자동 생성되지 않는다. [MCP Architecture](https://modelcontextprotocol.io/specification/2025-06-18/architecture)

### 포트가 열렸다는 사실이 AI가 연결됐다는 오해

소켓과 heartbeat는 Python adapter가 살아 있음을 보일 뿐 공급자 로그인·쿼터·모델 응답을 보장하지 않는다. 비동기 시스템에서 느린 프로세스와 죽은 프로세스를 완벽히 구분할 수 없다는 실패 탐지 한계는 고전 연구의 핵심 문제다. 따라서 timeout은 `suspected`이지 즉시 `unavailable`이나 반대표가 아니다. [Chandra–Toueg, Unreliable Failure Detectors](https://research.google/pubs/unreliable-failure-detectors-for-asynchronous-systems-preliminary-version/)

### 더 큰 메시지 시스템이면 자동으로 더 낫다는 오해

NATS JetStream은 durable consumer, ACK, redelivery, flow control을 제공하지만 별도 서버·클라이언트 의존성·운영·보안 설정을 추가한다. 현재 한 PC의 두 worker에는 CSC가 이미 같은 핵심 의미론을 갖기 시작했으므로 지금 교체하면 안전 문제보다 이행 복잡도가 커진다. [JetStream Consumers](https://github.com/nats-io/nats.docs/blob/master/nats-concepts/jetstream/consumers.md)

### 상주 프로세스가 항상 더 싸고 빠르다는 오해

Antigravity 공식 문서는 한 프로세스의 stream 입력이 시작 오버헤드를 피하고 warmed conversation을 재사용한다고 설명한다. 그러나 장기 프로세스는 메모리 누수, stuck turn, 세션 오염, 자격증명 만료를 supervisor가 처리해야 한다. 장기 실행 자체가 안정성을 보장하지 않는다. [Antigravity Headless Mode](https://antigravity.google/docs/cli/headless/)

## 4. /REDTEAM — 공개 구현과 표준 비교

| 후보 | 실제로 해결하는 것 | 남는 문제 | 현재 판정 |
|---|---|---|---|
| Python CSC TCP + signed event log | 중앙 라우팅, 프로젝트별 감사, 최소 의존성 | 인증·supervisor·실질 건강도 미완성 | `GO / harden` |
| MCP stdio Bridge | Codex/Claude가 상대 CLI를 typed tool로 호출 | peer chat·합의·durable queue 아님, host 수명주기 종속 | `PILOT only` |
| Antigravity/Claude stream-json | 한 프로세스 다중 turn, 구조화 이벤트, 세션 연속성 | stuck process·권한 prompt·쿼터 회로 필요 | `GO after security` |
| ACP adapter | IDE/client↔coding agent 세션·권한·terminal 표준화 | 현재 agy는 제3자 shim 의존, 3자 합의 프로토콜 아님 | `RESEARCH MORE` |
| A2A | 이기종 agent의 task·artifact·stream·push 의미론 | HTTP/SSE 서버, 인증, discovery가 현 단일 PC에는 과함 | `Borrow semantics` |
| NATS JetStream | durable consumer, ACK/redelivery, flow control | 새 서버·설치·운영 비용, 단일 PC에는 과대 | `NO-GO now` |
| Windows named pipe/AF_PIPE | 포트 노출 축소, Windows ACL 적용 가능 | 같은 사용자 침해 방어 불가, 플랫폼 종속 | `Phase 4 A/B test` |

A2A는 독립·불투명 agent 간 협업, 동기/stream/push와 장기 작업을 직접 목표로 하므로 MCP보다 사용자 목표에 개념적으로 가깝다. 그러나 공식 명세도 streaming client가 끊겼다가 재접속하면 상태 갱신을 놓칠 수 있고 중요한 정보는 별도 영속 기록이 필요하다고 경고한다. CSC의 `.agent-swarm` 정본을 없애면 안 되는 이유다. [A2A Specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)

ACP는 client가 파일, terminal, 권한 요청을 중개하는 coding-agent 인터페이스로 유용하지만 agent-to-agent 의결망은 아니다. 특히 공개 Antigravity ACP shim 중에는 비대화형 권한 문제 때문에 `--dangerously-skip-permissions`를 기본 사용하거나 세션 파일 mtime으로 대화를 추정하는 구현이 있어 그대로 채택하면 안 된다. [ACP Schema](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/schema/v1/schema.json), [제3자 Antigravity ACP adapter의 한계](https://github.com/steviethebear/antigravity-agent-acp)

## 5. Claude Code Bridge와 Antigravity Bridge의 정확한 역할

### Claude Code Bridge

`claude mcp serve`는 Claude Code 기능을 MCP server로 노출하여 MCP host가 Claude를 도구처럼 호출하는 방향에 가치가 있다. 반대로 Claude Code가 다른 MCP server를 등록하는 기능도 있다. 이것은 **호출 표준화**이지 Claude가 CSC 채팅방을 자율 감시하고 Codex 앱을 깨우는 기능은 아니다. Claude 공식 CLI는 `stream-json`, session name/resume, background session도 제공하므로 먼저 기존 Python adapter에서 공식 CLI 표면을 직접 활용하는 것이 더 작다. [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-usage)

### Antigravity Bridge

과거 프로젝트의 `antigravity-bridge` fork는 `use_antigravity`, result polling, cancel, health 등을 stdio MCP 도구로 제공한다. 하지만 현재 Codex에는 등록돼 있지 않고 다른 프로젝트의 vendored third-party 코드다. 이번 프로젝트로 복사·등록하기 전 공급망·권한·업데이트 경계를 다시 감사해야 한다.

현재 `agy`는 공식적으로 NDJSON stdin에 여러 user event를 보내 한 프로세스에서 연속 turn을 처리할 수 있다. 그러므로 병목 제거의 1순위는 제3자 MCP fork 이식보다 Python adapter의 공식 stream-json driver다.

## 6. PC 환경 영구 고정 가치평가

| 방식 | 가치 | 위험 | 판정 |
|---|---|---|---|
| 전역 자동 로그인·무인 승인·항상 실행 | 즉시성은 높음 | 권한 남용, 업데이트/쿼터 장애 루프, 모든 프로젝트 오염 | `NO-GO` |
| 프로젝트별 `swarm-profile.json` + 수동 `activate` | 재현성·격리·롤백이 좋음 | 사용자가 한 번 시작해야 함 | `GO now as design` |
| 사용자 로그인 시 supervisor 자동 시작 | 체감 상시성 높음 | OS 설정 변경, 오류 자동재생산 | `GO after Phase 1~4 + approval` |
| API/로그인 토큰 복사·공유 | 없음 | 자격증명 유출·계정 경계 붕괴 | `PROHIBITED` |

권장 영구 프로필은 실행 파일 경로, 프로젝트 루트, 포트 또는 pipe 이름, 허용 agent, timeout, 회로 상태 경로, 로그 보존 한도만 선언한다. 자격증명 값과 자동승인 토큰은 넣지 않는다. `activate`는 프로필을 읽어 기존 정상 프로세스를 재사용하고, 불일치 프로세스는 종료하기 전에 정확한 자식 정체성과 사용자 권한을 확인한다. `deactivate`와 자동 시작 제거 절차를 같은 단계에서 제공해야 한다.

## 7. /OPTIMIZE — 확정된 다음 순서

1. **완료: Phase 1B** — durable envelope signing API, bounded fail-closed replay window, unsigned/tampered TASK 실행 차단, signed RESULT, authenticated await를 구현했다. 집중 8개와 전체 61개 테스트가 exit 0으로 통과했다.
2. **다음: Phase 1C** — broker 연결마다 nonce challenge-response를 구현한다. 인증 전 REGISTER/PING/ROSTER/TASK를 처리하지 않는다.
3. **승인 게이트: Phase 1D** — 실제 session key 파일과 Windows ACL 생성은 사용자 명시 승인 후 수행한다.
4. **Phase 1E/2/3** — 공격·재시작 smoke, 원문/감사 분리, 공급자 회로 차단기를 끝낸다.
5. **CLI 장기 세션 pilot** — Antigravity stream-json을 먼저 격리 실험하고 Claude stream-json/resume를 같은 계약으로 맞춘다. 한 turn timeout, cancel, 재시작, conversation ID, 권한 거부를 시험한다.
6. **Phase 4 supervisor** — ROSTER+heartbeat+queue age+task deadline+last successful model probe를 합쳐 건강도를 계산한다.
7. **영구 프로필 pilot** — 프로젝트별 profile/deactivate/rollback을 만든 후에만 선택적 Windows 로그인 자동 시작을 제안한다.
8. **MCP/ACP/A2A 재평가** — 여러 프로젝트·다른 PC·IDE가 실제 요구가 될 때만 표준 어댑터나 NATS를 도입한다.

## 8. 3자 토론 판정

- Codex: Python CSC를 보안 강화하고 A2A 의미론과 공식 CLI stream을 차용하는 하이브리드에 `YES`.
- Antigravity: 1차 답변에서 같은 하이브리드 방향에 `YES`. 미측정 수치·RCE 과장은 Codex가 기각했다. 근거 기반 재심은 3회 무출력 dead-letter라 최종 교정표는 없음.
- Claude Code: TASK 수신 후 `quota_exhausted`; 모델 의견 없음.

따라서 **Phase 1B는 Claude 1개가 검증된 부재이고 활성 Codex+Antigravity가 저위험 보안 선행에 2/2 YES라 `APPROVED_DEGRADED`**다. 브리지 선택과 PC 영구화는 Antigravity 교정 재심과 Claude 의견이 없어 `PROVISIONAL_RECOMMENDATION`이며 만장일치라고 쓰지 않는다.

## 9. 핵심요약 — 모르는 것을 모르는 사용자용

```text
사용자
  ↕ 대화
Codex PC 앱 (사령관, 사용자가 말할 때 활동)
  ↕ Python CSC 로컬 서버 (포트 알림·작업 배달·결과 회수)
  ├─ Claude Code CLI adapter → Claude 모델 호출
  └─ Antigravity CLI adapter → Antigravity 모델 호출
  ↕
.agent-swarm (서명된 작업·결과·감사 기록)
```

- “포트 연결됨”은 초인종 선이 연결됐다는 뜻이다. 상대 AI가 답할 크레딧과 로그인까지 정상이라는 뜻은 아니다.
- MCP는 AI끼리의 카카오톡이 아니라, 한 AI 앱이 외부 기능을 꽂아 쓰는 표준 플러그에 가깝다.
- A2A는 AI끼리 일감을 주고받는 규격에 더 가깝지만, 지금 PC에는 너무 큰 설비다. 좋은 메시지 규칙만 가져온다.
- 지금 가장 효과적인 개선은 Python 서버를 버리는 것이 아니라, 서버를 인증하고 두 CLI를 공식 연속 스트림으로 따뜻하게 유지하는 것이다.
- PC 영구화는 가능하지만 “언제나 무인 승인”이 아니라 “이 프로젝트에서만 안전하게 자동 복구되고 한 명령으로 끌 수 있는 상태”로 만들어야 한다.

## 10. Claim-to-source ledger

| 주장 | 출처 | 접근일 | 신뢰/한계 |
|---|---|---|---|
| MCP는 host-client-server이며 client-server가 1:1 세션 | Model Context Protocol, Architecture | 2026-09-04 | 공식 명세, 높음 |
| A2A는 agent 협업·장기 task·stream/push를 목표로 함 | a2aproject/A2A specification | 2026-09-04 | 공식 공개 명세, 높음 |
| A2A stream은 재접속 중 일부 상태 유실 가능 | a2aproject/A2A specification §streaming | 2026-09-04 | 공식 공개 명세, 높음 |
| agy는 한 프로세스 다중 prompt stream과 conversation reuse 지원 | Google Antigravity Headless Mode | 2026-09-04 | 공식 제품 문서, 높음 |
| Claude CLI는 MCP, stream-json, resume/background session 표면 제공 | Claude Code CLI Reference 및 로컬 2.1.259 help | 2026-09-04 | 공식 문서+현장 실측, 높음 |
| JetStream durable consumer는 at-least-once/ACK/redelivery/flow control 제공 | nats-io/nats.docs GitHub | 2026-09-04 | 프로젝트 공식 저장소, 높음 |
| heartbeat/timeout만으로 느림과 죽음을 완전 구분할 수 없음 | Chandra & Toueg, PODC 1991 | 2026-09-04 | 원 연구, 개념 적용 |
| ACP 공개 shim은 권한·세션 추정 한계를 가질 수 있음 | ACP schema + third-party adapter README | 2026-09-04 | 표준은 높음, shim 평가는 해당 구현에만 적용 |

연구는 각 핵심 선택지의 공식/원자료가 확보되고 추가 일반 검색이 결론을 바꿀 가능성이 낮아진 지점에서 중단했다.
