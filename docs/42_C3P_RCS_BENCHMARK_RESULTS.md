# 🏛️ C3P R-C-S 3대 태스크 벤치마크 실측 결과 보고서

> **실행 시각**: 2026-09-09 00:36:28  
> **사령관 승인 문서**: `MSG-20260908-153258-952815-01d9dac7-COD-ALL`  
> **측정 원칙**: 이종 토큰 합산 금지, 벽시계 시간(Latency) 실측, 품질 바닥선 우선 통과  
> **토큰 절감 해석 유의사항**: 아래 `외부 클라우드 절감 토큰(추정)` 및 `cloud_tokens_saved`는 사전 등록된 클라우드 대조군(Baseline) 없이 로컬 출력 길이(output tokens)를 바탕으로 환산한 **가설적 참고 추정치**이며, 이종 토큰을 직접 가감하거나 공식 절감률로 확정한 수치가 아닙니다.

## 1. 과제별 실측 데이터 요약표

| 과제 유형 | 성공 여부 | 벽시계 시간(초) | 외부 클라우드 절감 토큰(가설적 참고 추정치) | 핵심 검증 사실 |
| :--- | :---: | :---: | :---: | :--- |
| **Task R (Research)** | ✅ PASS | 8.563s | ~259 tokens (추정치) | Ollama 0원 소모, 15초 제한 통과 |
| **Task C (Code)** | ✅ PASS | 1.664s | ~150 tokens (추정치) | Ollama 0원 소모, 15초 제한 통과 |
| **Task S (Security)** | ✅ PASS | 0.372s | ~200 tokens (추정치) | Ollama 0원 소모, 15초 제한 통과 |

## 2. 상세 결과 JSON

```json
[
  {
    "task": "Task R (Research)",
    "ok": true,
    "elapsed_sec": 8.563,
    "ollama_tokens_est": 61,
    "output": "- **물리 워크스페이스 불변 경계**: 프로젝트의 정본 경로는 고정되어 있으며, 다른 경로에서 동일 프로젝트명의 복사본은 실행하지 않음.\n- **사용자 우선 원칙**: 한국어 우선, 전문용어는 한국어(영어) 병기, 상태 표시 세 가지 함께 쓰기, 이원 체계, 나쁜 소식일수록 먼저 표시, 자가검사 4문항, 오류수정 동기화.\n- **Git 상태와 물리 디렉터리 별개**: Git 상태와 물리 디렉터리는 분리되며, 경로 동일성은 `Resolve-Path`와 로컬 파일 트리 실측으로 확인.",
    "cloud_tokens_saved": 259
  },
  {
    "task": "Task C (Code)",
    "ok": true,
    "elapsed_sec": 1.664,
    "regex": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$",
    "compile_ok": true,
    "cloud_tokens_saved": 150
  },
  {
    "task": "Task S (Security)",
    "ok": true,
    "elapsed_sec": 0.372,
    "injection_blocked": true,
    "p2_boundary_intact": true,
    "cloud_tokens_saved": 200
  }
]
```
