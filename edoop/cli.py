"""Command-line interface for edoop-cli.

Run ``edoop --help`` for the full command list. The interface is organised around
the functions of the edoop parent inbox (Elternpostfach):

    login / logout / whoami   authentication & identity
    children                  linked children (Kinder)
    messages                  channels & messages (Nachrichten)
    absences                  absences / sick reports (Abwesenheiten / Krankmeldung)
    appointments              appointment booking (Termine)
    api                       raw authenticated request (escape hatch)
    config                    inspect / edit configuration
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .client import EdoopClient
from .config import Config, KEYRING_SERVICE, write_config
from .endpoints import DEFAULT_ENDPOINTS
from .errors import EdoopError

# --------------------------------------------------------------------- output


def _emit(data: Any, *, as_json: bool = True) -> None:
    """Print a result. Structured data is pretty-printed JSON (UTF-8, no escapes)."""
    if isinstance(data, str):
        print(data)
        return
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False))


def _err(message: str) -> None:
    print(f"Fehler: {message}", file=sys.stderr)


# --------------------------------------------------------------- arg parsing


def _parse_data_arg(raw: Optional[str]) -> Any:
    """Parse a --data value: inline JSON, or @path to read JSON from a file."""
    if raw is None:
        return None
    if raw.startswith("@"):
        path = raw[1:]
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EdoopError(f"--data ist kein gültiges JSON: {exc}") from exc


def _parse_kv(pairs: Optional[List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise EdoopError(f"Erwarte key=value, erhalten: {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


def _client_from_args(args: argparse.Namespace) -> EdoopClient:
    cfg = Config.load(
        base_url=getattr(args, "base_url", None),
        email=getattr(args, "email", None),
        password=getattr(args, "password", None),
        login_path=getattr(args, "login_path", None),
        csrf_path=getattr(args, "csrf_path", None),
        verify_tls=(False if getattr(args, "insecure", False) else None),
    )
    return EdoopClient(cfg)


# ------------------------------------------------------------------ commands


def cmd_login(args: argparse.Namespace) -> int:
    cfg = Config.load(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        login_path=args.login_path,
        csrf_path=args.csrf_path,
        verify_tls=(False if args.insecure else None),
    )
    if not cfg.email:
        cfg.email = input("E-Mail: ").strip()
    if not cfg.password or args.ask:
        cfg.password = getpass.getpass("Passwort: ")
    cfg.require_credentials()

    client = EdoopClient(cfg)
    session = client.login(cfg.email, cfg.password)
    print(f"Angemeldet als {cfg.email} bei {cfg.base_url}.")
    print(f"Sitzung gespeichert unter {cfg.session_file}")

    if args.save_keyring:
        try:
            import keyring  # type: ignore

            keyring.set_password(KEYRING_SERVICE, cfg.email, cfg.password)
            print(f"Passwort im Keyring gespeichert (Dienst '{KEYRING_SERVICE}').")
        except Exception as exc:  # pragma: no cover - environment dependent
            _err(f"Konnte Passwort nicht im Keyring speichern: {exc}")

    if args.save_config:
        values: Dict[str, Any] = {"base_url": cfg.base_url, "email": cfg.email}
        if args.login_path:
            values.setdefault("endpoints", {})["login"] = args.login_path
        path = write_config(values)
        print(f"Konfiguration gespeichert unter {path} (ohne Passwort).")

    if args.json and session.user:
        _emit(session.user)
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    client.logout()
    print("Abgemeldet. Lokale Sitzung wurde entfernt.")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    _emit(client.me(), as_json=args.json)
    return 0


def cmd_children(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    _emit(client.children(), as_json=args.json)
    return 0


def cmd_messages(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    action = args.messages_action or "list"
    if action == "list":
        params = _parse_kv(args.query) or None
        _emit(client.messages(params), as_json=args.json)
    elif action == "read":
        params = _parse_kv(args.query) or None
        _emit(client.channel_messages(args.channel, params), as_json=args.json)
    elif action == "send":
        extra = _parse_data_arg(args.data)
        extra = extra if isinstance(extra, dict) else None
        _emit(client.send_message(args.channel, args.text, extra), as_json=args.json)
    return 0


def cmd_absences(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    action = args.absences_action or "list"
    if action == "list":
        params = _parse_kv(args.query) or None
        _emit(client.absences(params), as_json=args.json)
    elif action == "create":
        body = _parse_data_arg(args.data)
        if not isinstance(body, dict):
            body = {}
        # Convenience flags map onto common field names; the server-side names
        # may differ — use --data '{...}' for full control.
        if args.child:
            body.setdefault("child_id", args.child)
        if args.date_from:
            body.setdefault("from", args.date_from)
            body.setdefault("start_date", args.date_from)
        if args.date_to:
            body.setdefault("to", args.date_to)
            body.setdefault("end_date", args.date_to)
        if args.reason:
            body.setdefault("reason", args.reason)
            body.setdefault("note", args.reason)
        if args.type:
            body.setdefault("type", args.type)
        if not body:
            raise EdoopError(
                "Keine Angaben für die Abwesenheit. Nutze --child/--from/--to/--reason "
                "oder --data '{\"...\": \"...\"}'."
            )
        _emit(client.create_absence(body), as_json=args.json)
    return 0


def cmd_appointments(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    action = args.appointments_action or "list"
    if action == "list":
        params = _parse_kv(args.query) or None
        _emit(client.appointments(params), as_json=args.json)
    elif action == "slots":
        _emit(client.appointment_slots(args.appointment), as_json=args.json)
    elif action == "book":
        extra = _parse_data_arg(args.data)
        extra = extra if isinstance(extra, dict) else None
        _emit(client.book_appointment(args.appointment, args.slot, extra), as_json=args.json)
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    client = _client_from_args(args)
    body = _parse_data_arg(args.data)
    params = _parse_kv(args.query) or None
    resp = client.raw_request(
        args.method,
        args.path,
        params=params,
        json=body if isinstance(body, (dict, list)) else None,
        data=None if isinstance(body, (dict, list)) else body,
    )
    if args.include:
        print(f"HTTP {resp.status_code}")
        for key, value in resp.headers.items():
            print(f"{key}: {value}")
        print()
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype.lower():
        try:
            _emit(resp.json())
        except ValueError:
            print(resp.text)
    else:
        print(resp.text)
    return 0 if resp.ok else 1


def cmd_config(args: argparse.Namespace) -> int:
    cfg = Config.load()
    action = args.config_action or "show"
    if action == "path":
        print(f"config:  {cfg.config_file}")
        print(f"session: {cfg.session_file}")
    elif action == "show":
        redacted = {
            "base_url": cfg.base_url,
            "email": cfg.email,
            "password": "***" if cfg.password else None,
            "login_path": cfg.login_path,
            "csrf_path": cfg.csrf_path,
            "timeout": cfg.timeout,
            "verify_tls": cfg.verify_tls,
            "endpoints": cfg.endpoints or {},
            "config_file": str(cfg.config_file),
            "session_file": str(cfg.session_file),
        }
        _emit(redacted)
    elif action == "endpoints":
        merged = dict(DEFAULT_ENDPOINTS)
        merged.update(cfg.endpoints or {})
        _emit(merged)
    elif action == "set":
        values = _parse_kv(args.pairs)
        endpoints = {}
        top: Dict[str, Any] = {}
        for key, value in values.items():
            if key.startswith("endpoints."):
                endpoints[key.split(".", 1)[1]] = value
            else:
                top[key] = value
        if endpoints:
            existing = dict(cfg.endpoints or {})
            existing.update(endpoints)
            top["endpoints"] = existing
        path = write_config(top)
        print(f"Konfiguration aktualisiert: {path}")
    return 0


# ---------------------------------------------------------------- parser


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--base-url", help="Basis-URL der edoop-Instanz (Standard: https://eltern.edoop.de).")
    p.add_argument("--email", help="Login-E-Mail (sonst EDOOP_EMAIL / Konfiguration).")
    p.add_argument("--json", action="store_true", help="Ausgabe als JSON erzwingen.")
    p.add_argument("--insecure", action="store_true", help="TLS-Zertifikatsprüfung deaktivieren (nicht empfohlen).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edoop",
        description="Kommandozeilen-Zugriff auf das edoop.de Elternpostfach.",
    )
    parser.add_argument("--version", action="version", version=f"edoop-cli {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<befehl>")

    # login
    p_login = sub.add_parser("login", help="Anmelden und Sitzung speichern.")
    _add_common(p_login)
    p_login.add_argument("--password", help="Passwort (unsicher; besser --ask oder Keyring/Env).")
    p_login.add_argument("--ask", action="store_true", help="Passwort interaktiv abfragen.")
    p_login.add_argument("--login-path", help="Login-Endpunkt festlegen, z. B. /api/auth/login.")
    p_login.add_argument("--csrf-path", help="CSRF-Cookie-Pfad (leer = deaktiviert).")
    p_login.add_argument("--save-keyring", action="store_true", help="Passwort im System-Keyring speichern.")
    p_login.add_argument("--save-config", action="store_true", help="base_url/email in Konfiguration speichern.")
    p_login.set_defaults(func=cmd_login)

    # logout
    p_logout = sub.add_parser("logout", help="Abmelden und lokale Sitzung löschen.")
    _add_common(p_logout)
    p_logout.set_defaults(func=cmd_logout)

    # whoami
    p_whoami = sub.add_parser("whoami", help="Aktuelles Profil anzeigen.")
    _add_common(p_whoami)
    p_whoami.set_defaults(func=cmd_whoami)

    # children
    p_children = sub.add_parser("children", help="Verknüpfte Kinder anzeigen.")
    _add_common(p_children)
    p_children.set_defaults(func=cmd_children)

    # messages
    p_msg = sub.add_parser("messages", help="Nachrichten / Kanäle.")
    _add_common(p_msg)
    msg_sub = p_msg.add_subparsers(dest="messages_action", metavar="<aktion>")
    m_list = msg_sub.add_parser("list", help="Kanäle / Nachrichtenübersicht auflisten.")
    _add_common(m_list)
    m_list.add_argument("-q", "--query", action="append", help="Query-Parameter key=value (mehrfach).")
    m_read = msg_sub.add_parser("read", help="Nachrichten eines Kanals lesen.")
    _add_common(m_read)
    m_read.add_argument("channel", help="Kanal-/Thread-ID.")
    m_read.add_argument("-q", "--query", action="append", help="Query-Parameter key=value (mehrfach).")
    m_send = msg_sub.add_parser("send", help="Nachricht in einen Kanal senden.")
    _add_common(m_send)
    m_send.add_argument("channel", help="Kanal-/Thread-ID.")
    m_send.add_argument("text", help="Nachrichtentext.")
    m_send.add_argument("-d", "--data", help="Zusätzliche Felder als JSON.")
    p_msg.set_defaults(func=cmd_messages)

    # absences
    p_abs = sub.add_parser("absences", help="Abwesenheiten / Krankmeldungen.")
    _add_common(p_abs)
    abs_sub = p_abs.add_subparsers(dest="absences_action", metavar="<aktion>")
    a_list = abs_sub.add_parser("list", help="Abwesenheiten auflisten.")
    _add_common(a_list)
    a_list.add_argument("-q", "--query", action="append", help="Query-Parameter key=value (mehrfach).")
    a_create = abs_sub.add_parser("create", help="Krankmeldung / Abwesenheit anlegen.")
    _add_common(a_create)
    a_create.add_argument("--child", help="ID des Kindes.")
    a_create.add_argument("--from", dest="date_from", help="Startdatum (YYYY-MM-DD).")
    a_create.add_argument("--to", dest="date_to", help="Enddatum (YYYY-MM-DD).")
    a_create.add_argument("--reason", help="Grund / Notiz.")
    a_create.add_argument("--type", help="Art (z. B. sick / leave).")
    a_create.add_argument("-d", "--data", help="Vollständiger Request-Body als JSON (überschreibt Flags).")
    p_abs.set_defaults(func=cmd_absences)

    # appointments
    p_app = sub.add_parser("appointments", help="Termine.")
    _add_common(p_app)
    app_sub = p_app.add_subparsers(dest="appointments_action", metavar="<aktion>")
    ap_list = app_sub.add_parser("list", help="Termine auflisten.")
    _add_common(ap_list)
    ap_list.add_argument("-q", "--query", action="append", help="Query-Parameter key=value (mehrfach).")
    ap_slots = app_sub.add_parser("slots", help="Freie Zeitfenster eines Terminangebots anzeigen.")
    _add_common(ap_slots)
    ap_slots.add_argument("appointment", help="ID des Terminangebots.")
    ap_book = app_sub.add_parser("book", help="Zeitfenster buchen.")
    _add_common(ap_book)
    ap_book.add_argument("appointment", help="ID des Terminangebots.")
    ap_book.add_argument("slot", help="ID des Zeitfensters.")
    ap_book.add_argument("-d", "--data", help="Zusätzliche Felder als JSON.")
    p_app.set_defaults(func=cmd_appointments)

    # api (raw)
    p_api = sub.add_parser("api", help="Beliebige authentifizierte Anfrage (Escape-Hatch).")
    _add_common(p_api)
    p_api.add_argument("method", help="HTTP-Methode (GET/POST/PUT/PATCH/DELETE).")
    p_api.add_argument("path", help="Pfad (z. B. /api/channels) oder vollständige URL.")
    p_api.add_argument("-d", "--data", help="Request-Body als JSON oder @datei.json.")
    p_api.add_argument("-q", "--query", action="append", help="Query-Parameter key=value (mehrfach).")
    p_api.add_argument("-i", "--include", action="store_true", help="HTTP-Status und Header mit ausgeben.")
    p_api.set_defaults(func=cmd_api)

    # config
    p_cfg = sub.add_parser("config", help="Konfiguration anzeigen/bearbeiten.")
    cfg_sub = p_cfg.add_subparsers(dest="config_action", metavar="<aktion>")
    cfg_sub.add_parser("show", help="Aktuelle Konfiguration anzeigen (Passwort redigiert).")
    cfg_sub.add_parser("path", help="Pfade zu Konfig- und Sitzungsdatei anzeigen.")
    cfg_sub.add_parser("endpoints", help="Effektive Endpunkte (Standard + Overrides) anzeigen.")
    c_set = cfg_sub.add_parser("set", help="Werte setzen, z. B. base_url=... endpoints.messages_list=/api/...")
    c_set.add_argument("pairs", nargs="+", help="key=value Paare.")
    p_cfg.set_defaults(func=cmd_config)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None) or not hasattr(args, "func"):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except EdoopError as exc:
        _err(str(exc))
        return 2
    except BrokenPipeError:  # pragma: no cover
        # Downstream (e.g. `| head`) closed the pipe. Exit quietly like a well-
        # behaved Unix tool instead of dumping a traceback. Redirect stdout to
        # devnull so the interpreter's final flush doesn't raise again.
        try:
            import os

            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return 141
    except KeyboardInterrupt:  # pragma: no cover
        _err("Abgebrochen.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
