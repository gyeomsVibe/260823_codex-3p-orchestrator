import copy
import unittest

from csc_auth import (
    AuthenticationError,
    ReplayError,
    generate_session_key,
    sign_envelope,
    verify_envelope,
)


class TestCscAuthentication(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))
        self.epoch = "epoch-test-1"
        self.now = 1_800_000_000.0
        self.message = {
            "message_id": "MSG-1",
            "sender": "codex",
            "recipient": "claude",
            "type": "TASK",
            "body": "review this",
        }

    def signed(self, **overrides):
        values = {
            "issued_at": self.now,
            "nonce": "01" * 16,
        }
        values.update(overrides)
        return sign_envelope(self.message, self.key, self.epoch, **values)

    def test_round_trip_preserves_message_without_mutating_input(self):
        original = copy.deepcopy(self.message)
        signed = self.signed()
        verified = verify_envelope(signed, self.key, self.epoch, now=self.now)
        self.assertEqual(verified, original)
        self.assertEqual(self.message, original)
        self.assertNotIn("auth", self.message)

    def test_canonical_order_produces_the_same_mac(self):
        reordered = dict(reversed(list(self.message.items())))
        first = self.signed()
        second = sign_envelope(
            reordered,
            self.key,
            self.epoch,
            issued_at=self.now,
            nonce="01" * 16,
        )
        self.assertEqual(first["auth"]["mac"], second["auth"]["mac"])

    def test_tampering_is_rejected(self):
        signed = self.signed()
        signed["body"] = "forged"
        with self.assertRaises(AuthenticationError):
            verify_envelope(signed, self.key, self.epoch, now=self.now)

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(AuthenticationError):
            verify_envelope(self.signed(), b"x" * 32, self.epoch, now=self.now)

    def test_replay_is_rejected_after_first_acceptance(self):
        seen = set()
        signed = self.signed()
        verify_envelope(signed, self.key, self.epoch, now=self.now, seen_nonces=seen)
        with self.assertRaises(ReplayError):
            verify_envelope(signed, self.key, self.epoch, now=self.now, seen_nonces=seen)

    def test_stale_and_future_messages_are_rejected(self):
        for issued_at in (self.now - 31, self.now + 31):
            with self.subTest(issued_at=issued_at):
                signed = self.signed(issued_at=issued_at)
                with self.assertRaises(AuthenticationError):
                    verify_envelope(signed, self.key, self.epoch, now=self.now)

    def test_old_epoch_and_unsigned_message_are_rejected(self):
        with self.assertRaises(AuthenticationError):
            verify_envelope(self.signed(), self.key, "epoch-new", now=self.now)
        with self.assertRaises(AuthenticationError):
            verify_envelope(self.message, self.key, self.epoch, now=self.now)

    def test_short_key_and_invalid_json_number_are_rejected(self):
        with self.assertRaises(AuthenticationError):
            sign_envelope(self.message, b"short", self.epoch)
        invalid = {**self.message, "value": float("nan")}
        with self.assertRaises(AuthenticationError):
            sign_envelope(invalid, self.key, self.epoch)

    def test_invalid_freshness_window_is_rejected(self):
        signed = self.signed()
        for invalid in (float("nan"), float("inf"), -1, "not-a-number"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(AuthenticationError):
                    verify_envelope(
                        signed,
                        self.key,
                        self.epoch,
                        now=self.now,
                        max_skew_seconds=invalid,
                    )

    def test_generated_key_has_256_bits(self):
        self.assertEqual(len(generate_session_key()), 32)


if __name__ == "__main__":
    unittest.main()
