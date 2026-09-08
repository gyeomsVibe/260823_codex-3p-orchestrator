"""csc_heartbeat.py 시험 — 감시자 상호감시가 오탐을 만들지 않는지 본다.

이 파일이 지키려는 것은 기능이 아니라 '조용함' 이다.
경보는 진짜일 때만 울려야 한다. 아직 계약을 안 쓴 동료(absent)를 죽었다고 부르면,
사람은 곧 이 경보를 무시하고 진짜 정지를 놓친다. 그래서 absent 케이스를 가장 많이 시험한다.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import csc_heartbeat as HB


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w, self._p = HB.WATCHERS, HB.POLICY
        HB.WATCHERS = os.path.join(self.tmp, "watchers")
        HB.POLICY = os.path.join(HB.WATCHERS, "policy.json")
        os.makedirs(HB.WATCHERS)
        self.now = time.time()

    def tearDown(self):
        HB.WATCHERS, HB.POLICY = self._w, self._p

    def _peer(self, name, age):
        # 파일 핸들을 with 로 확실히 닫는다 (ResourceWarning 방지 — Codex 지적 MSG-042714).
        with open(os.path.join(HB.WATCHERS, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump({"name": name, "heartbeat_epoch": self.now - age}, f)

    def _policy(self, **kw):
        with open(HB.POLICY, "w", encoding="utf-8") as f:
            json.dump(kw, f)

    # ── 오탐 방지 (핵심) ──
    def test_absent_peer_is_not_an_alert(self):
        # 동료 파일이 없다 = 아직 계약을 안 쓴다. 죽음이 아니다.
        r = HB.check_peers("claude-code-6c", self.now)
        self.assertEqual(r["stale"], [])

    def test_empty_dir_is_not_an_alert(self):
        r = HB.check_peers("claude-code-6c", self.now)
        self.assertEqual(r["stale"], [])
        self.assertEqual(r["fresh"], [])

    def test_broken_file_is_not_judged(self):
        # 읽을 수 없는 파일은 판정하지 않는다(추정 금지).
        with open(os.path.join(HB.WATCHERS, "codex.json"), "w", encoding="utf-8") as f:
            f.write("not json{")
        r = HB.check_peers("claude-code-6c", self.now)
        names = [x[0] for x in r["stale"] + r["fresh"]]
        self.assertNotIn("codex", names)

    # ── 진짜 정지는 잡는다 ──
    def test_stale_peer_is_detected(self):
        self._peer("antigravity", 100)     # 임계 30 초과
        r = HB.check_peers("claude-code-6c", self.now)
        self.assertEqual([x[0] for x in r["stale"]], ["antigravity"])

    def test_fresh_peer_is_not_stale(self):
        self._peer("antigravity", 2)
        r = HB.check_peers("claude-code-6c", self.now)
        self.assertEqual([x[0] for x in r["fresh"]], ["antigravity"])
        self.assertEqual(r["stale"], [])

    # ── 경계 ──
    def test_excludes_self(self):
        self._peer("claude-code-6c", 100)
        r = HB.check_peers("claude-code-6c", self.now)
        names = [x[0] for x in r["stale"] + r["fresh"]]
        self.assertNotIn("claude-code-6c", names)

    def test_policy_overrides_threshold(self):
        self._policy(stale_seconds=5)
        self._peer("antigravity", 10)      # 기본 30 이면 fresh, 정책 5 면 stale
        r = HB.check_peers("claude-code-6c", self.now)
        self.assertEqual([x[0] for x in r["stale"]], ["antigravity"])

    def test_missing_policy_uses_default(self):
        self.assertEqual(HB.stale_seconds(), HB.DEFAULT_STALE_SECONDS)

    # ── 쓰기 ──
    def test_write_is_atomic_and_readable(self):
        HB.write_heartbeat("claude-code-6c", started_epoch=self.now)
        p = os.path.join(HB.WATCHERS, "claude-code-6c.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["name"], "claude-code-6c")
        self.assertEqual(d["started_epoch"], self.now)
        self.assertIn("heartbeat_epoch", d)
        # 임시파일이 남지 않는다
        self.assertEqual([f for f in os.listdir(HB.WATCHERS) if f.endswith(".tmp")], [])

    def test_write_then_check_roundtrip(self):
        # 내가 쓰고 동료가 확인하면 fresh 로 보인다.
        HB.write_heartbeat("antigravity", started_epoch=self.now)
        r = HB.check_peers("claude-code-6c")
        self.assertIn("antigravity", [x[0] for x in r["fresh"]])


    # ── 필수 동료 미기동 (Codex MSG-042714 계약 보강) ──
    def test_absent_non_required_stays_silent(self):
        # required_peers 가 없으면 absent 는 여전히 조용하다 (흔한 경우 오탐 방지).
        r = HB.check_peers("claude", self.now)
        self.assertEqual(r["missing_required"], [])

    def test_required_absent_becomes_alert(self):
        # 필수인데 파일이 없으면 경보한다.
        self._policy(required_peers=["antigravity"])
        r = HB.check_peers("claude", self.now)
        self.assertEqual([x[0] for x in r["missing_required"]], ["antigravity"])

    def test_required_present_is_not_missing(self):
        self._policy(required_peers=["antigravity"])
        self._peer("antigravity", 2)
        r = HB.check_peers("claude", self.now)
        self.assertEqual(r["missing_required"], [])

    def test_enabled_at_grace_suppresses_missing(self):
        # 활성화 시각 전에는 필수 동료 absent 도 봐준다(배포 유예).
        self._policy(required_peers=["antigravity"], enabled_at=self.now + 3600)
        r = HB.check_peers("claude", self.now)
        self.assertEqual(r["missing_required"], [])

    def test_required_does_not_flag_self(self):
        # 내가 필수 목록에 있어도 나를 미기동으로 잡지 않는다.
        self._policy(required_peers=["claude"])
        r = HB.check_peers("claude", self.now)
        self.assertEqual(r["missing_required"], [])

    # ── 역할명 파일 + instance_id (Codex 권고) ──
    def test_role_filename_with_instance_id(self):
        HB.write_heartbeat("claude", instance_id="claude-code-6c", started_epoch=self.now)
        # 파일은 역할명으로, 세션 식별자는 필드로.
        self.assertTrue(os.path.exists(os.path.join(HB.WATCHERS, "claude.json")))
        self.assertFalse(os.path.exists(os.path.join(HB.WATCHERS, "claude-code-6c.json")))
        with open(os.path.join(HB.WATCHERS, "claude.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["name"], "claude")
        self.assertEqual(d["instance_id"], "claude-code-6c")

    def test_backward_compat_without_instance_id(self):
        # instance_id 를 안 줘도 동작한다(기존 호출 유지). antigravity 가 이 형태로 연동했다.
        HB.write_heartbeat("antigravity")
        with open(os.path.join(HB.WATCHERS, "antigravity.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["instance_id"], "antigravity")

    def test_report_does_not_create_its_own_heartbeat(self):
        HB.report("claude", instance_id="claude-code-6c")
        self.assertFalse(os.path.exists(os.path.join(HB.WATCHERS, "claude.json")))

    def test_report_preserves_started_epoch_and_instance_id(self):
        started = self.now - 3600
        HB.write_heartbeat(
            "antigravity",
            instance_id="antigravity-ide",
            started_epoch=started,
        )
        self._peer("claude", 100)

        HB.report("antigravity", instance_id="antigravity-ide")

        with open(os.path.join(HB.WATCHERS, "antigravity.json"), encoding="utf-8") as f:
            heartbeat = json.load(f)
        self.assertEqual(heartbeat["started_epoch"], started)
        self.assertEqual(heartbeat["instance_id"], "antigravity-ide")

    def test_once_writes_exactly_one_heartbeat(self):
        original = HB.write_heartbeat
        with mock.patch.object(HB, "write_heartbeat", wraps=original) as write:
            result = HB.main([
                "--me", "claude",
                "--instance-id", "claude-code-6c",
                "--once",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(write.call_count, 1)
        self.assertIn("started_epoch", write.call_args.kwargs)


class IndependenceTests(unittest.TestCase):
    def test_no_project_import(self):
        # csc.py 계열을 import 하면 그 코드가 깨질 때 감시자도 죽는다.
        import ast
        with open(HB.__file__, encoding="utf-8") as f:
            src = f.read()
        bad = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                bad |= {a.name for a in n.names if a.name.startswith("csc")}
            elif isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("csc"):
                bad.add(n.module)
        self.assertEqual(bad, set())


if __name__ == "__main__":
    unittest.main()
