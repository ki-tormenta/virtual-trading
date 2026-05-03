"""PKCE OAuth フロー用ヘルパー。"""
import base64
import hashlib
import secrets
import time
from typing import TypedDict

_TTL_SECONDS = 300  # 5 分


class _Entry(TypedDict):
    verifier: str
    expires_at: float


_store: dict[str, _Entry] = {}


def create_verifier() -> tuple[str, str]:
    """code_verifier と code_challenge を生成する。

    Returns:
        (code_verifier, code_challenge)
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def store_verifier(state: str, verifier: str) -> None:
    """Supabase の state をキーに verifier を保存する。"""
    _store[state] = {"verifier": verifier, "expires_at": time.monotonic() + _TTL_SECONDS}
    _purge_expired()


def get_verifier(state: str) -> str | None:
    """state に対応する verifier を取り出す（取り出したら削除）。

    Returns:
        verifier 文字列、または期限切れ / 存在しない場合は None
    """
    entry = _store.pop(state, None)
    if entry is None:
        return None
    if time.monotonic() > entry["expires_at"]:
        return None
    return entry["verifier"]


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [k for k, v in _store.items() if now > v["expires_at"]]
    for k in expired:
        del _store[k]
