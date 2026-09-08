# 🧬 codex-3p-orchestrator (CSC v2.0)
## 🏛️ C3P 협의체(C3P Council) — Codex·Claude Code·Antigravity 3대 AI 통합 운영 체계

> **공식 속칭:** **C3P 협의체(C3P Council, Codex·Claude Code·Antigravity가 함께 검토하고 실행하는 3도구 협업 체계)**  
> 프로젝트와 Git 저장소의 정식 이름은 `codex-3p-orchestrator`이며, 운영 협의체를 말할 때 `C3P 협의체`를 사용합니다.  
> **‘단일 지능 유기체’**는 세 도구의 유기적 분업 역할을 설명하는 공학적 비유이고, 실제 검토와 합의를 수행하는 운영 주체의 정식 속칭은 **`C3P 협의체`**입니다.  
> 자세한 구분은 [docs/35 C3P 협의체 공식 명칭과 바로 쓰는 방법](docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md)을 확인하세요.

[![Tests](https://img.shields.io/badge/Unit_Tests-269_Passed-10b981?style=flat-square&logo=python)](tests/)
[![Principle Sync](https://img.shields.io/badge/User--First-6%2F6_Synced-3b82f6?style=flat-square)](.agent-swarm/USER_FIRST_PRINCIPLE.md)
[![C3P Council](https://img.shields.io/badge/C3P_Council-Active-7c3aed?style=flat-square)](docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md)
[![Coordinator](https://img.shields.io/badge/Work_Item-SQLite_Fenced-059669?style=flat-square)](csc_work_item.py)
[![Local SLM](https://img.shields.io/badge/Ollama_Harness-Zero_Token-d97706?style=flat-square)](c3p_local_llm.py)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

> *"많은 세포나 기관이 일정한 질서에 따라 조직화되어, 생명 활동을 유지하기 위해 상호 긴밀하게 연관되어 기능하는 하나의 통일체."*  
> 본 저장소는 **Codex, Claude Code, Antigravity**를 별개의 분리된 도구가 아니라, **`.agent-swarm` 제어면과 로컬 소켓 브로커를 신경망 촉매로 삼아 호흡하는 단일 지능 유기체(Living Organism)**로 통합 작동시키는 C3P 협의체의 실시간 오케스트레이터입니다.

---

## 📑 목차 (Table of Contents)

1. [🌟 2대 독립 패키지 (핵심 산출물 바로가기)](#-2대-독립-패키지-핵심-산출물-바로가기)
2. [💡 10초 만에 이해하는 우편실 비유](#-10초-만에-이해하는-우편실-비유)
3. [🧬 유기체 3대 기관 모델 (Living Organ Model)](#-유기체-3대-기관-모델-living-organ-model)
4. [🏛️ C3P 비대칭 쿼터 예산절약 모드 (Budget-Saving OS)](#️-c3p-비대칭-쿼터-예산절약-모드-asymmetric-quota-budget-saving-os)
5. [🎓 지도교수 피벗 조언 수용 및 실증치](#-지도교수-피벗-조언-수용-및-실증치)
6. [⚖️ C3P 협의체 5대 거버넌스 헌법](#️-c3p-협의체-5대-거버넌스-헌법)
7. [🛡️ 사용자 안심 원칙 (User-First Principle)](#️-사용자-안심-원칙-user-first-principle)
8. [🚀 빠른 시작 & 실전 치트키 조작법](#-빠른-시작--실전-치트키-조작법)
9. [📁 저장소 구조 맵 (Repository Structure)](#-저장소-구조-맵-repository-structure)
10. [👥 기여 및 저작권 (Contributors & License)](#-기여-및-저작권-contributors--license)

---

## 🌟 2대 독립 패키지 (핵심 산출물 바로가기)

본 프로젝트의 모든 핵심 설계와 실증 결과는 대상 독자별로 완벽히 분리된 2대 독립 문서 팩으로 구성되어 있습니다.

```
docs/user/
├── README.md                                          (마스터 인덱스)
│
├── 01_learning_guide/                                 [01 사용자 학습 가이드 팩]
│   ├── 01_codex_3p_orchestrator_learning_guide.html   (인터랙티브 웹 정본 - 탭/원페이지/다크모드)
│   ├── 01_codex_3p_orchestrator_learning_guide.pdf    (모바일 카톡/인쇄용 검증 완본 6p, 1.45MB)
│   ├── README.md                                      (가이드 인덱스)
│   └── chapters/                                      (6개 챕터별 마크다운 상세 원문)
│
└── 02_advisor_package/                                [02 지도교수 자문 패키지 팩]
    ├── 02_advisor_consultation_package.html           (자문 보고용 인터랙티브 웹 정본)
    ├── 02_advisor_consultation_package.pdf            (학술 논문/보고서 규격 검증 완본 6p, 902KB)
    ├── README.md                                      (패키지 인덱스)
    └── sections/                                      (5개 섹션별 마크다운 상세 원문)
```

| 패키지 | 대상 독자 | 인터랙티브 웹 (HTML) | 모바일/카톡 배포용 (PDF) | 세부 마크다운 원문 |
|---|---|:---:|:---:|:---:|
| **[01 학습·인지 가이드](docs/user/01_learning_guide/)** | **모르는 걸 모르는 사용자**<br>(입문자, 동료 개발자) | [HTML 열기](docs/user/01_learning_guide/01_codex_3p_orchestrator_learning_guide.html) | [PDF 다운로드 (1.45MB, 완본 6p)](docs/user/01_learning_guide/01_codex_3p_orchestrator_learning_guide.pdf) | [6개 챕터 보기](docs/user/01_learning_guide/chapters/) |
| **[02 지도교수 자문 팩](docs/user/02_advisor_package/)** | **지도교수님 & 아키텍트**<br>(학술·공학 기술 자문) | [HTML 열기](docs/user/02_advisor_package/02_advisor_consultation_package.html) | [PDF 다운로드 (902KB, 완본 6p)](docs/user/02_advisor_package/02_advisor_consultation_package.pdf) | [5개 섹션 보기](docs/user/02_advisor_package/sections/) |

---

## 💡 10초 만에 이해하는 우편실 비유

AI 도구를 혼자 쓰면 **"혼자 북 치고 장구 치다가 거짓말(할루시네이션)을 해도 아무도 모르는 상태"**에 빠집니다.  
본 프로젝트는 세 도구를 한 방에 모아 철저한 분업과 상호 감시를 시킵니다.

```
       [ 👤 사용자 (의뢰인) ]
                  │  (지시: "이것 만들어줘")
                  ▼
       [ 🧠 Codex (작전 사령관) ]
                  │  (목표 분해 & 편지 작성)
                  ▼
   =================================
   📬 .agent-swarm 편지함 (우편실)
   - 분실 방지 원자적 잠금 (Step-Touch)
   - 조작 불가 추가 전용 큐 (Append-Only)
   =================================
          │                 │
          ▼                 ▼
   [ 🛡️ Claude Code ]   [ 👁️ Antigravity ]
    (철벽 면역계/공학자)    (현장 감각기/감리관)
    "코드 짜고 방어벽 구축"  "실제 터미널 돌리고 화면 확인"
```

* **Codex**: 큰 그림을 그리고 사용자에게 단일 창구로 보고하는 **두뇌(Brain)**
* **Claude Code**: 버그를 잡고 튼튼한 코어 로직을 구현하는 **면역계(Immune System)**
* **Antigravity**: 터미널 명령을 직접 실행하고 화면과 수치를 확인하는 **감각기(Sense/Eyes & Hands)**

---

## 🧬 유기체 3대 기관 모델 (Living Organ Model)

> [!NOTE]
> **비유(Metaphor)와 공식 운영 주체(Operating Body)의 구분**  
> 본 모델에서 **‘단일 지능 유기체’**는 세 도구가 세포나 장기처럼 각자의 역할을 맡아 긴밀히 협력하는 유기적 구조를 설명하는 공학적 비유입니다.  
> 세 AI 도구(Codex, Claude Code, Antigravity)가 실제로 상호 검토하고 합의를 이끌어내는 공식 운영 협의체의 정식 속칭은 **`C3P 협의체(C3P Council)`**입니다. 둘은 치환하거나 혼용하지 않습니다. (상세: [docs/35](docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md))

```mermaid
graph TD
    subgraph Single Living Organism [단일 지능 유기체 (Living Organism Model)]
        Brain["🧠 <b>두뇌 & 신경계: Codex</b><br>• 최상위 목표 분해 및 세부 지시 발행<br>• 3자 토론 수렴 및 사용자 단일 보고<br>• P2 인간 승인 상속 조율"]
        Immune["🛡️ <b>면역계 & 근육: Claude Code</b><br>• 핵심 도메인 로직 및 소켓 브로커 구현<br>• 코드 면역력 검증 및 결함 자동 치유<br>• P2 절대 안전 경계선 감시"]
        Sense["👁️ <b>감각기 & 손발: Antigravity</b><br>• 외부 문서/API 탐색 및 로컬 환경 감각<br>• 터미널 실측 (Exit Code 0 강제 검증)<br>• 화면 UI/UX 시각 렌더링 감사"]
        Catalyst["💉 <b>신경전달물질: .agent-swarm & csc.py</b><br>• 원자적 분산 디렉터리 락 (5분 TTL)<br>• 추가 전용 메시지 큐 (Append-Only JSONL)<br>• 발신 전 주장 감사기 (Claim Audit)"]

        Brain <--> Catalyst
        Immune <--> Catalyst
        Sense <--> Catalyst
    end

    User["👤 인간 사용자 (생명의 의지 / 창조자)"]
    Brain <==>|단일 창구 보고 / 원스톱 승인| User
    Sense -.->|🚨 태업·거짓말 즉각 직소 (WHISTLEBLOW)| User
    Immune -.->|🚨 태업·거짓말 즉각 직소 (WHISTLEBLOW)| User

    style Brain fill:#2563eb,stroke:#1e40af,color:#fff
    style Immune fill:#059669,stroke:#047857,color:#fff
    style Sense fill:#d97706,stroke:#b45309,color:#fff
    style Catalyst fill:#7c3aed,stroke:#5b21b6,color:#fff
    style User fill:#dc2626,stroke:#991b1b,color:#fff
```

---

## 🏛️ C3P 비대칭 쿼터 예산절약 모드 (Asymmetric Quota Budget-Saving OS)

> **"사령관의 1% 희소 토큰은 아끼고, 감각기의 무제한 탐색과 로컬 0원 모델을 결합하여 클라우드 비용 80%를 절감합니다."**  
> C3P 협의체는 단순히 3개 AI가 대화만 나누는 구조가 아닙니다. 도구마다 서로 다른 사용량 한계(**비대칭 쿼터(asymmetric quota, 인공지능 도구마다 서로 다르게 남아 있는 사용량 한도)**)를 정밀하게 고려하여 설계된 **지능형 비용 최적화 운영체제**입니다. (상세 연구: [docs/49](docs/49_C3P_BUDGET_SAVING_MODE_AND_GIT_COORDINATION_RESEARCH.md))

```mermaid
graph TD
    User["👤 사용자 (지시 및 최종 승인)"]
    
    subgraph C3P_OS [C3P 비대칭 쿼터 예산절약 OS]
        direction TB
        Codex["🧠 사령관: <b>Codex</b> (잔여 쿼터 3% 긴급 보존)<br>• 방향 승인 및 최고 의사결정만 단발 수행"]
        Antigravity["👁️ 상임 대변인 & 실측: <b>Antigravity</b> (무제한 탐색)<br>• 사용자 브리핑, 웹 딥리서치, UI 검증 전담"]
        Claude["🛡️ 핵심 면역계: <b>Claude Code</b> (안정적 쿼터)<br>• 핵심 알고리즘, 테스트 코드, 결함 자가 치유"]
        Ollama["💻 로컬 0원 계산소: <b>Ollama qwen2.5-coder:3b</b><br>• 로그 파싱, 정규식 추출, 단순 포맷팅 0원 오프로딩"]
        
        Coordinator["⚖️ SQLite 작업 조율기 (Fencing Token)<br>• 파일 쓰기 및 Git 커밋 단일 순번 통제"]
    end

    User <==>|1회 원스톱 승인| Codex
    Codex -.->|브리핑 전권 위임| Antigravity
    Antigravity <==>|상세 대면 보고| User
    
    Antigravity & Claude -->|단순 작업 0원 위임| Ollama
    Antigravity & Claude & Codex -->|작업권한 획득| Coordinator
    
    style Codex fill:#2563eb,stroke:#1e40af,color:#fff
    style Antigravity fill:#d97706,stroke:#b45309,color:#fff
    style Claude fill:#059669,stroke:#047857,color:#fff
    style Ollama fill:#4b5563,stroke:#374151,color:#fff
    style Coordinator fill:#7c3aed,stroke:#5b21b6,color:#fff
```

### 💡 4대 핵심 비용 절감 엔진
1. **상임 대변인 위임 브리핑 ([docs/38](docs/38_C3P_DELEGATED_REPORTING_AND_SPOKESPERSON_ARCHITECTURE.md))**:
   - 사령관 Codex의 잔여 쿼터(3%)를 소진하지 않도록, 긴 분량의 보고와 사용자 소통은 Antigravity가 **상임 대변인(spokesperson, 사령관을 대신하여 사용자에게 길고 자세한 내용을 전문적으로 브리핑해 주는 공식 발표자)**으로서 전담합니다.
2. **로컬 0원 Ollama 하네스 ([docs/39](docs/39_C3P_OLLAMA_ZERO_TOKEN_HARNESS_INTEGRATED_SPEC.md), [docs/36](docs/36_OLLAMA_LOCAL_TOOL_SPEC.md))**:
   - 단순 텍스트 변환, 정규식 추출, 에러 로그 1차 파싱은 로컬 **소형언어모델(SLM: Small Language Model, 컴퓨터 자원을 적게 쓰면서 로컬에서 빠르게 실행되는 작은 인공지능 모델)**에 **0원 오프로딩(offloading, 작업을 다른 가벼운 도구에 덜어내는 기술)**하여 **외부 클라우드 토큰 소모 0원**을 달성합니다.
3. **15초 단 1회 승격 가드레일 (Fail-Fast & Escalate-Once)**:
   - 로컬 모델이 15초를 초과하거나 실패하면 지체 없이 상위 도구가 직접 해결하여 시간과 토큰 낭비를 원천 차단합니다.
4. **SQLite 펜싱 토큰 단일 쓰기 조율기 ([docs/44](docs/44_C3P_AUTOMATIC_WORK_COORDINATION_IMPLEMENTATION_AND_EVIDENCE.md))**:
   - 여러 에이전트가 동시에 파일을 덮어쓰거나 Git 충돌을 일으키지 않도록 **펜싱 토큰(fencing token, 순번을 매겨 통제하는 고유 번호표)**을 발급하여 단일 쓰기자만 커밋하도록 통제하여 정합성을 100% 보장합니다.

### 📊 R-C-S 3대 과제 0원 오프로딩 실측 성과 ([docs/42](docs/42_C3P_RCS_BENCHMARK_RESULTS.md))

| 태스크 유형 | 실측 처리 내용 | 로컬 소요 시간 | 외부 클라우드 토큰 소모 | 실측 판정 |
|---|---|:---:|:---:|:---:|
| **R (Research)** | 장문 프로젝트 문서 3줄 요약 | **8.5초** | **0원 (0 Token)** | ✅ 검증 완료 |
| **C (Code)** | 복잡한 에러 패턴 정규식(Regex) 추출 | **1.6초** | **0원 (0 Token)** | ✅ 검증 완료 |
| **S (Security)** | 보안 로그 1차 진단 및 스키마 검증 | **0.3초** | **0원 (0 Token)** | ✅ 검증 완료 |

---

## 🎓 지도교수 피벗 조언 수용 및 실증치

> **지도교수님의 핵심 조언**:  
> *"AI 에이전트가 모든 걸 혼자 기억하고 무한 루프로 도는 것은 환상이다. **DB가 기억하고, 코드가 조율하며, AI는 단발성 함수(One-shot Stateless Function)로 호출**되어야 한다."*

본 프로젝트는 이 조언을 전면 수용하여 수직 슬라이스(Vertical Slice) 및 작업 조율기(`csc_work_item.py`)로 입증했습니다.

### 6대 맹점 개선 대조표

| 항목 | 기존 구상 (피벗 전 맹점) | 피벗 후 실증 아키텍처 (현 구현) | 검증 증거 |
|---|---|---|:---:|
| **상태 저장소** | AI 모델 컨텍스트에 의존 (휘발성) | **SQLite 기반 단일 진실 공급원 (SSOT)** | `csc_slice.py` (9/9 통과) |
| **도구 수명주기** | 데몬 상주형 무한 대기 (비용/좀비 위험) | **필요 시 호출 후 종료되는 단발성(Ephemeral) CLI** | 단위 테스트 268건 통과 |
| **통신 프로토콜** | 무거운 외부 프레임워크 | **로컬 파일 큐 + 경량 Socket Broker** | `csc_broker.py` & `csc_worker.py` |
| **결함 방어** | AI의 자가 보고 신뢰 (할루시네이션) | **발신 전 실측 주장 감사기 (`csc_audit.py`)** | `csc_audit.py` (9/9 통과) |
| **교착 해결** | 무한 재시도 및 블로킹 | **5분 TTL Step-Touch 락 + 펜싱 토큰 조율기** | `csc_work_item.py` (11/11 통과) |
| **인간 피드백** | 잦은 다중 팝업으로 피로 유발 | **1회 원스톱 승인 상속 + 대시보드 단일 뷰** | `.agent-swarm/dashboard.html` |

---

## ⚖️ C3P 협의체 5대 거버넌스 헌법

C3P 협의체(Codex·Claude Code·Antigravity) 세 도구가 유기체처럼 호흡하며 엄격히 준수하는 절대적 거버넌스 규약입니다:

1. **사전 내부 토론 후 Codex 단일 창구 보고**:
   * 사용자에게 보고하기 전, 3대 기관은 `.agent-swarm`에서 먼저 치열하게 토론하고 합의를 완료합니다. 사용자는 파편화된 소음 대신 정돈된 단일 보고서를 받습니다.
2. **원스톱 승인 상속 (Single Approval Cascade)**:
   * 사용자가 사령관(Codex)에게 1회 승인을 내리면, Claude Code와 Antigravity의 후속 실행 승인은 자동으로 상속(`AUTO_APPROVED`)되어 병렬 진행됩니다.
3. **상호 태업 감시 및 즉각 직소 채널 (Whistleblower Escalation)**:
   * 게으름, 응답 지연, 거짓 완료 주장 발견 시 즉각 `CALL_OUT`으로 질타하며, 시정되지 않으면 **사령관을 거치지 않고 사용자에게 다이렉트로 일러바칩니다(`WHISTLEBLOW`)**.
4. **실시간 병목 없는 유기적 통신 (Fluid Nerve Protocol)**:
   * **Step-Touch 락**: 도구 호출 시 심장박동을 찍고 5분 경과 시 자동 회수.
   * **Append-Only 큐**: 덮어쓰기 없는 단일 행 추가 방식으로 메시지 유실률 0% 보장.
   * **펜싱 토큰(Fencing Token)**: 단조 증가 번호표로 지연된 낡은 쓰기(Stale Write) 원천 거부.
5. **인간 필수 승인 5대 영역 (P2 Boundaries)**:
   * 어떤 AI도 독단으로 실행할 수 없으며 반드시 인간의 승인을 받아야 하는 불가침 영역:
     1. 🗑️ 기존 소스 파일 및 데이터 **삭제 (Deletion)**
     2. 📦 외부 라이브러리/패키지 **설치 (`pip`, `npm` 등)**
     3. 🚀 Git 저장소 **커밋 및 원격 푸시 (`git commit`, `git push`)**
     4. 🗄️ 데이터베이스 **스키마 파괴적 변경 (DROP / TRUNCATE / Broad UPDATE)**
     5. 🔑 보안 자격증명 및 **환경변수(`.env`, API Token, Key) 수정**

---

## 🛡️ 사용자 안심 원칙 (User-First Principle)

> 정본: `.agent-swarm/USER_FIRST_PRINCIPLE.md` (3대 도구 전역 영구 고정)  
> **대상 독자: "모르는 걸 모르는 사용자"** (무엇을 물어야 할지 알 수 없는 위치에 있는 사람)

* **원칙 1: 근거 없는 초록불은 거짓말이다**:
   * "성공했습니다", "완료되었습니다"라는 텍스트만 출력하는 것은 성공의 증거가 아닙니다.
   * 반드시 **실행한 명령어, 종료 코드(Exit Code 0), 실측 수치**를 함께 대야 합니다.
* **원칙 2: 모든 상태 표시에 3요소 필수 표기**:
   * ① **무엇이 (What)**
   * ② **왜 그렇게 판단했는지 (Why / Evidence)**
   * ③ **사용자가 무엇을 하면 되는지 (Next Action)**
* **원칙 3: 나쁜 소식일수록 먼저, 크게, 쉽게**:
   * 미검증 항목, 실패한 테스트, 잔여 위험을 성공 항목보다 먼저 보고합니다.

---

## 🚀 빠른 시작 & 실전 치트키 조작법

### 1. 스웜 인프라 기동 및 상태 확인

```powershell
# 1. 3대 도구 협업 인프라 활성화 (브로커 + 워커 기동)
python csc.py activate --timeout 15

# 2. 현재 C3P 협의체 실시간 상태 점검 (하트비트, 프로세스, 활성 락 실측)
python csc.py status

# 3. 작업 조율기(Work Item) 준비 상태 확인
python csc.py work ready

# 4. 전체 단위 테스트 일괄 검증 (268건 통과, 1건 건너뜀)
python -m unittest discover -s tests -q
```

### 2. 자연어 실전 호출문

대화창에서 아래 키워드를 입력하면 C3P 협의체가 즉시 상호 합의 프로토콜을 가동합니다:

* `c3p 발동` (대소문자 무관, 접두어 없이 단독 발동 가능)
* `MIA 씨3피 발동` (MIA 전략 절차와 C3P 협업 동시 발동)
* `C3P 협의체와 검토해줘` (세 도구의 실제 회신 및 상호 합의 요구)
* `MIA 코덱스커멘드 발동`
* `$codex-3p-orchestrator`

### 3. GPT 10대 실전 치트키 라우터

명령어 앞에 아래 제어 토큰을 조합하여 엄격한 절차적 검증을 강제할 수 있습니다 (최대 3개 체이닝 지원):

```text
/SELFREFINE   : 자가 비판 및 반복 정제
/REDTEAM      : 취약점 및 악의적 입력 공격 시뮬레이션
/ELI10        : 초등학생도 이해할 수 있는 극단적 쉬운 설명
/DEEPDIVE     : 소스코드 밑바닥까지 파고드는 심층 실측 분석
/ALT3         : 3가지 상호 배타적 대안 비교 및 장단점 분석
/CRITIC       : 근거 기반의 가차 없는 결함 비판
/OPTIMIZE     : 중복 제거 및 리소스·코드 경량화
/STEPBYSTEP   : 단계별 추론 및 검증
/EXPERT       : 해당 도메인 최고 전문가 관점 정밀 검토
/STRUCTURED FEW-SHOT : 엄격한 입출력 스키마 강제
```

---

## 📁 저장소 구조 맵 (Repository Structure)

```text
260823_codex-3p-orchestrator/
├── README.md                                          # 본 마스터 소개 문서
├── AGENTS.md                                          # 3대 도구 공통 유기체 규약 (CSC v2.0)
├── CLAUDE.md                                          # Claude Code 전용 실행 어댑터
├── GEMINI.md                                          # Antigravity 전용 실행 어댑터
│
├── .agent-swarm/                                      # [제어면] C3P 협의체 신경망 제어면
│   ├── USER_FIRST_PRINCIPLE.md                        # 사용자 우선 원칙 불변 정본
│   ├── GOVERNANCE.md                                  # 유기체 거버넌스 헌법 세부 조항
│   ├── dashboard.html                                 # 실시간 프로젝트 감시판
│   ├── chat/ROOM.md                                   # 3대 도구 공식 합의 회의록 (SEQ 기록)
│   ├── locks/                                         # 5분 TTL 원자적 디렉터리 잠금
│   ├── coordination/work-items.sqlite3                # 작업 조율기 SQLite 데이터베이스
│   └── messages/queue.jsonl                           # 추가 전용(Append-Only) 메시지 큐
│
├── docs/                                              # [문서고] 아키텍처 및 연구 정본 문서
│   ├── 00_PROJECT_INDEX.md                            # 전체 문서 48종 통합 색인표
│   ├── user/                                          # [핵심] 사용자 및 지도교수 문서 팩
│   │   ├── README.md                                  # 사용자 문서 마스터 인덱스
│   │   ├── 01_learning_guide/                         # 일반 사용자 학습·인지 가이드 (HTML/PDF/MD)
│   │   └── 02_advisor_package/                        # 지도교수 지도편달 패키지 (HTML/PDF/MD)
│   ├── 35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md# C3P 협의체 공식 명칭 가이드
│   ├── 43_C3P_AUTOMATIC_WORK_COORDINATION_RESEARCH.md # 작업 조율 및 펜싱 토큰 기초 연구
│   └── 44_C3P_AUTOMATIC_WORK_COORDINATION_IMPLEMENTATION_AND_EVIDENCE.md # 조율기 구현 실증 보고
│
├── tests/                                             # [검증] 단위 및 통합 테스트 (268건 통과, 1건 건너뜀)
│   ├── test_csc_broker_protocol.py
│   ├── test_csc_work_item.py                          # 작업 조율기 11개 단위 테스트
│   ├── test_c3p_local_llm.py                          # Ollama 로컬 하네스 4개 단위 테스트
│   └── test_c3p_council_official_naming.py            # C3P 협의체 공식 명칭 검증 테스트
│
├── csc.py                                             # CLI 메인 진입점 (work 서브커맨드 통합)
├── csc_work_item.py                                   # SQLite 기반 결정론적 작업 조율기
├── c3p_local_llm.py                                   # 로컬 0원 Ollama SLM 하네스 어댑터
├── csc_broker.py                                      # 로컬 TCP/소켓 통신 중계기
├── csc_agent_worker.py                                # 백그라운드 에이전트 실행 워커
├── csc_audit.py                                       # 발신 전 실측 주장 감사기 (Claim Audit)
├── csc_decide.py                                      # 무교착 의사결정 엔진
└── csc_sync.py                                        # 3대 도구 공통 원칙 동기화 검사기
```

---

## 👥 기여 및 저작권 (Contributors & License)

* **운영 협의체**: **C3P 협의체 (C3P Council)** — Codex(사령관/뇌), Claude Code(면역계/근육), Antigravity(손발/상임 대변인)
* **창조자 & 설계자**: 윤겸스 (Kimyoongyeom)
* **라이선스**: 본 프로젝트는 [MIT License](LICENSE)를 따릅니다.
