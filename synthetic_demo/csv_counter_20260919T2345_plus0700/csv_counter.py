"""CSV job status counter (standard library only)."""

import argparse
import csv

VALID_STATUSES = ("completed", "failed", "unknown")
REQUIRED_COLUMNS = ("job_id", "status")


def count_job_statuses(csv_path):
    """Read CSV with columns job_id,status and count statuses.

    job_id values are kept as strings (no int conversion).

    Returns:
        dict: {"completed": int, "failed": int, "unknown": int}

    Raises:
        FileNotFoundError: if csv_path does not exist.
        ValueError: on missing/invalid header, or any invalid status value.
    """
    counts = {status: 0 for status in VALID_STATUSES}
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty: missing header 'job_id,status'.")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                "CSV header must contain columns %s; missing: %s (found: %s)."
                % (list(REQUIRED_COLUMNS), missing, reader.fieldnames)
            )
        for row_number, row in enumerate(reader, start=2):
            job_id = row.get("job_id", "")
            # Keep job_id as string explicitly (csv already yields str/None).
            job_id = "" if job_id is None else str(job_id)
            status_raw = row.get("status", "")
            status = "" if status_raw is None else str(status_raw).strip()
            if status not in VALID_STATUSES:
                raise ValueError(
                    "Invalid status value %r at row %d (job_id=%r). "
                    "Allowed values: %s."
                    % (status_raw, row_number, job_id, list(VALID_STATUSES))
                )
            counts[status] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Count completed/failed/unknown statuses from a job CSV."
    )
    parser.add_argument("csv_file", help="Path to CSV file with columns job_id,status")
    args = parser.parse_args(argv)
    counts = count_job_statuses(args.csv_file)
    print(
        "completed=%d failed=%d unknown=%d"
        % (counts["completed"], counts["failed"], counts["unknown"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
