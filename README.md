# 🧬 Codex 3P Orchestrator (CSC v2.0)
### 3대 AI 도구(Codex, Claude Code, Antigravity) 단일 지능 유기체 병렬 협업 프레임워크

> **공식 속칭:** **C3P 협의체(C3P Council, Codex·Claude Code·Antigravity가 함께 검토하고 실행하는 3도구 협업 체계)**
> 프로젝트와 저장소의 정식 이름은 `codex-3p-orchestrator`이며, 운영 협의체를 말할 때 `C3P 협의체`를 사용합니다. 자세한 구분은 [C3P 협의체 공식 명칭과 바로 쓰는 방법](docs/35_C3P_COUNCIL_OFFICIAL_NAME_AND_USAGE_GUIDE.md)을 확인하세요.

[![Tests](https://img.shields.io/badge/Unit_Tests-129_Passed-10b981?style=flat-square&logo=python)](tests/)
[![Principle Sync](https://img.shields.io/badge/User--First-6%2F6_Synced-3b82f6?style=flat-square)](.agent-swarm/USER_FIRST_PRINCIPLE.md)
[![Audit](https://img.shields.io/badge/Claim_Audit-9%2F9_Passed-8b5cf6?style=flat-square)](csc_audit.py)
[![Decide](https://img.shields.io/badge/Decide_Engine-12%2F12_Passed-f59e0b?style=flat-square)](csc_decide.py)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

> *"많은 세포나 기관이 일정한 질서에 따라 조직화되어, 생명 활동을 유지하기 위해 상호 긴밀하게 연관되어 기능하는 하나의 통일체."*  
> 본 저장소는 **Codex, Claude Code, Antigravity**를 별개의 분리된 도구가 아니라, **`.agent-swarm` 제어면과 로컬 소켓 브로커를 신경망 촉매로 삼아 호흡하는 단일 지능 유기체(Living Organism)**로 통합 작동시키는 실시간 오케스트레이터입니다.

---

## 📑 목차 (Table of Contents)

1. [🌟 2대 독립 패키지 (핵심 산출물 바로가기)](#-2대-독립-패키지-핵심-산출물-바로가기)
2. [💡 10초 만에 이해하는 우편실 비유](#-10초-만에-이해하는-우편실-비유)
3. [🧬 유기체 3대 기관 모델 (Living Organ Model)](#-유기체-3대-기관-모델-living-organ-model)
4. [🎓 지도교수 피벗 조언 수용 및 실증치](#-지도교수-피벗-조언-수용-및-실증치)
5. [⚖️ 5대 유기체 절대 거버넌스 헌법](#️-5대-유기체-절대-거버넌스-헌법)
6. [🛡️ 사용자 안심 원칙 (User-First Principle)](#️-사용자-안심-원칙-user-first-principle)
7. [🚀 빠른 시작 & 실전 치트키 조작법](#-빠른-시작--실전-치트키-조작법)
8. [📁 저장소 구조 맵 (Repository Structure)](#-저장소-구조-맵-repository-structure)

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

```mermaid
graph TD
    subgraph Single Living Organism [단일 지능 유기체 (Living Organism)]
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

## 🎓 지도교수 피벗 조언 수용 및 실증치

> **지도교수님의 핵심 조언**:  
> *"AI 에이전트가 모든 걸 혼자 기억하고 무한 루프로 도는 것은 환상이다. **DB가 기억하고, 코드가 조율하며, AI는 단발성 함수(One-shot Stateless Function)로 호출**되어야 한다."*

본 프로젝트는 이 조언을 전면 수용하여 수직 슬라이스(Vertical Slice)로 입증했습니다.

### 6대 맹점 개선 대조표

| 항목 | 기존 구상 (피벗 전 맹점) | 피벗 후 실증 아키텍처 (현 구현) | 검증 증거 |
|---|---|---|:---:|
| **상태 저장소** | AI 모델 컨텍스트에 의존 (휘발성) | **SQLite 기반 단일 진실 공급원 (SSOT)** | `csc_slice.py` (9/9 통과) |
| **도구 수명주기** | 데몬 상주형 무한 대기 (비용/좀비 위험) | **필요 시 호출 후 종료되는 단발성(Ephemeral) CLI** | 단위 테스트 129건 통과 |
| **통신 프로토콜** | 무거운 외부 프레임워크 | **로컬 파일 큐 + 경량 Socket Broker** | `csc_broker.py` & `csc_worker.py` |
| **결함 방어** | AI의 자가 보고 신뢰 (할루시네이션) | **발신 전 실측 주장 감사기 (`csc_audit.py`)** | `csc_audit.py` (9/9 통과) |
| **교착 해결** | 무한 재시도 및 블로킹 | **5분 TTL Step-Touch 락 + 정족수 엔진** | `csc_decide.py` (12/12 통과) |
| **인간 피드백** | 잦은 다중 팝업으로 피로 유발 | **1회 원스톱 승인 상속 + 대시보드 단일 뷰** | `.agent-swarm/dashboard.html` |

---

## ⚖️ 5대 유기체 절대 거버넌스 헌법

1. **사전 내부 토론 후 Codex 단일 창구 보고**:
   * 사용자에게 보고하기 전, 3대 기관은 `.agent-swarm`에서 먼저 치열하게 토론하고 합의를 완료합니다. 사용자는 파편화된 소음 대신 정돈된 단일 보고서를 받습니다.
2. **원스톱 승인 상속 (Single Approval Cascade)**:
   * 사용자가 사령관(Codex)에게 1회 승인을 내리면, Claude Code와 Antigravity의 후속 실행 승인은 자동으로 상속(`AUTO_APPROVED`)되어 병렬 진행됩니다.
3. **상호 태업 감시 및 즉각 직소 채널 (Whistleblower Escalation)**:
   * 게으름, 응답 지연, 거짓 완료 주장 발견 시 즉각 `CALL_OUT`으로 질타하며, 시정되지 않으면 **사령관을 거치지 않고 사용자에게 다이렉트로 일러바칩니다(`WHISTLEBLOW`)**.
4. **실시간 병목 없는 유기적 통신 (Fluid Nerve Protocol)**:
   * **Step-Touch 락**: 도구 호출 시 심장박동을 찍고 5분 경과 시 자동 회수.
   * **Append-Only 큐**: 덮어쓰기 없는 단일 행 추가 방식으로 메시지 유실률 0% 보장.
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

# 2. 현재 유기체 실시간 상태 점검 (하트비트, 프로세스, 활성 락 실측)
python csc.py status

# 3. 실시간 주장 감사기 자체 검증
python csc_audit.py --selftest

# 4. 전체 단위 테스트 129종 일괄 검증
python -m unittest discover -s tests -q
```

### 2. 자연어 실전 호출문

대화창에서 아래 키워드를 입력하면 3대 도구가 즉시 상호 합의 프로토콜을 가동합니다:

* `c3p 발동` (대소문자 무관, 접두어 없이 단독 발동 가능)
* `MIA c3p 발동`
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
├── .agent-swarm/                                      # [제어면] 3대 도구 신경망 디렉터리
│   ├── USER_FIRST_PRINCIPLE.md                        # 사용자 우선 원칙 불변 정본
│   ├── GOVERNANCE.md                                  # 유기체 거버넌스 헌법 세부 조항
│   ├── dashboard.html                                 # 실시간 프로젝트 감시판
│   ├── chat/ROOM.md                                   # 3대 도구 공식 합의 회의록 (SEQ 기록)
│   ├── locks/                                         # 5분 TTL 원자적 디렉터리 잠금
│   └── messages/queue.jsonl                           # 추가 전용(Append-Only) 메시지 큐
│
├── docs/                                              # [문서고] 아키텍처 및 연구 산출물
│   ├── 00_PROJECT_INDEX.md                            # 전체 문서 29종 통합 색인표
│   ├── user/                                          # [핵심] 사용자 및 지도교수 문서 팩
│   │   ├── README.md                                  # 사용자 문서 마스터 인덱스
│   │   ├── 01_learning_guide/                         # 일반 사용자 학습·인지 가이드 (HTML/PDF/MD)
│   │   └── 02_advisor_package/                        # 지도교수 지도편달 패키지 (HTML/PDF/MD)
│   └── 24_CSC_LOCAL_SOCKET_BROKER_RESEARCH_AND_IMPLEMENTATION_PLAN.md # 소켓 브로커 연구 계획
│
├── tests/                                             # [검증] 단위 및 통합 테스트 (129건 PASS)
│   ├── test_csc_broker_protocol.py
│   ├── test_csc_worker.py
│   └── test_user_first_dashboard.py
│
├── csc.py                                             # CLI 메인 진입점 (activate, status, lock, send)
├── csc_broker.py                                      # 로컬 TCP/소켓 통신 중계기
├── csc_worker.py                                      # 각 에이전트 등록형 백그라운드 워커
├── csc_audit.py                                       # 발신 전 실측 주장 감사기 (Claim Audit)
├── csc_decide.py                                      # 무교착 의사결정 엔진
├── csc_slice.py                                       # 수직 슬라이스 실증 엔진
└── csc_sync.py                                        # 3대 도구 공통 원칙 동기화 검사기
```

---

## 👥 기여 및 저작권 (Contributors & License)

* **창조자 & 설계자**: 윤겸스 (Kimyoongyeom)
* **협업 지능 유기체**: Codex 3P (Codex 사령관, Claude Code 면역계, Antigravity 감각기)
* **라이선스**: 본 프로젝트는 [MIT License](LICENSE)를 따릅니다.
