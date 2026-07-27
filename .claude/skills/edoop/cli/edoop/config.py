"""Configuration and credential resolution for edoop-cli.

Resolution order (highest priority first):

1. Explicit CLI flags (passed by the caller as keyword overrides).
2. Environment variables: ``EDOOP_BASE_URL``, ``EDOOP_EMAIL``,
   ``EDOOP_PASSWORD``, ``EDOOP_ENDPOINTS`` (JSON), ``EDOOP_CONFIG``,
   ``EDOOP_STATE_DIR``.
3. Config file (JSON) at ``$EDOOP_CONFIG`` or the platform default
   (``$XDG_CONFIG_HOME/edoop/config.json`` → ``~/.config/edoop/config.json``).
4. The optional system keyring (service ``edoop-cli``) for the password.

Credentials are NEVER written to the config file by this tool. Store the
password in your keyring (``edoop login --save-keyring``) or supply it via the
``EDOOP_PASSWORD`` environment variable / interactive prompt.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .errors import ConfigError

DEFAULT_BASE_URL = "https://eltern.edoop.de"
KEYRING_SERVICE = "edoop-cli"
_APP_DIR_NAME = "edoop"


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / _APP_DIR_NAME


def _state_home() -> Path:
    if os.environ.get("EDOOP_STATE_DIR"):
        return Path(os.environ["EDOOP_STATE_DIR"])
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / _APP_DIR_NAME


def config_path() -> Path:
    """Path to the JSON config file (may not exist)."""
    if os.environ.get("EDOOP_CONFIG"):
        return Path(os.environ["EDOOP_CONFIG"])
    return _config_home() / "config.json"


def session_path() -> Path:
    """Path to the persisted session file (may not exist)."""
    return _state_home() / "session.json"


def _load_config_file() -> Dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Konfigurationsdatei {path} kann nicht gelesen werden: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Konfigurationsdatei {path} muss ein JSON-Objekt enthalten.")
    return data


def _keyring_password(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, email)
    except Exception:
        return None


@dataclass
class Config:
    """Resolved runtime configuration."""

    base_url: str = DEFAULT_BASE_URL
    email: Optional[str] = None
    password: Optional[str] = None
    login_path: Optional[str] = None
    csrf_path: Optional[str] = None
    timeout: float = 30.0
    verify_tls: bool = True
    user_agent: str = "edoop-cli/0.1 (+https://github.com/SZzip/SZzip)"
    endpoints: Dict[str, str] = field(default_factory=dict)
    # Where the config/session live (kept for diagnostics / `edoop config path`).
    config_file: Path = field(default_factory=config_path)
    session_file: Path = field(default_factory=session_path)

    @classmethod
    def load(cls, **overrides) -> "Config":
        """Build a :class:`Config` from file, env and explicit ``overrides``.

        ``overrides`` values that are ``None`` are ignored, so callers can pass
        argparse results straight through.
        """
        file_cfg = _load_config_file()

        def pick(key: str, env: str, default=None):
            if overrides.get(key) is not None:
                return overrides[key]
            if os.environ.get(env):
                return os.environ[env]
            if key in file_cfg and file_cfg[key] is not None:
                return file_cfg[key]
            return default

        base_url = pick("base_url", "EDOOP_BASE_URL", DEFAULT_BASE_URL)
        email = pick("email", "EDOOP_EMAIL")
        password = pick("password", "EDOOP_PASSWORD")

        # Endpoint overrides: config file + EDOOP_ENDPOINTS (JSON) + explicit.
        endpoints: Dict[str, str] = {}
        if isinstance(file_cfg.get("endpoints"), dict):
            endpoints.update(file_cfg["endpoints"])
        env_ep = os.environ.get("EDOOP_ENDPOINTS")
        if env_ep:
            try:
                parsed = json.loads(env_ep)
                if isinstance(parsed, dict):
                    endpoints.update(parsed)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"EDOOP_ENDPOINTS ist kein gültiges JSON: {exc}") from exc
        if isinstance(overrides.get("endpoints"), dict):
            endpoints.update(overrides["endpoints"])

        # Password may live in the keyring keyed by email.
        if not password:
            password = _keyring_password(email)

        verify_tls = pick("verify_tls", "EDOOP_VERIFY_TLS", True)
        if isinstance(verify_tls, str):
            verify_tls = verify_tls.strip().lower() not in ("0", "false", "no", "off")

        timeout = pick("timeout", "EDOOP_TIMEOUT", 30.0)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 30.0

        cfg = cls(
            base_url=str(base_url).rstrip("/"),
            email=email,
            password=password,
            login_path=pick("login_path", "EDOOP_LOGIN_PATH"),
            csrf_path=pick("csrf_path", "EDOOP_CSRF_PATH"),
            timeout=timeout,
            verify_tls=bool(verify_tls),
            user_agent=pick("user_agent", "EDOOP_USER_AGENT", cls.user_agent),
            endpoints=endpoints,
        )
        return cfg

    def require_credentials(self) -> None:
        if not self.email:
            raise ConfigError(
                "Keine E-Mail-Adresse konfiguriert. Setze EDOOP_EMAIL, nutze --email "
                "oder trage 'email' in die Konfigurationsdatei ein."
            )
        if not self.password:
            raise ConfigError(
                "Kein Passwort gefunden. Setze EDOOP_PASSWORD, nutze --password/--ask "
                "oder speichere es im Keyring (edoop login --save-keyring)."
            )


def write_config(values: Dict) -> Path:
    """Merge ``values`` into the config file and write it back (mode 600).

    Refuses to persist a plaintext ``password`` key.
    """
    if "password" in values:
        raise ConfigError(
            "Passwörter werden nicht in die Konfigurationsdatei geschrieben. "
            "Nutze den Keyring oder EDOOP_PASSWORD."
        )
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _load_config_file()
    current.update(values)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
