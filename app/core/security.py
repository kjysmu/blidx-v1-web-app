from datetime import datetime, timedelta, timezone
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from passlib.context import CryptContext
from app.core.config import settings


PASSWORD_HASH_ROUNDS = 600_000
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__rounds=PASSWORD_HASH_ROUNDS,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def verify_and_update_password(
    plain_password: str, password_hash: str
) -> tuple[bool, str | None]:
    return pwd_context.verify_and_update(plain_password, password_hash)


class AccessTokenError(ValueError):
    code = "invalid_session"


class AccessTokenExpiredError(AccessTokenError):
    code = "session_expired"


def create_access_token(subject: str, session_version: int = 1) -> str:
    issued_at = datetime.now(timezone.utc)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "ver": session_version,
        "purpose": "access",
        "iat": issued_at,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, str | int]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError as exc:
        raise AccessTokenExpiredError("Session expired") from exc
    except JWTError as exc:
        raise AccessTokenError("Invalid session") from exc

    if payload.get("purpose") not in {None, "access"}:
        raise AccessTokenError("Invalid token purpose")
    subject = payload.get("sub")
    version = payload.get("ver", 1)
    if (
        not isinstance(subject, str)
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise AccessTokenError("Invalid session claims")
    return {"user_id": subject, "session_version": version}


def create_linkedin_oauth_state(subject: str, nonce: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.LINKEDIN_OAUTH_STATE_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "nonce": nonce,
        "purpose": "linkedin_oauth",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_linkedin_oauth_state(token: str) -> dict[str, str] | None:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None
    if payload.get("purpose") != "linkedin_oauth":
        return None
    subject = payload.get("sub")
    nonce = payload.get("nonce")
    if not isinstance(subject, str) or not isinstance(nonce, str):
        return None
    return {"user_id": subject, "nonce": nonce}
