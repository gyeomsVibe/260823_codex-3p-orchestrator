"""Command-line interface for the C3P capacity-routing proof."""

from __future__ import annotations

import argparse
import json

from .policy import evaluate_pilot, load_json, route_task, validate_evidence_packet


def main() -> int:
    parser = argparse.ArgumentParser(description="C3P Antigravity capacity-routing proof")
    sub = parser.add_subparsers(dest="command", required=True)
    route = sub.add_parser("route")
    route.add_argument("profile")
    validate = sub.add_parser("validate-evidence")
    validate.add_argument("packet")
    validate.add_argument("--project-root", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("baseline")
    evaluate.add_argument("candidate")
    evaluate.add_argument("--policy", required=True)
    args = parser.parse_args()

    if args.command == "route":
        result = route_task(load_json(args.profile))
        exit_code = 0
    elif args.command == "validate-evidence":
        result = validate_evidence_packet(load_json(args.packet), args.project_root)
        exit_code = 2 if result["status"] == "ESCALATE" else 0
    else:
        result = evaluate_pilot(
            load_json(args.baseline), load_json(args.candidate), load_json(args.policy)
        )
        exit_code = 0 if result["decision"] == "SCALE" else 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
