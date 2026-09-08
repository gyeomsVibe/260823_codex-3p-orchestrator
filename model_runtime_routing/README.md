# C3P 모델·추론 강도 사전 선택기

이 폴더는 새 하위 작업을 시작하기 전에 작업의 위험과 검증 가능성을 보고
모델 등급과 추론 강도를 고르는 결정론적 정책(deterministic policy, 같은 입력에는
같은 결정을 내리는 규칙) 시제품이다. 실행 중인 모델을 교체하거나 전역 설정을
바꾸지 않는다.

## 안전 원칙

- 모델은 자신을 낮은 등급으로 강등하지 못한다.
- 보안·인증·배포·파괴 작업은 사용량이 부족해도 품질 등급을 낮추지 않는다.
- 사용량을 모르면 한 번만 순차 실행한다.
- 실패한 작업은 `BLOCKED` 또는 `DEFER_OR_EQUIVALENT_FALLBACK`으로 드러낸다.
- 실제 실행기는 선택 결과와 실제 해석된 모델·사용량을 별도 감사 로그에 남겨야 한다.

## 건식 실행

```powershell
python -m model_runtime_routing .\task-profile.json
```

필수 입력은 `task_id`, `platform`, `task_kind`, `risk`, `quota_state`다.
출력의 `launch_args`는 검토용이며 이 시제품은 해당 명령을 실행하지 않는다.
