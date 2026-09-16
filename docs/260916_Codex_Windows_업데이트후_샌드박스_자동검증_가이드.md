# Codex나 Windows 업데이트 후 샌드박스를 자동으로 다시 검증하는 방법

- 문서 유형: 운영 가이드(How-to)
- 대상: 업데이트 뒤 샌드박스가 다시 깨질까 걱정하는 사람
- 최종 검증일: 2026-09-16

Codex 버전이나 Windows 빌드가 바뀌면 예약 작업이 이를 감지한다. 감지 직후 실제 샌드박스 경계 검사 7개를 다시 실행하며, 통과한 버전만 마지막 정상 상태로 기록한다.

## 자동 유지관리 흐름

`CodexSandboxUpdateMaintenance` 예약 작업은 Windows 로그온 시점과 30분 간격으로 실행된다.

1. `codex --version`으로 Codex CLI 버전을 읽는다.
2. Windows 레지스트리에서 빌드와 업데이트 리비전(Update Build Revision, UBR)을 읽는다.
3. 마지막 정상 검증 버전과 현재 버전을 비교한다.
4. 어느 하나라도 바뀌면 샌드박스 경계 검사 7개를 실행한다.
5. 버전이 그대로여도 마지막 전체 검사가 24시간을 넘으면 다시 실행한다.
6. 검사가 모두 통과한 경우에만 현재 버전을 마지막 정상 상태로 저장한다.
7. Git 경계 규칙과 Git ignore 지원 파일을 안전한 정본에서 복원한다.
8. 모든 저장소의 ACL을 읽기 전용으로 감사한다.

상태 파일은 저장소의 `.codex-sandbox-maintenance\state.json`에 저장된다. 이 폴더는 Git에서 제외된다. Microsoft Store 앱 컨테이너의 `%LOCALAPPDATA%` 리디렉션과 관계없이 예약 작업과 현재 세션이 같은 상태를 읽는다. 토큰, 쿠키, Git 인증정보는 기록하지 않는다.

## 자동으로 복원하는 항목

유지관리 작업은 이 저장소가 직접 관리하는 두 파일만 자동 복원한다.

- `~/.codex/rules/sandbox-git-boundary.rules`: 보호된 Git 쓰기를 `prompt`로 보내는 규칙
- `%LOCALAPPDATA%\Temp\codex-git-ignore\ignore`: 샌드박스가 읽을 수 있는 Git ignore 사본

규칙 파일이 달라졌다면 기존 파일을 `.codex-sandbox-maintenance\backups`에 백업한 뒤 정본을 복사한다. Git config와 인증정보는 복사하지 않는다.

## 자동으로 바꾸지 않는 항목

유지관리 작업은 `~/.codex/config.toml`과 Windows ACL을 읽기만 한다. 업데이트가 구성 형식을 바꿨을 때 과거 설정을 강제로 덮어쓰면 새 버전을 더 손상할 수 있기 때문이다.

다음 조건이 달라지면 상태를 비정상으로 기록하고 종료 코드 10을 반환한다.

- `approval_policy = "on-request"`
- `default_permissions = ":workspace"`
- `approvals_reviewer = "auto_review"`
- 레거시 `sandbox_mode`와 `[sandbox_workspace_write]`가 없음

예약 작업이 실패 상태를 계속 유지하므로 다음 30분 실행에서도 재검증한다. 실패한 버전은 마지막 정상 버전으로 승격하지 않는다.

## 수동으로 즉시 재검증하기

업데이트 직후 기다리지 않고 검사하려면 저장소 루트에서 다음 명령을 실행한다.

```powershell
pwsh -NoProfile -File tools\maintain-codex-sandbox-after-updates.ps1 -ForceValidation
```

정상 출력에는 `healthy=True`가 포함되고 종료 코드는 0이다.

## 예약 작업 다시 설치하기

예약 작업이 삭제됐거나 경로가 달라졌다면 다음 명령으로 다시 등록한다.

```powershell
pwsh -NoProfile -File tools\install-codex-sandbox-maintenance-task.ps1
```

설치기는 기존 `CodexSandboxAclCleanup` 작업의 XML을 로컬 백업한 뒤 새 작업으로 교체한다. 새 작업은 배터리 사용 중에도 실행하며, 놓친 실행은 Windows가 다시 가능한 시점에 시작한다.

## 종료 코드

| 코드 | 뜻 | 다음 행동 |
|---|---|---|
| 0 | 검사와 안전한 자기복구가 완료됨 | 작업 계속 |
| 2 | 필요한 스크립트 또는 지원 파일 처리 실패 | 작업 로그 확인 |
| 3 | 폐기된 ACL `Clean` 요청을 안전하게 거부함 | ACL을 삭제하지 말 것 |
| 10 | 설정 또는 회귀 검사 불일치 | 상태 JSON과 작업 로그 확인 |
| 20 | Codex 실행 파일이나 관리 파일을 읽지 못한 운영 오류 | 작업 로그와 설치 경로 확인 |

작업 로그는 `.codex-sandbox-maintenance\maintenance-task.out`에 저장된다. 크기가 1 MB를 넘으면 이전 로그 한 세대만 `.previous`로 보관해 무한 증가를 막는다.

## 현재 실측 결과

| 항목 | 결과 |
|---|---|
| Codex 버전 지문 | `codex-cli 0.154.0` |
| Windows 빌드 지문 | `26100.8875` |
| 경계 회귀 검사 | 7/7 통과 |
| 자동화 테스트 | 10/10 통과 |
| 예약 작업 트리거 | 로그온 1개, 30분 반복 1개 |
| 예약 작업 결과 | exit 0 |
| 저장소 루트 ACL | 실행 전후 동일 |
| `.git` ACL | 실행 전후 동일 |

공식 OpenAI 문서는 네이티브 Windows와 WSL2가 서로 다른 샌드박스 구현을 사용하며, 설정 변경은 실행 환경이 갱신된 뒤 반영된다고 설명한다. 규칙 기능은 실험적이며 변경될 수 있으므로 버전 감지 후 실제 동작을 다시 측정한다.

## 근거 자료

- [OpenAI 샌드박스 문서](https://learn.chatgpt.com/ko-KR/docs/sandboxing?surface=app)
- [OpenAI 권한 문서](https://learn.chatgpt.com/ko-KR/docs/permissions)
- [OpenAI 규칙 문서](https://learn.chatgpt.com/ko-KR/docs/agent-configuration/rules)
- [전체 샌드박스 복구 사용자 가이드](260916_Codex_Windows_샌드박스_영구복구_사용자가이드.md)
