# 🏁 Rennwochenende-Bot für Discord

Postet jeden **Donnerstagabend** automatisch, welche Rennen am kommenden Wochenende
laufen – Formel 1, WEC, IMSA und GT World Challenge – mit allen Zeiten in **Berliner Zeit**.

- **Formel 1** wird automatisch geladen (Jolpica-API: Trainings, Sprint, Qualifying, Rennen).
- **FIA WEC** wird automatisch von fiawec.com geladen (alle Sessions inkl. Hyperpole).
  Solange die WEC noch keine Uhrzeiten veröffentlicht hat, steht in der Übersicht
  „Zeit folgt“ und es kommt (noch) keine Erinnerung.
- **IMSA, GT World Challenge** trägst du in `rennen.toml` ein. Für diese Serien gibt
  es keine freie, zuverlässige Schnittstelle. Du kannst die Zeiten einfach in Ortszeit
  der Strecke eintragen, der Bot rechnet sie selbst um.

Zusätzlich kommt **für jede einzelne Session** (FP1, FP2, FP3, Qualifying, Sprint, Rennen –
und alle Sessions aus `rennen.toml`) eine eigene Erinnerung, standardmäßig etwa **30 Minuten
vor dem Start**.

Läuft kostenlos über GitHub Actions – kein eigener Server nötig.

## Einrichtung (ca. 10 Minuten)

### 1. Discord-Webhook anlegen
1. In Discord: Rechtsklick auf den Kanal → **Kanal bearbeiten** → **Integrationen** → **Webhooks**
2. **Neuer Webhook** → Name z. B. „Rennwochenende“, optional ein Bild
3. **Webhook-URL kopieren** (diese URL geheim halten!)

### 2. Auf GitHub hochladen
1. Auf github.com ein neues Repository anlegen (darf privat sein)
2. Alle Dateien aus diesem Ordner hochladen – **inklusive** des Ordners `.github/workflows`
3. Im Repository: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Name: `DISCORD_WEBHOOK_URL`
   - Wert: die kopierte Webhook-URL

### 3. Testen
Im Repository: **Actions** → **Rennwochenende posten** → **Run workflow**.
Nach ein paar Sekunden sollte die Nachricht im Discord-Kanal erscheinen.

Ab dann läuft es jeden Donnerstag um 18:00 Uhr (Winterzeit) bzw. 19:00 Uhr (Sommerzeit).

## Rolle pingen (optional)

Bei jeder Session-Erinnerung wird eine bestimmte Rolle gepingt, z. B. `@Rennfans`.
Es wird **nur diese eine Rolle** erwähnt, niemals @everyone oder @here.

1. **Rollen-ID kopieren:** In Discord **Einstellungen → Erweitert → Entwicklermodus** einschalten.
   Dann **Servereinstellungen → Rollen**, Rechtsklick auf die Rolle → **Rollen-ID kopieren**.
2. **Rolle pingbar machen:** In den Einstellungen der Rolle
   **„Erlaube jedem, @mention für diese Rolle zu nutzen“** einschalten. Ohne diese Option
   zeigt Discord den Namen zwar an, schickt aber keine Benachrichtigung.
3. **Variable anlegen:** Auf GitHub unter **Settings → Secrets and variables → Actions →
   Variables** eine neue Repository-Variable `DISCORD_ROLLEN_ID` mit der kopierten Zahl anlegen
   (die Rollen-ID ist nicht geheim, deshalb Variable statt Secret).

### Pings nur in einem bestimmten Kanal
Ein Webhook schreibt immer nur in genau einen Kanal. Gepingt wird also nur dort, wo der
Webhook hingehört.

- **Alles in einem Kanal:** nichts weiter tun.
- **Erinnerungen mit Ping in einem eigenen Kanal** (z. B. `#session-alarm`), Übersicht
  weiter ohne Ping im normalen Kanal: In dem gewünschten Kanal einen zweiten Webhook anlegen
  und dessen URL als Secret `ERINNERUNGEN_WEBHOOK_URL` speichern.

Die Rolle zusätzlich bei der **Wochenübersicht** pingen: In `rennwochenende.yml` das `#` vor der
Zeile `DISCORD_ROLLEN_ID` entfernen.

## Einstellungen
**Wochenübersicht** – in `.github/workflows/rennwochenende.yml`:

| Variable | Bedeutung |
|---|---|
| `F1_TRAININGS: "nein"` | Blendet die freien Trainings (F1 + WEC) in der Übersicht aus |
| `LEERES_WOCHENENDE_POSTEN: "nein"` | An rennfreien Wochenenden wird nichts gepostet |
| `WEC_AUTOMATISCH: "nein"` | WEC nicht automatisch laden (dann selbst in `rennen.toml` pflegen) |
| `cron: "7 17 * * 4"` | Zeitpunkt (UTC). `4` = Donnerstag, `5` = Freitag |

**Session-Erinnerungen** – in `.github/workflows/session-erinnerungen.yml`:

| Variable | Bedeutung |
|---|---|
| `VORLAUF_MINUTEN: "30"` | Wie viele Minuten vor dem Start erinnert wird |

Der Bot prüft von Donnerstagmorgen bis Sonntagnacht alle 15 Minuten (jeweils zur Minute
:07/:22/:37/:52, weil GitHub Läufe zur vollen Stunde oft verspätet), welche Session bald
startet. Die Erinnerung kommt deshalb etwa 15–30 Minuten vor dem Start. Fällt ein Lauf aus,
wird bis 20 Minuten nach dem Start noch nachträglich erinnert. In `gepostet.json` merkt er sich, was
schon verschickt wurde, damit nichts doppelt kommt – diese Datei legt er selbst an.

Kosten: Bei einem **öffentlichen** Repository sind GitHub Actions unbegrenzt kostenlos
(die Webhook-URL bleibt trotzdem geheim, sie liegt in den Secrets). Bei einem **privaten**
Repository liegt der Verbrauch mit ca. 1.600 Minuten pro Monat unter dem kostenlosen
Kontingent von 2.000 Minuten.

## Rennen eintragen (`rennen.toml`)
```toml
[[rennen]]
serie    = "IMSA"
name     = "24 Stunden von Daytona"
strecke  = "Daytona International Speedway"
zeitzone = "America/New_York"
sessions = [
  { name = "Rennen (24 h)", start = "2027-01-23 13:40" },
]
```
Am einfachsten trägst du einmal zu Saisonbeginn alle Rennen ein, sobald die offiziellen
Zeitpläne da sind. Die Datei kannst du direkt auf GitHub im Browser bearbeiten.

## Lokal ausprobieren
```bash
python bot.py --dry-run                     # zeigt die Nachricht, ohne zu posten
python bot.py --dry-run --datum 2026-11-19  # für ein anderes Wochenende
python bot.py --erinnerungen --dry-run --jetzt "2026-11-07 11:40"   # Erinnerung testen
```
Benötigt Python 3.11 oder neuer, keine weiteren Pakete.
