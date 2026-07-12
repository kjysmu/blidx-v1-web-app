import json
import math
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import (
    hash_password,
    verify_and_update_password,
    verify_password,
)
from app.models.user import User


DUMMY_PASSWORD_HASH = hash_password("blidx-invalid-login-placeholder")


@dataclass(frozen=True)
class AuthenticationResult:
    status: Literal["ok", "invalid", "locked"]
    user: dict | None = None
    retry_after_seconds: int | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthStore:
    def __init__(self) -> None:
        self.path = Path(__file__).resolve().parent.parent / "data" / "auth_users.json"
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"users": []})

    def _read(self) -> dict:
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def register(self, email: str, password: str, user_name: str | None = None) -> dict:
        normalized_email = email.strip().lower()
        if self._database_enabled():
            return self._register_db(normalized_email, password, user_name)

        with self.lock:
            data = self._read()
            if self._find_by_email(data, normalized_email):
                raise ValueError("Email is already registered")
            user = {
                "id": str(uuid.uuid4()),
                "email": normalized_email,
                "user_name": user_name.strip() if user_name else normalized_email.split("@")[0],
                "password_hash": hash_password(password),
                "session_version": 1,
                "failed_login_attempts": 0,
                "locked_until": None,
                "password_changed_at": None,
                "last_login_at": None,
                "created_at": utc_now().isoformat(),
            }
            data["users"].append(user)
            self._write(data)
            return self._public_user(user)

    def authenticate(self, email: str, password: str) -> AuthenticationResult:
        normalized_email = email.strip().lower()
        if self._database_enabled():
            return self._authenticate_db(normalized_email, password)

        with self.lock:
            data = self._read()
            user = self._find_by_email(data, normalized_email)
            if not user:
                verify_password(password, DUMMY_PASSWORD_HASH)
                return AuthenticationResult(status="invalid")

            now = utc_now()
            retry_after = self._retry_after(user.get("locked_until"), now)
            if retry_after:
                return AuthenticationResult(
                    status="locked", retry_after_seconds=retry_after
                )
            if user.get("locked_until"):
                user["locked_until"] = None
                user["failed_login_attempts"] = 0

            password_valid, replacement_hash = verify_and_update_password(
                password, user["password_hash"]
            )
            if not password_valid:
                attempts = int(user.get("failed_login_attempts", 0)) + 1
                user["failed_login_attempts"] = attempts
                if attempts >= settings.AUTH_MAX_FAILED_ATTEMPTS:
                    locked_until = now + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)
                    user["locked_until"] = locked_until.isoformat()
                    result = AuthenticationResult(
                        status="locked",
                        retry_after_seconds=settings.AUTH_LOCKOUT_MINUTES * 60,
                    )
                else:
                    result = AuthenticationResult(status="invalid")
                self._write(data)
                return result

            user["failed_login_attempts"] = 0
            user["locked_until"] = None
            user["last_login_at"] = now.isoformat()
            if replacement_hash:
                user["password_hash"] = replacement_hash
            self._write(data)
            return AuthenticationResult(status="ok", user=self._public_user(user))

    def get_user(self, user_id: str) -> dict | None:
        if self._database_enabled():
            return self._get_user_db(user_id)

        with self.lock:
            user = self._find_by_id(self._read(), user_id)
            return self._public_user(user) if user else None

    def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> dict:
        if current_password == new_password:
            raise ValueError("New password must be different from the current password")
        if self._database_enabled():
            return self._change_password_db(user_id, current_password, new_password)

        with self.lock:
            data = self._read()
            user = self._find_by_id(data, user_id)
            if not user or not verify_password(current_password, user["password_hash"]):
                raise ValueError("Current password is incorrect")
            user["password_hash"] = hash_password(new_password)
            user["session_version"] = int(user.get("session_version", 1)) + 1
            user["password_changed_at"] = utc_now().isoformat()
            user["failed_login_attempts"] = 0
            user["locked_until"] = None
            self._write(data)
            return self._public_user(user)

    def revoke_all_sessions(self, user_id: str, current_password: str) -> dict:
        if self._database_enabled():
            return self._revoke_all_sessions_db(user_id, current_password)

        with self.lock:
            data = self._read()
            user = self._find_by_id(data, user_id)
            if not user or not verify_password(current_password, user["password_hash"]):
                raise ValueError("Current password is incorrect")
            user["session_version"] = int(user.get("session_version", 1)) + 1
            self._write(data)
            return self._public_user(user)

    @staticmethod
    def _database_enabled() -> bool:
        return bool(settings.USE_DATABASE_STORAGE)

    def _register_db(
        self, email: str, password: str, user_name: str | None = None
    ) -> dict:
        with SessionLocal() as db:
            user = User(
                email=email,
                user_name=user_name.strip() if user_name else email.split("@")[0],
                password_hash=hash_password(password),
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ValueError("Email is already registered") from exc
            db.refresh(user)
            return self._public_user_db(user)

    @staticmethod
    def _authenticate_db(email: str, password: str) -> AuthenticationResult:
        with SessionLocal() as db:
            user = (
                db.query(User).filter(User.email == email).with_for_update().first()
            )
            if not user:
                verify_password(password, DUMMY_PASSWORD_HASH)
                return AuthenticationResult(status="invalid")

            now = utc_now()
            retry_after = AuthStore._retry_after(user.locked_until, now)
            if retry_after:
                return AuthenticationResult(
                    status="locked", retry_after_seconds=retry_after
                )
            if user.locked_until:
                user.locked_until = None
                user.failed_login_attempts = 0

            password_valid, replacement_hash = verify_and_update_password(
                password, user.password_hash
            )
            if not password_valid:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= settings.AUTH_MAX_FAILED_ATTEMPTS:
                    user.locked_until = now + timedelta(
                        minutes=settings.AUTH_LOCKOUT_MINUTES
                    )
                    result = AuthenticationResult(
                        status="locked",
                        retry_after_seconds=settings.AUTH_LOCKOUT_MINUTES * 60,
                    )
                else:
                    result = AuthenticationResult(status="invalid")
                db.commit()
                return result

            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = now
            if replacement_hash:
                user.password_hash = replacement_hash
            db.commit()
            db.refresh(user)
            return AuthenticationResult(
                status="ok", user=AuthStore._public_user_db(user)
            )

    @staticmethod
    def _change_password_db(
        user_id: str, current_password: str, new_password: str
    ) -> dict:
        parsed_user_id = AuthStore._parse_user_id(user_id)
        with SessionLocal() as db:
            user = (
                db.query(User)
                .filter(User.id == parsed_user_id)
                .with_for_update()
                .first()
            )
            if not user:
                raise ValueError("User not found")
            if not verify_password(current_password, user.password_hash):
                raise ValueError("Current password is incorrect")
            user.password_hash = hash_password(new_password)
            user.session_version = (user.session_version or 1) + 1
            user.password_changed_at = utc_now()
            user.failed_login_attempts = 0
            user.locked_until = None
            db.commit()
            db.refresh(user)
            return AuthStore._public_user_db(user)

    @staticmethod
    def _revoke_all_sessions_db(user_id: str, current_password: str) -> dict:
        parsed_user_id = AuthStore._parse_user_id(user_id)
        with SessionLocal() as db:
            user = (
                db.query(User)
                .filter(User.id == parsed_user_id)
                .with_for_update()
                .first()
            )
            if not user:
                raise ValueError("User not found")
            if not verify_password(current_password, user.password_hash):
                raise ValueError("Current password is incorrect")
            user.session_version = (user.session_version or 1) + 1
            db.commit()
            db.refresh(user)
            return AuthStore._public_user_db(user)

    @staticmethod
    def _parse_user_id(user_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(user_id)
        except ValueError as exc:
            raise ValueError("User not found") from exc

    @staticmethod
    def _get_user_db(user_id: str) -> dict | None:
        try:
            parsed_user_id = uuid.UUID(user_id)
        except ValueError:
            return None

        with SessionLocal() as db:
            user = db.get(User, parsed_user_id)
            return AuthStore._public_user_db(user) if user else None

    @staticmethod
    def _find_by_email(data: dict, email: str) -> dict | None:
        return next((user for user in data.get("users", []) if user["email"] == email), None)

    @staticmethod
    def _find_by_id(data: dict, user_id: str) -> dict | None:
        return next((user for user in data.get("users", []) if user["id"] == user_id), None)

    @staticmethod
    def _public_user(user: dict) -> dict:
        public = deepcopy(user)
        public.pop("password_hash", None)
        public.setdefault("session_version", 1)
        public.pop("failed_login_attempts", None)
        public.pop("locked_until", None)
        return public

    @staticmethod
    def _public_user_db(user: User) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "user_name": user.user_name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "session_version": user.session_version or 1,
            "password_changed_at": (
                user.password_changed_at.isoformat() if user.password_changed_at else None
            ),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    @staticmethod
    def _retry_after(value: str | datetime | None, now: datetime) -> int:
        if not value:
            return 0
        try:
            locked_until = (
                datetime.fromisoformat(value) if isinstance(value, str) else value
            )
        except ValueError:
            return 0
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return max(0, math.ceil((locked_until - now).total_seconds()))


auth_store = AuthStore()
