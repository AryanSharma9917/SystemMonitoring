"""Single-administrator password verification and revocable server-side sessions."""

import hashlib
import secrets
import time

from fastapi import HTTPException, Request

from system_monitoring.storage import Database

COOKIE = "monitor_session"
ITERATIONS = 600_000


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin requests are not allowed")


class Authentication:
    def __init__(self, database: Database, settings):
        self.database, self.settings = database, settings

    def bootstrap(self) -> None:
        if not self.settings.admin_password:
            return
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT id FROM administrators").fetchone():
                connection.execute(
                    "INSERT INTO administrators(id, username, password_hash) VALUES(1,?,?)",
                    (
                        self.settings.admin_username,
                        password_hash(self.settings.admin_password.get_secret_value()),
                    ),
                )

    def login(self, username: str, password: str) -> dict:
        denied = False
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            admin = connection.execute("SELECT * FROM administrators WHERE id=1").fetchone()
            if admin is None:
                raise HTTPException(503, "Administrator access has not been configured")
            if admin["locked_until"] > time.time():
                raise HTTPException(429, "Too many sign-in attempts; try again in one minute")
            # Always verify the password, including incorrect usernames.
            valid_password = verify_password(password, admin["password_hash"])
            if not valid_password or not secrets.compare_digest(
                username.encode(), admin["username"].encode()
            ):
                attempts = admin["failed_attempts"] + 1 if admin["locked_until"] == 0 else 1
                connection.execute(
                    "UPDATE administrators SET failed_attempts=?, locked_until=? WHERE id=1",
                    (attempts, time.time() + 60 if attempts >= 5 else 0),
                )
                denied = True
            else:
                connection.execute("UPDATE administrators SET failed_attempts=0, locked_until=0")
                connection.execute("DELETE FROM sessions WHERE expires_at<=?", (time.time(),))
                # Bound storage even when a valid operator signs in repeatedly.
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions "
                    "ORDER BY created_at DESC LIMIT -1 OFFSET 19)"
                )
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                expires = time.time() + self.settings.session_seconds
                connection.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?)",
                    (token_hash(token), csrf, expires, time.time()),
                )
        if denied:
            raise HTTPException(401, "Incorrect username or password")
        return {
            "token": token,
            "csrf_token": csrf,
            "expires_at": expires,
            "username": admin["username"],
        }

    def session(self, request: Request) -> dict:
        raw = request.cookies.get(COOKIE, "")
        if not raw:
            raise HTTPException(401, "Sign in to continue")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT s.*, a.username FROM sessions s CROSS JOIN administrators a "
                "WHERE s.token_hash=? AND s.expires_at>?",
                (token_hash(raw), time.time()),
            ).fetchone()
        if row is None:
            raise HTTPException(401, "Your session has expired; sign in again")
        return dict(row)


def require_admin(request: Request) -> dict:
    session = request.app.state.authentication.session(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        same_origin(request)
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf.encode(), session["csrf_token"].encode()):
            raise HTTPException(403, "Refresh your session before making changes")
    return session
