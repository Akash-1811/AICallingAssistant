"""Email/password signup, login, and JWT session checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.websockets import WebSocket

from app.call_store import Base, get_db
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=120)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def user_to_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_token(creds.credentials)
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    async with get_db() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def websocket_jwt_ok(websocket: WebSocket) -> bool:
    token = websocket.query_params.get("token")
    if not token:
        return False
    return decode_token(token) is not None


@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignupBody) -> AuthResponse:
    email = body.email.strip().lower()
    async with get_db() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(body.password),
            display_name=body.display_name.strip() if body.display_name else None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_token(user.id)
    return AuthResponse(access_token=token, user=user_to_out(user))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginBody) -> AuthResponse:
    email = body.email.strip().lower()
    async with get_db() as session:
        user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id)
    return AuthResponse(access_token=token, user=user_to_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_to_out(user)
