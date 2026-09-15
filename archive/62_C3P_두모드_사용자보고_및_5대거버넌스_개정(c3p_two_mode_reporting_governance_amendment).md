# C3P 두 모드 사용자 보고 및 5대 거버넌스 개정

> 상태: `USER_CONFIRMED_PERMANENT_POLICY`  
> 적용: 일반 모드와 C3P 예산절약 모드  
> 공통 식별자: `C3P_TWO_MODE_REPORTING_GOVERNANCE_V1`

## 1. 결정

사용자 보고 경로와 승인 경로를 분리한다.

| 항목 | 일반 모드 | 예산절약 모드 |
|---|---|---|
| 기본 사용자 보고 | Codex가 종합 보고를 조율 | Antigravity가 직접 대변 브리핑 |
| Codex 역할 | 작업 조율, 검증 취합, P2 승인 경계 | 작업 조율, 검증 취합, P2 승인 경계 |
| Antigravity 역할 | 실측·탐색 결과 제공 | 실측·탐색 결과와 사용자 직접 브리핑 |
| P2 승인·정족수 판정 | 별도 사용자·증거 관문 | 별도 사용자·증거 관문 |

직접 브리핑은 승인권이 아니다. 모든 보고는 `운영모드`, `발신 도구`, `관찰 사실`, `검증 상태`, `사용자 다음 행동`을 표시한다. `WHISTLEBLOW`(직접 위험 신고)는 두 모드 모두에서 유지한다.

## 2. 5대 거버넌스 헌법 개정

1. **사전 내부 토론 후 모드별 사용자 보고**: 일반 모드는 Codex 종합 보고, 예산절약 모드는 Antigravity 직접 대변 브리핑을 기본으로 한다.
2. **원스톱 승인 상속**: 보고 자체는 승인이 아니다. P2 경계는 발신 도구와 무관하게 사용자 승인을 요구한다.
3. **상호 감시와 직접 신고**: 거짓 완료·태업·위험은 `CALL_OUT`으로 기록하고, 긴급 위험은 대변 체계와 무관하게 직접 신고할 수 있다.
4. **유체 통신 규약**: 보고 봉투에는 모드·발신자·사실·검증·다음 행동을 넣는다. 요약은 원문 증거를 대체하지 않는다.
5. **P2 인간 승인 경계**: 삭제, 설치, commit·push, 파괴적 데이터 변경, 시크릿 변경은 어떤 보고나 대변 위임으로도 승인되지 않는다.

## 3. 비판·레드팀 판정

| 위험 | 재현 조건 | 영향 | 최소 방어 |
|---|---|---|---|
| 보고권을 승인권으로 오해 | Antigravity 브리핑만 보고 P2 실행 | 무단 외부효과 | 모든 보고에 P2 상태와 승인 주체 표시 |
| 두 모드 혼동 | 일반 모드에서 대변 보고를 강제하거나 반대 | 책임·토큰 경로 혼선 | `mode`와 `reporter` 필수 표시 |
| 단일 창구가 다시 SPOF가 됨 | Codex 지연·쿼터 소진 | 사용자 소통 정지 | 예산절약 모드 직접 대변 브리핑과 `WHISTLEBLOW` 유지 |
| 대변인이 미검증 완료를 전달 | 테스트·원문 증거 없음 | 잘못된 의사결정 | `verification_status`와 원문 경로 필수 |

## 4. 최신 공개 근거와 적용 범위

- [OpenAI Agents SDK의 관리자·핸드오프 구분](https://openai.github.io/openai-agents-python/agents/)은 중앙 관리자가 대화를 유지하는 방식과 전문 에이전트가 대화를 넘겨받는 방식을 구분한다. C3P는 이를 일반 모드와 예산절약모드의 보고 경로 분리에만 참고하며, 구현 권한을 자동 이전하지 않는다.
- [OpenAI Agents SDK의 승인 흐름](https://openai.github.io/openai-agents-python/human_in_the_loop/)은 민감 도구 호출을 승인 대기로 중단하고 재개하는 방식을 설명한다. C3P의 P2 경계는 보고자와 무관하게 별도 승인으로 유지한다.
- [AutoGen의 UserProxyAgent 설명](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html)은 사용자 입력을 팀에 전달하는 별도 에이전트 역할을 제공한다. 이는 Antigravity의 대변 브리핑이 사령권 승계를 뜻하지 않는다는 설계 근거다.
- [LangChain의 Human-in-the-Loop 문서](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)는 파일 쓰기·SQL 실행 같은 도구 호출을 정책에 따라 중단·승인·거절하도록 설명한다. C3P도 직접 보고와 실행 승인을 분리한다.

이 자료들은 C3P의 구현 완료 증거가 아니라 역할·승인 분리 원칙을 검토하는 최신 공개 근거다.

## 5. 검증과 변경 경계

- 공통 규칙 파일은 `python csc_sync.py`에서 `C3P_TWO_MODE_REPORTING_GOVERNANCE_V1`을 검사한다.
- 회귀 검사는 `tests/test_user_first_dashboard.py`의 공통 계약 검사를 사용한다.
- 이 문서는 사용자 보고·거버넌스 규칙만 바꾼다. 런타임 기동 상태, 정족수, Antigravity의 파일 수정 권한, commit·push 승인은 별도로 실측·승인해야 한다.
