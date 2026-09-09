"""Tests for the durable, local C3P user-absence state record."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from c3p_absence_state_store import (
    STATE_RELATIVE_PATH,
    arm_user_absence_mode,
    read_user_absence_mode,
)


class C3PAbsenceStateStoreTests(unittest.TestCase):
    def test_arming_persists_an_explicit_armed_record(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = arm_user_absence_mode(root, "C3P 사용자부재 모드")
            self.assertEqual("ARMED", record["state"])
            self.assertEqual(record, read_user_absence_mode(root))
            self.assertTrue((root / STATE_RELATIVE_PATH).exists())

    def test_missing_record_is_not_treated_as_armed(self):
        with TemporaryDirectory() as temporary:
            self.assertIsNone(read_user_absence_mode(Path(temporary)))


if __name__ == "__main__":
    unittest.main()
