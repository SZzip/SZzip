"""Persistent session storage (cookies + bearer token) for edoop-cli.

The session file is written with ``0o600`` permissions and lives outside the
repository (``~/.local/state/edoop/session.json`` by default). It is a cache of
authentication material, not configuration, and can be deleted at any time with
``edoop logout``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests


@dataclass
class Session:
    base_url: Optional[str] = None
    token: Optional[str] = None
    token_header: str = "Authorization"
    token_scheme: str = "Bearer"
    cookies: List[Dict] = field(default_factory=list)
    user: Optional[Dict] = None  # cached identity payload, if the API returned one

    # ------------------------------------------------------------------ I/O
    @classmethod
    def load(cls, path: Path) -> "Session":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            base_url=data.get("base_url"),
            token=data.get("token"),
            token_header=data.get("token_header", "Authorization"),
            token_scheme=data.get("token_scheme", "Bearer"),
            cookies=data.get("cookies", []) or [],
            user=data.get("user"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "base_url": self.base_url,
            "token": self.token,
            "token_header": self.token_header,
            "token_scheme": self.token_scheme,
            "cookies": self.cookies,
            "user": self.user,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    @staticmethod
    def clear(path: Path) -> bool:
        """Delete the session file. Returns True if a file was removed."""
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    # ------------------------------------------------------- requests glue
    def is_authenticated(self) -> bool:
        return bool(self.token) or bool(self.cookies)

    def apply_to(self, http: requests.Session) -> None:
        """Load stored cookies (and token header) into a requests session."""
        for c in self.cookies:
            try:
                http.cookies.set(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain"),
                    path=c.get("path", "/"),
                )
            except Exception:
                continue
        if self.token:
            value = f"{self.token_scheme} {self.token}".strip() if self.token_scheme else self.token
            http.headers[self.token_header] = value

    def capture_from(self, http: requests.Session) -> None:
        """Snapshot the current cookies from a requests session."""
        cookies = []
        for c in http.cookies:
            cookies.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                }
            )
        self.cookies = cookies
