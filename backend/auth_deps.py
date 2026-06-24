# auth_deps.py
# ─────────────────────────────────────────────
# FastAPI dependency that verifies a Supabase JWT
# on incoming requests and extracts the user.
#
# Used like this on any protected route:
#
#   @router.get("/something")
#   async def my_route(user: AuthUser = Depends(get_current_user)):
#       user.id        ← the authenticated user's UUID
#       user.email     ← their email
#
# This file does NOT do the actual login/signup —
# that lives in routers/auth.py. This file only
# verifies a token that was already issued.
# ─────────────────────────────────────────────

from fastapi import Header, HTTPException
from supabase import create_client
from pydantic import BaseModel
from config import settings
import logging

logger = logging.getLogger(__name__)

# A separate client using the anon key — this is the client
# that actually respects RLS policies. The main `supabase`
# client in database.py uses service_role and deliberately
# bypasses RLS, which is correct for system/background work
# but wrong for anything done on behalf of a specific user.
auth_client = create_client(settings.supabase_url, settings.supabase_key)


class AuthUser(BaseModel):
    """Minimal user info extracted from a verified token"""
    id: str
    email: str | None = None
    access_token: str  # kept so routes can build a per-request,
                        # RLS-respecting Supabase client if needed


async def get_current_user(
    authorization: str = Header(..., description="Bearer <access_token>")
) -> AuthUser:
    """
    Verify the Authorization header and return the authenticated user.

    Raises 401 if the header is missing, malformed, or the
    token is invalid/expired — FastAPI's Depends() means this
    check runs BEFORE the route function body executes at all.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be 'Bearer <token>'"
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        # Ask Supabase Auth to verify this token is real and
        # not expired, and tell us who it belongs to.
        response = auth_client.auth.get_user(token)
        user = response.user

        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return AuthUser(
            id=user.id,
            email=user.email,
            access_token=token
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_user_scoped_client(user: AuthUser):
    """
    Build a Supabase client that uses the anon key AND carries
    the user's own JWT on every request it makes.

    This is what actually makes RLS policies kick in — without
    attaching the user's token, Supabase has no way to evaluate
    auth.uid() inside a policy, since auth.uid() is derived from
    the JWT on the request, not from anything we pass manually.
    """
    client = create_client(settings.supabase_url, settings.supabase_key)
    client.postgrest.auth(user.access_token)
    return client