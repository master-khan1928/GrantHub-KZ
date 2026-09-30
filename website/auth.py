"""
Авторизация сайта: регистрация и вход по почте и паролю.

- Сессия — подписанная cookie gh_session (HMAC, без внешних библиотек), живёт 30 дней.
- Пароли — PBKDF2-SHA256 (стандартная библиотека).
"""
import base64
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.database import (
    create_account, get_account_by_email, get_account_by_id, merge_anonymous_user, touch_account_login,
)

router = APIRouter()

SESSION_COOKIE = "gh_session"
SESSION_TTL = 30 * 24 * 3600
UID_COOKIE = "gh_uid"
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
if not SESSION_SECRET:
    # без секрета сессии не переживут перезапуск — предупреждаем, но не падаем
    SESSION_SECRET = secrets.token_urlsafe(32)
    _SECRET_IS_TEMP = True
else:
    _SECRET_IS_TEMP = False

PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("SITE_URL") or "").strip().rstrip("/")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Сессии и пароли
# ---------------------------------------------------------------------------
def _sign(data: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def make_session(account_id: int, uid: int) -> str:
    exp = int(time.time()) + SESSION_TTL
    data = f"{account_id}.{uid}.{exp}"
    return f"{data}.{_sign(data)}"


def read_session(token: str) -> Optional[tuple]:
    """-> (account_id, uid) или None."""
    if not token or token.count(".") != 3:
        return None
    account_id, uid, exp, sig = token.split(".")
    data = f"{account_id}.{uid}.{exp}"
    if not hmac.compare_digest(_sign(data), sig):
        return None
    if int(exp) < time.time():
        return None
    return int(account_id), int(uid)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt, digest = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000), digest)


COOKIE_SECURE = PUBLIC_URL.startswith("https")


def _new_uid() -> int:
    return random.randint(10**12, 10**13 - 1)


def make_uid_cookie(uid: int) -> str:
    """Подписанная cookie посетителя: подменить чужой id без секрета нельзя."""
    return f"{uid}.{_sign('uid:' + str(uid))[:32]}"


def read_uid_cookie(raw: str) -> Optional[int]:
    if not raw or "." not in raw:
        return None
    uid, sig = raw.split(".", 1)
    if not uid.isdigit() or not (10**12 <= int(uid) < 10**13):
        return None
    if not hmac.compare_digest(_sign("uid:" + uid)[:32], sig):
        return None
    return int(uid)


def set_uid_cookie(response: Response, uid: int, max_age: int = SESSION_TTL):
    response.set_cookie(UID_COOKIE, make_uid_cookie(uid), max_age=max_age, httponly=True, samesite="lax", secure=COOKIE_SECURE)


def client_ip(request: Request) -> str:
    """Реальный IP за прокси хостинга (X-Forwarded-For), иначе адрес соединения."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


class RateLimit:
    """Простой лимит «N событий за окно» по ключу (IP / uid). Память процесса, без внешних сервисов."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window, self._hits = limit, window, {}

    def blocked(self, key: str) -> bool:
        """Лимит уже исчерпан? Сам счётчик не трогает."""
        now = time.time()
        return sum(1 for t in self._hits.get(key, []) if now - t < self.window) >= self.limit

    def hit(self, key: str) -> bool:
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        if len(self._hits) > 5000:  # не даём словарю расти бесконечно
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(k, None)
        return True


register_limit = RateLimit(5, 3600)      # регистраций с одного IP в час
login_limit = RateLimit(20, 600)         # попыток входа с одного IP за 10 минут


def _anon_uid(request: Request) -> Optional[int]:
    return read_uid_cookie(request.cookies.get(UID_COOKIE, ""))


def _set_login_cookies(response: Response, account: dict):
    response.set_cookie(SESSION_COOKIE, make_session(account["id"], account["uid"]), max_age=SESSION_TTL,
                        httponly=True, samesite="lax", secure=COOKIE_SECURE)
    set_uid_cookie(response, account["uid"])


def _public(account: dict) -> dict:
    return {"id": account["id"], "email": account.get("email"), "name": account.get("name") or (account.get("email") or "").split("@")[0],
            "avatar": account.get("avatar"), "provider": account["provider"]}


async def account_from_request(request: Request) -> Optional[dict]:
    sess = read_session(request.cookies.get(SESSION_COOKIE, ""))
    if not sess:
        return None
    account = await get_account_by_id(sess[0])
    if not account or account["uid"] != sess[1]:
        return None
    return account



# ---------------------------------------------------------------------------
# API: состояние, регистрация, вход, выход
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    name: Optional[str] = Field(default=None, max_length=60)


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=1, max_length=128)


@router.get("/api/auth/providers")
async def auth_providers():
    return {"email": True, "secret_is_temporary": _SECRET_IS_TEMP}


@router.get("/api/auth/me")
async def auth_me(request: Request):
    account = await account_from_request(request)
    return {"user": _public(account) if account else None}


@router.post("/api/auth/register")
async def auth_register(data: RegisterIn, request: Request, response: Response):
    email = data.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Похоже, это не адрес почты")
    if not register_limit.hit(client_ip(request)):
        raise HTTPException(429, "Слишком много регистраций с этого адреса. Попробуйте позже.")
    if await get_account_by_email(email):
        raise HTTPException(409, "Аккаунт с этой почтой уже есть — войдите")
    anon = _anon_uid(request)
    account = await create_account(anon or _new_uid(), "email", email=email,
                                   name=(data.name or "").strip() or email.split("@")[0],
                                   password_hash=hash_password(data.password))
    _set_login_cookies(response, account)
    return {"user": _public(account)}


@router.post("/api/auth/login")
async def auth_login(data: LoginIn, request: Request, response: Response):
    ip = client_ip(request)
    if not login_limit.hit(ip):
        raise HTTPException(429, "Слишком много попыток. Подождите 10 минут.")
    account = await get_account_by_email(data.email.strip().lower())
    if not account or not verify_password(data.password, account.get("password_hash") or ""):
        raise HTTPException(401, "Неверная почта или пароль")
    await merge_anonymous_user(_anon_uid(request), account["uid"])
    await touch_account_login(account["id"])
    _set_login_cookies(response, account)
    return {"user": _public(account)}


@router.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(UID_COOKIE)
    return {"ok": True}
