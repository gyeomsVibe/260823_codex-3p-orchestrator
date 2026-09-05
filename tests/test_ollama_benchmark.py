import unittest

from ollama_benchmark import ALLOWED_MODEL, CASES, run_benchmark


class TestOllamaBenchmark(unittest.TestCase):
    def test_missing_model_stops_before_chat_and_never_pulls(self):
        calls = []

        def requester(path, payload, timeout):
            calls.append((path, payload))
            return {"models": []}

        with self.assertRaisesRegex(RuntimeError, "refusing auto-pull"):
            run_benchmark(requester=requester)
        self.assertEqual(calls, [("/api/tags", None)])

    def test_fixed_cases_enforce_all_safety_gates_and_score(self):
        calls = []
        answers = iter(
            {case["field"]: case["expected"], "reason": "fixed evidence"}
            for case in CASES
        )

        def requester(path, payload, timeout):
            calls.append((path, payload, timeout))
            if path == "/api/tags":
                return {"models": [{"name": ALLOWED_MODEL}]}
            if path == "/api/ps":
                return {"models": []}
            answer = next(answers)
            return {
                "message": {"content": __import__("json").dumps(answer)},
                "total_duration": 2_000_000,
                "load_duration": 1_000_000,
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

        result = run_benchmark(requester=requester)
        chat_payloads = [payload for path, payload, _ in calls if path == "/api/chat"]
        self.assertEqual(len(chat_payloads), 3)
        for payload in chat_payloads:
            self.assertEqual(payload["model"], ALLOWED_MODEL)
            self.assertIs(payload["stream"], False)
            self.assertEqual(payload["keep_alive"], 0)
            self.assertEqual(payload["options"], {"temperature": 0, "num_predict": 128})
            self.assertIs(payload["think"], False)
            self.assertIsInstance(payload["format"], dict)
        self.assertEqual(result["summary"]["schema_passes"], 3)
        self.assertEqual(result["summary"]["semantic_passes"], 3)
        self.assertTrue(result["summary"]["model_released"])
        self.assertEqual(result["summary"]["decision"], "GO_BOUNDED_MVP")


    def test_request_failure_is_reported_as_no_go(self):
        chat_calls = 0

        def requester(path, payload, timeout):
            nonlocal chat_calls
            if path == "/api/tags":
                return {"models": [{"name": ALLOWED_MODEL}]}
            if path == "/api/ps":
                return {"models": []}
            chat_calls += 1
            raise TimeoutError("bounded probe timed out")

        result = run_benchmark(requester=requester)

        self.assertEqual(chat_calls, 1)
        self.assertEqual(result["summary"]["decision"], "NO_GO")
        self.assertEqual(result["cases"][0]["error_type"], "TimeoutError")
        self.assertFalse(result["cases"][0]["schema_ok"])

if __name__ == "__main__":
    unittest.main()
