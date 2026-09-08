"""Dry-run command-line interface for the C3P routing policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .policy import build_launch_args, load_catalog, route_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run a C3P model-routing decision")
    parser.add_argument("profile", type=Path, help="task profile JSON path")
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()

    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    decision = route_task(profile, load_catalog(args.catalog))
    payload = decision.to_dict()
    payload["launch_args"] = (
        build_launch_args(decision) if decision.status == "READY" else None
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
