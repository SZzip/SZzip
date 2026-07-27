"""edoop-cli — command-line access to the edoop.de parent inbox (Elternpostfach).

This package talks to the same private JSON API that the edoop web app
(https://eltern.edoop.de) and the mobile apps use. edoop does not publish an
official/public API, so the endpoint paths in :mod:`edoop.endpoints` are a
best-effort mapping that can be overridden from configuration without touching
any code (see the README, section "Endpunkte anpassen").
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
