# routers/auth.py
# ─────────────────────────────────────────────
# Signup, login, and logout via Supabase Auth.
#
# This is intentionally thin — Supabase Auth handles
# password hashing, token issuing, and token refresh
# entirely on its own servers. This router is mostly
# just a pass-through with friendlier error messages.
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from auth_deps import get_current_user, AuthUser, auth_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    class Config:
        # Keep validation simple but real — Supabase itself
        # also enforces a minimum, this just fails fast with
        # a clearer message before even hitting the network.
        pass


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
async def signup(data: SignupRequest):
    """
    Create a new account.

    Example:
    POST /api/auth/signup
    {"email": "garima@example.com", "password": "a-strong-password"}
    """
    if len(data.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters"
        )

    try:
        result = auth_client.auth.sign_up({
            "email": data.email,
            "password": data.password,
        })
    except Exception as e:
        logger.warning(f"Signup failed for {data.email}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    if not result.user:
        raise HTTPException(status_code=400, detail="Signup failed")

    # Depending on your Supabase project's email confirmation
    # setting, result.session may be None here (user must
    # confirm their email before they can log in). Handle both.
    return {
        "success": True,
        "user": {"id": result.user.id, "email": result.user.email},
        "session": (
            {"access_token": result.session.access_token}
            if result.session else None
        ),
        "message": (
            "Signed up successfully."
            if result.session else
            "Signed up — check your email to confirm your account before logging in."
        )
    }


@router.post("/login")
async def login(data: LoginRequest):
    """
    Log in with email + password, get back an access token.

    Example:
    POST /api/auth/login
    {"email": "garima@example.com", "password": "a-strong-password"}
    """
    try:
        result = auth_client.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password,
        })
    except Exception as e:
        logger.warning(f"Login failed for {data.email}: {e}")

        # Supabase's own error message distinguishes "wrong password"
        # from "email not confirmed yet" — but only in the raw exception
        # text, not as a separate error code we can branch on cleanly.
        # Checking for this substring is the same approach Supabase's
        # own client libraries use internally, since gotrue doesn't
        # expose a more structured error type here.
        error_text = str(e).lower()
        if "email not confirmed" in error_text or "not confirmed" in error_text:
            raise HTTPException(
                status_code=403,
                detail="Please confirm your email before logging in. Check your inbox for the confirmation link."
            )

        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "success": True,
        "user": {"id": result.user.id, "email": result.user.email},
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
    }


@router.get("/me")
async def get_me(user: AuthUser = Depends(get_current_user)):
    """
    Confirm who the current token belongs to — useful for the
    frontend to check on page load whether a stored token is
    still valid, and for testing auth manually with curl.

    Example:
    GET /api/auth/me
    Authorization: Bearer <token>
    """
    return {
        "success": True,
        "user": {"id": user.id, "email": user.email}
    }