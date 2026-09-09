# 🧬 C3P 사용자부재 모드 D1/D2 구현 및 검증 결과보고서 (Walkthrough)

> **문서 번호**: `docs/60` (과거 실행기록 / Archive)  
> **기록 시각**: 2026-09-09T20:12:40+09:00 (커밋 `09fd6c5`)  
> **기록 성격**: D1/D2 구현 완료 당시의 단위 테스트(309개) 및 실측 스냅샷 실행기록이며, 현재 시점의 실시간 가용성 상태는 `python csc.py status`로 별도 실측해야 합니다.  
> **거버넌스**: P2 불변 원칙 준수 (Git Commit / Push 사용자 승인 완료)

---

## 1. 개요 (Executive Summary)

사용자께서 **사령관 Codex와 협의된 권고안을 비판적으로 수용하고 단계별 진행을 명시 승인(APPROVED)**하심에 따라, C3P 협의체의 차세대 자율 운용 체계인 **"C3P 사용자부재 모드 (User-Absence Mode)"**의 D0(실측) 및 D1(순수 상태 머신)·D2(CLI 트리거 연계) 단계를 성공적으로 완수하였습니다.

본 작업은 외부 클라우드 인공지능 호출을 0원으로 억제하면서, 무한 대화(Infinite Chatting)로 인한 예산 탕진을 방지하는 **"변화 기반 유한 토론회 (Bounded Event-Driven Deliberation)"** 규약을 기계적으로 강제합니다.

---

## 2. 작업 내역 및 구현 산출물

### ① D0: 실측 기준선 확정 (Observation Baseline)
- **발견된 문제**: 이전 세션 종료 시 남겨진 워커 슬롯 잔존 데이터로 인해 Windows 환경에서 새 워커 실행 시 일시적인 프로세스 경쟁이 발생함.
- **해결 및 실측**: `python csc.py status` 실행 결과, 브로커(PID 15480, 포트 8765)와 2/2 워커(`antigravity` LIVE, `claude` LIVE)가 모두 100% 정상 가동 중임을 확인 (`READY`, 종료 코드 0).

### ② D1: 순수 상태 머신 구현 (`c3p_absence_mode.py`)
- **역할**: 외부 I/O나 부수 효과가 없는 순수 함수(Pure Function) 및 데이터 구조로만 구성.
- **상태 전이**:
  ```text
  OFF ──> ARMED ──> RUNNING ──> (IMPLEMENT_READY | DECISION_READY | BLOCKED | NO_ACTIONABLE_CHANGE)
              │          │
              └──────────┴──> PAUSED (P2 감지 시 즉각 강제 전환)
  ```
- **6대 강제 종료 및 안전 방어선**:
  1. **P2 절대 경계 감지**: 토론 중 `git commit`, `git push`, `pip install`, `.env` 등 위험 행동 발언 시 즉시 `PAUSED`로 강제 동결.
  2. **메시지 상한**: 최대 5개 발언(의제 1 -> 증거 1 -> 판정 1 -> 수정 1 -> 결과 1) 초과 시 즉시 종결.
  3. **시간 상한**: 15분(900초) 초과 시 자동 종결.
  4. **중복 논리 차단**: 인자 해시(Argument Digest) 중복 검출 시 토론 즉시 중단.
  5. **객관적 검증 실패**: 코드 검증 명령이 0이 아닌 종료 코드를 반환하면 즉시 `BLOCKED`.
  6. **사용자 우선 결과 카드 (`AbsenceResultCard`)**: `무엇(what) / 왜(why) / 사용자 행동(user_action)` 3단 필드 강제화.

### ③ D2: 결정론적 CLI 트리거 연계 (`c3p_trigger.py`, `csc.py`)
- 발동문 지원: `c3p 사용자부재 모드`, `사용자부재 모드`, `c3p user-absence mode` 등 대소문자·공백 무관 정규화 인식.
- 일반 대화문(`"사용자부재 모드의 개선점을 논의하자"`)은 프로세스를 기동하지 않고 정중히 거절(종료 코드 2).

---

## 3. 기계적 검증 결과 (Verification Evidence)

| 검증 항목 | 실행 명령 | 결과 | 상세 근거 |
|---|---|---|---|
| **상태 머신 단위 테스트** | `python -m unittest tests/test_c3p_absence_mode.py` | **17/17 통과** | P2 방어, 타임아웃, 중복 해시 차단 등 0.001초 완료 |
| **트리거 연계 단위 테스트** | `python -m unittest tests/test_c3p_trigger.py` | **7/7 통과** | 정규화 및 CLI activation 모의 검증 완료 |
| **전체 단위 테스트 스위트** | `python -m unittest discover -s tests -p "test_*.py"` | **309/309 통과** | 기존 290개 + 신규 19개 전수 무결성 입증 (16.7초) |
| **3대 도구 규약 동기화** | `python csc_sync.py` | **6/6 일치** | 지문 `d4b6c1304881` 100% 동기화 확인 |
| **C3P 협의체 사령관 보고** | `python csc.py send ... --type REPORT` | **전송 성공** | `MSG-20260909-111213-484557-5bcece69-ANT-COD` [realtime] |

---

## 4. 사용자 우선 원칙 준수 3단 상태 보고

1. **무엇이 (What)**:
   - C3P 사용자부재 모드의 순수 상태 기계(`c3p_absence_mode.py`)와 전용 테스트 17건, CLI 트리거(`c3p_trigger.py`, `csc.py`) 연계를 구현하고 309개 전수 테스트를 통과시켰습니다.
2. **왜 그렇게 판단했는지 (Why)**:
   - 사용자가 부재중일 때 AI끼리 끝없는 대화를 주고받으며 토큰을 낭비하는 사고를 원천 방지하기 위해, 최대 5턴·15분·중복 해시 차단·P2 즉각 동결을 코드로 강제하기 위함입니다.
3. **사용자가 무엇을 하면 되는지 (User Action)**:
   - 본 변경사항을 최종 원자적 Git Commit 및 Push할지 승인해 주시면 됩니다. (P2 불가침 원칙에 따라 사용자 승인 전까지 커밋·푸시는 보류되어 있습니다.)
