# Ollama 3+1 참여 및 Claude 부재 대체 결정

- 갱신일: 2026-09-04
- 상태: **3+1 PILOT GO / EQUAL FOURTH VOTE NO-GO**
- 적용 범위: Codex, Claude Code, Antigravity, 로컬 Ollama

## 1. 결정

Ollama를 네 번째 구성요소로 추가하는 가치는 있다. 그러나 현재는 Claude Code와 동등한 능력·표결권을 자동 승계하지 않는다.

권장 구조는 **4자 동등체가 아니라 3+1 복원력 구조**다.

```text
Codex             : 총괄·사용자 창구·최종 합성
Claude Code       : 코어 구현·코드 비판
Antigravity       : 연구·실측·QA
Ollama Local Seat : 쿼터 독립 초안·반례·저위험 예비 표결 후보
```

Ollama의 자리는 모델 태그와 벤치마크 digest에 결속한다. 모델을 바꾸면 자격을 다시 평가한다.

## 2. MIA 적합성 평가

| 기준 | 평가 | 근거 |
|---|---|---|
| 타당성 | 조건부 높음 | 이미 로컬 API와 CLI가 있고 외부 공급자 쿼터와 독립적 |
| 유효성 | 현재 낮음 | 최신 `qwen3.5:4b` 고정 시험이 첫 사례에서 45초 타임아웃 |
| 가치 부합 | 높음 | Claude 사용량 소진 때 판단 공백과 대기 비용을 줄이는 방향 |
| 품질 동등성 | 미확인 | 3B/4B 로컬 모델은 Claude Code의 구현·장기 문맥 능력과 동등하다는 증거 없음 |
| 운영 단순성 | 중간 | 직접 Ollama API 사용은 단순하지만 네 번째 상태·모델 자격·정족수 관리가 추가됨 |
| 프라이버시 | 높음 | 로컬 실행 시 프로젝트 내용이 외부 모델 공급자 호출로 나가지 않음 |

판정은 **아키텍처 실험 GO, 동등 표결권 NO-GO**다.

## 3. 로컬 실측

- Ollama: `0.33.2`
- 설치 모델:
  - `qwen3.5:4b` — 3.4GB
  - `qwen2.5-coder:3b` — 1.9GB
  - `qwen3-embedding:0.6b` — 639MB, 생성·표결 모델 아님
- GPU: NVIDIA GeForce GTX 1660 Ti, VRAM 6,144MiB
- CPU: Intel i7-9750H, 6코어/12스레드
- RAM: 31.8GiB, 조회 시 여유 19.5GiB

WMI `AdapterRAM`은 약 4GB로 표시됐지만 NVIDIA `nvidia-smi` 실측은 6,144MiB였다. 모델 크기 판단에는 후자를 사용한다.

## 4. 최신 벤치마크 판정

정본 아티팩트:

- `.agent-swarm/results/ollama-benchmark-20260904.json`
- SHA-256: `7B8B29C0B9020A215DB74973F512656C552BE097CB9D4F4C4E83BA9980DB0929`

결과:

- 모델: `qwen3.5:4b`
- 역할: `non_voting_untrusted_advisor`
- 첫 `approval_boundary` 사례: 45.022초 타임아웃
- schema: 실패
- semantic: 실패
- 모델 해제: 성공
- 최종: `NO_GO`

이전의 성공 관찰보다 현재 정본 파일의 최신 결과와 digest를 우선한다. 현재 모델은 표결 대체 자격이 없다.

## 5. 4자 의사결정 정책

### 현재 단계

Ollama는 무투표 보조자다. 기존 3자 정족수는 바꾸지 않는다.

### 자격 통과 후 LOW 범위

Ollama가 고정 평가를 통과하면 `LOCAL_ALTERNATE` 자격을 얻는다.

| 상태 | 판정 |
|---|---|
| 4개 모두 가용, 4 YES | `APPROVED_4_OF_4` |
| Claude만 검증된 불능, Codex+Antigravity+Ollama 3 YES | LOW·가역 작업만 `APPROVED_LOCAL_SUBSTITUTE` |
| 4개 중 3 YES, 1 NO | LOW·가역 작업만 `APPROVED_SUPERMAJORITY_WITH_DISSENT`; 반대 전문 보존 |
| 두 개 이상 불능 | AI 표결만으로 변경 승인 금지 |
| MEDIUM에서 명시적 NO | 사용자에게 이견 보고 후 보류 |
| 인증·설치·시스템 변경·삭제·commit/push | Ollama가 있어도 사용자 승인과 기존 고위험 게이트 유지 |

Ollama의 표는 Claude의 과거 표를 복제하는 것이 아니라 독립적으로 생성돼야 한다. Claude가 사용량 소진이면 같은 결정에서 재호출하지 않고 Ollama 자격 여부를 즉시 확인한다.

## 6. 모델 후보 평가

### 1순위: 설치된 `qwen2.5-coder:3b`

- 장점: 이미 설치됨, 1.9GB, 코드 특화, 추가 다운로드 없음
- 약점: 3B 규모의 추론·반례 품질 한계
- 결정: 다음 동일 벤치마크 대상으로 추천

### 2순위: `qwen2.5-coder:7b` 또는 7B Q3 양자화

- 공식 Ollama 태그 크기: 기본 4.7GB, Q3 변형 약 3.5~4.1GB
- 6GB VRAM에서 짧은 컨텍스트 시험 가능성이 있으나 KV cache와 런타임 오버헤드를 포함하면 여유가 작다.
- 결정: 3B 품질이 부족할 때만 설치 승인 후 비교 시험

### 보류: `gpt-oss-20b`

- OpenAI는 약 16GB 메모리에서 실행 가능하다고 설명한다.
- 시스템 RAM에는 들어갈 수 있지만 6GB VRAM을 넘겨 CPU/RAM 오프로딩과 큰 지연이 예상된다.
- 결정: 실시간 표결 후보가 아니라 야간 비동기 심층 검토 후보

### 기각: `qwen3-coder:30b`, `devstral-2:123b`

- Qwen3-Coder 30B의 Ollama 크기는 약 19GB다.
- Devstral 2 123B의 Ollama 크기는 약 75GB다.
- 현재 장비에서 실시간 예비 표결자 목표와 맞지 않는다.

## 7. 추가 도구 조사

### Goose CLI

공식 Ollama 통합 문서가 있고 로컬 모델을 에이전트 형태로 사용할 수 있다. 그러나 CSC가 이미 Ollama API 호출·권한 제한·스키마 검증을 직접 담당하므로 지금 추가하면 에이전트 루프와 권한 면이 중복된다. **현 단계 설치 비추천**.

### OpenCode 또는 Claude Code의 Ollama launch

Ollama 공식 모델 페이지는 `ollama launch opencode`와 `ollama launch claude` 통합을 안내한다. 하지만 목적은 Claude 제품을 흉내 내는 UI가 아니라 독립적인 로컬 예비 판단석이다. 기존 CSC 어댑터에 직접 연결하는 편이 출처와 권한을 더 명확하게 통제한다. **현 단계 비추천**.

### Qwen Code CLI

공식 Qwen 저장소는 비대화형 실행과 여러 클라우드 모델 인증을 지원한다. 클라우드 경로는 다시 사용량·인증 의존성을 만들며, 로컬 Ollama 직접 호출보다 복원력 이점이 작다. **클라우드 비상 공급자 후보로만 보류**.

결론: 지금 필요한 것은 새 CLI 설치가 아니라 기존 Ollama의 모델 평가와 CSC 직접 어댑터다.

## 8. 공식 근거

- Ollama Qwen2.5-Coder 모델·크기: https://ollama.com/library/qwen2.5-coder
- Ollama Qwen3-Coder 모델·크기: https://ollama.com/library/qwen3-coder
- Ollama 구조화 출력: https://docs.ollama.com/capabilities/structured-outputs
- Ollama 도구 호출: https://docs.ollama.com/capabilities/tool-calling
- Ollama Goose 통합: https://docs.ollama.com/integrations/goose
- OpenAI gpt-oss 소개·메모리 조건: https://openai.com/index/introducing-gpt-oss/
- Qwen Code 공식 설정: https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/settings.md

## 9. 단계별 실행 계획

1. Phase 1 브로커 인증과 Phase 2 원문 기록 분리를 먼저 구현한다.
2. `ollama_benchmark.py`가 allowlist 모델을 명시적 인자로 받도록 테스트 우선으로 확장한다.
3. 설치된 `qwen2.5-coder:3b`를 현재 3개 고정 사례와 동일 제한으로 실행한다.
4. 통과 기준을 schema 3/3, semantic 3/3, 개별 응답 30초 이내, 모델 해제로 둔다.
5. 실패하면 표결권 없이 초안·분류 역할만 유지한다.
6. 품질만 부족하고 지연은 통과하면 사용자 승인 후 7B Q3 모델 한 개만 설치·시험한다.
7. 기준 통과 시 `ollama` 어댑터와 `LOCAL_ALTERNATE` 정족수 테스트를 구현한다.
8. Claude 실제 부재를 모의하여 Codex+Antigravity+Ollama의 LOW 3/3 대체 표결을 검증한다.
9. 성공 후에도 MEDIUM/HIGH 자동 대체는 별도 3자 검토와 사용자 승인을 요구한다.

## 10. 최종 요약

Ollama 추가는 사용량 제한에 강한 시스템을 만드는 데 가치가 있다. 그러나 현재 `qwen3.5:4b`는 최신 시험에서 시간 초과했으므로 Claude의 빈자리를 맡길 수 없다. 우선 설치된 코드 특화 3B 모델을 같은 시험으로 검증하고, 통과할 때만 저위험 작업의 네 번째 예비 표결자로 승격한다. 새 CLI 도구 설치는 현재 이득보다 복잡성이 커서 보류한다.
