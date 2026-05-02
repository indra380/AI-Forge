import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_or_create_google_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _set_auth_cookie(response: Response, user_id: str) -> None:
    token = create_access_token(user_id)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT != "development",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await register_user(db, payload.email, payload.password)
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await authenticate_user(db, payload.email, payload.password)
    _set_auth_cookie(response, str(user.id))
    return UserResponse(id=user.id, email=user.email)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("access_token", path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, google_id=user.google_id)


@router.get("/google")
async def google_login() -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail={"error": "not_configured", "message": "Google OAuth not configured"},
        )
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail={"error": "not_configured", "message": "Google OAuth not configured"},
        )

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

        userinfo_response = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    email: str = userinfo.get("email", "")
    google_id: str = userinfo.get("sub", "")

    try:
        user = await get_or_create_google_user(db, email, google_id)
    except HTTPException as exc:
        # Non-amzur.com email — redirect to frontend with error
        error_msg = urllib.parse.quote(exc.detail["message"])
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/?auth_error={error_msg}")

    redirect = RedirectResponse(url=settings.FRONTEND_URL)
    _set_auth_cookie(redirect, str(user.id))
    return redirect
