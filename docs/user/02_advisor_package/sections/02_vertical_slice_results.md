# 🧪 제2절: 수직 슬라이스 (Vertical Slice) 자체 실증 결과

## 1. csc_slice.py 자체검증 9/9 전원 통과
외부 의존성을 완전히 배제하고 순수 코드 기반으로 결함을 방어하는지 전수 검증했습니다:

- `[OK] valid`: 정상 스키마 JSON은 안전하게 DB 저장
- `[OK] bad_enum`: 허용되지 않은 임의 판정값 거부
- `[OK] out_of_range`: 신뢰도 수치(0.0~1.0) 초과 거부
- `[OK] missing / extra`: 필수 키 누락 및 위조 여분 키 배제
- `[OK] liar`: 형식은 맞으나 진위는 미확인된 경우 분리 기록
- `[OK] idempotent`: 동일 요청 재실행 시 중복 적재 방지
- 🔥 `[OK] override`: AI 주장=GO, 실제 종료코드=1 ➡️ 코드가 BLOCKED로 역전!
- `[OK] confirm`: AI 주장=GO, 실제 종료코드=0 ➡️ 코드가 최종 GO 인가

## 2. 실제 모델 CLI 호출 실측 증거
교수님의 원칙대로 Claude Code CLI를 단발성 서브프로세스로 기동하여 결과를 수집했습니다:

```json
$ python csc_slice.py run --provider claude --task "1+1의 값이 2인지 판정하라."
{
  "call_id": "4364e8fcdfa6541d",
  "status": "STORED",
  "data": {
    "verdict": "GO",
    "confidence": 0.99,
    "reason": "표준 산술에서 1+1은 2이므로 참이다."
  },
  "elapsed_s": 8.07
}
```
*Codex CLI의 경우 명령줄 해석(.CMD vs .EXE) 및 토큰 소진 이슈를 확인하여 파이프라인 핸들러를 보강했습니다.*
