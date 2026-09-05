비즈니스 로직의 확장성과 에이전트들의 실시간 파일 입출력(Polling/Watch) 속도를 고려하여, 강력한 JSON 제어와 예외 처리가 가능한 **Python 기반의 초기화 스크립트**와 이를 간편하게 실행할 수 있는 **Bash 래퍼(Wrapper)** 조합으로 작성했습니다.

이 스크립트는 실행 즉시 지정된 디렉터리에 .agent-swarm 인프라를 구축하고, 3대 AI가 즉시 통신할 수 있는 채널과 초기 메시지를 자동으로 주입합니다.

## ---

**1\. Core Python 스크립트 (csc\_init.py)**

프로젝트 루트 디렉터리에서 실행하면 폴더 구조를 만들고 초기 설정 및 사령관(Codex)의 최초 브로드캐스트 메시지를 생성합니다.

*`#!/usr/bin/env python3`*  
`import os`  
`import json`  
`from datetime import datetime`

`def create_swarm_infrastructure():`  
    `base_dir = ".agent-swarm"`  

    `# 1. 필요 하위 디렉터리 정의`  
    `sub_dirs = [`  
        `"tasks",`  
        `"channels",`  
        `"lock",`  
        `"logs"`  
    `]`  

    `print(f"🚀 [CSC] Codex Swarm Command 인프라 초기화를 시작합니다.")`  

    `# 폴더 생성`  
    `for sub in sub_dirs:`  
        `path = os.path.join(base_dir, sub)`  
        `os.makedirs(path, exist_ok=True)`  
        `print(f"  └─ 폴더 생성 완료: {path}")`

    `# 2. 기본 config.json 생성`  
    `config_data = {`  
        `"project_name": "260823_Codex-Swarm-Command-(CSC)",`  
        `"initialized_at": datetime.utcnow().isoformat() + "Z",`  
        `"status": "ACTIVE",`  
        `"commander": "Codex",`  
        `"agents": {`  
            `"codex": {"status": "READY", "role": "Commander / Architect"},`  
            `"claude_code": {"status": "READY", "role": "Core Builder"},`  
            `"antigravity": {"status": "READY", "role": "Researcher & QA"}`  
        `}`  
    `}`  

    `with open(os.path.join(base_dir, "config.json"), "w", encoding="utf-8") as f:`  
        `json.dump(config_data, f, indent=2, ensure_ascii=False)`

    `# 3. 빈 태스크 보드 초기화`  
    `for board in ["backlog.json", "in-progress.json", "completed.json"]:`  
        `with open(os.path.join(base_dir, "tasks", board), "w", encoding="utf-8") as f:`  
            `json.dump([], f, indent=2)`

    `# 4. 각 에이전트 인박스(Inbox) 채널 초기화`  
    `inboxes = ["codex-inbox.json", "claude-inbox.json", "antigravity-inbox.json"]`  
    `for inbox in inboxes:`  
        `with open(os.path.join(base_dir, "channels", inbox), "w", encoding="utf-8") as f:`  
            `json.dump([], f, indent=2)`

    `# 5. 사령관(Codex)의 최초 시스템 가동 선언 메세지 주입 (general.log)`  
    `initial_log = (`  
        `f"[{datetime.utcnow().isoformat()}Z] [SYSTEM] CSC 인프라가 성공적으로 구축되었습니다.\n"`  
        `f"[{datetime.utcnow().isoformat()}Z] [Codex] 전 에이전트 청취 바람. 사령관 Codex다. "`  
        `f"본 프로젝트는 3분할 병렬 세션으로 실행된다. Claude Code와 Antigravity는 각자의 Inbox를 모니터링하라.\n"`  
    `)`  
    `with open(os.path.join(base_dir, "channels", "general.log"), "w", encoding="utf-8") as f:`  
        `f.write(initial_log)`

    `# 6. 상호 충돌 방지 뮤텍스 레지스트리 생성`  
    `with open(os.path.join(base_dir, "lock", "lock.registry"), "w", encoding="utf-8") as f:`  
        `json.dump({"locked_files": {}}, f, indent=2)`

    ``print(f"✨ [CSC] `.agent-swarm` 초기화가 완료되었습니다. 에이전트 기동 준비 완료.")``

`if __name__ == "__main__":`  
    `create_swarm_infrastructure()`

## ---

**2\. 단축 실행용 Bash 스크립트 (csc.sh)**

터미널이나 CLI 환경에서 스킬 형태로 쉽고 빠르게 호출하기 위해 파이썬 스크립트를 래핑하는 명령어 파일입니다.

*`#!/bin/bash`*

*`# 에러 발생 시 즉시 중단`*  
`set -e`

`SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"`

`case "$1" in`  
    `init)`  
        `python3 "$SCRIPT_DIR/csc_init.py"`  
        `;;`  
    `status)`  
        `if [ -d ".agent-swarm" ]; then`  
            `echo "📊 [CSC Status] 대화창 상태 (general.log 최근 5줄):"`  
            `tail -n 5 .agent-swarm/channels/general.log`  
        `else`  
            `echo "❌ .agent-swarm 폴더가 없습니다. 'csc init'을 먼저 실행하세요."`  
        `fi`  
        `;;`  
    `*)`  
        `echo "사용법:"`  
        `echo "  csc init   - .agent-swarm 협업 환경 인프라 초기화"`  
        `echo "  csc status - 현재 스웜 실시간 통신 및 대화 로그 확인"`  
        `exit 1`  
        `;;`  
`esac`

## ---

**3\. 설치 및 스킬 발동 방법**

> 1. 프로젝트 루트 폴더에 위 두 파일을 각각 csc\_init.py, csc.sh로 저장합니다.  
> 2. 터미널에서 스크립트에 **실행 권한**을 부여합니다:  
>    `chmod +x csc_init.py csc.sh`

> 3. 전역 명령어나 에일리어스(Alias)로 등록하여 **스킬처럼 발동**합니다:  
>    *`# 초기화 스킬 발동`*  
>    `./csc.sh init`

>    *`# 스웜 통신 상태 모니터링`*  
>    `./csc.sh status`

## ---

**다음 단계 제안**

인프라 구축이 완료되었으니, 이제 3대 도구가 움직이기 시작해야 합니다.

> * **AGENTS.md 파일 설계**: 세 에이전트가 이 폴더를 기반으로 어떻게 읽고 쓰며 소통해야 하는지 알려주는 **지침 지정 시스템 프롬프트 문서**를 만들까요?  
> * 아니면, 파일 생성을 감지하는 **실시간 파일 감시(File Watcher) 루프 예제**를 구현해 볼까요?