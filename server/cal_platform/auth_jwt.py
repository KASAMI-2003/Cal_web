"""JWT 校验（与 Rust 登录签发共用密钥 HS256）。"""

from __future__ import annotations

import os
import time
from typing import Any

try:
    import jwt
except ImportError:
    jwt = None  # type: ignore

DEFAULT_SECRET = os.environ.get('JWT_SECRET', 'calweb-dev-jwt-secret-change-in-production')
DEFAULT_ALG = 'HS256'
TOKEN_TTL_SEC = int(os.environ.get('JWT_TTL_SEC', str(7 * 24 * 3600)))


def issue_token(username: str, secret: str | None = None) -> str:
    if jwt is None:
        raise RuntimeError('PyJWT 未安装，请 pip install PyJWT')
    secret = secret or DEFAULT_SECRET
    payload = {
        'sub': username,
        'iat': int(time.time()),
        'exp': int(time.time()) + TOKEN_TTL_SEC,
    }
    return jwt.encode(payload, secret, algorithm=DEFAULT_ALG)


def verify_token(token: str | None, secret: str | None = None) -> dict[str, Any] | None:
    if not token or jwt is None:
        return None
    secret = secret or DEFAULT_SECRET
    try:
        return jwt.decode(token, secret, algorithms=[DEFAULT_ALG])
    except Exception:
        return None


def username_from_headers(headers) -> str | None:
    auth = headers.get('Authorization') or headers.get('authorization') or ''
    if auth.lower().startswith('bearer '):
        claims = verify_token(auth[7:].strip())
        if claims:
            return str(claims.get('sub') or '')
    return None


def require_auth(headers, body_username: str | None = None) -> tuple[str | None, str | None]:
    """返回 (username, error_message)。"""
    from_header = username_from_headers(headers)
    if from_header:
        if body_username and body_username.strip() and body_username.strip() != from_header:
            return None, 'token 用户与 body.username 不一致'
        return from_header, None
    if body_username and body_username.strip():
        return body_username.strip(), None
    return None, '需要登录（Authorization: Bearer <token> 或 username）'
