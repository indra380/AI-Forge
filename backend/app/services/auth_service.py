from datetime import datetime, timedelta, timezone
import uuid

import bcrypt
from fastapi import Cookie, Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User


EMPLOYEE_EMAIL_DOMAIN = "@amzur.com"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_employee_email(email: str) -> str:
    normalized = _normalize_email(email)
    if not normalized.endswith(EMPLOYEE_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Amzur employee email required"},
        )
    return normalized


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == _normalize_email(email))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    normalized_email = _validate_employee_email(email)
    existing_user = await get_user_by_email(db, normalized_email)
    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "conflict", "message": "User already exists"},
        )

    user = User(email=normalized_email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    normalized_email = _validate_employee_email(email)
    user = await get_user_by_email(db, normalized_email)
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials", "message": "Invalid email or password"},
        )
    return user


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Missing auth token"},
        )

    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail={"error": "unauthorized", "message": "Invalid auth token"},
            )
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid auth token"},
        ) from exc

    try:
        parsed_user_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid auth token"},
        ) from exc

    stmt = select(User).where(User.id == parsed_user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "User not found"},
        )
    return user


async def get_or_create_google_user(
    db: AsyncSession, email: str, google_id: str
) -> User:
    normalized_email = _validate_employee_email(email)
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        # Link google_id if not already linked
        if user.google_id is None:
            user.google_id = google_id
            await db.commit()
            await db.refresh(user)
        return user

    # Create new Google-only user (no password)
    user = User(email=normalized_email, google_id=google_id, hashed_password=None)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
