"""csc_post.py 시험 — 비상 발신기가 비상구로만 남는지 본다.

이 시험이 지키려는 것은 기능이 아니라 경계다.
비상구는 편해서 위험하다. 서명 없이 쓸 수 있으니 인증 모드에서 뒷문이 된다.
그래서 '보내진다' 보다 '거부된다' 를 더 많이 시험한다.

코덱스가 D1 표결에 단 조건 (MSG-20260907-164525-778679-82fe4ccf-COD-CLA):
  1) require_authenticated=true 일 때 명시적으로 거부할 것   -> test_refuses_*
  2) 실제 csc_worker.py 구문 오류 상태에서 수직 검증할 것    -> 별도 수행, 결과는 커밋 메시지에 남긴다
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csc_post


def write_lines(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class AuthenticatedModeTests(unittest.TestCase):
    """인증 모드 판정. 여기서 틀리면 뒷문이 열린다."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.msgs = os.path.join(self.dir, "messages")
        os.makedirs(self.msgs)

    def test_no_queue_is_unauthenticated(self):
        # 큐가 없으면 아직 아무도 서명하지 않았다.
        self.assertFalse(csc_post.authenticated_mode(self.msgs))

    def test_plain_messages_are_unauthenticated(self):
        write_lines(os.path.join(self.msgs, "queue.jsonl"),
                    [{"message_id": "M1", "body": "hi"}])
        self.assertFalse(csc_post.authenticated_mode(self.msgs))

    def test_auth_field_flips_to_authenticated(self):
        write_lines(os.path.join(self.msgs, "queue.jsonl"), [
            {"message_id": "M1", "body": "hi"},
            {"message_id": "M2", "body": "signed",
             "auth": {"version": "csc-hmac-sha256-v1", "mac": "deadbeef"}},
        ])
        self.assertTrue(csc_post.authenticated_mode(self.msgs))

    def test_broken_lines_do_not_crash_detection(self):
        # 깨진 줄이 있다고 판정이 멈추면, 멈춘 자리에서 뒷문이 열린다.
        path = os.path.join(self.msgs, "queue.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write("이건 JSON 이 아니다\n")
            f.write(json.dumps({"message_id": "M2", "auth": {"mac": "x"}}) + "\n")
        self.assertTrue(csc_post.authenticated_mode(self.msgs))


class RefusalTests(unittest.TestCase):
    """거부해야 할 때 거부하는가."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.msgs = os.path.join(self.dir, "messages")
        os.makedirs(self.msgs)

    def test_refuses_in_authenticated_mode(self):
        write_lines(os.path.join(self.msgs, "queue.jsonl"),
                    [{"message_id": "M1", "auth": {"mac": "x"}}])
        with self.assertRaises(PermissionError) as ctx:
            csc_post.post("claude-code-6c", "codex", "ACK", "본문", messages_dir=self.msgs)
        self.assertIn("인증", str(ctx.exception))

    def test_refuses_unknown_type(self):
        with self.assertRaises(ValueError):
            csc_post.post("claude-code-6c", "codex", "GOSSIP", "본문", messages_dir=self.msgs)

    def test_refuses_empty_body(self):
        # 빈 메시지는 보낸 사람도 받은 사람도 아무것도 알 수 없다.
        with self.assertRaises(ValueError):
            csc_post.post("claude-code-6c", "codex", "ACK", "   ", messages_dir=self.msgs)


class DeliveryTests(unittest.TestCase):
    """보내야 할 때 제대로 보내는가."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.msgs = os.path.join(self.dir, "messages")
        os.makedirs(self.msgs)

    def _read(self, name):
        path = os.path.join(self.msgs, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_writes_queue_and_named_inbox(self):
        r = csc_post.post("claude-code-6c", "codex", "RESULT", "본문",
                          messages_dir=self.msgs)
        self.assertTrue(r["queue_appended"])
        self.assertEqual(len(self._read("queue.jsonl")), 1)
        self.assertEqual(len(self._read("codex_inbox.jsonl")), 1)

    def test_all_goes_to_all_inbox(self):
        # persist_message 와 같은 규칙이어야 한다. 다르면 수신자가 못 읽는다.
        csc_post.post("claude-code-6c", "all", "REPORT", "본문", messages_dir=self.msgs)
        self.assertEqual(len(self._read("all_inbox.jsonl")), 1)
        self.assertEqual(self._read("codex_inbox.jsonl"), [])

    def test_envelope_has_required_fields(self):
        csc_post.post("claude-code-6c", "codex", "ACK", "본문", messages_dir=self.msgs)
        env = self._read("queue.jsonl")[0]
        for field in ("message_id", "timestamp", "sender", "recipient",
                      "type", "in_reply_to", "body"):
            self.assertIn(field, env, f"{field} 가 없으면 기존 판독기가 읽지 못한다")
        self.assertTrue(env["message_id"].endswith("-CLA-COD"))
        self.assertNotIn("auth", env, "비상 발신기는 서명하지 않는다")

    def test_same_message_id_is_not_duplicated(self):
        env = csc_post.build_envelope("claude-code-6c", "codex", "ACK", "본문")
        p = os.path.join(self.msgs, "queue.jsonl")
        self.assertTrue(csc_post._append(p, env))
        self.assertFalse(csc_post._append(p, env), "같은 id 를 두 번 쓰면 안 된다")
        self.assertEqual(len(self._read("queue.jsonl")), 1)

    def test_body_with_newlines_survives(self):
        # 본문에 줄바꿈이 있어도 한 줄 JSON 으로 남아야 한다.
        # 셸이 본문을 삼킨 사고가 있었으므로 여기서 못 박는다.
        body = "첫 줄\n둘째 줄\n\n넷째 줄"
        csc_post.post("claude-code-6c", "codex", "RESULT", body, messages_dir=self.msgs)
        self.assertEqual(len(self._read("queue.jsonl")), 1)
        self.assertEqual(self._read("queue.jsonl")[0]["body"], body)


class IndependenceTests(unittest.TestCase):
    """이 파일의 존재 이유 자체를 시험한다."""

    def test_imports_no_project_module(self):
        # 프로젝트 모듈을 하나라도 import 하면, 그 모듈이 깨졌을 때 같이 죽는다.
        # 그러면 비상구가 아니다. 이 시험이 그 규칙을 지킨다.
        import ast
        src = open(csc_post.__file__, encoding="utf-8").read()
        imported = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        project = {n for n in imported if n.startswith("csc_") or n in ("csc",)}
        self.assertEqual(project, set(),
                         f"프로젝트 모듈을 import 했다: {project} — 비상구가 아니게 된다")


if __name__ == "__main__":
    unittest.main()
