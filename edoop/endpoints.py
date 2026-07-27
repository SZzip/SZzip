"""Central registry of edoop API endpoint paths.

edoop.de ships no public API documentation, so these paths are a best-effort
reconstruction of the private API used by the web app (https://eltern.edoop.de)
and the mobile apps. They are intentionally kept in ONE place and are fully
overridable from configuration, so you never have to edit code to correct a
path once you have captured the real request (see README → "Endpunkte anpassen").

How to override
---------------
In ``~/.config/edoop/config.json``::

    {
      "endpoints": {
        "messages_list": "/api/v1/channels",
        "absences_create": "/api/v1/absences"
      }
    }

or via environment variable (JSON object)::

    export EDOOP_ENDPOINTS='{"messages_list": "/api/v1/channels"}'

Paths may contain ``{placeholders}`` that are filled in by the client, e.g.
``"/api/channels/{channel_id}/messages"``.
"""

from __future__ import annotations

from typing import Dict

# --- Authentication ---------------------------------------------------------
# Login is tried against a *list* of candidate paths (see client.LOGIN_CANDIDATES)
# because the exact route is not documented. ``login`` below is the preferred one
# and can be pinned with ``edoop login --login-path`` or config ``endpoints.login``.
#
# ``csrf_cookie`` is only used for the Laravel-Sanctum style SPA flow: the client
# performs a GET against it first so the server sets an ``XSRF-TOKEN`` cookie,
# which is then echoed back as the ``X-XSRF-TOKEN`` header. Set it to an empty
# string to disable that pre-flight entirely.

DEFAULT_ENDPOINTS: Dict[str, str] = {
    # Auth
    "login": "/api/login",
    "logout": "/api/logout",
    "csrf_cookie": "/sanctum/csrf-cookie",
    # Identity / profile
    "me": "/api/me",
    "profile": "/api/profile",
    "children": "/api/children",
    # Messages / channels (Nachrichten)
    "messages_list": "/api/channels",
    "channel_messages": "/api/channels/{channel_id}/messages",
    "message_send": "/api/channels/{channel_id}/messages",
    # Absences / sick reports (Abwesenheiten / Krankmeldung)
    "absences_list": "/api/absences",
    "absences_create": "/api/absences",
    "absence_detail": "/api/absences/{absence_id}",
    # Appointments (Termine)
    "appointments_list": "/api/appointments",
    "appointment_slots": "/api/appointments/{appointment_id}/slots",
    "appointment_book": "/api/appointments/{appointment_id}/book",
}


def resolve(name: str, overrides: Dict[str, str] | None = None) -> str:
    """Return the (possibly overridden) endpoint template for ``name``.

    Raises:
        KeyError: if ``name`` is unknown and not provided via ``overrides``.
    """
    if overrides and name in overrides:
        return overrides[name]
    return DEFAULT_ENDPOINTS[name]
