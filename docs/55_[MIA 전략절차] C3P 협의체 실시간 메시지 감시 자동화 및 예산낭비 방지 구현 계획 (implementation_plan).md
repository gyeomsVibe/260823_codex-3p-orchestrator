# 🏛️ [MIA 전략절차] C3P 협의체 실시간 메시지 감시 자동화 및 예산낭비 방지 구현 계획

> **정본 식별자**: `implementation_plan.md`  
> **적용 표준**: MIA 전략절차(1. 기획 ➡️ 2. 검토 ➡️ 3. 실행 ➡️ 4. 검증) 및 전문용어 3단 병기 원칙 (2026-09-07 신설)  
> **제어 토큰**: `/DEEPDIVE` `/EXPERT` `/OPTIMIZE`  
> **원격 정본**: `https://github.com/gyeomsVibe/260823_codex-3p-orchestrator` (HEAD: `b2b04c3` 동기화 100% 완료, 272개 단위 테스트 전수 통과)

---

## 1. 기획 (Frame) — 문제 정의 및 목표 성과

### 1.1. 배경 및 사용자 문제 제기 (/CRITIC & /DEEPDIVE)
사용자는 **"GitHub 저장소를 전수분석하여, 'mia c3p 발동' 시 C3P 협의체 실시간 메시지 감시를 각 3대 AI 도구(Antigravity, Claude Code, Codex) 시작 시 예산낭비를 방지하는 로직으로 자동으로 작동시키는 계획을 세우라"**고 지시했습니다.

저장소 전수분석(`docs/01`~`53`, 272개 단위 테스트, `csc_runtime.py`, `csc_agent_worker.py`) 결과 드러난 **핵심 결함 및 예산 낭비 요인**:
1. **[결함 1: LLM의 능동 폴링(Active Polling Loop)으로 인한 무한 토큰 탕진 위험]**:
   - AI 에이전트(LLM)가 대화창이나 터미널에서 새 메시지를 기다리기 위해 루프(`while True` 또는 반복 턴)를 돌며 `run_command`나 파일 읽기를 반복하면 매 턴마다 수만 토큰의 프롬프트가 외부 클라우드 API로 쏟아져 예산이 급속도로 고갈됩니다.
2. **[결함 2: 3대 도구 시작 시 수동 개입 및 3도구 파편화]**:
   - 현재 `csc_runtime.activate()`는 백그라운드에서 `claude`와 `antigravity` 워커 2개만 띄우며, 사령관인 `codex` 세션 감시나 3개 도구가 각자 새로운 세션을 시작할 때의 **자동 시작 훅(Automatic Startup Hooks)** 규격이 일원화되어 있지 않습니다.
   - 사용자가 매번 긴 셸 명령(`python csc.py activate`)을 수동으로 치지 않으면 실시간 감시가 꺼진 상태로 방치됩니다.
3. **[결함 3: 비대칭 쿼터(Asymmetric Quota) 사령관 보호 장치 부재]**:
   - Codex 사령관은 잔여 쿼터(Rate Limit / 잔여 quota)가 매우 부족합니다(3%). 만약 메시지 감시 과정에서 수천 줄의 원본 로그나 대용량 파일이 여과 없이 사령관 작전판으로 전달되면 1~2턴 만에 쿼터가 조기 방전되어 C3P 협의체 전체가 마비됩니다.

### 1.2. 목표 성과 (Measurable Success Signals)
- **외부 토큰 0원 감시 (Zero-Token Standby)**: 3대 AI 도구의 대기 상태에서는 외부 LLM API 토큰 소모가 **정확히 0원(0 토큰)**이어야 함 (로컬 Python 소켓 감시 데몬 전담).
- **시작 시 단 1회 멱등 가동 (Idempotent 1-Shot Activation)**: Antigravity, Claude Code, Codex 어느 도구에서든 세션 시작 시 단 1회의 멱등성 검사로 브로커와 감시 워커를 자동 연결/재사용 (`reused`).
- **컨텍스트 실드(Context Shield) & Ollama 0원 트리아지**: 단순 이벤트와 로그는 로컬 경량 모델(`qwen2.5-coder:3b`)로 1차 정제하고, 사령관 Codex에는 오직 "3줄 요약 + 실측 지표" 작업 카드만 전달하여 쿼터 80% 이상 절감.
- **272개 단위 테스트 100% 회귀 방어**: 기존 모든 단위 테스트 통과 상태 유지 및 신규 예산절약 자동감시 테스트 추가.

---

## 2. 검토 (Review) — 4대 렌즈 평가 및 3대 대안 비교 (/ALT3 & /EXPERT)

### 2.1. 4대 렌즈 심층 평가

| 검토 렌즈 | 평가 기준 | 비판적 분석 (/CRITIC) 및 해결책 (/OPTIMIZE) |
| :--- | :--- | :--- |
| **① 기술적 타당성<br>(Feasibility)** | 소켓 이벤트 기반<br>무비용 비동기 대기 | **결함**: LLM 내부에서 타이머나 슬립을 돌리면 턴이 유지되어 토큰 발생.<br>**해결책**: OS 레벨의 `RegisteredQueueWorker` 파이썬 데몬이 로컬 소켓(8765)에서 블로킹 `select`로 대기하다가, 실제 메시지 도착 시에만 최소 단위 프로세스를 기동. |
| **② 경제성·비용<br>(Economics)** | 토큰 낭비 방지<br>및 쿼터 보존 | **결함**: 3대 도구가 각자 풀 모델로 원문 텍스트를 감시하면 비용 폭증.<br>**해결책**: `qwen2.5-coder:3b` 로컬 SLM(0원)으로 1차 필터링 및 3줄 요약 수행. Antigravity가 대변인으로서 무거운 탐색을 전담하여 Codex 쿼터 방전 차단. |
| **③ 거버넌스·보안<br>(Governance)** | P2 인간 승인 경계<br>및 멱등성 보장 | **결함**: 감시자가 임의로 파괴적 명령을 실행하거나 중복 프로세스를 난립시킬 위험.<br>**해결책**: 읽기 전용 샌드박스 유지, SQLite 펜싱 토큰 기반 단일 처리 보장, PID 트리 검증을 통한 좀비 프로세스 방지. |
| **④ 사용자 경험<br>(User-First)** | 완전 자동화 및<br>전문용어 3단 병기 | **결함**: 시작할 때마다 복잡한 CLI 명령을 외워야 하면 "모르는 걸 모르는 사용자"는 활용 불가.<br>**해결책**: `c3p 발동` 1회 또는 각 도구의 시작 파일(`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) 자동 훅을 통해 원클릭 0초 자동 기동. |

### 2.2. 3대 대안 비교 (/ALT3)

```mermaid
graph TD
    subgraph ALT3_Comparison [C3P 실시간 메시지 감시 3대 아키텍처 대안]
        subgraph AltA [대안 A: LLM 대화창 주기적 턴 폴링]
            A1[AI 에이전트 대화창] -->|10초마다 명령 실행| A2[python csc.py status]
            A2 -->|반복 프롬프트 발생| A3[💥 토큰 폭증 & 쿼터 10분 내 고갈]
        end

        subgraph AltB [대안 B: 독립 백그라운드 셸 스크립트 분리]
            B1[별도 셸 스크립트 실행] -->|파일 폴링| B2[queue.jsonl 감시]
            B2 -->|소켓 브로커와 미연동| B3[⚠️ 동맥경화 & Windows 파일 락 충돌]
        end

        subgraph AltC [대안 C: 0원 로컬 하네스 결합형 소켓 슈퍼바이저 (추천안)]
            C1[3대 도구 시작 훅] -->|1초 멱등 검사| C2[csc.py activate --budget-saving]
            C2 -->|0원 파이썬 소켓 대기| C3[소켓 이벤트 + Ollama 0원 1차 필터링]
            C3 -->|유효 과업 도착 시에만| C4[3줄 요약 작업 카드로 에이전트 전달]
        end
    end

    style AltA fill:#fee2e2,stroke:#ef4444
    style AltB fill:#fef3c7,stroke:#f59e0b
    style AltC fill:#dcfce7,stroke:#10b981
```

- **선택된 정본안**: **대안 C (0원 로컬 하네스 결합형 소켓 슈퍼바이저)**
  - 대기 시 토큰 0원 달성.
  - 소켓 이벤트 푸시로 찰나의 지연 없는 즉시 반응.
  - 비대칭 쿼터 보존을 위한 컨텍스트 실드 결합.

---

## 3. 사용자 검토 필요 항목 (User Review Required)

> [!IMPORTANT]
> **3대 AI 도구 시작 훅(Hooks) 자동 연동 범위**:
> 1. **Antigravity**: `GEMINI.md` 및 `codex-3p-orchestrator` 스킬에서 "c3p 발동" 또는 세션 시작 시 `csc.py activate --budget-saving`을 1회 백그라운드 실행하여 0원 감시 데몬을 가동합니다.
> 2. **Claude Code**: 프로젝트 루트의 `CLAUDE.md` 지침에 "세션 시작 시 CSC 브로커 및 워커 활성화 검사(`python csc.py activate`)"를 정식 행동 수칙으로 명시합니다.
> 3. **Codex**: `AGENTS.md` 지침에 사령관 기동 시 소켓 헬스체크 및 Antigravity 대변인 자동 연결 로직을 영구 등재합니다.
> 
> 외부 패키지 설치나 파괴적 삭제 없이, 순수 파이썬 로컬 소켓 및 규칙 파일 동기화로만 구현되므로 시스템 환경에 부작용이 없습니다.

---

## 4. 상세 구현 명세 (Proposed Changes)

### 4.1. 런타임 및 브로커 엔진 보강

#### [MODIFY] [`csc_runtime.py`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/csc_runtime.py)
- `activate()` 함수에 `--budget-saving` 모드 기본 지원:
  - 브로커 및 워커가 이미 살아있으면(Fresh & Roster 등록) 단 1ms 만에 `reused`로 즉시 반환하여 중복 프로세스 생성 방지.
  - Codex 사령관용 0원 감시 어댑터 상태 확인 로직 추가.
  - Windows 파일 락 방어 및 소켓 감시 통합.

#### [MODIFY] [`csc_agent_worker.py`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/csc_agent_worker.py)
- `RegisteredQueueWorker`에 0원 로컬 트리아지(Ollama `qwen2.5-coder:3b`) 연동 훅 탑재:
  - 수신된 메시지가 단순 하트비트나 중복 이벤트일 경우 LLM CLI를 띄우지 않고 0원 처리.
  - 실제 실행이 필요한 `TASK`에 한해서만 Bounded CLI 1회 호출.

#### [MODIFY] [`csc.py`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/csc.py)
- `activate` 하위 명령에 `--budget-saving` 플래그 및 기본값 설정.
- `watch` 또는 `monitor` 명령어를 추가/정비하여, 백그라운드 감시 상태를 한눈에 볼 수 있는 초경량 상태 출력 제공.

---

### 4.2. 3대 도구 공통 규칙 및 어댑터 동기화

#### [MODIFY] [`AGENTS.md`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/AGENTS.md)
- 2.7절 신설: **"3대 도구 시작 시 예산낭비 방지 실시간 감시 자동 작동 규약 (Zero-Token Auto-Watch Standard)"**
- 전문용어 3단 병기(`한국어 + 영어 원어 + 쉬운 설명`) 준수.

#### [MODIFY] [`GEMINI.md`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/GEMINI.md)
- Antigravity 시작 및 "c3p 발동" 시 0원 백그라운드 감시자 자동 검사 규약 반영.

#### [MODIFY] [`CLAUDE.md`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/CLAUDE.md)
- Claude Code 세션 시작 시 0원 백그라운드 감시자 자동 검사 규약 반영.

#### [MODIFY] [`.agents/skills/codex-3p-orchestrator/SKILL.md`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/.agents/skills/codex-3p-orchestrator/SKILL.md)
- "c3p 발동", "MIA c3p 발동" 트리거 시 예산낭비 방지 0원 감시 자동 기동 시퀀스 다이어그램 및 스텝 갱신.

---

### 4.3. 신규 연구 문서 및 단위 테스트

#### [NEW] [`docs/54_C3P_ZERO_TOKEN_AUTO_WATCH_AND_BUDGET_SAVING_SPEC.md`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/docs/54_C3P_ZERO_TOKEN_AUTO_WATCH_AND_BUDGET_SAVING_SPEC.md)
- 3대 도구 시작 시 예산낭비 방지 실시간 감시 설계 및 검증 증거 보고서 (MIA 전략절차 정본).

#### [NEW] [`tests/test_csc_zero_token_auto_watch.py`](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/tests/test_csc_zero_token_auto_watch.py)
- 시작 시 0원 대기, 멱등 재사용(`reused`), 토큰 소모 없는 소켓 이벤트 필터링을 검증하는 단위 테스트 추가.

---

## 5. 검증 계획 (Verification Plan)

### 5.1. 자동화 단위 테스트
```bash
# 1. 신규 예산절약 자동 감시 단위 테스트 단독 검증
python -m unittest tests/test_csc_zero_token_auto_watch.py

# 2. 전체 272+ 단위 테스트 회귀 검증
python -m unittest discover -s tests -p "test_*.py"

# 3. 3대 도구 규칙 동기화 일치도 검증
python csc_sync.py
```

### 5.2. 실기동 검증 (Live Activation Test)
```bash
# 1. 0원 예산절약 모드로 1회 가동
python csc.py activate --timeout 10

# 2. 소켓 Roster 및 백그라운드 프로세스 생존성 실측
python csc.py roster
python csc.py doctor --json

# 3. 감시판(dashboard.html) 갱신 및 파일 타임스탬프 확인
```
