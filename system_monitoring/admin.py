"""Create or reset the local administrator without exposing a password in arguments."""

import argparse
import getpass

from system_monitoring.auth import password_hash
from system_monitoring.config import Settings
from system_monitoring.storage import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    database = Database(settings.database_path)
    database.initialize()
    password = getpass.getpass("New administrator password (at least 12 characters): ")
    if not 12 <= len(password) <= 1024 or password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords must match and contain at least 12 characters")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT id FROM administrators").fetchone()
        if existing and not args.reset_password:
            raise SystemExit("An administrator exists; use --reset-password for account recovery")
        connection.execute(
            "INSERT INTO administrators(id, username, password_hash) VALUES(1,?,?) "
            "ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash, "
            "username=excluded.username, failed_attempts=0, locked_until=0",
            (settings.admin_username, password_hash(password)),
        )
        connection.execute("DELETE FROM sessions")
    print("Administrator saved. Existing sessions have been revoked.")


if __name__ == "__main__":
    main()
