"""Unit tests for csv_counter (standard library only)."""

import csv
import tempfile
import unittest
from pathlib import Path

from csv_counter import count_job_statuses


def _write_csv(path, rows, header=("job_id", "status")):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


class TestCountJobStatuses(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "jobs.csv"
            _write_csv(
                p,
                [
                    ("001", "completed"),
                    ("002", "failed"),
                    ("003", "unknown"),
                    ("004", "completed"),
                    ("007", "failed"),
                ],
            )
            result = count_job_statuses(str(p))
        self.assertEqual(result, {"completed": 2, "failed": 2, "unknown": 1})

    def test_happy_path_keeps_job_id_as_string(self):
        # Leading zeros must survive; implementation must not int() job_id.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "jobs.csv"
            _write_csv(p, [("001", "completed"), ("007", "failed")])
            with open(p, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                job_ids = [row["job_id"] for row in reader]
            self.assertEqual(job_ids, ["001", "007"])
            self.assertTrue(all(isinstance(j, str) for j in job_ids))
            result = count_job_statuses(str(p))
        self.assertEqual(result, {"completed": 1, "failed": 1, "unknown": 0})

    def test_empty_file_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "empty.csv"
            _write_csv(p, [])
            result = count_job_statuses(str(p))
        self.assertEqual(result, {"completed": 0, "failed": 0, "unknown": 0})

    def test_bad_status_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            _write_csv(p, [("001", "completed"), ("002", "running")])
            with self.assertRaises(ValueError) as ctx:
                count_job_statuses(str(p))
        self.assertIn("Invalid status", str(ctx.exception))
        self.assertIn("running", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
