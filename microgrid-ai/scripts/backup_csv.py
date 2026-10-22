"""Back up the microgrid database and export the readings table to CSV.

Usage
-----
    python scripts/backup_csv.py
    python scripts/backup_csv.py --out D:\\backups
    python scripts/backup_csv.py --csv-only
    python scripts/backup_csv.py --keep 20

The database copy uses SQLite's online backup API, so it is consistent even
while the Flask backend is running and writing.  The CSV is produced from the
same ``db.export_csv`` helper the dashboard's "Export CSV" button uses, so both
contain exactly the stored columns.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from config import settings  # noqa: E402


def backup_database(destination: Path) -> int:
    """Copy the live database to ``destination`` using the backup API."""
    source_connection = sqlite3.connect(str(db.db_path()))
    destination_connection = sqlite3.connect(str(destination))
    try:
        with destination_connection:
            source_connection.backup(destination_connection)
        size = destination.stat().st_size
    finally:
        destination_connection.close()
        source_connection.close()
    return size


def export_csv(destination: Path) -> int:
    columns, rows = db.export_csv()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def prune(directory: Path, pattern: str, keep: int) -> List[Path]:
    """Delete all but the newest ``keep`` files matching ``pattern``."""
    if keep <= 0:
        return []
    candidates = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    removed: List[Path] = []
    for path in candidates[:-keep]:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "backups"),
                        help="destination directory (default ./backups)")
    parser.add_argument("--csv-only", action="store_true",
                        help="skip the database copy, export CSV only")
    parser.add_argument("--db-only", action="store_true",
                        help="skip the CSV export, copy the database only")
    parser.add_argument("--keep", type=int, default=10,
                        help="how many backups of each kind to retain (0 = all)")
    args = parser.parse_args()

    if args.csv_only and args.db_only:
        print("--csv-only and --db-only are mutually exclusive.")
        return 2

    settings.ensure_directories()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print("Database : %s" % db.db_path())
    print("Output   : %s" % out_dir)
    print("-" * 52)

    exit_code = 0

    if not args.csv_only:
        if Path(db.db_path()).exists():
            destination = out_dir / ("microgrid_%s.db" % stamp)
            size = backup_database(destination)
            print("DB backup  : %s (%d bytes)" % (destination.name, size))
        else:
            print("DB backup  : skipped - no database file yet")
            exit_code = 1

    if not args.db_only:
        destination = out_dir / ("readings_%s.csv" % stamp)
        count = export_csv(destination)
        print("CSV export : %s (%d rows)" % (destination.name, count))

    if args.keep > 0:
        for pattern in ("microgrid_*.db", "readings_*.csv"):
            for old in prune(out_dir, pattern, args.keep):
                print("Removed old: %s" % old.name)

    print("-" * 52)
    print("Done at %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
