"""Unit tests for Antigravity telemetry extraction and aggregation."""

import json
import tempfile
import unittest
from pathlib import Path

from antigravity_capacity_routing.telemetry import (
    TelemetryParseError,
    extract_telemetry,
    parse_cli_json,
    parse_stream_json,
    record_telemetry_event,
    summarize_telemetry,
)


class TestAntigravityTelemetry(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "telemetry.jsonl"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_cli_json_with_warning_preamble(self) -> None:
        raw = (
            "warning: --mode plan has no effect while slash command expansion is disabled.\n"
            '{"conversation_id":"conv-123","status":"SUCCESS","response":"Hello World",'
            '"duration_seconds":1.5,"num_turns":1,"usage":{"input_tokens":1000,"output_tokens":50,'
            '"thinking_tokens":30,"cache_read_tokens":0,"total_tokens":1050}}\n'
        )
        data = parse_cli_json(raw)
        self.assertEqual(data["conversation_id"], "conv-123")
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["response"], "Hello World")
        self.assertEqual(data["duration_seconds"], 1.5)
        self.assertEqual(data["usage"]["total_tokens"], 1050)
        self.assertEqual(data["usage"]["thinking_tokens"], 30)

    def test_parse_cli_json_preserves_denied_actions(self) -> None:
        raw = (
            '{"conversation_id":"conv-denied","status":"SUCCESS","response":"",'
            '"duration_seconds":3,"denied_actions":[{"action":"escalate_admin",'
            '"display_name":"Bash"}],"usage":{"total_tokens":21206}}'
        )

        data = parse_cli_json(raw)

        self.assertEqual(data["denied_actions"][0]["action"], "escalate_admin")

    def test_parse_stream_json_with_result_event(self) -> None:
        raw = (
            "warning: banner notice\n"
            '{"event":"init","conversation_id":"c-abc","init":{"cwd":"/test","tools":["read"]}}\n'
            '{"event":"step_update","step_update":{"conversation_id":"c-abc","step_index":0,"state":"DONE"}}\n'
            '{"event":"result","result":{"conversation_id":"c-abc","status":"SUCCESS","response":"Done work",'
            '"duration_seconds":2.1,"num_turns":1,"usage":{"input_tokens":5000,"output_tokens":200,'
            '"thinking_tokens":100,"cache_read_tokens":0,"total_tokens":5200}}}\n'
        )
        data = parse_stream_json(raw)
        self.assertEqual(data["conversation_id"], "c-abc")
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["response"], "Done work")
        self.assertEqual(data["usage"]["total_tokens"], 5200)
        self.assertEqual(data["stream_events_count"], 3)

    def test_parse_stream_json_fallback_on_step_updates(self) -> None:
        raw = (
            '{"event":"init","conversation_id":"c-xyz","init":{}}\n'
            '{"event":"step_update","step_update":{"conversation_id":"c-xyz","step_index":0,"state":"DONE",'
            '"text_delta":"part 1 ","duration_seconds":1.0,"usage":{"input_tokens":200,"output_tokens":20,"total_tokens":220}}}\n'
            '{"event":"step_update","step_update":{"conversation_id":"c-xyz","step_index":1,"state":"DONE",'
            '"text_delta":"part 2","duration_seconds":2.0,"usage":{"input_tokens":200,"output_tokens":40,"total_tokens":240}}}\n'
        )
        data = parse_stream_json(raw)
        self.assertEqual(data["conversation_id"], "c-xyz")
        self.assertEqual(data["response"], "part 1 part 2")
        self.assertEqual(data["usage"]["total_tokens"], 240)

    def test_extract_telemetry_universal(self) -> None:
        raw_json = '{"conversation_id":"1","status":"SUCCESS","response":"hi","duration_seconds":0.5,"usage":{"total_tokens":100}}'
        data1 = extract_telemetry(raw_json)
        self.assertEqual(data1["total_tokens"] if "total_tokens" in data1 else data1["usage"]["total_tokens"], 100)

        raw_stream = '{"event":"result","result":{"conversation_id":"2","status":"SUCCESS","response":"ok","duration_seconds":0.8,"usage":{"total_tokens":250}}}'
        data2 = extract_telemetry(raw_stream)
        self.assertEqual(data2["usage"]["total_tokens"], 250)

    def test_parse_invalid_raises_error(self) -> None:
        with self.assertRaises(TelemetryParseError):
            parse_cli_json("just some random text without json")
        with self.assertRaises(TelemetryParseError):
            parse_stream_json("just some random text without json")
        with self.assertRaises(TelemetryParseError):
            extract_telemetry("")

    def test_record_and_summarize_telemetry(self) -> None:
        rec1 = {
            "conversation_id": "c-1",
            "status": "SUCCESS",
            "duration_seconds": 2.0,
            "usage": {"input_tokens": 1000, "output_tokens": 100, "thinking_tokens": 50, "total_tokens": 1100},
        }
        rec2 = {
            "conversation_id": "c-2",
            "status": "SUCCESS",
            "duration_seconds": 3.0,
            "usage": {"input_tokens": 2000, "output_tokens": 200, "thinking_tokens": 80, "total_tokens": 2200},
        }
        record_telemetry_event(rec1, self.log_file)
        record_telemetry_event(rec2, self.log_file)

        lines = self.log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

        summary = summarize_telemetry([rec1, rec2])
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["success_rate"], 1.0)
        self.assertEqual(summary["total_tokens"], 3300)
        self.assertEqual(summary["input_tokens"], 3000)
        self.assertEqual(summary["output_tokens"], 300)
        self.assertEqual(summary["thinking_tokens"], 130)
        self.assertEqual(summary["total_duration_seconds"], 5.0)
        self.assertEqual(summary["avg_duration_seconds"], 2.5)


if __name__ == "__main__":
    unittest.main()
