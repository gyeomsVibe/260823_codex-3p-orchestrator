# 🎯 MIA 전략절차 기반 'C3P 협의체(C3P Council)' 정본 명칭 및 리드미 전수 동기화 실행 계획서

> **과제 식별자**: `MIA-STRATEGIC-C3P-COUNCIL-README-SYNC-20260909`  
> **기준 정본**: [AGENTS.md](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/AGENTS.md) 0.6절 & [docs/35 C3P 협의체 공식 명칭과 바로 쓰는 방법](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md)  
> **감사 도구**: `/CRITIC` (비판적 전수 감사) & `/SELFREFINE` (품질 바닥선 자가 교정)

---

## 1. 기획 (Frame) — 깃 저장소 전수조사 및 문제 정의

### 1.1. 관찰된 핵심 결함 (Observable Problems)
깃 저장소 전체의 마크다운 문서, 코드, 테스트 파일을 전수조사한 결과 다음과 같은 정합성 불일치가 발견되었습니다:

1. **리드미([README.md](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/README.md)) 표제 및 주객 전도**:
   - 상단 대제목이 `Codex 3P Orchestrator`로만 강조되어 있고, 정작 세 AI 도구가 검토하고 합의하는 운영 주체인 **`C3P 협의체(C3P Council, Codex·Claude Code·Antigravity가 함께 검토하고 실행하는 3도구 협업 체계)`**가 인용구 구석에 작게 축소되어 있습니다.
2. **비유(Metaphor)와 공식 명칭(Official Term)의 혼용**:
   - `AGENTS.md` 0.6절은 **"‘단일 지능 유기체’는 세 도구의 역할 결합 구조를 설명하는 비유이고, ‘C3P 협의체’는 검토·합의를 수행하는 운영 주체의 이름이다. 둘은 치환하지 않는다"**라고 엄격히 규정하고 있으나, 리드미 본문에서는 이 구분이 명확히 설명되지 않고 '유기체'라는 비유 위주로 서술되어 있습니다.
3. **낡은 상태(Stale State) 방치**:
   - 단위 테스트 통과 뱃지: `Unit_Tests-237_Passed` (실제: **267개 전원 통과**).
   - 문서 색인 수량: `전체 문서 29종` (실제: **44종**).
   - 신규 핵심 모듈 누락: [csc_work_item.py](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/csc_work_item.py) (작업 조율기), [c3p_local_llm.py](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/c3p_local_llm.py) (0원 Ollama 하네스), [csc_agent_worker.py](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/csc_agent_worker.py) (백그라운드 워커)가 저장소 구조 맵에 누락됨.
4. **회귀 방지 테스트의 구멍 (Test Gap)**:
   - [tests/test_c3p_council_official_naming.py](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/tests/test_c3p_council_official_naming.py)가 규칙 파일(`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`)만 검사하고, 방문자가 가장 먼저 보는 정문인 **`README.md`를 검사 대상에서 빠뜨려** 낡은 표기가 방치되도록 방조함.

---

## 2. 검토 (Review) — /CRITIC 4대 렌즈 평가 및 /REDTEAM 분석

### 2.1. 4대 렌즈 평가
- **Value (가치성)**: 깃허브 저장소를 방문하는 사용자, 동료 개발자, 지도교수님이 첫 화면(`README.md`)만 보고도 **‘C3P 협의체’의 공식 속칭과 역할 체계, 그리고 267개 테스트 통과의 최신 실증치**를 한눈에 직관적으로 파악할 수 있음.
- **Feasibility (실현가능성)**: 문서 및 마크다운, 테스트 코드 수준의 수정으로 시스템 부작용이 없으며 즉시 안전하게 적용 가능.
- **Viability (지속가능성)**: `test_c3p_council_official_naming.py`에 `README.md` 검증을 추가하여 향후 어떤 에이전트도 리드미를 구버전으로 되돌릴 수 없도록 기계적 면역벽 구축.
- **Risk (위험도)**: 0 (로컬 가역적 수정 및 단위 테스트 Exit Code 0 검증).

---

## 3. 실행 (Execute) — /SELFREFINE 전수 정제 대상 파일 및 변경안

### 3.1. [README.md](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/README.md) 전면 정합화
1. **표제부 개편**:
   - 메인 제목: `# 🧬 codex-3p-orchestrator (CSC v2.0)`
   - 부제목: `## 🏛️ C3P 협의체(C3P Council) — Codex·Claude Code·Antigravity 3대 AI 운영 협의체`
   - 공식 첫 표기 안내문: `C3P 협의체(C3P Council, Codex·Claude Code·Antigravity가 함께 검토하고 실행하는 3도구 협업 체계)` 명시 및 `단일 지능 유기체`(비유)와의 엄격한 구분 정의 추가.
2. **뱃지 전수 최신화**:
   - `Unit_Tests-267_Passed` (237 ➡️ 267 갱신)
   - `C3P_Council-Active` 뱃지 신설 (docs/35 링크)
   - `Coordinator-SQLite_Fenced` 뱃지 신설 (csc_work_item.py 링크)
   - `Ollama_Harness-Zero_Token` 뱃지 신설 (c3p_local_llm.py 링크)
3. **본문 섹션 정합화**:
   - 제3장 (유기체 모델): 비유(단일 지능 유기체)와 운영 주체(C3P 협의체)의 구분을 명시하는 Callout 추가.
   - 제5장 (거버넌스): `## ⚖️ C3P 협의체 5대 거버넌스 헌법`으로 명명 정합화.
   - 제7장 (빠른 시작): 단위 테스트 안내문 267건 갱신, 자연어 호출문에 `C3P 협의체와 검토해줘` 추가.
   - 제8장 (구조 맵): `00_PROJECT_INDEX.md` (44종 색인표), `csc_work_item.py`, `c3p_local_llm.py`, `csc_agent_worker.py` 추가 반영.
   - 제9장 (기여 및 저작권): `운영 협의체: C3P 협의체 (C3P Council)`로 정식 명시.

### 3.2. [.agent-swarm/README.md](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/.agent-swarm/README.md)
- 제어면의 운영 주체로 `C3P 협의체 (C3P Council)`를 명시하고 [docs/35](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md) 링크 연결.

### 3.3. [docs/user/README.md](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/docs/user/README.md) 및 사용자 팩
- 가이드 및 자문 팩에서 3대 도구 협의체의 공식 속칭이 `C3P 협의체`임을 명시하고 유기체 비유와의 관계 정합화.

### 3.4. [tests/test_c3p_council_official_naming.py](file:///d:/D_Workspace_NB/-agentic-ai-workspace/260823_codex-3p-orchestrator/tests/test_c3p_council_official_naming.py) 회귀 테스트 보강
- `README.md`를 테스트 대상 파일 목록에 추가.
- `README.md` 내 `C3P 협의체`, `FIRST_MENTION`, `267_Passed`, `csc_work_item.py` 포함 여부를 검증하는 단위 테스트 추가.

---

## 4. 검증 (Verify) — 완료 조건 및 승인 절차

1. **단위 테스트 실행**:
   - `python -m unittest tests/test_c3p_council_official_naming.py` ➡️ **PASS**
   - `python -m unittest discover tests` ➡️ **전체 267개 이상 테스트 전원 통과** (새 검증 추가로 268개)
2. **원칙 동기화 검사**:
   - `python csc_sync.py` ➡️ **6/6 Synced 통과**
3. **사용자 최종 확인**:
   - 수정 완료 후 `git status -s` 및 `git diff`를 투명하게 제시하고 최종 검토 요청.

---

## 5. 사용자 승인 요청 (User Review Required)

위 기획·검토·정제 계획에 따라 **README.md 및 관련 문서, 테스트 보강 작업을 진행할지 승인해 주시기 바랍니다.**
