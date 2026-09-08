import tempfile
import threading
import unittest
from pathlib import Path

from csc_work_item import CoordinationError, WorkCoordinator, access_conflicts, normalize_resource


class WorkCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.coordinator = WorkCoordinator(Path(self.temp_dir.name) / "work-items.sqlite3")

    def plan(self, task_id, *, owner=None, reads=(), writes=(), dependencies=()):
        return self.coordinator.create(
            task_id,
            f"goal {task_id}",
            "bounded test scope",
            owner_hint=owner,
            read_set=reads,
            write_set=writes,
            dependencies=dependencies,
            acceptance="observable result exists",
            verification="unit test exits zero",
        )

    def approve(self, task_id, revision=1):
        return self.coordinator.approve(task_id, revision)

    def complete(self, task_id, agent="claude"):
        claimed = self.coordinator.claim(task_id, agent, 1, lease_seconds=30, now=100)
        token = claimed["fencing_token"]
        self.coordinator.submit(task_id, agent, 1, token, {"ok": True})
        return self.coordinator.review(task_id, 1, "accept")

    def test_complete_lifecycle_and_heartbeat(self):
        self.plan("WI-1", owner="claude", writes=["src/service.py"])
        self.approve("WI-1")
        claimed = self.coordinator.claim("WI-1", "claude", 1, lease_seconds=10, now=100)
        token = claimed["fencing_token"]
        self.assertEqual(claimed["status"], "RUNNING")
        self.assertNotIn("result_json", claimed)
        heartbeat = self.coordinator.heartbeat("WI-1", "claude", 1, token, lease_seconds=20, now=105)
        self.assertEqual(heartbeat["lease_expires_at"], 125)
        submitted = self.coordinator.submit("WI-1", "claude", 1, token, {"tests": "passed"})
        self.assertEqual(submitted["status"], "REVIEW")
        done = self.coordinator.review("WI-1", 1, "accept")
        self.assertEqual(done["status"], "DONE")
        self.assertEqual(done["result"], {"tests": "passed"})

    def test_controller_only_transitions_and_owner_reservation(self):
        with self.assertRaisesRegex(CoordinationError, "only codex"):
            self.coordinator.create(
                "WI-X", "goal", "scope", acceptance="yes", verification="check", actor="claude"
            )
        self.plan("WI-2", owner="antigravity")
        with self.assertRaisesRegex(CoordinationError, "only codex"):
            self.coordinator.approve("WI-2", 1, actor="claude")
        self.approve("WI-2")
        with self.assertRaisesRegex(CoordinationError, "reserved"):
            self.coordinator.claim("WI-2", "claude", 1)

    def test_dependencies_block_until_done(self):
        self.plan("WI-A", owner="claude")
        self.plan("WI-B", owner="antigravity", dependencies=["WI-A"])
        self.approve("WI-A")
        self.approve("WI-B")
        with self.assertRaisesRegex(CoordinationError, "DEPENDENCY_BLOCKED"):
            self.coordinator.claim("WI-B", "antigravity", 1)
        self.complete("WI-A")
        claimed = self.coordinator.claim("WI-B", "antigravity", 1)
        self.assertEqual(claimed["claimed_by"], "antigravity")

    def test_missing_dependency_is_rejected_on_approval(self):
        self.plan("WI-MISSING", dependencies=["WI-NOT-THERE"])
        with self.assertRaisesRegex(CoordinationError, "unknown dependencies"):
            self.approve("WI-MISSING")

    def test_write_conflicts_are_serialized_but_read_read_is_parallel(self):
        self.plan("WI-WRITE", owner="claude", writes=["src"])
        self.plan("WI-READ-CONFLICT", owner="antigravity", reads=["SRC/service.py"])
        self.plan("WI-READ-SAFE", owner="antigravity", reads=["docs/guide.md"])
        for task_id in ("WI-WRITE", "WI-READ-CONFLICT", "WI-READ-SAFE"):
            self.approve(task_id)
        self.coordinator.claim("WI-WRITE", "claude", 1)
        with self.assertRaisesRegex(CoordinationError, "ACCESS_CONFLICT: WI-WRITE"):
            self.coordinator.claim("WI-READ-CONFLICT", "antigravity", 1)
        safe = self.coordinator.claim("WI-READ-SAFE", "antigravity", 1)
        self.assertEqual(safe["status"], "RUNNING")

    def test_stale_revision_and_token_are_rejected_after_expiry_reassignment(self):
        self.plan("WI-STALE", owner="claude", writes=["src/a.py"])
        self.approve("WI-STALE")
        first = self.coordinator.claim("WI-STALE", "claude", 1, lease_seconds=5, now=100)
        old_token = first["fencing_token"]
        reassigned = self.coordinator.revoke_expired("WI-STALE", 1, now=106)
        self.assertEqual(reassigned["revision"], 2)
        second = self.coordinator.claim("WI-STALE", "claude", 2, now=107)
        self.assertGreater(second["fencing_token"], old_token)
        with self.assertRaisesRegex(CoordinationError, "STALE_REVISION"):
            self.coordinator.submit("WI-STALE", "claude", 1, old_token, {"stale": True})

    def test_expired_claim_can_only_be_reassigned_once(self):
        self.plan("WI-RETRY", owner="claude")
        self.approve("WI-RETRY")
        self.coordinator.claim("WI-RETRY", "claude", 1, lease_seconds=5, now=100)
        with self.assertRaisesRegex(CoordinationError, "has not expired"):
            self.coordinator.revoke_expired("WI-RETRY", 1, now=104)
        self.coordinator.revoke_expired("WI-RETRY", 1, now=106)
        self.coordinator.claim("WI-RETRY", "claude", 2, lease_seconds=5, now=110)
        with self.assertRaisesRegex(CoordinationError, "REASSIGNMENT_LIMIT_REACHED"):
            self.coordinator.revoke_expired("WI-RETRY", 2, now=116)

    def test_submitted_result_is_not_revoked_while_codex_reviews_it(self):
        self.plan("WI-REVIEW", owner="claude")
        self.approve("WI-REVIEW")
        claimed = self.coordinator.claim("WI-REVIEW", "claude", 1, lease_seconds=5, now=100)
        self.coordinator.submit("WI-REVIEW", "claude", 1, claimed["fencing_token"], {"ok": True})
        with self.assertRaisesRegex(CoordinationError, "no active claim"):
            self.coordinator.revoke_expired("WI-REVIEW", 1, now=200)

    def test_heartbeat_and_result_payload_fail_closed(self):
        self.plan("WI-STRICT", owner="claude")
        self.approve("WI-STRICT")
        claimed = self.coordinator.claim("WI-STRICT", "claude", 1, now=100)
        token = claimed["fencing_token"]
        with self.assertRaisesRegex(CoordinationError, "lease_seconds must be positive"):
            self.coordinator.heartbeat("WI-STRICT", "claude", 1, token, lease_seconds=0, now=101)
        with self.assertRaisesRegex(CoordinationError, "JSON object"):
            self.coordinator.submit("WI-STRICT", "claude", 1, token, [])

    def test_atomic_claim_allows_only_one_conflicting_worker(self):
        self.plan("WI-C1", writes=["shared/output.json"])
        self.plan("WI-C2", writes=["shared/output.json"])
        self.approve("WI-C1")
        self.approve("WI-C2")
        barrier = threading.Barrier(2)
        results = []

        def claim(task_id, agent):
            barrier.wait()
            try:
                self.coordinator.claim(task_id, agent, 1)
                results.append("claimed")
            except CoordinationError:
                results.append("blocked")

        threads = [
            threading.Thread(target=claim, args=("WI-C1", "claude")),
            threading.Thread(target=claim, args=("WI-C2", "antigravity")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["claimed", "blocked"])

    def test_resource_contract(self):
        self.assertEqual(normalize_resource("Docs\\Guide.md"), "docs/guide.md")
        self.assertTrue(access_conflicts([], ["src"], ["src/a.py"], []))
        self.assertFalse(access_conflicts(["src/a.py"], [], ["src/b.py"], []))
        for invalid in ("", "../secret", "C:/absolute", "/absolute"):
            with self.assertRaises(CoordinationError):
                normalize_resource(invalid)


if __name__ == "__main__":
    unittest.main()
