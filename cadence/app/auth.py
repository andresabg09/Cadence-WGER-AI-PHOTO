"""Who is calling: session cookie -> user, plus the small guards around login."""

import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, Response

from . import security, store

COOKIE = "cadence_session"


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def set_session(response: Response, request: Request, user_id: int) -> None:
    token = security.new_token()
    store.create_session(user_id, security.token_hash(token))
    response.set_cookie(
        COOKIE, token, max_age=store.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=_secure(request), path="/",
    )


def clear_session(response: Response, request: Request) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        store.delete_session(security.token_hash(token))
    response.delete_cookie(COOKIE, path="/")


def current_user(request: Request) -> store.User:
    token = request.cookies.get(COOKIE)
    user = store.user_for_session(security.token_hash(token)) if token else None
    if user is None:
        raise HTTPException(401, "Inicia sesión para continuar")
    return user


def require_admin(user: store.User = Depends(current_user)) -> store.User:
    if not user.is_admin:
        raise HTTPException(403, "Solo el administrador puede hacer esto")
    return user


class Throttle:
    """Failed attempts per key inside a sliding window (in memory: good enough for one process)."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window_s
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        return self._hits[key]

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.limit

    def fail(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")
