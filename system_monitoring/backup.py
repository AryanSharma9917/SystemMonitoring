"""Consistent SQLite snapshots and restoration to a new, unused database path."""

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from system_monitoring.storage import SCHEMA_VERSION


def validate(connection: sqlite3.Connection) -> int:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if not 1 <= version <= SCHEMA_VERSION:
        raise ValueError("Unsupported database schema; use the matching application version")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Database integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("Database contains invalid references")
    table_query = "SELECT name FROM sqlite_master WHERE type='table'"
    tables = {row[0] for row in connection.execute(table_query)}
    required = {"services", "incidents"}
    if version >= 2:
        required.add("checks")
    if version >= 3:
        required.update({"administrators", "sessions", "notifications"})
    if not required <= tables:
        raise ValueError("Database is missing application tables")
    return version


def snapshot(source: Path, destination: Path, *, restore: bool = False) -> int:
    """Never modify source or overwrite destination; publish a validated file atomically.

    SQLite's backup API includes committed WAL data while the application is running.
    Restore also invalidates sessions and clears leases in the private copy. Operators
    must stop the application before switching it to the restored file.
    """
    source, destination = source.resolve(), destination.absolute()
    if source == destination.resolve() or destination.exists() or destination.is_symlink():
        raise ValueError("Destination must be a new, unused path")
    descriptor, temporary = tempfile.mkstemp(prefix=".monitoring-snapshot-", dir=destination.parent)
    os.close(descriptor)
    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original,
            closing(sqlite3.connect(temporary)) as copy,
        ):
            # Bound retries if an external writer keeps the source locked.
            import time

            deadline = time.monotonic() + 60

            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise TimeoutError("Snapshot exceeded its 60 second deadline")

            original.backup(copy, pages=256, progress=progress, sleep=0.05)
            version = validate(copy)
            if restore:
                with copy:
                    if version >= 3:
                        copy.execute("DELETE FROM sessions")
                        copy.execute("UPDATE notifications SET lease_token=NULL, lease_until=0")
                    if version >= 2:
                        copy.execute("UPDATE services SET check_token=NULL, check_lease_until=0")
                validate(copy)
        # Flush the closed snapshot before publishing its name. A hard link, unlike
        # rename/replace, fails if another process has created the destination.
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return version
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        version = snapshot(args.source, args.destination, restore=args.operation == "restore")
    except (OSError, sqlite3.Error, ValueError, TimeoutError):
        # Configuration, filenames and database payloads may contain private data.
        parser.exit(
            1,
            "Snapshot failed: check paths, permissions, schema and database integrity.\n",
        )
    print(f"{args.operation.capitalize()} complete: consistent schema {version} snapshot created.")


if __name__ == "__main__":
    main()
