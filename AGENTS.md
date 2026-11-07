# AGENTS.md – Übergabe für KI-Agenten

Diese Datei fasst zusammen, was in der bisherigen Unterhaltung mit dem Nutzer gebaut und
entschieden wurde, damit ein anderer Agent nahtlos weiterarbeiten kann.
Stand: 05.11.2026. Für die Einrichtung durch den Menschen siehe `README.md`.

## Update 05.11.2026 (zweite Sitzung)

- **WEC wird jetzt automatisch geladen** (`wec_events()`): Slugs `/en/race/<name>-<jahr>` von der
  fiawec.com-Startseite, pro Rennseite das JSON-LD `SportsEvent` mit `subEvent` (alle Sessions).
  Platzhalter (mehrere Sessions exakt 00:00/12:00) → `Session.bestaetigt=False`: Übersicht zeigt
  „Zeit folgt“, keine Erinnerung. Abschaltbar mit `WEC_AUTOMATISCH=nein`.
- Der frühere TOML-Eintrag „WEC Bahrain 07.11.2026“ war **falsch** (2026 gibt es kein Bahrain;
  am 06.–08.11.2026 läuft 6h Monza). Entfernt.
- `senden()`: `?wait=true`, Retry bei 429/5xx mit `Retry-After`; ein Fehler bricht die übrigen
  Erinnerungen nicht mehr ab. Toleranz nach hinten 20 min.
- Cron auf Minuten 7/22/37/52 (nicht :00), inzwischen täglich. `DISCORD_ROLLEN_ID` ist jetzt
  eine **Repository-Variable** (`vars.`), kein Secret. `F1_TRAININGS` in der Übersicht = `ja`.
- Live geprüft: Jolpica 2026 (Sprint-Wochenenden: `SprintQualifying` + `Sprint`), fiawec.com.
- Discord: eigener privater Kanal mit Webhook, gepingt wird eine eigene, erwähnbare Rolle
  (ID als Repository-Variable `DISCORD_ROLLEN_ID`). Nur Rollenmitglieder sehen den Kanal und dürfen
  lesen/reagieren, schreiben/verwalten dürfen nur Admins. Der Webhook postet unabhängig von
  Kanalrechten. Server-/Kanalnamen und IDs stehen bewusst nicht hier (öffentliches Repo).
- Weiterhin manuell: IMSA, GTWC (keine maschinenlesbaren Feeds mit Uhrzeiten gefunden).
- Windows lokal: `zoneinfo` braucht dort das Paket `tzdata` (auf dem Ubuntu-Runner nicht nötig).

## Update 06.11.2026: Erinnerungen robust gegen stündliche GitHub-Läufe

- Live beobachtet: GitHub startet den 15-min-Cron oft nur **ca. einmal pro Stunde**. Dadurch
  wurden WEC FP2 (14:30) und F1 FP1 (16:30) verpasst. F1 FP1 wurde nachträglich gepostet.
- Neu in `modus_erinnerungen()`: Fenster `[jetzt − NACHHOL_MINUTEN, jetzt + VORLAUF + WARTEN_MINUTEN)`.
  Zukünftige Sessions: Job wartet (`time.sleep`) bis Start − Vorlauf. Verpasste Sessions bis
  60 min nach Start → Nachricht „🟢 Läuft bereits“. `gepostet.json` wird nach jedem Post gespeichert.
  Workflow `timeout-minutes: 80`. Kosten: wartende Jobs verbrauchen Actions-Minuten (privates
  Repo: 2.000 frei/Monat) – bei Engpass Repo öffentlich machen oder externen Trigger nutzen.

## Update 06.11.2026 (abends): Lücken aus der Abdeckungsprüfung behoben

- Prüfung per Sub-Agent: F1 2026 und WEC Monza vollständig abgedeckt. F1 FP2 Brasilien kam
  pünktlich 19:30 (Warte-Logik live bestätigt).
- **Cron jetzt täglich** (`7,22,37,52 * * * *`), vorher nur Do–So → Mittwochs-Sessions
  (Le Mans, Sebring, Petit Le Mans) wären nie erinnert worden. Repo ist **öffentlich**, Minuten gratis.
- **Quellen einzeln abgesichert:** `alle_events()` fängt pro Quelle jede Exception ab;
  `_http_text`-Aufrufer fangen `OSError`/`http.client.HTTPException` (vorher killte z. B.
  `ConnectionResetError` bei fiawec.com auch F1). ld+json-Listen werden ignoriert.
- **F1 ohne Uhrzeit** (`time` fehlt in Jolpica) → `_f1_session()` legt Session mit
  `bestaetigt=False` an (Übersicht „Zeit folgt“, keine Erinnerung) statt 00:00 UTC.
- Weiterhin offen: IMSA/GTWC haben in `rennen.toml` nur Daten, **keine Uhrzeiten** → keine
  Erinnerungen, bis offizielle Zeitpläne eingetragen sind. Push-Fehler von `gepostet.json`
  kann zu Doppel-Post führen (kein Retry).

## Update 07.11.2026: Nachrichten automatisch löschen (Wunsch des Nutzers)

- Erinnerungen werden **60 min nach Ende der Session** gelöscht, die Wochenübersicht **60 min
  nach Ende der letzten Session des Wochenendes** (ohne Sessions: Mo 00:00).
- `senden()` liefert die Discord-Antwort (`?wait=true` → `id`). Löschen per
  `DELETE <webhook>/messages/<id>` (`nachricht_loeschen()`, 404 = schon weg).
- Ende = Start + Dauer aus `session_ende()`: `F1_DAUER`, `ANDERE_DAUER` (Regex auf Session-Namen),
  Rennen anderer Serien: Stunden aus Eventname („6 Stunden“, „24 Hours“, „Rolex 24“), sonst 180.
  In `rennen.toml` optional `dauer = <Minuten>` pro Session.
- Dateien, getrennt nach Schreiber (damit sich die Workflows nicht in die Quere kommen):
  `loeschen.json` (nur Erinnerungs-Workflow: `offen` ID → {ab, webhook-Variable}, `erledigt`
  = gelöschte Übersichts-IDs) und `uebersicht.json` (nur Übersichts-Workflow: id, loeschen_ab).
  `rennwochenende.yml` hat dafür `contents: write` und einen Commit-Schritt.
- Gelöscht wird zu Beginn jedes Erinnerungs-Laufs (`alte_nachrichten_loeschen()`), also bei
  stündlichen Läufen bis ~1 h später. Schalter: `LOESCHEN`, `LOESCHEN_NACH_MINUTEN`.
- Nachrichten von vor dieser Änderung haben keine gespeicherte ID und werden **nicht** gelöscht.
- Getestet gegen einen nachgebauten Webhook (POST/DELETE), nicht gegen echtes Discord.

## Ziel des Projekts (Wünsche des Nutzers)

Der Nutzer (deutschsprachig, Zeitzone Europe/Berlin) wollte einen Discord-Bot, der:

1. **Jede Woche** eine Nachricht schickt, welche Rennen am Wochenende laufen –
   **Formel 1, FIA WEC, IMSA, GT World Challenge** – mit Uhrzeiten in **Berliner Zeit**. ✅
2. **Jede einzelne Session** (FP1, FP2, FP3, Qualifying …) zusätzlich als **eigene
   Nachricht** schickt. ✅ Umgesetzt als Erinnerung kurz vor dem Start (Standard 30 min).
3. Bei diesen Nachrichten eine **bestimmte Rolle pingt**, und zwar **nur in einem Kanal**
   eines Servers. ✅ Über `DISCORD_ROLLEN_ID` + optional eigenen Webhook für die Erinnerungen.

Alle Texte, Nachrichten, Kommentare und Variablennamen sind **auf Deutsch**. Das bitte beibehalten.

## Architektur-Entscheidungen

- **Kein dauerhaft laufender Bot**, sondern ein Python-Skript, das über **Discord-Webhooks**
  postet und per **GitHub Actions (cron)** läuft. Grund: kein Server/Hosting nötig, kostenlos.
  Folge: Es gibt keine Slash-Commands und keine Interaktion. Dafür wäre ein echter Bot
  (z. B. discord.py) mit Hosting nötig.
- **Nur Python-Standardbibliothek** (Python ≥ 3.11 wegen `tomllib`). Keine `requirements.txt`.
  Bitte keine Abhängigkeiten einführen, ohne den Workflow anzupassen.
- **Formel 1** kommt automatisch aus der freien **Jolpica-F1-API** (Ergast-Nachfolger, kein Key):
  `https://api.jolpi.ca/ergast/f1/{jahr}/races/?limit=100`. Zeiten dort sind UTC.
- **WEC, IMSA, GTWC** haben keine freie, zuverlässige API. Sie werden **manuell in
  `rennen.toml`** gepflegt, mit Ortszeit + IANA-Zeitzone. Der Bot rechnet nach Berlin um.
  Recherchiert wurde: Das PyPI-Paket `motorsport-calendar` scrapt WEC/GTWC-HTML, hat aber
  **kein IMSA**. Deshalb wurde es nicht verwendet.
- **Doppelte Erinnerungen** werden über `gepostet.json` verhindert. Der Workflow committet die
  Datei nach jedem Lauf zurück ins Repo (`permissions: contents: write`, `concurrency`-Gruppe).

## Dateien

| Datei | Inhalt |
|---|---|
| `bot.py` | Gesamte Logik (~370 Zeilen). Zwei Modi: Wochenübersicht (Standard) und `--erinnerungen`. |
| `rennen.toml` | Manueller Kalender für WEC/IMSA/GTWC. Enthält aktuell nur WEC Bahrain + kommentierte Vorlagen. |
| `.github/workflows/rennwochenende.yml` | Wochenübersicht, Do 17:00 UTC (`0 17 * * 4`). |
| `.github/workflows/session-erinnerungen.yml` | Erinnerungen, täglich alle 15 min (:07/:22/:37/:52 UTC). Committet `gepostet.json`. |
| `README.md` | Einrichtungsanleitung für den Nutzer (Webhook, Secrets, Rolle, Einstellungen). |
| `gepostet.json` | Wird zur Laufzeit erzeugt: `{"SERIE|Event|Session|ISO-Start": "ISO-Start"}`, Einträge > 7 Tage werden gelöscht. |

## Aufbau von `bot.py`

- Datenmodell: `Session(name, start, training)` und `Event(serie, name, strecke, sessions)`.
  `start` ist **immer** ein zeitzonen-bewusstes `datetime` in `Europe/Berlin`.
- Quellen: `f1_events(jahre)` lädt alle F1-Wochenenden mit allen Sessions.
  `datei_events(pfad)` liest `rennen.toml`. `alle_events()` kombiniert beide.
- `filtern(events, von, bis, mit_trainings)` behält nur Sessions in `[von, bis)`.
- Übersicht: `wochenende(heute)` liefert Fr 00:00 bis Mo 00:00. `uebersicht()` baut einen
  Embed pro Event (max. 10). F1-Trainings werden nur bei `F1_TRAININGS=ja` gezeigt.
- Erinnerungen: `modus_erinnerungen()` sucht Sessions mit Start in
  `[jetzt − 15 min, jetzt + VORLAUF_MINUTEN)`, die noch nicht in `gepostet.json` stehen.
  Pro Session wird **eine eigene Nachricht** geschickt (`erinnerung()`), mit 1 s Pause dazwischen.
  Der Status wird erst nach erfolgreichem Senden gespeichert.
  Die Nachricht enthält einen Discord-Zeitstempel `<t:unix:R>` („in 25 Minuten“).
- Ping: `mit_ping()` setzt `<@&ROLLEN_ID>` in `content` und setzt **immer**
  `allowed_mentions` (`parse: []`, nur diese eine Rolle). Ohne Rolle wird niemand gepingt.
- F1-Session-Namen: FP1, FP2, FP3, Sprint-Qualifying, Sprint, Qualifying, Rennen
  (Mapping `F1_SESSIONS`, deckt alte `SprintShootout` und neue `SprintQualifying` ab).

## Konfiguration (Umgebungsvariablen / GitHub-Secrets)

| Name | Wo | Bedeutung |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Secret, **Pflicht** | Haupt-Webhook (Übersicht und Fallback für Erinnerungen) |
| `ERINNERUNGEN_WEBHOOK_URL` | Secret, optional | Eigener Kanal für Erinnerungen + Ping |
| `DISCORD_ROLLEN_ID` | Secret, optional | Zu pingende Rolle. Wirkt standardmäßig nur bei Erinnerungen, in `rennwochenende.yml` auskommentiert |
| `VORLAUF_MINUTEN` | Workflow, Standard `30` | Vorlauf der Erinnerungen |
| `F1_TRAININGS` | Workflow, Standard `nein` | F1-Trainings in der Wochenübersicht |
| `LEERES_WOCHENENDE_POSTEN` | Workflow, Standard `ja` | Bei rennfreiem Wochenende trotzdem posten |

Ja/Nein-Werte akzeptieren `ja/true/yes/1`.

## Testen

```bash
python bot.py --dry-run --datum 2026-11-05                         # Übersicht
python bot.py --erinnerungen --dry-run --jetzt "2026-11-07 11:40"  # Erinnerung (WEC Bahrain)
DISCORD_ROLLEN_ID=123456789012345678 python bot.py --erinnerungen --dry-run --jetzt "2026-11-07 11:40"
```
`--dry-run` gibt nur das JSON aus, sendet nichts und schreibt **keine** `gepostet.json`.

**Was getestet wurde:** Formatierung, Umrechnung UTC/Ortszeit → Berlin, Wochenendfenster,
Erinnerungsfenster, Schutz gegen Doppel-Posts, Rollen-Ping und `allowed_mentions`, ungültige
Rollen-ID. Die Workflow-YAMLs sind syntaktisch geprüft. Für F1 wurde eine **nachgebaute**
API-Antwort verwendet.

**Was NICHT getestet wurde** (die Entwicklungsumgebung hatte keinen Netzzugang):
- Echter Abruf der Jolpica-API: Feldnamen/Struktur gegen eine Live-Antwort prüfen.
- Echtes Senden an Discord und echte GitHub-Actions-Läufe inkl. `git push` von `gepostet.json`.

## Offene Punkte / bekannte Einschränkungen

- **`rennen.toml` ist fast leer.** Nur WEC 8h Bahrain (07.11.2026, Start 14:00 Ortszeit
  angenommen nach Vorjahren, **nicht bestätigt**) ist eingetragen. Die Kalender für 2027
  (WEC, IMSA, GTWC Europe/America/Asia?) müssen ergänzt werden, sobald sie veröffentlicht sind.
  Eintragen bitte nur aus offiziellen Quellen, keine Zeiten raten.
  Unklar: Welche GTWC-Regionen der Nutzer will. Bisher ist nur „GTWC“ als eine Serie vorgesehen.
- **GitHub-Cron ist ungenau** (oft einige Minuten Verspätung). Deshalb gibt es das
  Warte- und Nachhol-Fenster (siehe Updates oben). Cron läuft inzwischen täglich.
- **Kontingent:** Repo ist öffentlich, Actions-Minuten unbegrenzt. Bei privatem Repo würde
  der tägliche Cron das freie Kontingent (2.000/Monat) voraussichtlich überschreiten.
- GitHub deaktiviert geplante Workflows nach 60 Tagen ohne Repo-Aktivität. Die automatischen
  Commits von `gepostet.json` sollten das verhindern. Nicht verifiziert.
- Max. 10 Embeds pro Übersicht (Discord-Limit). Weitere Events werden abgeschnitten.

## Vom Nutzer angedeutete / angebotene nächste Schritte

- Eine **eigene Rolle pro Serie** (z. B. `@F1`, `@WEC`) – angeboten, noch nicht gebaut.
  Naheliegend: `DISCORD_ROLLEN_IDS` als Mapping, z. B. `F1=123,WEC=456`.
- Kalender 2027 in `rennen.toml` eintragen.
- Bei Bedarf Umstieg auf einen echten Bot (Slash-Commands wie `/naechstes-rennen`),
  dann wäre aber Hosting nötig.
