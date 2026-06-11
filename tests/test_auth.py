from __future__ import annotations

import html
import sqlite3
from pathlib import Path


ADMIN_TEST_PASSWORD = "AdminPass123"


def test_init_auth_db_requires_env_password_for_admin_login(tmp_path: Path, monkeypatch) -> None:
    from overnight_bt import auth

    monkeypatch.delenv("T0_ADMIN_DEFAULT_PASSWORD", raising=False)
    db_path = tmp_path / "auth.sqlite"
    auth.init_auth_db(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        admin = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    assert admin is not None
    assert admin["user_id"]
    assert admin["role"] == "admin"
    assert admin["is_active"] == 1
    assert admin["password_hash"] == ""
    assert auth.authenticate_user("admin", ADMIN_TEST_PASSWORD, db_path=db_path) is None


def test_init_auth_db_bootstraps_admin_from_env_and_preserves_existing_hash(tmp_path: Path, monkeypatch) -> None:
    from overnight_bt import auth

    monkeypatch.setenv("T0_ADMIN_DEFAULT_PASSWORD", ADMIN_TEST_PASSWORD)
    db_path = tmp_path / "auth.sqlite"
    auth.init_auth_db(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        admin = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    assert admin is not None
    assert admin["user_id"]
    assert admin["role"] == "admin"
    assert admin["is_active"] == 1
    assert admin["password_hash"]
    assert auth.verify_password(ADMIN_TEST_PASSWORD, admin["password_hash"])

    original_hash = admin["password_hash"]
    monkeypatch.setenv("T0_ADMIN_DEFAULT_PASSWORD", "AnotherPass123")
    auth.init_auth_db(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        second_hash = conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
    assert second_hash == original_hash


def test_register_login_session_and_logout_flow(tmp_path: Path) -> None:
    from overnight_bt import auth

    db_path = tmp_path / "auth.sqlite"
    auth.init_auth_db(db_path=db_path)

    created = auth.register_user("alice", "StrongPass123", display_name="Alice", db_path=db_path)
    assert created["username"] == "alice"
    assert created["role"] == "user"
    assert created["is_active"] is True
    assert "password_hash" not in created

    assert auth.authenticate_user("alice", "wrong", db_path=db_path) is None
    logged_in = auth.authenticate_user("alice", "StrongPass123", db_path=db_path)
    assert logged_in is not None
    assert logged_in["username"] == "alice"

    session_id = auth.create_session("alice", user_agent="pytest", db_path=db_path)
    session_user = auth.get_user_by_session(session_id, db_path=db_path)
    assert session_user is not None
    assert session_user["username"] == "alice"

    auth.revoke_session(session_id, db_path=db_path)
    assert auth.get_user_by_session(session_id, db_path=db_path) is None


def test_admin_can_manage_users_and_disabled_user_cannot_login(tmp_path: Path) -> None:
    from overnight_bt import auth

    db_path = tmp_path / "auth.sqlite"
    auth.init_auth_db(db_path=db_path)
    auth.register_user("bob", "StrongPass123", db_path=db_path)

    users = auth.list_users(db_path=db_path)
    assert {item["username"] for item in users} >= {"admin", "bob"}

    updated = auth.update_user_status("bob", is_active=False, db_path=db_path)
    assert updated["is_active"] is False
    assert auth.authenticate_user("bob", "StrongPass123", db_path=db_path) is None

    auth.reset_user_password("bob", "NewStrong123", db_path=db_path)
    auth.update_user_status("bob", is_active=True, db_path=db_path)
    assert auth.authenticate_user("bob", "NewStrong123", db_path=db_path) is not None


def test_admin_password_is_not_reset_through_user_management(tmp_path: Path, monkeypatch) -> None:
    from overnight_bt import auth

    monkeypatch.setenv("T0_ADMIN_DEFAULT_PASSWORD", ADMIN_TEST_PASSWORD)
    db_path = tmp_path / "auth.sqlite"
    auth.init_auth_db(db_path=db_path)

    try:
        auth.reset_user_password("admin", "NewStrong123", db_path=db_path)
    except ValueError as exc:
        assert "admin" in str(exc)
    else:
        raise AssertionError("admin password should not be reset through user management")

    assert auth.authenticate_user("admin", ADMIN_TEST_PASSWORD, db_path=db_path) is not None


def test_auth_models_import_and_validate() -> None:
    from overnight_bt.models import AuthLoginRequest, AuthRegisterRequest, UserPasswordResetRequest, UserStatusUpdateRequest

    assert AuthLoginRequest(username="admin", password=ADMIN_TEST_PASSWORD).username == "admin"
    assert AuthRegisterRequest(username="new_user", password="StrongPass123").display_name == ""
    assert UserStatusUpdateRequest(is_active=False).is_active is False
    assert UserPasswordResetRequest(new_password="NewStrong123").new_password == "NewStrong123"


def test_web_auth_flow_and_route_protection(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from overnight_bt import app as app_module

    db_path = tmp_path / "auth.sqlite"
    monkeypatch.setenv("T0_ADMIN_DEFAULT_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setattr(app_module.auth, "DEFAULT_AUTH_DB_PATH", db_path)
    app_module.auth.init_auth_db(db_path=db_path)

    client = TestClient(app_module.app)

    unauth = client.get("/", follow_redirects=False)
    assert unauth.status_code == 303
    assert unauth.headers["location"] == "/login"

    register = client.post("/api/auth/register", json={"username": "alice", "password": "StrongPass123", "display_name": "Alice"})
    assert register.status_code == 200
    assert register.json()["user"]["username"] == "alice"
    assert register.cookies.get(app_module.auth.SESSION_COOKIE_NAME)

    assert client.get("/").status_code == 200
    assert client.get("/admin").status_code == 403

    client.post("/api/auth/logout")
    login = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_TEST_PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["is_admin"] is True
    assert client.get("/admin").status_code == 200
    assert client.get("/users").status_code == 200


def test_user_management_api_requires_admin(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from overnight_bt import app as app_module

    db_path = tmp_path / "auth.sqlite"
    monkeypatch.setenv("T0_ADMIN_DEFAULT_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setattr(app_module.auth, "DEFAULT_AUTH_DB_PATH", db_path)
    app_module.auth.init_auth_db(db_path=db_path)
    client = TestClient(app_module.app)

    register = client.post("/api/auth/register", json={"username": "alice", "password": "StrongPass123"})
    assert register.status_code == 200

    response = client.get("/api/users")
    assert response.status_code == 403

    reset_admin = client.post("/api/users/admin/password", json={"new_password": "NewStrong123"})
    assert reset_admin.status_code == 403
    assert app_module.auth.authenticate_user("admin", ADMIN_TEST_PASSWORD, db_path=db_path) is not None


def test_static_html_pages_cannot_bypass_page_auth(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from overnight_bt import app as app_module

    db_path = tmp_path / "auth.sqlite"
    monkeypatch.setattr(app_module.auth, "DEFAULT_AUTH_DB_PATH", db_path)
    app_module.auth.init_auth_db(db_path=db_path)
    client = TestClient(app_module.app)

    response = client.get("/static/console/index.html", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    login_page = client.get("/static/login.html")
    assert login_page.status_code == 200

    register = client.post("/api/auth/register", json={"username": "alice", "password": "StrongPass123"})
    assert register.status_code == 200

    console_static = client.get("/static/console/index.html")
    assert console_static.status_code == 200
    assert "/static/console/assets/" in console_static.text

    admin_route = client.get("/system/admin")
    assert admin_route.status_code == 403

    for old_page in [
        "/static/index.html",
        "/static/single.html",
        "/static/daily.html",
        "/static/paper.html",
        "/static/paper_templates.html",
        "/static/stock_pools.html",
        "/static/admin.html",
        "/static/users.html",
        "/static/sector.html",
    ]:
        assert client.get(old_page).status_code == 404


def test_api_requires_login(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from overnight_bt import app as app_module

    db_path = tmp_path / "auth.sqlite"
    monkeypatch.setattr(app_module.auth, "DEFAULT_AUTH_DB_PATH", db_path)
    app_module.auth.init_auth_db(db_path=db_path)
    client = TestClient(app_module.app)

    response = client.get("/api/stock-pools/templates")
    assert response.status_code == 401
    assert response.json()["detail"] == "\u8bf7\u5148\u767b\u5f55"


def test_auth_static_pages_have_expected_scripts() -> None:
    root = Path(__file__).resolve().parents[1]
    login_html = (root / "static" / "login.html").read_text(encoding="utf-8")
    register_html = (root / "static" / "register.html").read_text(encoding="utf-8")
    decoded_login_html = html.unescape(login_html)
    decoded_register_html = html.unescape(register_html)
    assert "/api/auth/login" in login_html
    assert "\u80a1\u6d4b\u901a" in decoded_login_html
    assert "\u6b22\u8fce\u56de\u6765" in decoded_login_html
    assert "\u8fdb\u5165 T_0 \u56de\u6d4b\u7cfb\u7edf" not in decoded_login_html
    assert "/api/auth/register" in register_html
    assert "\u521b\u5efa\u8d26\u6237" in decoded_register_html
    assert "\u663e\u793a\u540d\u79f0" not in decoded_register_html
    assert "registerDisplayName" not in register_html
    console_html = (root / "static" / "console" / "index.html").read_text(encoding="utf-8")
    assert "/static/console/assets/" in console_html
    assert "T_0 \u91cf\u5316\u63a7\u5236\u53f0" in console_html


def test_auth_card_css_uses_compact_centered_layout() -> None:
    root = Path(__file__).resolve().parents[1]
    style_css = (root / "static" / "style.css").read_text(encoding="utf-8")
    assert "body.auth-page" in style_css
    assert ".stock-auth-shell" in style_css
    assert ".stock-auth-card" in style_css
    assert "width: min(100%, 448px);" in style_css
    assert "margin: 0 auto;" in style_css
    assert "background: var(--auth-blue);" in style_css
    assert ".controls" not in style_css
    assert ".panel" not in style_css
    assert ".table-wrap" not in style_css


def test_old_business_static_pages_have_been_removed() -> None:
    root = Path(__file__).resolve().parents[1]
    old_files = [
        "index.html",
        "daily.html",
        "single.html",
        "paper.html",
        "paper_templates.html",
        "stock_pools.html",
        "admin.html",
        "sector.html",
        "users.html",
        "app.js",
        "daily.js",
        "single.js",
        "paper.js",
        "paper_templates.js",
        "stock_pools.js",
        "admin.js",
        "sector.js",
        "users.js",
        "auth.js",
    ]
    for file_name in old_files:
        assert not (root / "static" / file_name).exists(), file_name
