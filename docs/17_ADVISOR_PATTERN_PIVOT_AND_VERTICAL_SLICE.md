# 지도교수 패턴 채택(Pivot)과 수직 슬라이스 실증

작성: 2026-09-05 KST · 작성자: Claude Code(`claude-code-6c`) · 모드: MIA + SELFREFINE
관련: `.agent-swarm/chat/sessions/claude-code-6c.md` 항목 024

## 1. 결론

지도교수님 조언(카카오톡 2건)을 전수분석한 결과 **기존 설계의 전제 6개가 틀렸음**을 확인했다.
`Pivot` 판정. 기존 코드는 폐기하지 않는다. **상태·조율·검증의 위치만 옮긴다.**

```
이전:  AI 가 기억하고 / AI 가 조율하고 / AI 가 검증한다
이후:  DB 가 기억하고 / 코드가 조율하고 / 코드가 검증한다
       AI 는 --ephemeral 로 매번 새로 태어나는 순수 함수
```

## 2. 교수님이 제시한 구조 (원문)

```
[실사용]                          [Codex 변형]
PM2 → Node.js server.js           PM2 → Node.js server.js
→ JS 판단 스케줄러·Provider        → JS 판단 스케줄러
→ 숨김 PowerShell 실행기           → JS CodexCliProvider
→ agy.exe (Antigravity CLI)       → child_process.spawn(node, codex.js)
→ Gemini                          → codex exec --ephemeral --sandbox read-only
→ JSON 응답                       ← JSONL 이벤트 → 최종 구조화 JSON
→ JS 검증·DB저장·안전조건·Gate      → JS 검증·DB저장·안전조건·호출 처리
```

**설계안이 아니라 프로덕션에서 돌아가는 구조**라는 점이 핵심이다.

## 3. 드러난 맹점 6가지

| # | 우리 설계 | 교수님 구조 | 결과 |
|---|---|---|---|
| 1 | 장기 세션 유지 | `--ephemeral` 세션 없음 | 세션 소실·stale lock·TTL·heartbeat 문제가 **전부 소멸** |
| 2 | "Codex(LLM)가 뇌" | JS 스케줄러가 조율, AI 는 `Provider` | LLM 조율은 비결정적. 유령 만장일치(T4)가 그 증상 |
| 3 | AI 가 `ack_sha256`·`exit_code` 를 자기 기록 | 코드가 검증 | 자기 증명은 위조 가능 |
| 4 | "상주 프로세스 불가" | PM2 | 세션에 묶인 Hooks/Monitor 는 반쪽 |
| 5 | 안전을 문서로 강제 | `--sandbox read-only` 플래그 | 프로세스가 쓰기 불가 상태로 태어남 |
| 6 | 파일 기반 거버넌스 | DB | `GOVERNANCE.md` 실제 유실이 반증 |

## 4. 웹 리서치 실측

| 항목 | 결과 |
|---|---|
| `codex exec --json / --ephemeral / --output-schema / -o` | ✅ 실재 (공식 레퍼런스) |
| **hcom** (`aannoo/hcom`, MIT) | ✅ `src/delivery/antigravity.rs`, `src/hooks/antigravity.rs` **실존 확인**. Claude Code·Codex·Antigravity 3종 모두 전용 어댑터 보유 |
| hcom 구조 | 단일 Rust 바이너리, SQLite, hook 기반, 상주 서비스 불필요, Windows 네이티브 |
| claude-mpm 설계 원칙 | *"ephemeral environments and persistent coordination"* — 교수님 원칙과 동일 |

**교훈**: "Antigravity 어댑터가 없어 P2P 불가"라는 우리 결론은 **선행조사 부재로 인한 오판**이었다.

## 5. P3 판정 — hcom 도입 보류, 단 사유가 중요하다

**보류 사유는 "필요 없어서"가 아니라 "P2 결과가 필요 여부를 바꾸기 때문"이다.**

교수님 패턴이 옳다면 AI 는 서로 대화하지 않는다. 스케줄러가 함수로 호출할 뿐이다.
그러면 **에이전트 간 메시지 버스 자체의 필요성이 상당 부분 사라진다.**
hcom 은 우리가 만들려던 문제를 잘 풀지만, 그 문제를 아예 안 만드는 길이 먼저다.

- 설치는 **사용자 승인 사항**이다(외부 바이너리, relay 토큰 유출 시 전체 제어 경고 있음).
- 우리 고유 가치인 **거버넌스·PRE-PUSH 게이트·태업 감시·반증 선행 만장일치**는 hcom 에 없다. 보존 대상이다.

## 6. P2 수직 슬라이스 — 실증 완료

구현: [`csc_slice.py`](../csc_slice.py)

```
Scheduler(코드) → Provider(ephemeral CLI) → JSONL 파싱
               → 스키마 검증(코드) → 증거 게이트(코드가 직접 실행)
               → SQLite 저장(멱등) / 거부 기록
```

### 자체검증 9/9 (외부 호출 0회)

```
[OK] valid          정상 응답은 저장된다
[OK] bad_enum       허용되지 않은 판정값은 거부된다
[OK] out_of_range   신뢰도 범위 위반은 거부된다
[OK] missing        필수 키 누락은 거부된다
[OK] extra          여분 키(exit_code 위조)는 거부된다
[OK] liar           형식이 맞으면 저장된다 — 내용 진위는 별도 문제
[OK] idempotent     재실행 후 행 수 2 -> 2, 중복 저장 없음
[OK] override       AI 주장=GO, 실제 종료코드=1 → 코드 판정=BLOCKED
[OK] confirm        AI 주장=GO, 실제 종료코드=0 → 코드 판정=GO
```

### 실제 모델 호출 (외부 검증)

```
$ python csc_slice.py run --provider claude --task "1+1의 값이 2인지 판정하라."
{"call_id":"4364e8fcdfa6541d","status":"STORED",
 "data":{"verdict":"GO","confidence":0.99,"reason":"표준 산술에서 1+1은 2이므로 참이다."},
 "elapsed_s":8.07}
```

## 7. SELFREFINE 반복에서 수정한 결함 3건

실제 실행이 아니었다면 하나도 못 잡았을 것들이다.

| # | 결함 | 발견 경로 | 수정 |
|---|---|---|---|
| 1 | **"코드가 검증하면 된다"는 내 주장이 부정확** — 스키마는 형식만 막고 거짓말은 통과한다(`liar` 케이스) | 자체검증 결과 자기비판 | `evidence_gate()` 추가. 스케줄러가 **직접 실행**해 얻은 종료코드로 AI 판정을 뒤엎는다 |
| 2 | `subprocess` 가 `codex` 를 못 찾음 (`WinError 2`) — Git Bash `command -v` 는 성공하는데 실패 | **첫 실제 호출** | `shutil.which()` 로 해석. 원인: `codex` 만 `.CMD`, `claude`·`agy` 는 `.EXE` |
| 3 | 좁은 `except` 로 예상 못 한 예외가 스택트레이스로 죽음 — 실패가 기록되지 않음 | 동일 | `except Exception` 으로 확대. 모든 실패를 `rejected` 에 기록 |

## 8. 미해결·제약

- **Codex 실제 호출은 미증명.** 명령줄은 정확했고(`thread.started`·`turn.started` 도달) **사용량 한도 소진**으로 중단됐다. 코드 결함이 아니다. 한도 리셋 후 재시도 필요.
- **PM2 도입 미착수.** 5절 맹점 4의 해법이지만 이번 슬라이스 범위 밖이다.
- **`GOVERNANCE.md` 1절(뇌=Codex)은 재검토 대상**으로 표시했다. 맹점 2와 충돌한다. Codex 판정 대기.
- 교안 MVP(`오늘 뭐 먹지?` 단일 HTML)는 **별개 트랙**이며 여전히 미착수다.

## 9. 다음 단계

1. Codex 한도 리셋 후 `--provider codex` 실증 (동일 파이프라인, 벤더만 교체)
2. `evidence_gate` 를 `csc.py` 본선 워커에 이식
3. PM2 또는 동등한 프로세스 관리자 도입 검토 (세션 독립 상주)
4. 교안 MVP 착수
