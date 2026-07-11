from datetime import datetime, timedelta, timezone
from jose import JWTError
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


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
