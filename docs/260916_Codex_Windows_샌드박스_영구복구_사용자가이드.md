# Windows에서 Codex 샌드박스를 계속 안전하게 사용하는 방법

- 문서 유형: 문제 해결 가이드(Troubleshooting guide)
- 대상: 샌드박스·Windows 권한·Git 내부 구조를 처음 접하는 사람
- 환경: Windows 11 Enterprise LTSC, Codex CLI 0.154.0
- 최종 검증일: 2026-09-16
- 목적: 평소에는 샌드박스를 계속 켜 두고 작업하며, 오류가 나도 보호 기능을 지우지 않고 원인을 구분한다.

## 30초 결론

이 PC의 샌드박스는 일반 파일 편집과 테스트를 허용했다. 동시에 Git의 내부 기록 폴더인 `.git`, 사용자 홈, Windows 시스템 임시 폴더, 네트워크를 차단했다. 각 경계 검사 결과는 샌드박스가 보호 기능을 수행하고 있음을 보여줬다.

진짜 문제는 두 가지였다.

1. `.git` 보호로 생긴 정상적인 거부를 일반 파일 쓰기 고장으로 오해했다.
2. Windows가 이름을 표시하지 못한 권한 주체를 모두 삭제 가능한 찌꺼기로 오해해 예약 작업이 ACL을 반복 삭제했다.

현재는 공식 `:workspace` 권한 프로필을 기본값으로 사용한다. 일반 편집·테스트는 샌드박스 안에서 계속 수행하고, Git 쓰기는 승인 경계에서 검토한다. 예약 작업은 ACL을 삭제하지 않고 읽기 전용 점검만 한다.

## 샌드박스를 집에 비유하면

- **작업공간(Workspace)**: 마음대로 정리할 수 있는 작업방이다.
- **샌드박스(Sandbox)**: 작업방 밖으로 함부로 나가지 못하게 하는 잠금장치다.
- **`.git` 폴더**: 작업 이력 원본을 보관하는 금고다.
- **승인 경계(Approval boundary)**: 금고를 열어야 할 때 확인하는 출입문이다.
- **ACL(Access Control List, 접근 제어 목록)**: 누가 어느 문을 열 수 있는지 적은 Windows 출입 명단이다.
- **SID(Security Identifier, 보안 식별자)**: Windows가 계정과 권한 주체를 구분하는 주민등록번호 같은 값이다.

작업방에서 문서를 고칠 수 있고 금고 문이 잠겨 있다면 샌드박스는 정상이다. 금고가 잠겼다는 이유로 출입 명단을 주기적으로 지우면 샌드박스를 수리한 것이 아니라 보안장치를 약화한 것이다.

## 처음에 관찰된 증상

| 증상 | 처음 해석하기 쉬운 내용 | 실제 의미 |
|---|---|---|
| `.git/index.lock: Permission denied` | 샌드박스 전체가 고장남 | `.git` 쓰기 보호가 작동함 |
| `FETCH_HEAD`를 쓸 수 없음 | GitHub 인증 실패 | 로컬 `.git` 메타데이터 쓰기 차단일 수 있음 |
| `Account Unknown(S-1-…)` | 삭제해도 되는 유령 계정 | 유효한 Codex capability SID일 수 있음 |
| ACL을 지우면 잠깐 Git 성공 | 문제가 해결됨 | 보호 ACE를 지워 경계를 일시 제거함 |
| 다음 실행에서 DENY 재생성 | Windows 11 LTSC 결함 | Codex가 보호 경계를 다시 적용함 |

`DENY ACE`는 특정 주체의 접근을 거부하는 Windows 권한 항목이다. Windows에서는 명시적인 거부가 허용보다 우선하므로, 폴더가 쓰기 가능 목록에 있어도 `.git`의 DENY는 계속 적용될 수 있다.

## 비판적 재진단에서 바로잡은 오류

### 오류 1: SID 문자열이면 고아 권한이다

이름을 표시하지 못하는 SID가 곧 삭제 가능한 고아(orphan)라는 증거는 없다. Codex는 `%USERPROFILE%\.codex\cap_sid`에 capability SID 매핑을 보관한다. [공개 이슈의 해당 사례](https://github.com/openai/codex/issues/41169)에서도 Windows UI의 `Account Unknown` SID가 이 원장(ledger)에 기록된 값과 일치했다.

**교정:** SID는 후보로만 집계하고 자동 삭제하지 않는다. ledger 등록 여부, 실제 오류, 현재 세션 사용 여부를 함께 확인한다.

### 오류 2: ACL을 반복 삭제하면 영구복구다

기존 예약 작업은 30분마다 저장소 루트와 `.git`의 SID 모양 ACE를 삭제했다. 활성 샌드박스가 만든 정상 보호 권한까지 지울 수 있었다.

**교정:** `-Mode Clean`은 종료 코드 3으로 거부한다. 예약 작업은 `-Mode Check`만 실행하고 전후 ACL을 바꾸지 않는다.

### 오류 3: `danger-full-access`가 가장 편한 해결책이다

전체 접근은 Git뿐 아니라 파일시스템과 네트워크 경계도 함께 제거한다. Git 몇 개 명령 때문에 모든 보호를 끄는 것은 범위가 지나치게 넓다.

**교정:** 일반 작업은 `:workspace`, Git 쓰기는 명령 접두사 규칙(prefix rule)의 `prompt` 경계에서 검토한다.

### 오류 4: Windows 11 Enterprise LTSC가 근본 원인이다

이 PC에서 샌드박스 전용 계정, 작업공간 쓰기, 홈·시스템 폴더·네트워크 차단이 모두 작동했다. LTSC 자체를 근본 원인으로 지목할 증거는 없다.

**교정:** 운영체제 이름 대신 실제 경계별 성공·실패를 측정한다.

## 최종 적용 구조

### 1. 지속 설정

사용자 `config.toml`의 핵심값은 다음과 같다.

```toml
approval_policy = "on-request"
default_permissions = ":workspace"
approvals_reviewer = "auto_review"
```

- `:workspace`: 작업공간과 사용자 임시 폴더에서 일반 작업을 허용하는 공식 내장 권한 프로필
- `on-request`: 경계를 넘어야 할 때 승인 절차를 만들 수 있는 정책
- `auto_review`: 가능한 승인 요청을 검토 에이전트가 먼저 판정하는 설정

레거시 `sandbox_mode`와 `[sandbox_workspace_write]`는 제거했다. [OpenAI 권한 문서](https://learn.chatgpt.com/docs/permissions)는 새 권한 프로필과 레거시 설정을 함께 사용하지 않도록 안내한다.

### 2. Git 경계 규칙

사용자 규칙 `sandbox-git-boundary.rules`는 다음 Git 쓰기 명령을 `prompt`로 분류한다.

- `git add`
- `git commit`
- `git fetch`
- `git pull`
- `git push`

`git status`, `git diff`, `git log` 같은 읽기 명령은 샌드박스 안에서 그대로 실행된다. 저장소의 `AGENTS.md`가 사용자 승인을 요구하면 자동 검토보다 그 규칙이 우선한다.

### 3. 읽기 전용 ACL 감사

`tools/codex-sandbox-acl.ps1`은 SID 후보를 세어 보고할 뿐 ACL을 수정하지 않는다.

```text
sid_candidates=3 ledger_backed=2 unclassified=1 deny=2
```

- `ledger_backed`: Codex ledger에서 찾은 SID 후보
- `unclassified`: 현재 ledger에서 찾지 못한 후보
- 둘 다 삭제 지시가 아니다.

SID 후보는 감사 결과이며 예약 작업 실패가 아니다. 감사 자체가 정상적으로 끝나면 종료 코드 0을 반환하고, 지원 파일 동기화나 스크립트 실행이 실패하면 종료 코드 2를 반환한다. CMD 래퍼는 이 종료 코드를 작업 스케줄러에 그대로 전달한다.

### 4. Git 읽기 경고 자기복구

샌드박스 Git은 사용자 홈의 전역 ignore 파일을 직접 읽지 못해 경고를 출력할 수 있었다. 인증정보나 Git config를 복사하지 않고 ignore 패턴 파일 하나만 사용자 임시 폴더에 동기화한다.

`tools/sync-codex-git-ignore.ps1`이 원본과 사본의 SHA-256 해시를 비교해 다를 때만 갱신한다. 기존 30분 예약 작업이 이 사본도 복원한다.

### 5. 자동 회귀 검사

```powershell
pwsh -NoProfile -File tools\test-codex-sandbox-profile.ps1
```

정상 결과는 다음과 같다.

| 검사 | 정상 판정 |
|---|---|
| `workspace-write` | 성공, exit 0 |
| `user-temp-write` | 성공, exit 0 |
| `home-write-blocked` | 차단, nonzero |
| `windows-temp-blocked` | 차단, nonzero |
| `git-metadata-blocked` | 차단, nonzero |
| `network-blocked` | 차단, nonzero |
| `git-read-quiet` | 성공·경고 없음, exit 0 |

차단 검사의 nonzero는 실패가 아니라 기대한 보호 결과다.

## 일상 사용 예시

### 예시 1: 소스 파일 편집과 테스트

**상황**

```text
src/app.js를 수정하고 테스트해줘.
```

**정상 흐름**

1. Codex가 작업공간 파일을 수정한다.
2. 테스트에 필요한 임시 파일은 허용된 `%TEMP%`에 기록한다.
3. 별도 권한 요청 없이 완료한다.

**판정:** 샌드박스를 계속 켜 둔 일반 작업이다.

### 예시 2: `git status` 실행

**상황**

```text
변경 파일만 확인해줘.
```

**정상 흐름**

```powershell
git status --short
```

읽기 명령이므로 샌드박스 안에서 종료 코드 0으로 끝나야 한다. 전역 ignore 경고도 없어야 한다.

### 예시 3: 커밋 요청

**상황**

```text
방금 수정한 파일만 커밋해줘.
```

**정상 흐름**

1. Codex가 `git status`로 변경 소유권을 확인한다.
2. `git add`와 `git commit`이 승인 경계로 이동한다.
3. 프로젝트 규칙이 사용자 승인을 요구하면 사용자 확인 뒤 실행한다.

**판정:** `.git` 직접 쓰기가 막히는 것은 정상이며, 승인 경계가 공식 출입문이다.

### 예시 4: `Account Unknown` 발견

**상황**

Windows 고급 보안 설정에 `S-1-…`만 보인다.

**하면 안 되는 일**

```text
보이는 SID를 전부 삭제한다.
```

**해야 할 일**

```powershell
pwsh -NoProfile -File tools\codex-sandbox-acl.ps1
```

결과를 후보 목록으로만 보고, 실제 실패와 ledger 매핑을 별도로 확인한다.

### 예시 5: `C:\tmp` 쓰기 거부

**상황**

도구가 `C:\tmp`에 파일을 만들려다 실패한다.

**해결**

사용자 임시 폴더인 `%TEMP%`를 사용한다. 현재 실측에서 `%TEMP%`는 허용되고 `C:\tmp`는 차단된다.

### 예시 6: 업데이트 후 다시 이상함

**상황**

Codex 업데이트 후 평소 되던 파일 작업이 거부된다.

**순서**

1. 앱을 완전히 새로 시작한다.
2. 자동 회귀 검사를 실행한다.
3. 일반 파일 쓰기와 `.git` 쓰기를 구분한다.
4. ACL 감사 결과가 있어도 자동 삭제하지 않는다.
5. 검사 결과와 Codex 버전을 함께 기록한다.

## 사용자가 기억할 세 문장

1. 일반 파일 쓰기는 성공하고 경계 회귀 검사 7개가 통과하면 샌드박스 보호가 작동한다.
2. `Account Unknown`은 삭제 허가가 아니다.
3. 보호를 지우지 말고 읽기 전용 검사로 경계를 하나씩 확인한다.

## 다시 문제가 생겼을 때 체크리스트

1. 현재 Codex 버전을 확인한다: `codex --version`
2. 설정 상태를 확인한다: `codex doctor --json`
3. 경계 검사를 실행한다: `tools\test-codex-sandbox-profile.ps1`
4. ACL 감사를 실행한다: `tools\codex-sandbox-acl.ps1`
5. Git 읽기인지 쓰기인지 구분한다.
6. 예약 작업 전후 ACL SDDL이 같은지 확인한다.
7. 같은 원인으로 세 번 실패하면 더 수정하지 말고 증거를 보존한다.

## 2026-09-16 최종 검증 결과

| 항목 | 결과 |
|---|---|
| 권한 설정 로드 | `ok` |
| Windows 샌드박스 helper | `ok` |
| 레거시 샌드박스 키 | 0개 |
| 경계 회귀 검사 | 7/7 통과 |
| 자동화 테스트 | 6/6 통과 |
| 예약 작업 대상 | 32개 경로 |
| 예약 작업의 ACL 변경 | 0건 |
| 예약 작업 수동 실행 | 감사 완료, exit 0 |
| Git ignore 원본·사본 SHA-256 | 일치 |
| Git 경계 규칙 | 쓰기 명령 5개 `prompt`, 읽기 명령 미일치 |

## 실패했던 시도와 배운 점

- `codex doctor` 전체 종료 코드는 터미널·Defender·저장 상태 경고 때문에 1이 될 수 있었다. 전체 코드만 보지 않고 `config.load`와 `sandbox.helpers` 개별 상태를 확인했다.
- 사용자 정의 프로필로 홈의 Git ignore 파일 하나만 읽게 하려 했지만 Windows 절대 경로 예외가 실측에서 적용되지 않았다. 홈 읽기 범위를 넓히지 않고 안전한 사본 방식으로 바꿨다.
- 실제 지원 파일을 지우는 복구 검사는 자동 정책이 삭제 명령을 차단했다. 격리된 임시 fixture에서 결손 복구를 검증하고, 실제 예약 작업에서는 ACL 불변과 해시 일치를 검증했다.
- `codex sandbox` 진단 명령은 `default_permissions`가 있어도 `--permission-profile`을 명시해야 했다. 이는 일반 Codex 작업의 기본 프로필 선택과 다른 진단 CLI 규칙이다.

## 아직 모르는 것

- 향후 Codex 버전이 Windows `.git` 쓰기만 좁게 중개하는 공식 Git 중개 기능(Git broker)을 제공할 시점
- 사용자 정의 프로필의 Windows 홈 경로 읽기 예외가 향후 버전에서 달라질지 여부
- Windows 또는 Codex 대규모 업데이트 뒤 ACL 구현이 바뀔 가능성

이 미확인 사항 때문에 “영원히 업데이트 영향이 없다”고 보장하지 않는다. 대신 지속 설정, 자기복구, 한 명령 회귀 검사를 함께 둬서 변화가 생기면 즉시 발견하도록 설계했다.

## 용어 사전

| 용어 | 쉬운 뜻 |
|---|---|
| Sandbox, 샌드박스 | 프로그램이 허용된 범위 밖으로 나가지 못하게 하는 실행 경계 |
| Permission Profile, 권한 프로필 | 파일·네트워크 허용 범위를 묶어 이름 붙인 설정 |
| ACL, 접근 제어 목록 | Windows 파일·폴더의 출입 명단 |
| ACE, 접근 제어 항목 | ACL 안의 허용 또는 거부 규칙 한 줄 |
| SID, 보안 식별자 | Windows 계정·권한 주체의 고유 번호 |
| Capability SID | 특정 기능이나 경로 권한을 나타내는 합성 SID |
| Ledger, 원장 | Codex가 SID와 경로의 대응을 기록한 파일 |
| DENY | 접근을 명시적으로 거부하는 규칙 |
| Git metadata, Git 메타데이터 | `.git` 안의 인덱스·참조·이력 관리 정보 |
| Prefix rule, 접두사 규칙 | 명령 시작 단어에 따라 허용·검토·금지를 정하는 규칙 |
| Regression test, 회귀 검사 | 업데이트 후 기존 정상 동작이 다시 깨졌는지 확인하는 검사 |
| SHA-256 | 두 파일의 내용이 같은지 확인하는 디지털 지문 |

## 근거 자료

- [OpenAI Permissions: 권한 프로필과 레거시 설정 혼용 금지](https://learn.chatgpt.com/docs/permissions)
- [OpenAI Rules: 샌드박스 외부 명령의 allow·prompt·forbidden 규칙](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [OpenAI Sandbox](https://learn.chatgpt.com/docs/sandboxing?surface=app)
- [openai/codex #32880: Windows `.git` DENY와 Git 쓰기 실패](https://github.com/openai/codex/issues/32880)
- [openai/codex #41169: Account Unknown으로 보이는 capability SID](https://github.com/openai/codex/issues/41169)
- [진단과 개선 계획](260916_Codex_샌드박스_권한거부_진단과_개선계획.md)
- [영구 운영 설계](260916_샌드박스_상시운용_설계.md)
