"""HTTP + authentication layer for edoop-cli.

Everything that touches the network lives here so that the exact request shape
(login route, auth scheme, endpoint paths) is contained in one place and can be
adapted without changing the command layer.
"""

from __future__ import annotations

import json as _json
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import requests

from . import endpoints as _endpoints
from .config import Config
from .errors import ApiError, AuthError, EndpointNotConfiguredError, NotLoggedInError
from .session import Session

# Candidate login routes, tried in order when a specific one is not pinned.
# edoop publishes no API docs, so login is auto-probed; pin the working one with
# ``edoop login --login-path`` or config ``endpoints.login`` once you know it.
LOGIN_CANDIDATES: Tuple[str, ...] = (
    "/api/login",
    "/api/auth/login",
    "/api/v1/login",
    "/api/v1/auth/login",
    "/api/sessions",
    "/login",
)

# JSON keys that commonly carry a bearer/access token.
_TOKEN_KEYS: Tuple[str, ...] = (
    "token",
    "access_token",
    "accessToken",
    "api_token",
    "apiToken",
    "auth_token",
    "authToken",
    "jwt",
    "bearer",
)


def _find_token(payload: Any) -> Optional[str]:
    """Best-effort search for a token string in a (possibly nested) JSON body."""
    if isinstance(payload, dict):
        for key in _TOKEN_KEYS:
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
        # Look one level down (e.g. {"data": {...}}, {"result": {...}}).
        for nested_key in ("data", "result", "auth", "session", "user"):
            nested = payload.get(nested_key)
            found = _find_token(nested)
            if found:
                return found
    return None


class EdoopClient:
    """Authenticated client for the edoop parent API."""

    def __init__(self, config: Config, session: Optional[Session] = None):
        self.config = config
        self.session = session or Session.load(config.session_file)
        self.http = requests.Session()
        self.http.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": config.user_agent,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.http.verify = config.verify_tls
        # Restore any persisted cookies / token.
        self.session.apply_to(self.http)

    # ------------------------------------------------------------------ url
    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.config.base_url}{path}"

    def _endpoint(self, name: str) -> str:
        try:
            return _endpoints.resolve(name, self.config.endpoints)
        except KeyError:  # pragma: no cover - defensive
            raise EndpointNotConfiguredError(
                f"Unbekannter Endpunkt '{name}'. Über config.endpoints.{name} setzen."
            )

    # -------------------------------------------------------------- low level
    def raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        data: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """Perform a request with the current session; return the raw response."""
        url = self._url(path)
        # For cookie/CSRF (Sanctum) flows echo the XSRF cookie as a header.
        merged_headers = dict(headers or {})
        xsrf = self.http.cookies.get("XSRF-TOKEN")
        if xsrf and "X-XSRF-TOKEN" not in merged_headers:
            merged_headers["X-XSRF-TOKEN"] = xsrf
        try:
            return self.http.request(
                method.upper(),
                url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers or None,
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(f"Netzwerkfehler bei {method.upper()} {url}: {exc}") from exc

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        require_auth: bool = True,
    ) -> Any:
        """Perform an authenticated request and return the parsed JSON body.

        Raises :class:`NotLoggedInError` on 401/419 and :class:`ApiError` on any
        other non-2xx response.
        """
        if require_auth and not self.session.is_authenticated():
            raise NotLoggedInError(
                "Nicht angemeldet. Bitte zuerst 'edoop login' ausführen."
            )
        resp = self.raw_request(method, path, params=params, json=json)
        if resp.status_code in (401, 419):
            raise NotLoggedInError(
                "Sitzung ist abgelaufen oder ungültig. Bitte erneut 'edoop login' ausführen."
            )
        if not resp.ok:
            raise ApiError(
                f"{method.upper()} {path} schlug fehl (HTTP {resp.status_code}).",
                status_code=resp.status_code,
                payload=_safe_body(resp),
            )
        return _safe_body(resp)

    # -------------------------------------------------------------- auth flow
    def _preflight_csrf(self) -> None:
        csrf_path = self.config.csrf_path
        if csrf_path is None:
            csrf_path = self._endpoint("csrf_cookie")
        if not csrf_path:  # explicitly disabled with an empty string
            return
        try:
            self.raw_request("GET", csrf_path)
        except ApiError:
            # Not every backend uses this flow; ignore failures silently.
            pass

    def login(self, email: str, password: str, extra_fields: Optional[Dict[str, Any]] = None) -> Session:
        """Authenticate and persist the resulting session.

        Tries the pinned login path (if any) or a list of candidates, accepts the
        first that returns a token, sets an auth cookie, or returns a user object.
        """
        self._preflight_csrf()

        payload: Dict[str, Any] = {"email": email, "password": password}
        if extra_fields:
            payload.update(extra_fields)

        candidates: Iterable[str]
        pinned = self.config.login_path or self.config.endpoints.get("login")
        if pinned:
            candidates = [pinned]
        else:
            candidates = LOGIN_CANDIDATES

        last_error: Optional[str] = None
        cookies_before = {c.name for c in self.http.cookies}

        for path in candidates:
            try:
                resp = self.raw_request("POST", path, json=payload)
            except ApiError as exc:
                last_error = str(exc)
                continue

            if resp.status_code in (404, 405):
                last_error = f"{path} -> HTTP {resp.status_code}"
                continue
            if resp.status_code in (401, 403, 419, 422):
                # Endpoint exists but rejected the credentials -> stop probing.
                raise AuthError(
                    f"Anmeldung abgelehnt (HTTP {resp.status_code}). "
                    "Bitte E-Mail/Passwort prüfen. Antwort: "
                    f"{_short(_safe_body(resp))}"
                )
            if not resp.ok:
                last_error = f"{path} -> HTTP {resp.status_code}"
                continue

            body = _safe_body(resp)
            token = _find_token(body)
            new_cookies = {c.name for c in self.http.cookies} - cookies_before
            # Some responses expose the auth cookie on the response object even
            # when the shared jar was not updated; treat either as success.
            has_auth_cookie = bool(new_cookies) or bool(getattr(resp, "cookies", None))

            if token or has_auth_cookie:
                # Success. Persist what we learned.
                self.session.base_url = self.config.base_url
                if token:
                    self.session.token = token
                    self.session.token_header = "Authorization"
                    self.session.token_scheme = "Bearer"
                    self.http.headers["Authorization"] = f"Bearer {token}"
                # Fold any response cookies into the shared jar before capturing.
                for cookie in getattr(resp, "cookies", []) or []:
                    self.http.cookies.set_cookie(cookie)
                self.session.capture_from(self.http)
                if isinstance(body, dict):
                    self.session.user = body.get("user") or body.get("data") or None
                self.session.save(self.config.session_file)
                return self.session

            last_error = (
                f"{path} antwortete mit HTTP {resp.status_code}, aber ohne erkennbares "
                f"Token oder Auth-Cookie."
            )

        raise AuthError(
            "Anmeldung fehlgeschlagen – kein passender Login-Endpunkt gefunden.\n"
            f"Letzter Hinweis: {last_error}\n"
            "Tipp: Ermittle die echte Login-URL im Browser (DevTools → Netzwerk) und "
            "übergib sie mit 'edoop login --login-path /pfad'."
        )

    def logout(self) -> None:
        """Best-effort server-side logout, then clear the local session."""
        try:
            self.raw_request("POST", self._endpoint("logout"))
        except ApiError:
            pass
        Session.clear(self.config.session_file)
        self.session = Session()

    # --------------------------------------------------------- high level API
    def me(self) -> Any:
        """Return the current user's profile (identity)."""
        return self.request("GET", self._endpoint("me"))

    def children(self) -> Any:
        """Return the children (Kinder) linked to this parent account."""
        return self.request("GET", self._endpoint("children"))

    def messages(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """List channels / message threads (Nachrichten)."""
        return self.request("GET", self._endpoint("messages_list"), params=params)

    def channel_messages(self, channel_id: str, params: Optional[Dict[str, Any]] = None) -> Any:
        path = self._endpoint("channel_messages").format(channel_id=channel_id)
        return self.request("GET", path, params=params)

    def send_message(self, channel_id: str, text: str, extra: Optional[Dict[str, Any]] = None) -> Any:
        path = self._endpoint("message_send").format(channel_id=channel_id)
        body: Dict[str, Any] = {"text": text, "body": text, "content": text}
        if extra:
            body.update(extra)
        return self.request("POST", path, json=body)

    def absences(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """List absences / sick reports (Abwesenheiten / Krankmeldungen)."""
        return self.request("GET", self._endpoint("absences_list"), params=params)

    def create_absence(self, body: Dict[str, Any]) -> Any:
        """Create an absence / sick report."""
        return self.request("POST", self._endpoint("absences_create"), json=body)

    def appointments(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """List appointments (Termine)."""
        return self.request("GET", self._endpoint("appointments_list"), params=params)

    def appointment_slots(self, appointment_id: str) -> Any:
        path = self._endpoint("appointment_slots").format(appointment_id=appointment_id)
        return self.request("GET", path)

    def book_appointment(self, appointment_id: str, slot_id: str, extra: Optional[Dict[str, Any]] = None) -> Any:
        path = self._endpoint("appointment_book").format(appointment_id=appointment_id)
        body: Dict[str, Any] = {"slot_id": slot_id, "slotId": slot_id}
        if extra:
            body.update(extra)
        return self.request("POST", path, json=body)


def _safe_body(resp: requests.Response) -> Any:
    """Return parsed JSON if possible, otherwise the raw text."""
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype.lower():
        try:
            return resp.json()
        except ValueError:
            pass
    text = resp.text
    # Some backends omit the header but still return JSON.
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            return _json.loads(stripped)
        except ValueError:
            pass
    return text


def _short(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else _json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


# Kept importable for callers/tests that want the raw URL join helper.
def absolute_url(base_url: str, path: str) -> str:
    if urlparse(path).scheme:
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
