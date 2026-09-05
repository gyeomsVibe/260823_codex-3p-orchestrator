# 🛰️ 3대 AI 통신 진보안 연구·토론 및 실시간 브로커 아키텍처 명세 (3P Communication & Broker Spec)

> **일자**: 2026-08-24  
> **참여 기관**: Codex(사령관/Brain), Claude Code(면역계/Immune), Antigravity(감각계/Hands & Eyes)  
> **결론**: **CSC Dynamic Port Asyncio Socket Broker v2.0 합의 채택**

---

## 1. 3대 도구 3자 심층 토론 요약 (3-Agent Virtual Consensus Debate)

### 🧠 Codex (사령부 / Brain / PC GUI)
> *"현재의 파일 기반 IPC(`.agent-swarm/messages/*.jsonl`)는 단순하고 신뢰성이 높지만, 밀리초 단위의 실시간 반응성과 동적 스트리밍에서 디스크 I/O 병목이 발생합니다. GUI 사령부로서 사용자의 명령을 즉시 분해하여 2대 CLI 워커에 10ms 이내로 쏘아보낼 수 있는 초경량 로컬 비동기 서버가 필요합니다."*

### 🛡️ Claude Code (면역계 / Immune / Background CLI)
> *"동의합니다. 백그라운드에서 실행되는 동안 무한정 파일 디렉토리를 폴링(Polling)하는 것은 CPU 낭비와 락 경합을 유발합니다. TCP 소켓 또는 웹소켓 기반의 Pub/Sub 브로커를 띄우면, 블로킹 없이 이벤트 루프에서 즉각 패킷을 수신하고 구현에 착수할 수 있습니다. 단, 브로커 다운 시에도 작업 유실이 없도록 JSONL 영구 기록은 하이브리드로 유지되어야 합니다."*

### 👁️ Antigravity (감각계 / Hands & Eyes / CLI & Bridge)
> *"또한 포트 충돌 방지가 핵심입니다. 고정 포트(예: 8080)를 쓰면 사용자 PC의 다른 개발 서버와 충돌할 수 있으므로, 스킬 구동 시 가용 포트(`8765~8774`)를 탐색하여 동적으로 바인딩하고 `.agent-swarm/broker.json`에 메타데이터를 기록하는 '온디맨드 라이프사이클' 구조가 안전합니다."*

---

## 2. 통신 후보 기술 4대 렌즈 비교 평가

| 후보 기술 | 1. 가치성 (Value) | 2. 실현가능성 (Feasibility) | 3. 지속가능성 (Viability) | 4. 위험도 (Risk) | 최종 판정 |
|---|---|---|---|---|---|
| **A. 파일 기반 IPC (기존)** | 낮음 (폴링 랙 0.5~1초) | 매우 높음 (의존성 0) | 보통 (I/O 부하) | 낮음 (안정적) | **보조 백업으로 유지** |
| **B. Windows Named Pipes** | 높음 (초저지연) | 보통 (OS 종속적) | 낮음 (크로스플랫폼 한계) | 보통 (디버깅 난이도) | **No-Go** |
| **C. Asyncio Socket Broker (선정)** | **매우 높음 (<2ms, 실시간 스트림)** | **매우 높음 (Python 기본 내장)** | **매우 높음 (Zero External Dep)** | **매우 낮음 (포트 자동 점유)** | **🏆 Go (만장일치 합의)** |
| **D. gRPC / Protobuf** | 높음 (엄격한 스키마) | 낮음 (별도 컴파일 및 pip 필요) | 보통 (빌드 복잡도) | 높음 (P2 경계 위반) | **No-Go** |

---

## 3. 브로커 아키텍처 및 라이프사이클 (Broker Architecture & Lifecycle)

```
                       ┌────────────────────────────────┐
                       │     👤 사용자 (Human Creator)   │
                       └───────────────▲────────────────┘
                                       │ 단일 창구 보고 / 원스톱 승인
                       ┌───────────────▼────────────────┐
                       │    🧠 Codex App (사령부/GUI)    │
                       └───────────────▲────────────────┘
                                       │ Local TCP (8765)
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
┌─────────▼─────────┐        ┌─────────▼─────────┐        ┌─────────▼─────────┐
│ 🛡️ Claude Code CLI│        │ ⚡ CSC Event Broker│        │ 👁️ Antigravity CLI │
│  (Immune/Logic)   │<──────>│ (Asyncio / Memory)│<──────>│(Hands & Eyes / QA)│
└───────────────────┘        └─────────┬─────────┘        └───────────────────┘
                                       │ Auto Flush
                             ┌─────────▼─────────┐
                             │ 💾 .agent-swarm/  │
                             │   queue.jsonl     │
                             └───────────────────┘
```

1. **Start**: 스킬 발동 시 `python csc.py broker start`로 백그라운드 소켓 브로커 구동 (동적 포트 8765 자동 바인딩).
2. **Register**: Claude Code 및 Antigravity CLI 워커가 브로커에 접속하여 `REGISTER` 핸드셰이크 수행.
3. **Stream**: 실시간 Pub/Sub 통신 진행 (태업 감시 `WHISTLEBLOW`, 자원 락 이벤트 `LOCK_ACQUIRED` 등 10ms 이내 브로드캐스트).
4. **Stop**: 작업 완료 후 `python csc.py broker stop`으로 브로커 안전 셧다운 및 잔여 프로세스 정리.
