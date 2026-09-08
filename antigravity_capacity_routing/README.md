# Antigravity 희소 토큰 절감 라우터

이 폴더는 Antigravity가 긴 열람·반복 검증을 먼저 수행하고 Codex·Claude Code는 판단과 예외에 집중할 때 실제 이득이 있는지 측정하는 최소 증명 모듈이다. `policy.py`는 AI를 직접 호출하지 않으며, 실제 호출과 계측은 저장소 루트의 `csc_agent_worker.py`가 담당한다.

## 작동 순서

1. `route`가 업무 특성을 받아 Antigravity 위임 가능 여부와 1~3개 레인을 결정한다.
2. `validate-evidence`가 Antigravity의 증거 위치와 해시를 검사한다.
3. `evaluate`가 기준 방식과 실험 방식의 희소 토큰, 품질, 시간, 검토 노력, 안전을 같은 기준으로 비교한다.
4. CSC Antigravity 워커가 모든 프롬프트에 읽기 전용 하네스 계약을 붙이고 `stream-json`의 응답과 토큰을 분리한다.
5. 권한 거부·빈 응답·0 토큰·깨진 스트림은 성공 표시와 무관하게 실패로 닫는다. 계측 로그에는 응답 전문을 저장하지 않는다.

세 도구는 모든 경로에서 협의체 구성원으로 남는다. Claude Code는 정상 경로에서 원문 전체 대신 작은 증거표만 심사하는 `COMPACT_SENTINEL`(압축 감시표) 역할을 맡고, 고위험 업무·증거 검사 실패·결과 불일치에서는 `FULL_REVIEW`로 전환한다. 고위험 업무의 Antigravity 레인 0은 협의체 탈퇴가 아니라 대량 실행 금지를 뜻하며, Antigravity는 `ADVISORY_ONLY`로 의견을 낸다.

## STRUCTURED FEW-SHOT 예시

### 예시 1 — 폭넓은 읽기 전용 조사

입력:

```json
{
  "task_id": "research-001",
  "task_kind": "research",
  "risk": "low",
  "read_only": true,
  "independent": true,
  "verifiable": true,
  "shared_write": false,
  "external_side_effect": false,
  "judgment_required": false,
  "bulk_work": true,
  "parallel_units": 3
}
```

결과의 핵심: `ANTIGRAVITY_FIRST`, 3개 레인, Claude는 `COMPACT_SENTINEL`.

### 예시 2 — 인증 코드 수정

입력에서 `task_kind=authentication`, `read_only=false`, `shared_write=true`, `risk=high`로 둔다.

결과의 핵심: `SCARCE_CONTROLLED`, Antigravity 레인 0개, Claude는 `FULL_REVIEW`.

### 예시 3 — 서로 나눌 수 없는 대용량 파일 읽기

입력에서 `task_kind=code_search`, `read_only=true`, `verifiable=true`, `independent=false`, `bulk_work=true`로 둔다.

결과의 핵심: `ANTIGRAVITY_FIRST`, 1개 순차 레인. 병렬화 비용은 만들지 않되 긴 열람은 옮긴다.

### Claude 압축 감시표 계약

Claude Code에는 원문이나 긴 Antigravity 답변을 다시 주지 않는다. 기계 검사 결과와 표본 주장만 다음 형식으로 전달한다.

```json
{
  "verdict": "ACCEPT | ESCALATE",
  "failed_claim_ids": [],
  "reason_codes": [],
  "critical_constraints": []
}
```

`ACCEPT`는 협의체 참여표이며 재구현 요청이 아니다. `ESCALATE`일 때만 원문 위치 중 필요한 부분을 추가로 읽는다.

증거 묶음의 모든 주장은 `claim_id`를 가져야 한다. 감시표의 `failed_claim_ids`가 정확한 주장을 가리켜야 긴 원문을 다시 보지 않고도 이견을 처리할 수 있다.

## 명령

```powershell
python -m antigravity_capacity_routing route task-profile.json
python -m antigravity_capacity_routing validate-evidence evidence.json --project-root .
python -m antigravity_capacity_routing evaluate baseline.json candidate.json --policy antigravity_capacity_routing/pilot_policy.json
```

`evaluate`는 `SCALE`일 때만 종료 코드 0을 반환한다. `ITERATE`와 `STOP`은 종료 코드 2다. 수치가 없는 항목을 0으로 추정하지 말고 실제 CLI 결과에서 기록해야 한다.

현재 수직 절편은 **완료 후 계측**까지 구현한다. 실행 도중 누적 토큰이 작업 예산을 넘으면 끊는 실시간 회로 차단기는 다음 구현 단위다. 작은 호출도 큰 고정비를 쓰는 실측이 나왔으므로, 작업당 상한을 임의 숫자로 정하지 않고 비교 파일럿에서 결정한다.
