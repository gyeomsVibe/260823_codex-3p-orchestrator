# 📡 Codex 3P Orchestrator 통신 프로토콜 및 거버넌스 명세

## 1. 통신 아키텍처 개요
본 시스템은 **Dynamic Port Socket Broker + Append-Only JSONL**의 2계층 하이브리드 통신 모델을 채택합니다.

```
[Layer 1: Real-time Event Plane]
  Codex (Brain) <== TCP Socket (Localhost:8765) ==> Claude CLI / Antigravity CLI
  - 지연시간: < 2ms
  - 이벤트 스트리밍, PING/PONG 하트비트, 태업 감시(Whistleblowing)

[Layer 2: Persistent Storage Plane]
  .agent-swarm/messages/queue.jsonl
  - SSOT 원자적 영구 기록, 세션 재개 및 복구 보장
```

## 2. 메시지 패킷 스키마 (Message Packet Schema)

```json
{
  "type": "TASK | EVENT | RESULT | RISK | CALL_OUT | WHISTLEBLOW | ACK",
  "id": "MSG-YYYYMMDD-HHMMSS-SRC-DST",
  "from": "codex | claude | antigravity",
  "to": "codex | claude | antigravity | all",
  "timestamp": "2026-08-24T13:00:00Z",
  "in_reply_to": "none | parent_id",
  "body": "내용",
  "meta": {
    "step_index": 1,
    "lock_acquired": "optional_resource_path"
  }
}
```

## 3. 동적 포트 바인딩 및 생명주기 관리
- 기본 포트: `8765` (충돌 시 `8766 ~ 8774` 범위 내 가용 포트 자동 점유)
- 브로커 메타 저장: `.agent-swarm/broker.json` (PID, Host, Port, Started_At)
- 종료 처리: 작업 완료 또는 오케스트레이션 종료 시 SIGTERM/Taskkill로 잔여 프로세스 방지.
