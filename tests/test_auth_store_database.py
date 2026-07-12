import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.auth_store as auth_store_module
from app.auth_store import AuthStore
from app.core.config import settings
from app.models.user import User


PASSWORD = "database-password-123"
NEW_PASSWORD = "database-password-456"


def database_store(tmp_path, monkeypatch) -> tuple[AuthStore, sessionmaker]:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    User.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(auth_store_module, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "USE_DATABASE_STORAGE", True)
    return AuthStore(), session_factory


def test_database_auth_password_rotation_and_session_revocation(tmp_path, monkeypatch):
    store, session_factory = database_store(tmp_path, monkeypatch)
    user = store.register("db-security@example.com", PASSWORD, "DB Tester")

    authenticated = store.authenticate(user["email"], PASSWORD)
    assert authenticated.status == "ok"
    assert authenticated.user["session_version"] == 1

    changed = store.change_password(user["id"], PASSWORD, NEW_PASSWORD)
    assert changed["session_version"] == 2
    assert changed["password_changed_at"] is not None
    assert store.authenticate(user["email"], PASSWORD).status == "invalid"
    assert store.authenticate(user["email"], NEW_PASSWORD).status == "ok"

    revoked = store.revoke_all_sessions(user["id"], NEW_PASSWORD)
    assert revoked["session_version"] == 3

    with session_factory() as db:
        persisted = db.get(User, uuid.UUID(user["id"]))
        assert persisted.session_version == 3
        assert persisted.failed_login_attempts == 0
        assert persisted.last_login_at is not None


def test_database_auth_persists_account_lockout(tmp_path, monkeypatch):
    store, session_factory = database_store(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "AUTH_MAX_FAILED_ATTEMPTS", 2)
    user = store.register("db-lockout@example.com", PASSWORD, "Lockout Tester")

    assert store.authenticate(user["email"], "wrong-password").status == "invalid"
    locked = store.authenticate(user["email"], "wrong-password")
    assert locked.status == "locked"
    assert locked.retry_after_seconds > 0

    with session_factory() as db:
        persisted = db.get(User, uuid.UUID(user["id"]))
        assert persisted.failed_login_attempts == 2
        assert persisted.locked_until is not None
