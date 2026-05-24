from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUTH_DB_PATH = PROJECT_ROOT / "data_store" / "stock_pool_templates.sqlite"
ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD_ENV = "T0_ADMIN_DEFAULT_PASSWORD"
SESSION_COOKIE_NAME = "t0_session"
SESSION_DAYS = 7
PBKDF2_ITERATIONS = 260_000


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _db_path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path or DEFAULT_AUTH_DB_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def connect_auth_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column_name, column_definition in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def hash_password(password: str) -> str:
    if len(str(password or "")) < 8:
        raise ValueError("密码长度至少 8 位")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = str(password_hash or "").split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, int(iterations_text))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _row_to_public_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    role = str(row["role"] or "user")
    username = str(row["username"] or "")
    return {
        "user_id": row["user_id"],
        "username": username,
        "display_name": row["display_name"] or username,
        "role": role,
        "is_admin": role == "admin",
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"] or "",
        "password_updated_at": row["password_updated_at"] or "",
    }


def _validate_username(username: str) -> str:
    clean = str(username or "").strip()
    if not clean:
        raise ValueError("用户名不能为空")
    if len(clean) < 3 or len(clean) > 32:
        raise ValueError("用户名长度必须在 3 到 32 位之间")
    if not all(ch.isalnum() or ch in "_-" for ch in clean):
        raise ValueError("用户名只能包含字母、数字、下划线和短横线")
    return clean


def _admin_default_password() -> str:
    return os.environ.get(ADMIN_DEFAULT_PASSWORD_ENV, "").strip()


def init_auth_db(db_path: str | Path | None = None) -> None:
    with connect_auth_db(db_path) as conn:
        now = now_text()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                is_revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_username
                ON auth_sessions(username, is_revoked, expires_at);
            """
        )
        _ensure_columns(
            conn,
            "users",
            {
                "user_id": "TEXT DEFAULT ''",
                "role": "TEXT NOT NULL DEFAULT 'user'",
                "is_active": "INTEGER NOT NULL DEFAULT 1",
                "last_login_at": "TEXT DEFAULT ''",
                "password_updated_at": "TEXT DEFAULT ''",
            },
        )
        for row in conn.execute("SELECT username, user_id FROM users").fetchall():
            if not row["user_id"]:
                conn.execute("UPDATE users SET user_id=?, updated_at=? WHERE username=?", (str(uuid4()), now, row["username"]))
        admin = conn.execute("SELECT * FROM users WHERE username=?", (ADMIN_USERNAME,)).fetchone()
        if admin is None:
            default_password = _admin_default_password()
            password_hash = hash_password(default_password) if default_password else ""
            conn.execute(
                """
                INSERT INTO users(user_id, username, password_hash, display_name, role, is_active, created_at, updated_at, password_updated_at)
                VALUES(?, ?, ?, ?, 'admin', 1, ?, ?, ?)
                """,
                (str(uuid4()), ADMIN_USERNAME, password_hash, ADMIN_USERNAME, now, now, now if password_hash else ""),
            )
        else:
            updates: dict[str, Any] = {"role": "admin", "is_active": 1}
            default_password = _admin_default_password()
            if not admin["password_hash"] and default_password:
                updates["password_hash"] = hash_password(default_password)
                updates["password_updated_at"] = now
            if not admin["user_id"]:
                updates["user_id"] = str(uuid4())
            set_sql = ", ".join([f"{key}=?" for key in updates] + ["updated_at=?"])
            conn.execute(f"UPDATE users SET {set_sql} WHERE username=?", [*updates.values(), now, ADMIN_USERNAME])


def get_user(username: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_auth_db(db_path)
    with connect_auth_db(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return _row_to_public_user(row)


def register_user(username: str, password: str, display_name: str = "", db_path: str | Path | None = None) -> dict[str, Any]:
    init_auth_db(db_path)
    clean = _validate_username(username)
    now = now_text()
    with connect_auth_db(db_path) as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (clean,)).fetchone():
            raise ValueError("用户名已存在")
        conn.execute(
            """
            INSERT INTO users(user_id, username, password_hash, display_name, role, is_active, created_at, updated_at, password_updated_at)
            VALUES(?, ?, ?, ?, 'user', 1, ?, ?, ?)
            """,
            (str(uuid4()), clean, hash_password(password), str(display_name or clean).strip() or clean, now, now, now),
        )
    user = get_user(clean, db_path=db_path)
    assert user is not None
    return user


def authenticate_user(username: str, password: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_auth_db(db_path)
    clean = str(username or "").strip()
    with connect_auth_db(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (clean,)).fetchone()
        if row is None or not bool(row["is_active"]) or not verify_password(password, row["password_hash"]):
            return None
        now = now_text()
        conn.execute("UPDATE users SET last_login_at=?, updated_at=? WHERE username=?", (now, now, clean))
        row = conn.execute("SELECT * FROM users WHERE username=?", (clean,)).fetchone()
        return _row_to_public_user(row)


def create_session(username: str, user_agent: str = "", db_path: str | Path | None = None) -> str:
    init_auth_db(db_path)
    session_id = secrets.token_urlsafe(32)
    now_dt = datetime.now()
    expires_at = now_dt + timedelta(days=SESSION_DAYS)
    with connect_auth_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions(session_id, username, created_at, expires_at, last_seen_at, user_agent, is_revoked)
            VALUES(?, ?, ?, ?, ?, ?, 0)
            """,
            (
                session_id,
                username,
                now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                str(user_agent or "")[:300],
            ),
        )
    return session_id


def get_user_by_session(session_id: str | None, db_path: str | Path | None = None) -> dict[str, Any] | None:
    if not session_id:
        return None
    init_auth_db(db_path)
    now = now_text()
    with connect_auth_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT u.* FROM auth_sessions s
            JOIN users u ON u.username=s.username
            WHERE s.session_id=? AND s.is_revoked=0 AND s.expires_at>=? AND u.is_active=1
            """,
            (session_id, now),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE session_id=?", (now, session_id))
        return _row_to_public_user(row)


def revoke_session(session_id: str | None, db_path: str | Path | None = None) -> None:
    if not session_id:
        return
    init_auth_db(db_path)
    with connect_auth_db(db_path) as conn:
        conn.execute("UPDATE auth_sessions SET is_revoked=1, last_seen_at=? WHERE session_id=?", (now_text(), session_id))


def list_users(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_auth_db(db_path)
    with connect_auth_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY role='admin' DESC, created_at DESC, username").fetchall()
        return [item for row in rows if (item := _row_to_public_user(row)) is not None]


def update_user_status(username: str, is_active: bool, db_path: str | Path | None = None) -> dict[str, Any]:
    clean = _validate_username(username)
    if clean == ADMIN_USERNAME and not is_active:
        raise ValueError("不能禁用 admin 用户")
    init_auth_db(db_path)
    with connect_auth_db(db_path) as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (clean,)).fetchone() is None:
            raise FileNotFoundError("用户不存在")
        conn.execute("UPDATE users SET is_active=?, updated_at=? WHERE username=?", (1 if is_active else 0, now_text(), clean))
        if not is_active:
            conn.execute("UPDATE auth_sessions SET is_revoked=1 WHERE username=?", (clean,))
    user = get_user(clean, db_path=db_path)
    assert user is not None
    return user


def reset_user_password(username: str, new_password: str, db_path: str | Path | None = None) -> dict[str, Any]:
    clean = _validate_username(username)
    if clean == ADMIN_USERNAME:
        raise ValueError("admin password must be reset on the server side")
    init_auth_db(db_path)
    now = now_text()
    with connect_auth_db(db_path) as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (clean,)).fetchone() is None:
            raise FileNotFoundError("用户不存在")
        conn.execute(
            "UPDATE users SET password_hash=?, password_updated_at=?, updated_at=? WHERE username=?",
            (hash_password(new_password), now, now, clean),
        )
        conn.execute("UPDATE auth_sessions SET is_revoked=1 WHERE username=?", (clean,))
    user = get_user(clean, db_path=db_path)
    assert user is not None
    return user


async def optional_current_user(t0_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict[str, Any] | None:
    return get_user_by_session(t0_session)


async def require_user(t0_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict[str, Any]:
    user = get_user_by_session(t0_session)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


async def require_admin(current_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="只有 admin 用户可以使用该功能")
    return current_user


def redirect_to_login_response() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)
