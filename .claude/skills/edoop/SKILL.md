---
name: edoop
description: >-
  Zugriff auf das edoop.de Elternpostfach über die gebündelte `edoop`-CLI.
  Nutze diesen Skill immer, wenn es um edoop, das Elternpostfach, die edoop-App
  oder Schulkommunikation über edoop geht – insbesondere beim Lesen/Senden von
  Nachrichten und Kanälen, beim Anlegen oder Auflisten von Krankmeldungen bzw.
  Abwesenheiten (Kind krankmelden), beim Ansehen und Buchen von Terminen
  (Elternsprechtag/Sprechstunde) oder beim Abrufen von Profil und verknüpften
  Kindern. Auch auslösen, wenn der Nutzer sinngemäß sagt „melde mein Kind krank",
  „gibt es neue Nachrichten von der Schule", „buche einen Elternsprechtag" oder
  einen edoop-Login/eine edoop-Aktion meint, ohne das Wort „CLI" zu verwenden.
---

# edoop – Elternpostfach über die CLI

Dieser Skill bündelt eine Kommandozeilen-Schnittstelle (`edoop`), mit der sich
die Funktionen des **edoop.de Elternpostfachs** automatisieren lassen:
Nachrichten, Krankmeldungen/Abwesenheiten, Terminbuchungen, Profil und Kinder.

Die CLI liegt selbst-enthalten unter `cli/` in diesem Skill. Die vollständige
Referenz steht in `cli/README.md` – dieser Skill fasst das Wichtigste zusammen
und beschreibt den empfohlenen Arbeitsablauf.

## Wichtig zu verstehen, bevor du loslegst

edoop veröffentlicht **keine offizielle/dokumentierte API**. Die CLI spricht die
private JSON-Schnittstelle an, die auch die Web-App (`https://eltern.edoop.de`)
und die Apps nutzen. Zwei Konsequenzen, die dein Vorgehen bestimmen:

1. **Endpunkt-Pfade sind eine Best-Effort-Nachbildung** und können abweichen.
   Wenn ein High-Level-Befehl (z. B. `edoop messages list`) HTTP 404/„nicht
   gefunden" liefert, ist das erwartbar – dann den echten Pfad ermitteln und per
   Konfiguration hinterlegen (siehe „Endpunkte verifizieren"). Nicht raten,
   sondern verifizieren.
2. **Der Befehl `edoop api <METHODE> <pfad>` funktioniert immer**, unabhängig von
   den vordefinierten Pfaden. Er ist dein zuverlässiges Werkzeug, um die API zu
   erkunden und Aktionen auszuführen, sobald der Login steht.

## Einrichtung (einmalig)

Stelle sicher, dass der Befehl verfügbar ist. Führe das Installationsskript aus –
es ist idempotent und tut nichts, wenn `edoop` bereits funktioniert:

```bash
bash "$SKILL_DIR/scripts/install.sh"   # $SKILL_DIR = Verzeichnis dieses Skills
```

Falls `edoop` nicht im PATH landet, funktioniert alternativ überall
`python3 -m edoop …` statt `edoop …`.

## Zugangsdaten – Sicherheitsregeln

Behandle die Zugangsdaten des Nutzers wie Geheimnisse:

- **Niemals** Passwörter in Dateien, Repos, Commits, Logs oder Kommandos
  schreiben, die in der Shell-History landen.
- Bevorzugt über Umgebungsvariablen für die aktuelle Sitzung:

  ```bash
  export EDOOP_EMAIL="…"; export EDOOP_PASSWORD="…"
  edoop login
  ```

- Wenn der Nutzer das Passwort nicht in einer Variablen hinterlegen möchte,
  weise ihn auf `edoop login --email … --ask` (verdeckte Abfrage) oder den
  Keyring (`--save-keyring`, benötigt das Extra `keyring`) hin.
- Nach `edoop login` liegt die Sitzung lokal unter
  `~/.local/state/edoop/session.json` (Rechte 600). Weitere Befehle brauchen
  dann kein Passwort mehr. `edoop logout` entfernt die Sitzung.

Wenn Zugangsdaten fehlen, erkläre kurz die drei Optionen und frage nach – rate
nicht und setze keine Platzhalter ein.

## Arbeitsablauf

1. **Sicherstellen, dass eingeloggt ist.** Ein beliebiger Lesebefehl (z. B.
   `edoop whoami`) zeigt schnell, ob eine gültige Sitzung besteht. Bei
   „Nicht angemeldet"/HTTP 401 zuerst `edoop login`.
2. **Aufgabe ausführen** mit dem passenden High-Level-Befehl (siehe unten).
3. **Bei fehlschlagenden High-Level-Befehlen** auf `edoop api` ausweichen und
   ggf. den Endpunkt korrigieren (siehe „Endpunkte verifizieren").
4. **Ergebnis knapp zusammenfassen.** Die CLI gibt JSON aus; fasse für den
   Nutzer das Wesentliche in Klartext zusammen, statt rohes JSON durchzureichen.

## Befehle

Alle Befehle kennen `--help`. Ausgabe ist JSON (UTF-8), gut mit `jq` filterbar.

**Identität & Kinder**

```bash
edoop whoami                 # aktuelles Profil
edoop children               # verknüpfte Kinder (IDs merken – für Krankmeldungen nötig)
```

**Nachrichten (Nachrichten/Kanäle)**

```bash
edoop messages list                      # Kanäle / Übersicht
edoop messages read <kanal-id>           # Nachrichten eines Kanals
edoop messages send <kanal-id> "Text"    # Nachricht senden
```

**Krankmeldung / Abwesenheiten**

```bash
edoop absences list
edoop absences create --child <kind-id> --from 2026-09-01 --to 2026-09-02 \
    --type sick --reason "Grippe"
# Volle Kontrolle über die Felder (falls Server andere Feldnamen erwartet):
edoop absences create -d '{"child_id": 42, "from": "2026-09-01", "to": "2026-09-01"}'
```

Für eine Krankmeldung brauchst du in der Regel die **Kind-ID** aus
`edoop children`. Frage im Zweifel Zeitraum und Grund beim Nutzer nach, bevor du
etwas anlegst – das Anlegen ist eine schreibende, nach außen wirkende Aktion.

**Termine**

```bash
edoop appointments list                        # verfügbare/gebuchte Termine
edoop appointments slots <termin-id>           # freie Zeitfenster
edoop appointments book <termin-id> <slot-id>  # Zeitfenster buchen
```

**Roh-Zugriff (immer verfügbar)**

```bash
edoop api GET  /api/channels
edoop api GET  /api/absences -q page=1 -q per_page=20
edoop api POST /api/absences -d '{"child_id": 42, "from": "2026-09-01", "to": "2026-09-01"}'
edoop api GET  /api/me -i          # -i: Statuszeile + Header anzeigen
```

Body inline (`-d '{…}'`) oder aus Datei (`-d @body.json`); Query mit `-q k=v`.

## Bestätigung vor schreibenden Aktionen

Lesen (list/read/whoami/children/slots) ist unkritisch. **Schreibende Aktionen**
– Krankmeldung anlegen, Nachricht senden, Termin buchen – wirken nach außen und
sind kaum umkehrbar. Vor deren Ausführung die konkreten Werte (Kind, Zeitraum,
Kanal, Termin/Slot, Text) mit dem Nutzer bestätigen, sofern er nicht bereits
eindeutig und vollständig dazu aufgefordert hat.

## Endpunkte verifizieren und korrigieren

Wenn ein High-Level-Befehl fehlschlägt, ist meist nur der Pfad falsch. Vorgehen:

```bash
edoop config endpoints          # aktuell wirksame Pfade (Standard + Overrides)
```

Den echten Pfad ermittelt der Nutzer am schnellsten im Browser: unter
`https://eltern.edoop.de` anmelden → Entwicklerwerkzeuge (F12) → **Netzwerk** →
die betreffende Aktion (Nachrichten öffnen, Krankmeldung anlegen) auslösen und
die aufgerufene URL samt Request-Body ablesen. Danach hinterlegen:

```bash
edoop config set endpoints.messages_list=/api/v2/channels
# oder für die Sitzung:
export EDOOP_ENDPOINTS='{"messages_list": "/api/v2/channels"}'
```

Verfügbare Endpunkt-Schlüssel: `login`, `logout`, `csrf_cookie`, `me`,
`profile`, `children`, `messages_list`, `channel_messages`, `message_send`,
`absences_list`, `absences_create`, `absence_detail`, `appointments_list`,
`appointment_slots`, `appointment_book`. Pfade dürfen Platzhalter wie
`{channel_id}` / `{appointment_id}` / `{absence_id}` enthalten.

Den Login-Pfad kann man auch direkt pinnen: `edoop login --login-path /api/auth/login`.

## Fehlerbehandlung – Kurzreferenz

- **„Nicht angemeldet" / HTTP 401/419** → Sitzung fehlt/abgelaufen → `edoop login`.
- **„Anmeldung abgelehnt" (403/422)** → E-Mail/Passwort prüfen (Endpunkt existiert).
- **„kein passender Login-Endpunkt gefunden"** → echten Login-Pfad im Browser
  ermitteln und mit `--login-path` übergeben.
- **HTTP 404 bei einem High-Level-Befehl** → Endpunkt-Pfad korrigieren (s. o.)
  oder direkt `edoop api` mit dem echten Pfad nutzen.
- **Andere Basis-URL der Schule** → `--base-url` / `EDOOP_BASE_URL` setzen
  (Standard `https://eltern.edoop.de`).

## Weiterführend

- `cli/README.md` – vollständige Referenz aller Befehle, Umgebungsvariablen und
  des Authentifizierungsablaufs.
- `cli/edoop/endpoints.py` – zentrale Liste aller Endpunkt-Pfade mit Kommentaren.
