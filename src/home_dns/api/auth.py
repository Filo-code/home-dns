"""Login, logout, session introspection and the session/CSRF/role dependencies.

See docs/specs/a7-backend.md §7.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from home_dns.api.context import DashboardContext
from home_dns.core.auth import Role, new_token, token_digest, tokens_match, verify_password
from home_dns.storage.dashboard import SessionRecord

SESSION_COOKIE = "hd_session"
CSRF_HEADER = "X-CSRF-Token"
_TOUCH_EVERY = timedelta(minutes=5)  # bounds session writes to one per 5 minutes per session
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_context(request: Request) -> DashboardContext:
    context: DashboardContext = request.app.state.dashboard
    return context


Context = Annotated[DashboardContext, Depends(get_context)]


def _unauthenticated() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")


def current_session(request: Request, context: Context) -> SessionRecord:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated()
    session = context.store.get_session(token_digest(token))
    if session is None:
        raise _unauthenticated()
    now = context.now()
    if (
        now - session.last_seen_at >= context.session_idle
        or now - session.created_at >= context.session_absolute
    ):
        context.store.delete_session(session.token_digest)
        raise _unauthenticated()
    if request.method in _UNSAFE_METHODS and not tokens_match(
        request.headers.get(CSRF_HEADER, ""), session.csrf_token
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    if now - session.last_seen_at >= _TOUCH_EVERY:
        context.store.touch_session(session.token_digest, now=now)
    return session


Session = Annotated[SessionRecord, Depends(current_session)]


def require_admin(session: Session) -> SessionRecord:
    if session.role is not Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return session


AdminSession = Annotated[SessionRecord, Depends(require_admin)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class SessionView(BaseModel):
    username: str
    role: Role
    csrf_token: str


@router.post("/login", response_model=SessionView)
def login(
    body: LoginRequest, request: Request, response: Response, context: Context
) -> SessionView:
    now = context.now()
    keys = (f"ip:{request.client.host if request.client else 'unknown'}", f"user:{body.username}")
    if any(context.limiter.is_locked(key, now) for key in keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed logins")
    user = context.store.get_user(body.username)
    valid = verify_password(body.password, user.password_hash if user else context.dummy_hash)
    if user is None or not valid:
        for key in keys:
            context.limiter.record_failure(key, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    for key in keys:
        context.limiter.reset(key)
    context.store.delete_expired_sessions(
        idle_before=now - context.session_idle, created_before=now - context.session_absolute
    )
    token, csrf = new_token(), new_token()
    context.store.create_session(token_digest(token), user.username, csrf, now=now)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(context.session_absolute.total_seconds()),
        path="/api",
        secure=context.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return SessionView(username=user.username, role=user.role, csrf_token=csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: Session, response: Response, context: Context) -> None:
    context.store.delete_session(session.token_digest)
    response.delete_cookie(
        SESSION_COOKIE, path="/api", secure=context.cookie_secure, httponly=True, samesite="strict"
    )


@router.get("/session", response_model=SessionView)
def session_info(session: Session) -> SessionView:
    return SessionView(username=session.username, role=session.role, csrf_token=session.csrf_token)
