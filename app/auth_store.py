import json
import threading
import uuid
from copy import deepcopy
from datetime import timezone, datetime
from pathlib import Path

from app.core.security import hash_password, verify_password


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
        with self.lock:
            data = self._read()
            if self._find_by_email(data, normalized_email):
                raise ValueError("Email is already registered")
            user = {
                "id": str(uuid.uuid4()),
                "email": normalized_email,
                "user_name": user_name.strip() if user_name else normalized_email.split("@")[0],
                "password_hash": hash_password(password),
                "created_at": utc_now().isoformat(),
            }
            data["users"].append(user)
            self._write(data)
            return self._public_user(user)

    def authenticate(self, email: str, password: str) -> dict | None:
        normalized_email = email.strip().lower()
        with self.lock:
            user = self._find_by_email(self._read(), normalized_email)
            if not user or not verify_password(password, user["password_hash"]):
                return None
            return self._public_user(user)

    def get_user(self, user_id: str) -> dict | None:
        with self.lock:
            user = self._find_by_id(self._read(), user_id)
            return self._public_user(user) if user else None

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
        return public


auth_store = AuthStore()
