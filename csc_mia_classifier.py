"""MIA 프로젝트 특성 감지 및 프론트엔드/백엔드 구조 제안기.

사용자 제안 및 C3P 협의체 3도구 합의(docs/28, docs/36)를 구현한다:
1. 프로젝트 루트를 안전하게 탐색하여 프론트엔드 및 백엔드 지표를 식별한다.
2. 풀스택 프로젝트 여부를 점수화(score)하여 분할 필요성을 제안한다.
3. 무단 쓰기 금지 원칙(P2)을 준수하여 감지(evaluate)는 100% 읽기 전용으로 수행한다.
4. 실제 디렉터리 생성(provision)은 명시적 사용자 인수(--yes/--apply)가 있을 때만 멱등(idempotent)하게 수행한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# 프론트엔드 단독 식별 지표 (설정 파일만으로 확실한 프론트엔드)
FRONTEND_STANDALONE_INDICATORS = {
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.mjs",
    "nuxt.config.ts",
    "webpack.config.js",
    "index.html",
}

# 프론트엔드 보조 지표 (내용에 웹 프레임워크가 포함되어야 인정)
FRONTEND_SECONDARY_INDICATORS = {
    "package.json",
    "tsconfig.json",
}

FRONTEND_FRAMEWORK_KEYWORDS = {
    "react", "vue", "svelte", "next", "vite", "nuxt", "angular", "solid-js", "preact"
}

# 백엔드 단독 식별 지표 (인프라 및 서버 전용 언어 설정)
BACKEND_STANDALONE_INDICATORS = {
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Dockerfile",
    "docker-compose.yml",
}

# 백엔드 보조 지표 (내용에 웹/서비스 프레임워크가 포함되어야 인정)
BACKEND_SECONDARY_INDICATORS = {
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "poetry.lock",
}

BACKEND_FRAMEWORK_KEYWORDS = {
    "django", "flask", "fastapi", "uvicorn", "gunicorn", "starlette", "tornado", "celery", "litestar"
}

# 하위 호환성을 위한 지표 집합
FRONTEND_INDICATORS = FRONTEND_STANDALONE_INDICATORS | FRONTEND_SECONDARY_INDICATORS
BACKEND_INDICATORS = BACKEND_STANDALONE_INDICATORS | BACKEND_SECONDARY_INDICATORS

# 스캔에서 무시할 디렉터리 목록
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".agent-swarm",
    ".vibe-clinic",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".gemini",
    "dist",
    "build",
    "venv",
    ".venv",
}


def _file_contains_any_keyword(file_path: Path, keywords: Set[str]) -> bool:
    """보조 지표 파일 내용에서 프레임워크 키워드 포함 여부를 검사합니다 (최대 64KB)."""
    try:
        if not file_path.is_file():
            return False
        content = file_path.read_text(encoding="utf-8", errors="ignore")[:65536].lower()
        return any(kw in content for kw in keywords)
    except Exception:
        return False


def scan_indicators(root_path: Path) -> Tuple[Set[str], Set[str]]:
    """프로젝트 루트를 순회하여 유효한 프론트/백엔드 지표 파일을 수집한다."""
    root = root_path.resolve()
    found_fe: Set[str] = set()
    found_be: Set[str] = set()

    if not root.exists() or not root.is_dir():
        return found_fe, found_be

    for current_dir, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        rel_dir = Path(current_dir).relative_to(root)

        for f in files:
            file_abs = Path(current_dir) / f
            rel_file = str(rel_dir / f).replace("\\", "/") if str(rel_dir) != "." else f

            # 프론트엔드 검사: 단독 지표이거나 보조 지표 + 키워드 포함 시 인정
            if f in FRONTEND_STANDALONE_INDICATORS or any(rel_file.endswith(ind) for ind in FRONTEND_STANDALONE_INDICATORS):
                found_fe.add(rel_file)
            elif f in FRONTEND_SECONDARY_INDICATORS or any(rel_file.endswith(ind) for ind in FRONTEND_SECONDARY_INDICATORS):
                if _file_contains_any_keyword(file_abs, FRONTEND_FRAMEWORK_KEYWORDS):
                    found_fe.add(rel_file)

            # 백엔드 검사: 단독 지표이거나 보조 지표 + 키워드 포함 시 인정
            if f in BACKEND_STANDALONE_INDICATORS or any(rel_file.endswith(ind) for ind in BACKEND_STANDALONE_INDICATORS):
                found_be.add(rel_file)
            elif f in BACKEND_SECONDARY_INDICATORS or any(rel_file.endswith(ind) for ind in BACKEND_SECONDARY_INDICATORS):
                if _file_contains_any_keyword(file_abs, BACKEND_FRAMEWORK_KEYWORDS):
                    found_be.add(rel_file)

    return found_fe, found_be


def evaluate_project(root_path: Path) -> Dict[str, Any]:
    """프로젝트 특성을 평가하고 프론트/백엔드 분할 여부를 판정한다."""
    root = root_path.resolve()
    fe_files, be_files = scan_indicators(root)

    has_frontend = len(fe_files) > 0
    has_backend = len(be_files) > 0

    has_fe_dir = (root / "frontend").is_dir() or (root / "client").is_dir() or (root / "web").is_dir()
    has_be_dir = (root / "backend").is_dir() or (root / "server").is_dir() or (root / "api").is_dir()

    is_fullstack = has_frontend and has_backend
    is_already_split = has_fe_dir and has_be_dir

    # 분할 추천 판정
    # 풀스택 프로젝트이면서 아직 명시적 frontend/backend 분리가 안 된 경우에만 추천
    should_split = is_fullstack and not is_already_split

    if is_already_split:
        status = "ALREADY_SPLIT"
        recommendation = "이미 프론트엔드와 백엔드가 분리 디렉터리로 구성되어 있습니다."
    elif should_split:
        status = "RECOMMEND_SPLIT"
        recommendation = "풀스택 프로젝트로 감지되었습니다. 작업 영역 격리를 위해 frontend/ 및 backend/ 디렉터리 분할 생성을 권장합니다."
    elif has_frontend and not has_backend:
        status = "FRONTEND_ONLY"
        recommendation = "순수 프론트엔드 단일 프로젝트로 감지되었습니다. 폴더 분할이 불필요합니다."
    elif has_backend and not has_frontend:
        status = "BACKEND_ONLY"
        recommendation = "순수 백엔드/CLI 라이브러리 프로젝트로 감지되었습니다. 폴더 분할이 불필요합니다."
    else:
        status = "GENERIC"
        recommendation = "특정 프레임워크 지표가 적은 일반 프로젝트입니다. 기본 디렉터리 구조를 유지하세요."

    return {
        "project_root": str(root),
        "status": status,
        "is_fullstack": is_fullstack,
        "should_split": should_split,
        "frontend_indicators": sorted(list(fe_files)),
        "backend_indicators": sorted(list(be_files)),
        "existing_structure": {
            "has_frontend_dir": has_fe_dir,
            "has_backend_dir": has_be_dir,
        },
        "recommendation": recommendation,
        "proposed_paths": {
            "frontend": str(root / "frontend") if should_split else None,
            "backend": str(root / "backend") if should_split else None,
        },
    }


def provision_folders(root_path: Path, force: bool = False) -> Dict[str, Any]:
    """사용자 승인 하에 안전하게 frontend 및 backend 디렉터리를 프로비저닝한다."""
    eval_result = evaluate_project(root_path)
    root = root_path.resolve()

    if not eval_result["should_split"] and not force:
        return {
            "success": False,
            "reason": f"분할 대상이 아닙니다 (상태: {eval_result['status']}). 강제 생성하려면 force=True 필요",
            "created_dirs": [],
        }

    created = []
    fe_dir = root / "frontend"
    be_dir = root / "backend"

    for target_dir, label in [(fe_dir, "프론트엔드"), (be_dir, "백엔드")]:
        target_resolved = target_dir.resolve()
        if not target_resolved.is_relative_to(root):
            raise ValueError(f"보안 위험: 프로비저닝 대상 경로가 프로젝트 루트를 벗어났습니다: {target_resolved}")

        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            readme_file = target_dir / "README.md"
            if not readme_file.exists():
                readme_file.write_text(
                    f"# {label} 작업 영역\n\n"
                    f"C3P 협의체 MIA 아키텍처 규칙에 따라 분할된 {label} 소스코드 디렉터리입니다.\n",
                    encoding="utf-8",
                )
            created.append(str(target_dir))

    return {
        "success": True,
        "reason": "디렉터리 및 안내 README 생성이 안전하게 완료되었습니다.",
        "created_dirs": created,
    }


def render_summary(result: Dict[str, Any]) -> str:
    """사용자가 한눈에 볼 수 있는 한국어 3요소 요약 보고서를 렌더링한다."""
    lines = [
        "====================================================================",
        "MIA 프로젝트 특성 분석 및 구조 평가 보고서",
        f"대상 경로: {result['project_root']}",
        "====================================================================",
        f"1. 판정 상태: {result['status']}",
        f"   - 풀스택 여부: {'예' if result['is_fullstack'] else '아니오'}",
        f"   - 분할 권고 여부: {'권장 (RECOMMENDED)' if result['should_split'] else '미권장 (NO_SPLIT_NEEDED)'}",
        "",
        "2. 감지된 지표:",
        f"   - 프론트엔드 지표 ({len(result['frontend_indicators'])}건): {', '.join(result['frontend_indicators']) or '없음'}",
        f"   - 백엔드 지표 ({len(result['backend_indicators'])}건): {', '.join(result['backend_indicators']) or '없음'}",
        "",
        f"3. 협의체 권고: {result['recommendation']}",
    ]
    if result["should_split"]:
        lines.extend([
            "",
            "4. 제안 디렉터리:",
            f"   - 프론트엔드: {result['proposed_paths']['frontend']}",
            f"   - 백엔드: {result['proposed_paths']['backend']}",
            "   (실제 생성은 'python csc_mia_classifier.py provision --apply' 명령 필요)",
        ])
    lines.append("--------------------------------------------------------------------")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIA 프로젝트 특성 감지 및 구조 분류기")
    subparsers = parser.add_subparsers(dest="command", help="실행 명령")

    eval_p = subparsers.add_parser("evaluate", help="프로젝트 구조 평가 (100%% 읽기 전용)")
    eval_p.add_argument("--path", default=".", help="검사할 프로젝트 루트 경로 (기본값: 현재 디렉터리)")
    eval_p.add_argument("--json", action="store_true", help="JSON 원문 출력")

    prov_p = subparsers.add_parser("provision", help="프론트/백엔드 디렉터리 안전 생성")
    prov_p.add_argument("--path", default=".", help="대상 프로젝트 루트 경로 (기본값: 현재 디렉터리)")
    prov_p.add_argument("--apply", action="store_true", help="생성 확인 플래그 (명시 필수)")
    prov_p.add_argument("--force", action="store_true", help="단일 스택이어도 강제 분할 생성")

    args = parser.parse_args(argv)

    if args.command == "evaluate" or args.command is None:
        target_path = Path(getattr(args, "path", ".")).resolve()
        res = evaluate_project(target_path)
        if getattr(args, "json", False):
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(render_summary(res))
        return 0

    elif args.command == "provision":
        target_path = Path(args.path).resolve()
        if not args.apply:
            print("🔴 안전 경계: 실제 디렉터리 생성을 위해서는 '--apply' 플래그가 필수입니다.", file=sys.stderr)
            print("   먼저 'python csc_mia_classifier.py evaluate' 로 분석 결과를 검토하세요.", file=sys.stderr)
            return 2
        res = provision_folders(target_path, force=args.force)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["success"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
