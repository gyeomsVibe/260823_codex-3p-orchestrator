#!/usr/bin/env python
"""Deterministic C3P work planning, ownership, and conflict control.

The coordinator is intentionally model-free.  SQLite transactions serialize
state changes, while plan revisions and fencing tokens reject stale results.
It coordinates cooperative agents; it does not bypass the existing sandbox,
Git, or user-approval boundaries.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional, Sequence


DEFAULT_DB = Path(__file__).resolve().parent / ".agent-swarm" / "coordination" / "work-items.sqlite3"
CONTROLLER = "codex"
TERMINAL = frozenset({"DONE", "CANCELLED", "FAILED"})
RISKS = frozenset({"low", "medium", "high"})


class CoordinationError(RuntimeError):
    """A safe, expected rejection of an invalid coordination transition."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_resource(value: str) -> str:
    """Return a case-insensitive, repository-relative resource key."""
    text = value.strip().replace("\\", "/")
    if not text or text.startswith("/") or ":" in text.split("/", 1)[0]:
        raise CoordinationError(f"resource must be repository-relative: {value!r}")
    if any(part in {"", ".", ".."} for part in PurePosixPath(text).parts):
        raise CoordinationError(f"resource contains an unsafe segment: {value!r}")
    return PurePosixPath(text).as_posix().rstrip("/").casefold()


def resources_overlap(left: str, right: str) -> bool:
    left_key = normalize_resource(left)
    right_key = normalize_resource(right)
    return (
        left_key == right_key
        or left_key.startswith(right_key + "/")
        or right_key.startswith(left_key + "/")
    )


def access_conflicts(
    left_reads: Sequence[str],
    left_writes: Sequence[str],
    right_reads: Sequence[str],
    right_writes: Sequence[str],
) -> bool:
    """Detect write/write and read/write conflicts; read/read is safe."""
    return any(resources_overlap(a, b) for a in left_writes for b in (*right_reads, *right_writes)) or any(
        resources_overlap(a, b) for a in left_reads for b in right_writes
    )


class WorkCoordinator:
    def __init__(self, db_path: os.PathLike[str] | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_hint TEXT,
                    read_set TEXT NOT NULL,
                    write_set TEXT NOT NULL,
                    dependencies TEXT NOT NULL,
                    acceptance TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    fencing_token INTEGER,
                    claimed_by TEXT,
                    lease_expires_at REAL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    fencing_token INTEGER,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _json_list(values: Iterable[str]) -> str:
        return json.dumps(sorted({normalize_resource(value) for value in values}), ensure_ascii=False)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for field in ("read_set", "write_set", "dependencies"):
            item[field] = json.loads(item[field])
        raw_result = item.pop("result_json")
        item["result"] = json.loads(raw_result) if raw_result else None
        return item

    @staticmethod
    def _event(
        conn: sqlite3.Connection,
        task_id: str,
        event_type: str,
        actor: str,
        revision: int,
        fencing_token: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        cursor = conn.execute(
            "INSERT INTO events(task_id,event_type,actor,revision,fencing_token,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (task_id, event_type, actor, revision, fencing_token, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
        )
        return int(cursor.lastrowid)

    def create(
        self,
        task_id: str,
        goal: str,
        scope: str,
        *,
        owner_hint: Optional[str] = None,
        read_set: Sequence[str] = (),
        write_set: Sequence[str] = (),
        dependencies: Sequence[str] = (),
        acceptance: str,
        verification: str,
        risk: str = "low",
        actor: str = CONTROLLER,
    ) -> dict[str, Any]:
        if actor != CONTROLLER:
            raise CoordinationError("only codex may create the canonical work graph")
        if risk not in RISKS:
            raise CoordinationError(f"unsupported risk: {risk}")
        if not task_id.strip() or not goal.strip() or not acceptance.strip() or not verification.strip():
            raise CoordinationError("task_id, goal, acceptance, and verification are required")
        now = utc_now()
        with self._transaction() as conn:
            try:
                conn.execute(
                    """INSERT INTO work_items(
                        task_id,goal,scope,owner_hint,read_set,write_set,dependencies,
                        acceptance,verification,risk,status,revision,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,'DRAFT',1,?,?)""",
                    (
                        task_id.strip(), goal.strip(), scope.strip(), owner_hint,
                        self._json_list(read_set), self._json_list(write_set),
                        json.dumps(sorted(set(dependencies)), ensure_ascii=False),
                        acceptance.strip(), verification.strip(), risk, now, now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CoordinationError(f"task already exists: {task_id}") from exc
            self._event(conn, task_id, "CREATED", actor, 1)
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise CoordinationError(f"unknown task: {task_id}")
        return self._decode(row)

    def list(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM work_items ORDER BY created_at, task_id").fetchall()
        finally:
            conn.close()
        return [self._decode(row) for row in rows]

    def _require_revision(self, row: sqlite3.Row, revision: int) -> None:
        if int(row["revision"]) != revision:
            raise CoordinationError(
                f"STALE_REVISION: expected {row['revision']}, received {revision}"
            )

    def _assert_acyclic(self, conn: sqlite3.Connection, task_id: str, dependencies: Sequence[str]) -> None:
        graph: dict[str, list[str]] = {}
        for row in conn.execute("SELECT task_id, dependencies FROM work_items"):
            graph[row["task_id"]] = json.loads(row["dependencies"])
        graph[task_id] = list(dependencies)
        missing = [dep for dep in dependencies if dep not in graph]
        if missing:
            raise CoordinationError(f"unknown dependencies: {', '.join(missing)}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise CoordinationError(f"dependency cycle detected at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        visit(task_id)

    def approve(self, task_id: str, revision: int, *, actor: str = CONTROLLER) -> dict[str, Any]:
        if actor != CONTROLLER:
            raise CoordinationError("only codex may approve the canonical work graph")
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise CoordinationError(f"unknown task: {task_id}")
            self._require_revision(row, revision)
            if row["status"] not in {"DRAFT", "ITERATE"}:
                raise CoordinationError(f"cannot approve task in {row['status']}")
            dependencies = json.loads(row["dependencies"])
            self._assert_acyclic(conn, task_id, dependencies)
            conn.execute("UPDATE work_items SET status='APPROVED',updated_at=? WHERE task_id=?", (utc_now(), task_id))
            self._event(conn, task_id, "APPROVED", actor, revision)
        return self.get(task_id)

    def _dependencies_done(self, conn: sqlite3.Connection, dependencies: Sequence[str]) -> bool:
        for dependency in dependencies:
            row = conn.execute("SELECT status FROM work_items WHERE task_id=?", (dependency,)).fetchone()
            if row is None or row["status"] != "DONE":
                return False
        return True

    def _find_conflict(self, conn: sqlite3.Connection, candidate: sqlite3.Row) -> Optional[str]:
        reads = json.loads(candidate["read_set"])
        writes = json.loads(candidate["write_set"])
        for row in conn.execute("SELECT * FROM work_items WHERE status IN ('RUNNING','REVIEW') AND task_id<>?", (candidate["task_id"],)):
            if access_conflicts(reads, writes, json.loads(row["read_set"]), json.loads(row["write_set"])):
                return str(row["task_id"])
        return None

    def claim(
        self,
        task_id: str,
        agent: str,
        revision: int,
        *,
        lease_seconds: float = 300.0,
        now: Optional[float] = None,
    ) -> dict[str, Any]:
        if lease_seconds <= 0:
            raise CoordinationError("lease_seconds must be positive")
        instant = time.time() if now is None else now
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise CoordinationError(f"unknown task: {task_id}")
            self._require_revision(row, revision)
            if row["status"] != "APPROVED":
                raise CoordinationError(f"task is not claimable: {row['status']}")
            if row["owner_hint"] and row["owner_hint"] != agent:
                raise CoordinationError(f"task is reserved for {row['owner_hint']}")
            dependencies = json.loads(row["dependencies"])
            if not self._dependencies_done(conn, dependencies):
                raise CoordinationError("DEPENDENCY_BLOCKED")
            conflict = self._find_conflict(conn, row)
            if conflict:
                raise CoordinationError(f"ACCESS_CONFLICT: {conflict}")
            token = self._event(conn, task_id, "CLAIMED", agent, revision)
            conn.execute(
                """UPDATE work_items SET status='RUNNING',claimed_by=?,fencing_token=?,
                   lease_expires_at=?,updated_at=? WHERE task_id=?""",
                (agent, token, instant + lease_seconds, utc_now(), task_id),
            )
        return self.get(task_id)

    @staticmethod
    def _validate_claim(row: sqlite3.Row, agent: str, revision: int, token: int) -> None:
        if row["claimed_by"] != agent:
            raise CoordinationError("OWNER_MISMATCH")
        if int(row["revision"]) != revision:
            raise CoordinationError("STALE_REVISION")
        if row["fencing_token"] is None or int(row["fencing_token"]) != token:
            raise CoordinationError("STALE_FENCING_TOKEN")

    def heartbeat(
        self,
        task_id: str,
        agent: str,
        revision: int,
        token: int,
        *,
        lease_seconds: float = 300.0,
        now: Optional[float] = None,
    ) -> dict[str, Any]:
        if lease_seconds <= 0:
            raise CoordinationError("lease_seconds must be positive")
        instant = time.time() if now is None else now
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "RUNNING":
                raise CoordinationError("task is not running")
            self._validate_claim(row, agent, revision, token)
            conn.execute("UPDATE work_items SET lease_expires_at=?,updated_at=? WHERE task_id=?", (instant + lease_seconds, utc_now(), task_id))
            self._event(conn, task_id, "HEARTBEAT", agent, revision, token)
        return self.get(task_id)

    def submit(self, task_id: str, agent: str, revision: int, token: int, result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise CoordinationError("result must be a JSON object")
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "RUNNING":
                raise CoordinationError("task is not running")
            self._validate_claim(row, agent, revision, token)
            conn.execute("UPDATE work_items SET status='REVIEW',result_json=?,updated_at=? WHERE task_id=?", (json.dumps(result, ensure_ascii=False), utc_now(), task_id))
            self._event(conn, task_id, "SUBMITTED", agent, revision, token, result)
        return self.get(task_id)

    def review(self, task_id: str, revision: int, decision: str, *, actor: str = CONTROLLER) -> dict[str, Any]:
        if actor != CONTROLLER:
            raise CoordinationError("only codex may review integrated results")
        if decision not in {"accept", "iterate"}:
            raise CoordinationError("decision must be accept or iterate")
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "REVIEW":
                raise CoordinationError("task is not in review")
            self._require_revision(row, revision)
            if decision == "accept":
                status, next_revision = "DONE", revision
            else:
                if int(row["retry_count"]) >= 1:
                    raise CoordinationError("REASSIGNMENT_LIMIT_REACHED")
                status, next_revision = "ITERATE", revision + 1
            conn.execute(
                """UPDATE work_items SET status=?,revision=?,fencing_token=NULL,claimed_by=NULL,
                   lease_expires_at=NULL,retry_count=retry_count+?,updated_at=? WHERE task_id=?""",
                (status, next_revision, 1 if decision == "iterate" else 0, utc_now(), task_id),
            )
            self._event(conn, task_id, "ACCEPTED" if decision == "accept" else "ITERATE", actor, next_revision)
        return self.get(task_id)

    def revoke_expired(self, task_id: str, revision: int, *, actor: str = CONTROLLER, now: Optional[float] = None) -> dict[str, Any]:
        if actor != CONTROLLER:
            raise CoordinationError("only codex may revoke an expired claim")
        instant = time.time() if now is None else now
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM work_items WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "RUNNING":
                raise CoordinationError("task has no active claim")
            self._require_revision(row, revision)
            if row["lease_expires_at"] is None or float(row["lease_expires_at"]) >= instant:
                raise CoordinationError("lease has not expired")
            if int(row["retry_count"]) >= 1:
                raise CoordinationError("REASSIGNMENT_LIMIT_REACHED")
            next_revision = revision + 1
            conn.execute(
                """UPDATE work_items SET status='APPROVED',revision=?,fencing_token=NULL,
                   claimed_by=NULL,lease_expires_at=NULL,retry_count=retry_count+1,updated_at=? WHERE task_id=?""",
                (next_revision, utc_now(), task_id),
            )
            self._event(conn, task_id, "EXPIRED_REVOKED", actor, next_revision)
        return self.get(task_id)

    def ready(self) -> list[dict[str, Any]]:
        ready: list[dict[str, Any]] = []
        conn = self._connect()
        try:
            for row in conn.execute("SELECT * FROM work_items WHERE status='APPROVED' ORDER BY created_at,task_id"):
                if self._dependencies_done(conn, json.loads(row["dependencies"])) and not self._find_conflict(conn, row):
                    ready.append(self._decode(row))
        finally:
            conn.close()
        return ready


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C3P deterministic work-item coordinator")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Coordination SQLite database")
    sub = parser.add_subparsers(dest="action", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--id", required=True)
    plan.add_argument("--goal", required=True)
    plan.add_argument("--scope", default="")
    plan.add_argument("--owner")
    plan.add_argument("--read", action="append", default=[])
    plan.add_argument("--write", action="append", default=[])
    plan.add_argument("--depends", action="append", default=[])
    plan.add_argument("--acceptance", required=True)
    plan.add_argument("--verification", required=True)
    plan.add_argument("--risk", choices=sorted(RISKS), default="low")

    for name in ("approve", "status"):
        item = sub.add_parser(name)
        item.add_argument("--id")
        if name == "approve":
            item.add_argument("--revision", type=int, required=True)

    claim = sub.add_parser("claim")
    claim.add_argument("--id", required=True)
    claim.add_argument("--agent", required=True)
    claim.add_argument("--revision", type=int, required=True)
    claim.add_argument("--lease-seconds", type=float, default=300.0)

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--id", required=True)
    heartbeat.add_argument("--agent", required=True)
    heartbeat.add_argument("--revision", type=int, required=True)
    heartbeat.add_argument("--token", type=int, required=True)
    heartbeat.add_argument("--lease-seconds", type=float, default=300.0)

    submit = sub.add_parser("submit")
    submit.add_argument("--id", required=True)
    submit.add_argument("--agent", required=True)
    submit.add_argument("--revision", type=int, required=True)
    submit.add_argument("--token", type=int, required=True)
    submit.add_argument("--result-json", required=True)

    review = sub.add_parser("review")
    review.add_argument("--id", required=True)
    review.add_argument("--revision", type=int, required=True)
    review.add_argument("--decision", choices=["accept", "iterate"], required=True)

    revoke = sub.add_parser("revoke-expired")
    revoke.add_argument("--id", required=True)
    revoke.add_argument("--revision", type=int, required=True)

    sub.add_parser("ready")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    coordinator = WorkCoordinator(args.db)
    try:
        if args.action == "plan":
            output = coordinator.create(
                args.id, args.goal, args.scope, owner_hint=args.owner,
                read_set=args.read, write_set=args.write, dependencies=args.depends,
                acceptance=args.acceptance, verification=args.verification, risk=args.risk,
            )
        elif args.action == "approve":
            if not args.id:
                raise CoordinationError("--id is required for approve")
            output = coordinator.approve(args.id, args.revision)
        elif args.action == "claim":
            output = coordinator.claim(args.id, args.agent, args.revision, lease_seconds=args.lease_seconds)
        elif args.action == "heartbeat":
            output = coordinator.heartbeat(args.id, args.agent, args.revision, args.token, lease_seconds=args.lease_seconds)
        elif args.action == "submit":
            output = coordinator.submit(args.id, args.agent, args.revision, args.token, json.loads(args.result_json))
        elif args.action == "review":
            output = coordinator.review(args.id, args.revision, args.decision)
        elif args.action == "revoke-expired":
            output = coordinator.revoke_expired(args.id, args.revision)
        elif args.action == "ready":
            output = coordinator.ready()
        else:
            output = coordinator.get(args.id) if args.id else coordinator.list()
    except (CoordinationError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "data": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
