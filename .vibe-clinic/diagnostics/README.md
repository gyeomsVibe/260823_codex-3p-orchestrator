# C3P 마일스톤 자가진단 항목

이 폴더는 `python csc_clinic.py --milestone <이름>`이 실행하는 기계 진단의 정본입니다.

- `01_regression.clinic.js`: 저장소 표준 `unittest` 회귀 검사
- `02_principle.clinic.js`: 세 도구 공통 원칙 동기화 검사
- `03_claims.clinic.js`: 최근 주장 감사 기록 검사
- `04_decision.clinic.js`: 의사결정 엔진 검사
- `05_declarations.clinic.js`: 런타임 선언과 실제 상태 대조
- `_shared.js`: 모든 진단이 함께 쓰는 실행·판정 도구

각 진단은 확인하지 못한 범위를 결과에 함께 적습니다. 진단이 없거나 결과를 읽지 못하면 통과로 처리하지 않습니다.
