# edoop-cli

Eine Kommandozeilen-Schnittstelle (CLI) für das **[edoop.de](https://edoop.de) Elternpostfach**.
Damit lassen sich die Funktionen der Eltern-Ansicht direkt aus dem Terminal nutzen:
Nachrichten, Krankmeldungen/Abwesenheiten und Terminbuchungen.

```console
$ edoop login
$ edoop messages list
$ edoop absences create --child 42 --from 2026-09-01 --to 2026-09-02 --reason "Grippe"
$ edoop appointments list
```

> **Wichtiger Hinweis zur API**
> edoop veröffentlicht **keine offizielle/öffentliche API**. Diese CLI spricht dieselbe
> private JSON-Schnittstelle an, die auch die Web-App (`https://eltern.edoop.de`) und die
> mobilen Apps verwenden. Die konkreten **Endpunkt-Pfade** wurden nach bestem Wissen
> nachgebildet und können sich jederzeit ändern. Sie sind **vollständig überschreibbar**,
> ohne Code zu ändern – siehe [Endpunkte anpassen](#endpunkte-anpassen). Für jede beliebige
> authentifizierte Anfrage gibt es außerdem den Befehl [`edoop api`](#roh-zugriff-edoop-api),
> der unabhängig von den vordefinierten Pfaden funktioniert.

---

## Installation

Voraussetzung: Python ≥ 3.9.

```bash
git clone https://github.com/SZzip/SZzip.git
cd SZzip
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
# optional: Passwort im System-Keyring ablegen können
pip install -e ".[keyring]"
```

Danach steht der Befehl `edoop` zur Verfügung (alternativ `python -m edoop`).

## Anmelden

Zugangsdaten werden **niemals** im Repository oder in der Konfigurationsdatei im Klartext
gespeichert. Es gibt drei empfohlene Wege, das Passwort bereitzustellen:

**1. Interaktiv (empfohlen für den Einstieg)**

```bash
edoop login --email deine@mail.de --ask
# Passwort wird verdeckt abgefragt
```

**2. Über Umgebungsvariablen** (z. B. für Skripte/Cron)

```bash
export EDOOP_EMAIL="deine@mail.de"
export EDOOP_PASSWORD="dein-passwort"
edoop login
```

**3. Im System-Keyring speichern** (benötigt das Extra `keyring`)

```bash
edoop login --email deine@mail.de --ask --save-keyring
# spätere Aufrufe finden das Passwort automatisch:
edoop messages list
```

Nach erfolgreicher Anmeldung wird die Sitzung (Cookie/Token) lokal unter
`~/.local/state/edoop/session.json` (Rechte `600`) zwischengespeichert. `edoop logout`
löscht sie wieder.

Die Basis-URL ist standardmäßig `https://eltern.edoop.de`. Sollte deine Schule eine andere
Adresse nutzen, setze sie mit `--base-url` oder `EDOOP_BASE_URL`.

## Befehle

| Befehl | Funktion |
| --- | --- |
| `edoop login` | Anmelden, Sitzung speichern |
| `edoop logout` | Abmelden, lokale Sitzung löschen |
| `edoop whoami` | Aktuelles Profil anzeigen |
| `edoop children` | Verknüpfte Kinder anzeigen |
| `edoop messages list` | Kanäle / Nachrichtenübersicht |
| `edoop messages read <kanal>` | Nachrichten eines Kanals lesen |
| `edoop messages send <kanal> "<text>"` | Nachricht senden |
| `edoop absences list` | Abwesenheiten / Krankmeldungen auflisten |
| `edoop absences create …` | Krankmeldung / Abwesenheit anlegen |
| `edoop appointments list` | Termine anzeigen |
| `edoop appointments slots <id>` | Freie Zeitfenster eines Angebots |
| `edoop appointments book <id> <slot>` | Zeitfenster buchen |
| `edoop api <METHODE> <pfad>` | Beliebige authentifizierte Anfrage |
| `edoop config …` | Konfiguration anzeigen/bearbeiten |

Jeder Befehl kennt `--help`. Die Ausgabe ist standardmäßig JSON (UTF-8), sodass sie sich gut
mit Werkzeugen wie [`jq`](https://jqlang.github.io/jq/) weiterverarbeiten lässt.

### Beispiele

```bash
# Krankmeldung für heute anlegen
edoop absences create --child 42 --from 2026-07-27 --to 2026-07-27 \
  --type sick --reason "Fieber"

# Nachrichten eines Kanals lesen und mit jq filtern
edoop messages read 1234 --json | jq '.[].text'

# Freie Termine ansehen und einen Slot buchen
edoop appointments slots 987
edoop appointments book 987 55
```

### Roh-Zugriff: `edoop api`

Dieser Befehl schickt eine beliebige authentifizierte Anfrage mit der gespeicherten Sitzung.
Er funktioniert **unabhängig** von den vordefinierten Endpunkten und ist ideal, um die echte
API zu erkunden oder zu verifizieren:

```bash
edoop api GET /api/channels
edoop api GET /api/absences -q page=1 -q per_page=20
edoop api POST /api/absences -d '{"child_id": 42, "from": "2026-07-27", "to": "2026-07-27"}'
edoop api GET /api/me -i        # -i: Statuszeile und Header mitanzeigen
```

Der Request-Body kann inline (`-d '{...}'`) oder aus einer Datei (`-d @body.json`) kommen.

## Endpunkte anpassen

Da die edoop-API nicht dokumentiert ist, liegen alle bekannten Pfade zentral in
`edoop/endpoints.py`. Du musst dafür **keinen Code ändern** – überschreibe sie stattdessen
per Konfiguration:

```bash
# effektive Endpunkte anzeigen (Standard + Overrides)
edoop config endpoints

# einen Pfad korrigieren
edoop config set endpoints.messages_list=/api/v2/channels
```

oder per Umgebungsvariable (JSON-Objekt):

```bash
export EDOOP_ENDPOINTS='{"messages_list": "/api/v2/channels", "absences_create": "/api/v2/absences"}'
```

**So findest du die echten Pfade:** Melde dich im Browser unter `https://eltern.edoop.de` an,
öffne die Entwicklerwerkzeuge (F12) → Reiter **Netzwerk**, und beobachte die Anfragen, während
du z. B. die Nachrichten öffnest oder eine Krankmeldung anlegst. Die aufgerufene URL und der
Request-Body zeigen dir Pfad und Feldnamen, die du dann per `edoop config set` bzw.
`edoop api` verwenden kannst. Alternativ lässt sich der Login-Pfad direkt pinnen:

```bash
edoop login --login-path /api/auth/login
```

## Konfiguration & Umgebungsvariablen

Auflösungsreihenfolge (höchste Priorität zuerst): **CLI-Flags → Umgebungsvariablen →
Konfigurationsdatei → Keyring**.

| Variable | Bedeutung |
| --- | --- |
| `EDOOP_BASE_URL` | Basis-URL (Standard `https://eltern.edoop.de`) |
| `EDOOP_EMAIL` | Login-E-Mail |
| `EDOOP_PASSWORD` | Passwort (nur für Skripte; sonst Keyring/`--ask`) |
| `EDOOP_LOGIN_PATH` | fester Login-Endpunkt |
| `EDOOP_CSRF_PATH` | CSRF-Cookie-Pfad (leer = deaktiviert) |
| `EDOOP_ENDPOINTS` | Endpunkt-Overrides als JSON-Objekt |
| `EDOOP_CONFIG` | Pfad zur Konfigurationsdatei |
| `EDOOP_STATE_DIR` | Ablageort der Sitzungsdatei |
| `EDOOP_TIMEOUT` | HTTP-Timeout in Sekunden |
| `EDOOP_VERIFY_TLS` | `0`/`false` deaktiviert die Zertifikatsprüfung |

Konfigurationsdatei standardmäßig unter `~/.config/edoop/config.json`. Pfade anzeigen:

```bash
edoop config path
```

## Authentifizierung im Detail

Beim `login` versucht die CLI automatisch mehrere übliche Login-Routen
(`/api/login`, `/api/auth/login`, …) und erkennt den Erfolg an einem Token im JSON-Body
oder an einem gesetzten Auth-Cookie. Es werden sowohl **Bearer-Token-** als auch
**Cookie-/CSRF-basierte** (Laravel-Sanctum-ähnliche) Abläufe unterstützt:

- Ein gefundenes Token wird als `Authorization: Bearer …` gesendet.
- Für Cookie-Flows wird vorab optional `/sanctum/csrf-cookie` geladen und das
  `XSRF-TOKEN`-Cookie als `X-XSRF-TOKEN`-Header zurückgespiegelt.

## Entwicklung

```bash
pip install -e ".[dev]"
pytest -q
```

Die Tests laufen vollständig **offline** (HTTP wird mit `requests-mock` simuliert) und decken
Konfigurationsauflösung, Login-Flows, Fehlerbehandlung und die Endpunkt-Overrides ab.

Projektstruktur:

```
edoop/
  cli.py         Argumentparsing & Befehle
  client.py      HTTP + Authentifizierung (einzige Netzwerk-Schicht)
  config.py      Konfigurations-/Credential-Auflösung
  session.py     persistente Sitzung (Cookies/Token)
  endpoints.py   zentrale, überschreibbare Endpunkt-Pfade
  errors.py      Ausnahmehierarchie
```

## Sicherheit & Datenschutz

- Passwörter werden nie ins Repository oder in die Konfigurationsdatei geschrieben.
- Die Sitzungsdatei wird mit Rechten `600` gespeichert; `edoop logout` entfernt sie.
- Deaktiviere die TLS-Prüfung (`--insecure`) nur zu Testzwecken.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
