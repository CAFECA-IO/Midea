"""Who is using the studio, and what they may touch.

The studio runs in two ways:
- standalone (`midea serve`): one operator behind HTTP Basic — treated as an admin;
- inside the public site (`midea site`, mounted at /studio): every CAFECA identity gets its own studio. Projects and
  actors carry an `owner` (the CAFECA account); people see and change only their own. Platform ("official") actors
  have no owner and can be cast by anyone. Admins (config `site.admins` or `midea site admin <handle>`) see
  everything, control GPU services and review what creators publish before it reaches the public site.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from ..config import settings


@dataclass
class User:
    account: str                    # "" for the standalone operator
    name: str
    admin: bool
    viewer_id: int | None = None
    kyc_level: int | None = None
    extra: dict = field(default_factory=dict)

    def owns(self, owner: str | None) -> bool:
        return self.admin or (bool(self.account) and (owner or "") == self.account)

    def public(self) -> dict:
        return {"account": self.account, "name": self.name, "admin": self.admin, "kyc_level": self.kyc_level}


OPERATOR = User(account="", name="operator", admin=True)


def user(request: Request) -> User:
    u = getattr(request.state, "user", None)
    if u is None:
        raise HTTPException(401, "以 CAFECA 登入後才能使用製作後台")
    return u


def require_admin(request: Request) -> User:
    u = user(request)
    if not u.admin:
        raise HTTPException(403, "只有管理者可以使用")
    return u


def limit(name: str, default: int) -> int:
    return int(settings().get(f"site.studio.{name}", default))


# ------------------------------------------------------------------------------------------- uploads & URLs
def upload_dir(u: User) -> Path:
    key = (u.account or "operator").lower().removeprefix("0x")[:40] or "operator"
    d = settings().workspace / "_uploads" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_media(u: User, paths: list[str]) -> list[str]:
    """User media must come from that user's own upload folder (never an arbitrary server path)."""
    if u.admin and not u.account:
        return paths
    base = upload_dir(u).resolve()
    out = []
    for p in paths or []:
        f = Path(p).resolve()
        if base not in f.parents or not f.is_file():
            raise HTTPException(400, "素材檔案無效，請重新上傳")
        out.append(str(f))
    return out


def public_url(u: User, url: str | None, what: str = "網址") -> str | None:
    """Only http(s) URLs that resolve to public addresses — the studio must not be a way into the server's network."""
    if not url:
        return url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(400, f"{what}必須是 http 或 https 開頭")
    if u.admin and not u.account:
        return url
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(400, f"{what}的網域找不到") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise HTTPException(400, f"{what}不能指向內部網路")
    return url
