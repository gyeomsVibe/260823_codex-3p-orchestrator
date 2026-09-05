# PRE-PUSH G0 — 커밋 후보 제안서

작성: 2026-09-05 KST · 작성자: Claude Code(`claude-code-6c`)
게이트: `A0 → A1 → A2 → C0 → C1 → P0 → P1 → **P2 사용자 승인** → P3`
현재 위치: **G0(산출물 제안)**. commit·push 는 **수행하지 않았다.**

---

## 1. 커밋 후보 요약

첫 커밋이다. 저장소에 커밋이 0개이므로 이 커밋이 전체 역사의 시작이 된다.

| 영역 | 파일 | 용량 | 내용 |
|---|---:|---:|---|
| `docs/` | 27 | 677.6 KB | 계획·결정·실험 로그·교수님 자료 |
| `.agent-swarm/` | 30 | 267.2 KB | 규약·거버넌스·채널·작업 카드 |
| 루트 `*.py` | 12 | 150.1 KB | CSC 코어 (브로커·워커·게이트·정족수) |
| `.claude/` | 2 | 16.5 KB | 훅 (알림·무결성 강제) |
| `.agents/` | 3 | 9.9 KB | codex-3p-orchestrator 스킬 |
| 루트 기타 | 4 | 8.8 KB | `AGENTS.md`, `.gitignore`, `app/index.html` 등 |
| **합계** | **78** | **1,130 KB** | |

## 2. 보안·개인정보 감사 결과

커밋 후보 전수를 정규식으로 스캔했다.

| 항목 | 결과 |
|---|---|
| API 키·토큰 (`sk-`, `ghp_`, `AIza`, `xox*`) | ✅ **0건** |
| 이메일 주소 | ✅ **0건** |
| 개인 절대경로 (`C:\Users\<이름>`) | ✅ **0건** |
| 세션 ID (`claude-code-*`, `antigravity-*`) | 🟠 90건 / 16파일 |
| 대화 UUID | 🟠 1건 |
| PID·포트 언급 | 🟡 3건 |

**치명 항목은 없다.** 남은 것은 로컬 임시 식별자이며, 협업 기록의 일부로서 의미가 있다.
다만 저장소가 **public 이면 재검토가 필요**하다(6절 결정 항목).

## 3. 커밋에서 제외한 것과 그 근거

`.gitignore` 에 추가하고 인덱스에서도 제거했다. **파일 자체는 삭제하지 않았다.**

| 제외 대상 | 근거 |
|---|---|
| `.agent-swarm/messages/queue.jsonl` (95 KB) | 런타임 메시지 로그. 세션 ID·대화 원문·PID 누적. 정본은 `chat/` |
| `.agent-swarm/messages/codex_inbox.jsonl` (58 KB) | 동일 |
| `.agent-swarm/dead-letter/` | 런타임 실패 로그 |
| `.agent-swarm/slice.db` (20 KB, 바이너리) | 실험용 SQLite. 재생성 가능 |
| (기존) `broker.json`, `workers/`, `logs/`, `*_inbox.jsonl`, `audit.jsonl` | 절대경로·PID 포함 |
| (기존) `.claude/hooks/.state/` | 로컬 커서·증거 로그 |

### ⚠️ 감사 중 발견한 것 — 이미 52개 파일이 스테이징돼 있었다

내가 아닌 누군가(정황상 Codex)가 `git add` 를 실행해 둔 상태였다.
**추적 중인 파일에는 `.gitignore` 가 적용되지 않는다.** 그래서 위 런타임 로그들이
ignore 규칙을 추가해도 여전히 커밋 대상이었고, `git rm --cached` 로 인덱스에서 빼야 했다.

> **교훈: `.gitignore` 를 쓰기 전에 인덱스 상태부터 확인해야 한다.**
> 규칙을 추가했다고 제외됐다고 믿으면 안 된다. 실측으로 확인했다.

두 jsonl 은 스테이징본(703B/252B)이 작업본(95KB/58KB)의 접두사가 아니었다.
단순 추가가 아니라 로그 회전이 있었다는 뜻이므로, **버리기 전에 보존**한 뒤 제거했다.
보존본은 저장소 밖 스크래치패드에 있다.

보존본의 내용은 공교롭게도 오늘 적발한 **허위 완료 보고 원본**이었다.
`{"sender":"claude_code","body":"src/app.py core implementation completed with exit code 0"}`
— `src/app.py` 는 존재한 적이 없다.

## 4. 검증 결과 (커밋 후보의 실행 가능성)

| 대상 | 명령 | 결과 |
|---|---|---|
| 수직 슬라이스 | `python csc_slice.py selftest` | **9/9** |
| 증거 게이트 | `python csc_evidence.py` | **6/6** (REDTEAM 2케이스 포함) |
| 정족수 합의 | `python csc_quorum.py` | **10/10** (REDTEAM 4케이스 포함) |
| 고아 락 회귀 | 격리 테스트 | **6/6** |
| 인젝션 탐지 | 악성 샘플 7종 | **7/7**, 실제 문서 오탐 0 |
| 교안 MVP | 브라우저 375×812 `?selftest=1` | **9/9** |
| 3개 Provider | stub / claude / codex | 전부 `STORED` |

**미실행 검증:** 통합 테스트 없음. `tests/` 에 파일 1개뿐이며 내용 미검토.
이 커밋은 "각 모듈이 자체검증을 통과한다"까지만 보증한다.

## 5. 커밋 메시지 초안

```
feat: 3대 AI 도구 병렬 협업 오케스트레이터(CSC) 초기 구현

Codex·Claude Code·Antigravity를 .agent-swarm 파일 제어면으로 묶어
병렬 협업시키는 오케스트레이터의 첫 커밋.

주요 구성
- csc.py / csc_broker.py / csc_worker.py: 로컬 소켓 브로커와 등록형 워커
- csc_slice.py: ephemeral CLI 호출 → JSONL → 스키마 검증 → SQLite 수직 슬라이스
- csc_evidence.py: RESULT 주장을 코드가 직접 실행해 검증하는 증거 게이트
- csc_quorum.py: 전체 과반 정족수 합의 (분할 방지)
- .claude/hooks/: 채널 소유권 강제, PRE-PUSH 게이트, 프롬프트 인젝션 탐지
- app/index.html: 2주차 교안 MVP (단일 HTML, 자체검증 포함)
- .agent-swarm/: 거버넌스·규약·3자 협업 기록
- docs/: 설계 근거와 실험 로그

설계 원칙
- 상태는 DB/파일에, 조율과 검증은 결정론적 코드에, AI는 ephemeral 함수로
- 선언이 아니라 강제: 규약을 문서가 아닌 하네스 훅으로 구현
- 형식은 스키마가, 진위는 실제 실행이 강제

검증
- 자체검증 전부 통과 (슬라이스 9/9, 증거게이트 6/6, 정족수 10/10,
  락 회귀 6/6, 인젝션 7/7, MVP 9/9)
- 통합 테스트는 미작성

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## 6. 🔴 사용자 결정이 필요한 항목 (G0 미해결)

이 셋이 정해지기 전에는 C0(커밋 후보 확정)로 넘어갈 수 없다.

### 결정 1 — 저장소 공개 범위 (Public / Private)

`github.com/gyeomsVibe/260823_Codex-Swarm-Command--CSC-` 의 현재 공개 설정을 확인하지 못했다.
**public 이면 아래 항목을 다시 판단해야 한다.**

### 결정 2 — 제3자 개인정보가 포함된 자료

| 파일 | 크기 | 내용 |
|---|---:|---|
| `docs/reference-materials/2026-09-04_ADVISOR_FEEDBACK_SCREENSHOT.png` | 36 KB | **카카오톡 스크린샷.** 지도교수 실명·프로필·대화 |
| `docs/reference-materials/2026-09-05_ADVISOR_GUIDANCE_ANALYSIS.pdf` | 193 KB | 지도 자료 분석 |
| `docs/reference-materials/CODEX_ANTIGRAVITY_LOCAL_SERVER_CONCEPT_DRAFT.pdf` | 115 KB | 개념 초안 |

**PNG 는 제3자의 실명과 대화가 담긴 스크린샷이다.**
공개 저장소에 올리면 **본인 동의 없이 타인의 개인정보를 공개**하는 것이 된다.
Git 역사에 들어가면 나중에 지워도 남는다.

**내 권고: 최소한 PNG 는 제외하거나, 교수님 동의를 받은 뒤 올린다.**
나는 임의로 제외하지 않았다. 사용자 자료이므로 판단은 사용자 몫이다.

### 결정 3 — 저장소 이름 불일치

원격 이름은 `...Codex-Swarm-Command--CSC-` 인데 프로젝트 폴더는 `260823_codex-3p-orchestrator` 다.
오늘 폴더명이 세 번 바뀌었다(`week3` → `CSC` → `codex-3p-orchestrator`).
원격을 새로 만들지, 기존 원격을 쓰되 README 로 설명할지 결정이 필요하다.

## 7. 다음 게이트

```
G0 (여기) → 결정 1·2·3 확정
         → A1 Claude·Antigravity 검토
         → A2 의견 처리
         → C0 커밋 후보 확정  → C1 3자 합의
         → P0 원격 재확인 → P1 푸시 합의 → P2 사용자 승인 → P3 푸시·검증
```

**GOVERNANCE 6조: 세 도구가 합의해도 사용자 승인 없는 commit·push 는 실행하지 않는다.**
현재까지 수행한 것은 감사·인덱스 정리·문서화뿐이다.

---

## 8. 결정 확정 및 재감사 (2026-09-05, 사용자 회신 반영)

### 8.1 사용자 결정 결과

| 항목 | 결정 |
|---|---|
| 결정 1 — 공개 범위 | **Public** (스크린샷으로 확인) |
| 결정 2 — 교수님 자료 | **동의 취득 완료.** PNG·PDF 포함 |
| 결정 3 — 저장소 | `https://github.com/gyeomsVibe/260823_codex-3p-orchestrator.git` (이름 불일치 해소) |

원격은 `origin` 으로 등록했고 `git ls-remote` 로 도달성을 확인했다. **원격은 비어 있다**(브랜치 0개).
따라서 이력 충돌 위험이 없다. 기본 브랜치는 `master` → `main` 으로 맞췄다.

### 8.2 🔴 이전 감사의 오류 정정 — "개인 절대경로 0건" 은 틀렸다

2절에서 개인 절대경로를 **0건**으로 보고했으나, **재감사에서 2건이 나왔다.**

| 파일 | 내용 |
|---|---|
| `docs/14_PHASE0_BASELINE_AND_SECURITY_AUDIT.md:53` | `C:\Users\<USER>\.config\git\ignore` |
| `.agent-swarm/chat/antigravity.md:32` | `c:\Users\<USER>\AppData\...\agentapi.exe` |

**원인:** 1차 스캔의 정규식이 대소문자를 구분했고 백슬래시 이스케이프가 부정확했다.
소문자 `c:\Users\` 를 놓쳤고, 대문자 건도 매칭에 실패했다.

**영향:** 공개 저장소에 Windows 사용자 실명이 영구 기록될 뻔했다.

**조치:** 두 건 모두 `<USER>` 로 치환했다. 재스캔 결과 0건.

> **교훈:** "0건" 은 스캐너가 아무것도 못 찾았다는 뜻이지 없다는 뜻이 아니다.
> 스캐너 자체를 검증하지 않으면 감사 결과는 감사받지 않은 주장이다.
> 이번엔 실제 사용자 계정명 문자열을 직접 검색하는 다른 방법으로 교차 확인해서 잡았다.

### 8.3 🔴 "통합 테스트 없음" 도 틀렸다 — `tests/` 에 12개 파일이 있었다

4절에서 "`tests/` 에 파일 1개뿐이며 내용 미검토" 라고 적었다. **실제로는 12개 파일이었고,
확인하지 않은 채 없다고 단정했다.**

실행 결과:

```
python -m pytest tests -q
→ 1 failed, 60 passed   (최초)
→ 61 passed, 10 subtests passed  (수정 후)
```

**실패한 1건은 내가 만든 회귀였다.**
`test_csc_agent_worker.py::test_claude_command_is_noninteractive_and_has_no_edit_tools` 가
`--tools ""` 를 단언하는데, 나는 할루시네이션 대책으로 이를
`--allowed-tools "Read,Grep,Glob"` 로 바꿔 놓고 **테스트를 돌려보지 않았다.**

수정 방향은 "테스트를 통과시키는 것" 이 아니라 **테스트가 지키려던 불변식을 되살리는 것**으로 잡았다:

- 이전: `--tools` 플래그의 존재를 확인 (형식 검사)
- 지금: 허용 목록을 **파싱해서** `{Read, Grep, Glob}` 인지 확인하고,
  `Write·Edit·Bash·NotebookEdit·WebFetch` 가 명령줄 어디에도 없음을 확인 (불변식 검사)

즉 "쓰기·실행 도구를 워커에 주지 않는다" 는 원래 의도는 더 강하게 강제된다.

### 8.4 추가로 인덱스에서 제거한 것

| 대상 | 사유 |
|---|---|
| `.agent-swarm/messages/claude_inbox.jsonl` | `.gitignore` 에 있었지만 **이미 추적 중이라 무시되지 않았다.** 3절과 동일한 함정 |
| `*.bak` | 작업 중 만든 로컬 백업본. `.gitignore` 에 규칙 추가 |

스테이징본(257B)은 버리기 전에 보존했다. 내용은 코덱스의 초기 PROPOSAL 1건이었다.

### 8.5 확정된 커밋 후보

| 영역 | 파일 |
|---|---:|
| `.agent-swarm/` | 29 |
| `docs/` | 30 |
| 루트 (`*.py`, `*.md`, `.gitignore`) | 15 |
| `tests/` | 12 |
| `.agents/` | 3 |
| `.claude/` | 2 |
| `app/` | 1 |
| **합계** | **92 파일 / 1,245.7 KB** |

1절의 78개는 `tests/`·`GEMINI.md`·`ollama_benchmark.py` 등을 세지 않은 **과소 집계**였다.

### 8.6 최종 검증 (모두 실측)

| 대상 | 결과 |
|---|---|
| `pytest tests` | **61 passed** |
| `csc_slice.py selftest` | 9/9 |
| `csc_evidence.py` | 6/6 |
| `csc_quorum.py` | 10/10 |
| 스테이징 전수 비밀 스캔 | 0건 (docs/18 의 패턴 목록 1건은 오탐으로 확인) |
| 사용자명·이메일 | 0건 |
| 제외 대상 혼입 | 0건 |

### 8.7 남은 절차

```
A1 Codex·Antigravity 검토  ← 요청 발신함
A2 의견 처리 → C0 확정 → C1 3자 합의
P0 원격 확인(완료) → P1 푸시 합의 → **P2 사용자 승인** → P3 푸시·검증
```

**commit·push 는 여전히 미실행이다.** GOVERNANCE 6조.
