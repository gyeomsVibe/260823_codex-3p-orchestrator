# Final Artifact / Commit / Push Gate

이 문서는 실제 최종화 때 같은 표를 갱신해 사용한다.

## A0 — Artifact Proposal

- 후보 산출물:
- 제외 항목:
- 소유자:
- 검증 계획:
- artifact digest:

## A1 — Peer Review

| 검사자 | session / turn / message | 검토 범위 | 원 발언 증거·해시 | 판정 |
|---|---|---|---|---|
| Claude Code | pending | 오류·보안·테스트·회귀 | pending | BLOCKED |
| Antigravity | pending | 실행·브라우저·IDE·UX의 구체적 텍스트 관찰 | pending | BLOCKED |
| Codex | current task | 범위·승인·통합·전체 상태 | pending | BLOCKED |

## A2 — Opinion Resolution

| 의견 ID | 원 발언자 | 처리 상태 | 반영 내용 또는 기각 근거 | 재검증 |
|---|---|---|---|---|

## C0 — Commit Candidate

- Git 저장소 여부: 현재 아님
- stage 대상:
- 제외 대상:
- staged diff:
- commit message:
- candidate commit SHA 또는 staged digest:
- 검사 종료 코드:
- 사용자 commit 승인:

## C1 — Commit Consensus

| 도구 | READY/BLOCKED | 근거 |
|---|---|---|
| Codex | BLOCKED | 후보 없음 |
| Claude Code | BLOCKED | 후보 없음 |
| Antigravity | BLOCKED | 후보 없음 |

## P0 — Pre-Push Refresh

- remote / branch:
- local HEAD:
- tracking SHA:
- remote SHA:
- fetch 결과:
- 미추적·무시 파일 감사:
- 비밀정보 감사:
- 로컬·배포 환경 동작 일치(배포가 범위일 때):

## P1 — Push Consensus

| 도구 | READY/BLOCKED | 확인한 SHA | 남은 위험 |
|---|---|---|---|
| Codex | BLOCKED | 없음 | 원격 미지정 |
| Claude Code | BLOCKED | 없음 | 검증 미수행 |
| Antigravity | BLOCKED | 없음 | 실물 미확인 |

## P2 — User Approval

- 정확한 push 대상:
- 승인에 결속된 commit SHA:
- 승인 상태: 미승인

대상 SHA 또는 내용이 바뀌면 READY와 사용자 승인은 무효이며 C0부터 다시 진행한다.

## P3 — Post-Push Verification

- push 종료 코드:
- HEAD = tracking = remote:
- 필수 경로 원격 존재:
- 잔여 위험:
