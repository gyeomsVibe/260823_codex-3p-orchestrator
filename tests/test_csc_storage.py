import os
import sys
import json
import threading
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csc_storage
from csc_storage import (
    canonicalize_envelope,
    append_once,
    persist_message,
    append_audit,
    resolve_messages_dir,
)


class TestCscStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = os.path.join(self.temp_dir.name, ".agent-swarm")
        self.messages_dir = os.path.join(self.base_dir, "messages")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_duplicate_message_id_single_line_in_queue_and_inbox(self):
        """Verify that persisting the same message_id twice results in exactly 1 line

        in queue.jsonl and 1 line in <recipient>_inbox.jsonl.
        """
        envelope = {
            "message_id": "MSG-DUP-001",
            "timestamp": "2026-09-03T10:00:00Z",
            "sender": "client_alpha",
            "recipient": "client_beta",
            "type": "PROPOSAL",
            "in_reply_to": "none",
            "body": "First delivery proposal",
        }

        # First persistence
        res1 = persist_message(envelope, base_dir=self.base_dir)
        self.assertEqual(res1.get("status"), "ok")
        self.assertTrue(res1.get("persisted"))
        self.assertFalse(res1.get("deduplicated"))

        # Second persistence with same message_id
        res2 = persist_message(envelope, base_dir=self.base_dir)
        self.assertEqual(res2.get("status"), "ok")
        self.assertTrue(res2.get("persisted"))
        self.assertTrue(res2.get("deduplicated"))

        queue_file = os.path.join(self.messages_dir, "queue.jsonl")
        inbox_file = os.path.join(self.messages_dir, "client_beta_inbox.jsonl")

        self.assertTrue(os.path.exists(queue_file))
        with open(queue_file, "r", encoding="utf-8") as f:
            q_lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(len(q_lines), 1, "queue.jsonl must contain exactly 1 line")
        q_record = json.loads(q_lines[0])
        self.assertEqual(q_record.get("message_id"), "MSG-DUP-001")

        self.assertTrue(os.path.exists(inbox_file))
        with open(inbox_file, "r", encoding="utf-8") as f:
            i_lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(len(i_lines), 1, "client_beta_inbox.jsonl must contain exactly 1 line")
        i_record = json.loads(i_lines[0])
        self.assertEqual(i_record.get("message_id"), "MSG-DUP-001")

    def test_recipient_all_records_only_to_all_inbox(self):
        """Verify that recipient 'all' records to all_inbox.jsonl in one place."""
        envelope = {
            "message_id": "MSG-BROADCAST-ALL",
            "sender": "commander",
            "recipient": "all",
            "type": "RESULT",
            "body": "Global swarm notification",
        }

        res = persist_message(envelope, base_dir=self.base_dir)
        self.assertTrue(res.get("persisted"))

        all_inbox = os.path.join(self.messages_dir, "all_inbox.jsonl")
        queue_file = os.path.join(self.messages_dir, "queue.jsonl")

        self.assertTrue(os.path.exists(all_inbox), "all_inbox.jsonl must be created")
        with open(all_inbox, "r", encoding="utf-8") as f:
            a_lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(len(a_lines), 1)
        self.assertEqual(json.loads(a_lines[0])["message_id"], "MSG-BROADCAST-ALL")

        with open(queue_file, "r", encoding="utf-8") as f:
            q_lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(len(q_lines), 1)

        # Idempotent re-append to 'all'
        res2 = persist_message(envelope, base_dir=self.base_dir)
        self.assertTrue(res2.get("deduplicated"))
        with open(all_inbox, "r", encoding="utf-8") as f:
            a_lines_after = [line.strip() for line in f if line.strip()]
        self.assertEqual(len(a_lines_after), 1, "Duplicate to 'all' must not add line")

    def test_concurrent_threads_append_consistency(self):
        """Verify that multiple concurrent threads appending unique and duplicate

        messages result in all lines being valid JSON and each unique ID recorded exactly once.
        No flaky sleep thresholds are used; thread completion is synchronized via join().
        """
        num_threads = 10
        unique_per_thread = 5
        shared_duplicate_ids = ["MSG-SHARED-001", "MSG-SHARED-002"]

        expected_unique_ids = set(shared_duplicate_ids)
        for t_idx in range(num_threads):
            for m_idx in range(unique_per_thread):
                expected_unique_ids.add(f"MSG-T{t_idx:02d}-M{m_idx:02d}")

        errors = []

        def worker(thread_idx: int):
            try:
                # 1. Append unique messages
                for m_idx in range(unique_per_thread):
                    msg_id = f"MSG-T{thread_idx:02d}-M{m_idx:02d}"
                    msg = {
                        "message_id": msg_id,
                        "sender": f"worker_{thread_idx}",
                        "recipient": "hub",
                        "type": "ACK",
                        "body": f"Worker {thread_idx} msg {m_idx}",
                    }
                    persist_message(msg, base_dir=self.base_dir)

                # 2. Append shared duplicate messages
                for dup_id in shared_duplicate_ids:
                    dup_msg = {
                        "message_id": dup_id,
                        "sender": f"worker_{thread_idx}",
                        "recipient": "hub",
                        "type": "ACK",
                        "body": "Shared content",
                    }
                    persist_message(dup_msg, base_dir=self.base_dir)
            except Exception as e:
                errors.append(f"Thread {thread_idx} failed: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Encountered thread execution errors: {errors}")

        queue_file = os.path.join(self.messages_dir, "queue.jsonl")
        self.assertTrue(os.path.exists(queue_file))

        recorded_ids = []
        with open(queue_file, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, 1):
                stripped = raw_line.strip()
                self.assertTrue(bool(stripped), f"Empty or whitespace line found at line {line_no}")
                try:
                    data = json.loads(stripped)
                except Exception as e:
                    self.fail(f"Line {line_no} failed JSON parsing: '{stripped}' ({e})")
                self.assertIn("message_id", data)
                recorded_ids.append(data["message_id"])

        # Every unique ID must appear EXACTLY once
        self.assertEqual(len(recorded_ids), len(expected_unique_ids))
        self.assertEqual(set(recorded_ids), expected_unique_ids)
        self.assertEqual(len(recorded_ids), len(set(recorded_ids)), "Duplicate message_ids found in queue.jsonl")

    def test_malformed_existing_lines_preserved(self):
        """Verify that existing malformed JSON lines in the target file are preserved

        and skipped without corrupting new valid appends or failing deduplication.
        """
        os.makedirs(self.messages_dir, exist_ok=True)
        queue_file = os.path.join(self.messages_dir, "queue.jsonl")

        malformed_line_1 = '{"corrupted": true, incomplete_object\n'
        malformed_line_2 = "NOT EVEN JSON PLAIN TEXT\n"
        valid_preexisting_id = "MSG-PREEXISTING-001"
        valid_preexisting_line = json.dumps({
            "message_id": valid_preexisting_id,
            "timestamp": "2026-09-03T10:00:00Z",
            "sender": "sys",
            "recipient": "all",
            "type": "ACK",
            "in_reply_to": "none",
            "body": "Existing valid message",
        }) + "\n"
        malformed_line_3_no_newline = "BROKEN LINE WITHOUT TRAILING NEWLINE"

        with open(queue_file, "w", encoding="utf-8") as f:
            f.write(malformed_line_1)
            f.write(malformed_line_2)
            f.write(valid_preexisting_line)
            f.write(malformed_line_3_no_newline)

        # 1. Attempt to append duplicate of pre-existing ID
        dup_envelope = {
            "message_id": valid_preexisting_id,
            "sender": "sys",
            "recipient": "all",
            "type": "ACK",
            "body": "Duplicate attempt",
        }
        res_dup = persist_message(dup_envelope, base_dir=self.base_dir)
        self.assertFalse(res_dup.get("deduplicated"), "Pre-existing ID was missing from inbox, so persist_message recovered inbox (deduplicated=False)")

        # Verify pre-existing ID in queue exactly 1 time
        with open(queue_file, "r", encoding="utf-8", errors="replace") as f:
            queue_ids = []
            for line in f:
                try:
                    parsed = json.loads(line.strip())
                    queue_ids.append(parsed.get("message_id"))
                except Exception:
                    pass
        self.assertEqual(queue_ids.count(valid_preexisting_id), 1)

        # Verify new inbox contains the recovered ID exactly 1 time
        inbox_file = os.path.join(self.messages_dir, "all_inbox.jsonl")
        self.assertTrue(os.path.exists(inbox_file))
        with open(inbox_file, "r", encoding="utf-8") as f:
            inbox_ids = []
            for line in f:
                try:
                    parsed = json.loads(line.strip())
                    inbox_ids.append(parsed.get("message_id"))
                except Exception:
                    pass
        self.assertEqual(inbox_ids.count(valid_preexisting_id), 1)

        # 2. Append brand-new valid message
        new_envelope = {
            "message_id": "MSG-BRAND-NEW-002",
            "sender": "user",
            "recipient": "agent",
            "type": "PROPOSAL",
            "body": "New valid payload",
        }
        res_new = persist_message(new_envelope, base_dir=self.base_dir)
        self.assertFalse(res_new.get("deduplicated"))

        # Inspect resulting file
        with open(queue_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Check preservation of malformed lines
        self.assertEqual(lines[0], malformed_line_1)
        self.assertEqual(lines[1], malformed_line_2)
        self.assertEqual(lines[2], valid_preexisting_line)
        self.assertTrue(lines[3].startswith(malformed_line_3_no_newline))

        # Check that the new line is appended as valid JSON
        new_record = json.loads(lines[-1].strip())
        self.assertEqual(new_record["message_id"], "MSG-BRAND-NEW-002")

        # Check that MSG-PREEXISTING-001 was NOT duplicated
        all_ids = []
        for line in lines:
            try:
                parsed = json.loads(line.strip())
                all_ids.append(parsed.get("message_id"))
            except Exception:
                pass
        self.assertEqual(all_ids.count(valid_preexisting_id), 1)

    def test_append_audit_isolated_from_queue(self):
        """Verify that append_audit writes only to audit.jsonl and never touches queue.jsonl."""
        audit_event = {
            "type": "REGISTER",
            "agent": "client_theta",
            "action": "CONNECTION_ESTABLISHED",
        }

        res = append_audit(audit_event, base_dir=self.base_dir)
        self.assertTrue(res)

        audit_file = os.path.join(self.messages_dir, "audit.jsonl")
        queue_file = os.path.join(self.messages_dir, "queue.jsonl")

        self.assertTrue(os.path.exists(audit_file), "audit.jsonl must exist")
        with open(audit_file, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["agent"], "client_theta")
        self.assertEqual(records[0]["type"], "REGISTER")
        self.assertIn("timestamp", records[0])

        self.assertFalse(os.path.exists(queue_file), "queue.jsonl must not be created by append_audit")

    def test_canonicalize_envelope_requires_message_id(self):
        """Verify that canonicalize_envelope raises ValueError when message_id is absent."""
        with self.assertRaises(ValueError):
            canonicalize_envelope({"type": "ACK", "body": "No ID"})

        with self.assertRaises(ValueError):
            canonicalize_envelope({"message_id": "", "type": "ACK"})

    def test_canonicalize_envelope_wire_format_conversion(self):
        """Verify that wire aliases (id, from, to) are mapped to canonical envelope fields."""
        wire = {
            "id": "WIRE-001",
            "from": "alice",
            "to": "bob",
            "type": "PROPOSAL",
            "body": "Hello Alice",
            "custom_metadata": 12345,
        }
        canonical = canonicalize_envelope(wire)
        self.assertEqual(canonical["message_id"], "WIRE-001")
        self.assertEqual(canonical["sender"], "alice")
        self.assertEqual(canonical["recipient"], "bob")
        self.assertEqual(canonical["type"], "PROPOSAL")
        self.assertEqual(canonical["body"], "Hello Alice")
        self.assertEqual(canonical["custom_metadata"], 12345)
        self.assertNotIn("id", canonical)
        self.assertNotIn("from", canonical)
        self.assertNotIn("to", canonical)


if __name__ == "__main__":
    unittest.main()
