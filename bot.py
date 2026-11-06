#!/usr/bin/env python3
"""
Rennwochenende-Bot für Discord
------------------------------
1. Wochenübersicht: postet die Rennen des kommenden Wochenendes (Fr–So).
2. Session-Erinnerungen: postet für JEDE Session (FP1, FP2, FP3, Qualifying,
   Sprint, Rennen …) eine eigene Nachricht kurz vor dem Start.

Alle Uhrzeiten in Berliner Zeit.

- Formel 1: wird automatisch über die freie Jolpica-F1-API geladen.
- FIA WEC: wird automatisch von fiawec.com geladen (strukturierte Daten der Rennseiten).
- IMSA, GT World Challenge: kommen aus der Datei rennen.toml.

Benötigt nur Python 3.11+ (keine zusätzlichen Pakete).

Aufruf:
    python bot.py                         # Wochenübersicht posten
    python bot.py --erinnerungen          # Erinnerungen für bald startende Sessions posten
    python bot.py --dry-run               # nur anzeigen, nichts senden
    python bot.py --datum 2026-11-05      # Übersicht für ein anderes Wochenende
    python bot.py --erinnerungen --jetzt "2026-11-07 11:40" --dry-run   # Erinnerung testen
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time as zeit
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")
HIER = Path(__file__).resolve().parent
STATUS_DATEI = HIER / "gepostet.json"

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

# Anzeige-Infos pro Serie (Name, Emoji, Farbe des Discord-Embeds)
SERIEN = {
    "F1":   {"name": "Formel 1",           "emoji": "🏎️", "farbe": 0xE10600},
    "WEC":  {"name": "FIA WEC",            "emoji": "🏆", "farbe": 0x00A3E0},
    "IMSA": {"name": "IMSA",               "emoji": "🇺🇸", "farbe": 0x1B365D},
    "GTWC": {"name": "GT World Challenge", "emoji": "🏁", "farbe": 0xF5A800},
}

# F1-Sessions aus der API -> Anzeigename, ist_training
F1_SESSIONS = [
    ("FirstPractice",    "FP1",               True),
    ("SecondPractice",   "FP2",               True),
    ("ThirdPractice",    "FP3",               True),
    ("SprintQualifying", "Sprint-Qualifying", False),
    ("SprintShootout",   "Sprint-Qualifying", False),
    ("Sprint",           "Sprint",            False),
    ("Qualifying",       "Qualifying",        False),
]


USER_AGENT = "rennwochenende-bot/1.2 (Discord-Webhook-Skript)"
WEC_BASIS = "https://www.fiawec.com"

# WEC-Session-Namen (englisch von fiawec.com) -> deutsch
WEC_UEBERSETZUNG = [
    (r"^Free Practice (\d+)$", r"FP\1"),
    (r"^Race$", "Rennen"),
    (r"^Warm-up$", "Warm-up"),
]


@dataclass
class Session:
    name: str
    start: datetime          # immer in Berliner Zeit
    training: bool = False
    bestaetigt: bool = True  # False = Uhrzeit vom Veranstalter noch nicht veröffentlicht


@dataclass
class Event:
    serie: str
    name: str
    strecke: str = ""
    sessions: list[Session] = field(default_factory=list)

    @property
    def erster_start(self) -> datetime:
        return min(s.start for s in self.sessions)


def ja(wert: str | None, standard: bool) -> bool:
    if wert is None:
        return standard
    return wert.strip().lower() in ("1", "ja", "true", "yes")


# ---------------------------------------------------------------------------
# Datenquellen
# ---------------------------------------------------------------------------
def _http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _http_json(url: str) -> dict:
    return json.loads(_http_text(url))


def _f1_session(name: str, d: str, t: str | None, training: bool = False) -> Session:
    """F1-Session aus Datum + Uhrzeit (UTC). Fehlt die Uhrzeit, ist sie noch nicht bestätigt."""
    if not t:
        return Session(name, datetime.combine(date.fromisoformat(d), time(12, 0), BERLIN),
                       training, bestaetigt=False)
    start = datetime.fromisoformat(f"{d}T{t.replace('Z', '')}").replace(tzinfo=UTC)
    return Session(name, start.astimezone(BERLIN), training)


def f1_events(jahre: set[int]) -> list[Event]:
    """Alle F1-Wochenenden der angegebenen Jahre mit allen Sessions."""
    events: list[Event] = []
    for jahr in sorted(jahre):
        url = f"https://api.jolpi.ca/ergast/f1/{jahr}/races/?limit=100"
        try:
            rennen = _http_json(url)["MRData"]["RaceTable"]["Races"]
        except (OSError, http.client.HTTPException, KeyError, ValueError) as e:
            print(f"⚠️  F1-Kalender {jahr} konnte nicht geladen werden: {e}", file=sys.stderr)
            continue
        for r in rennen:
            sessions = []
            for feld, anzeige, ist_training in F1_SESSIONS:
                if feld in r:
                    s = r[feld]
                    sessions.append(_f1_session(anzeige, s["date"], s.get("time"), ist_training))
            sessions.append(_f1_session("Rennen", r["date"], r.get("time")))
            strecke = r.get("Circuit", {}).get("circuitName", "")
            events.append(Event("F1", r["raceName"].replace("Grand Prix", "GP"), strecke, sessions))
    return events


def _wec_session_name(roh: str, eventname: str) -> str:
    """'Qualifying - HYPERCAR - 6 Hours of Monza' -> 'Qualifying Hypercar'."""
    teile = [t.strip() for t in roh.split(" - ")]
    if teile and teile[-1] == eventname:
        teile = teile[:-1]
    if not teile:
        return roh
    haupt = teile[0]
    for muster, ersatz in WEC_UEBERSETZUNG:
        haupt = re.sub(muster, ersatz, haupt)
    klassen = [k.replace("HYPERCAR", "Hypercar") for k in teile[1:]]
    return " ".join([haupt, *klassen])


def _wec_eventname_deutsch(name: str) -> str:
    """'6 Hours of Monza' -> '6 Stunden von Monza'."""
    name = re.sub(r"(\d+) Hours of ", r"\1 Stunden von ", name)
    return name


def wec_events(jahre: set[int]) -> list[Event]:
    """WEC-Rennen der angegebenen Jahre automatisch von fiawec.com.

    Jede Rennseite enthält strukturierte Daten (schema.org SportsEvent) mit allen Sessions.
    Solange der Zeitplan nicht veröffentlicht ist, stehen dort Platzhalter (mehrere Sessions
    exakt um 00:00 bzw. 12:00) – diese Sessions werden als unbestätigt markiert.
    """
    try:
        startseite = _http_text(f"{WEC_BASIS}/en/")
    except (OSError, http.client.HTTPException) as e:
        print(f"⚠️  WEC-Kalender konnte nicht geladen werden: {e}", file=sys.stderr)
        return []

    slugs = sorted({m for m in re.findall(r"/en/race/([a-z0-9\-]+-(\d{4}))", startseite)
                    if int(m[1]) in jahre and "prologue" not in m[0]})
    events: list[Event] = []
    for slug, _ in slugs:
        try:
            seite = _http_text(f"{WEC_BASIS}/en/race/{slug}")
            daten = None
            for block in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', seite):
                kandidat = json.loads(block)
                if isinstance(kandidat, dict) and kandidat.get("@type") == "SportsEvent" and kandidat.get("subEvent"):
                    daten = kandidat
                    break
            if daten is None:
                continue
            eventname = re.sub(r"^WEC\s+|\s+\d{4}$", "", daten["name"]).strip()
            roh = []
            for sub in daten["subEvent"]:
                if "Cancelled" in sub.get("eventStatus", ""):
                    continue
                start = datetime.fromisoformat(sub["startDate"])
                roh.append((_wec_session_name(sub["name"], eventname), start))
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as e:
            print(f"⚠️  WEC-Rennen {slug} konnte nicht gelesen werden: {e}", file=sys.stderr)
            continue

        # Platzhalter erkennen: gleiche Uhrzeit 00:00/12:00 bei mehreren Sessions
        haeufigkeit: dict[time, int] = {}
        for _, start in roh:
            haeufigkeit[start.time()] = haeufigkeit.get(start.time(), 0) + 1
        sessions = []
        for name, start in roh:
            uhr = start.time()
            platzhalter = uhr in (time(0, 0), time(12, 0)) and haeufigkeit.get(uhr, 0) > 1
            sessions.append(Session(name, start.astimezone(BERLIN),
                                    training=name.startswith(("FP", "Warm-up")),
                                    bestaetigt=not platzhalter))
        if sessions:
            strecke = daten.get("location", {}).get("name", "")
            events.append(Event("WEC", _wec_eventname_deutsch(eventname), strecke, sessions))
    return events


def datei_events(pfad: Path) -> list[Event]:
    """Alle Einträge aus rennen.toml."""
    if not pfad.exists():
        print(f"⚠️  {pfad.name} nicht gefunden – nur F1 wird geprüft.", file=sys.stderr)
        return []
    with pfad.open("rb") as f:
        daten = tomllib.load(f)

    events = []
    for eintrag in daten.get("rennen", []):
        tz = ZoneInfo(eintrag.get("zeitzone", "Europe/Berlin"))
        sessions = []
        for s in eintrag.get("sessions", []):
            if len(s["start"].strip()) == 10:
                # Nur Datum ("JJJJ-MM-TT"): Uhrzeit noch nicht veröffentlicht
                tag = date.fromisoformat(s["start"].strip())
                sessions.append(Session(s["name"], datetime.combine(tag, time(12, 0), BERLIN),
                                        bestaetigt=False))
                continue
            lokal = datetime.strptime(s["start"], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            sessions.append(Session(s["name"], lokal.astimezone(BERLIN)))
        if not sessions and "datum_bis" in eintrag:
            # Nur Termin des Wochenendes bekannt, noch kein Zeitplan
            von = date.fromisoformat(str(eintrag.get("datum_von", eintrag["datum_bis"])))
            bis = date.fromisoformat(str(eintrag["datum_bis"]))
            text = f"Wochenende {von:%d.%m.}–{bis:%d.%m.}, Zeitplan folgt"
            sessions.append(Session(text, datetime.combine(bis, time(12, 0), BERLIN),
                                    bestaetigt=False))
        if not sessions:
            continue
        events.append(Event(eintrag["serie"].upper(), eintrag["name"],
                            eintrag.get("strecke", ""), sessions))
    return events


def alle_events(von: datetime, bis: datetime, datei: Path) -> list[Event]:
    """Alle Quellen laden. Fällt eine Quelle aus, laufen die anderen trotzdem weiter."""
    jahre = {von.year, bis.year}
    quellen = [("F1", lambda: f1_events(jahre)), (datei.name, lambda: datei_events(datei))]
    if ja(os.getenv("WEC_AUTOMATISCH"), True):
        quellen.append(("WEC", lambda: wec_events(jahre)))
    events: list[Event] = []
    for name, laden in quellen:
        try:
            events += laden()
        except Exception as e:  # bewusst breit: eine kaputte Quelle darf die anderen nicht stoppen
            print(f"⚠️  Quelle {name} übersprungen ({type(e).__name__}: {e})", file=sys.stderr)
    return events


def filtern(events: list[Event], von: datetime, bis: datetime,
            mit_trainings: bool = True) -> list[Event]:
    """Nur Sessions im Zeitfenster [von, bis); Events ohne passende Session fallen weg."""
    ergebnis = []
    for e in events:
        sessions = [s for s in e.sessions
                    if von <= s.start < bis and (mit_trainings or not s.training)]
        if sessions:
            ergebnis.append(Event(e.serie, e.name, e.strecke, sessions))
    return ergebnis


def tage_filtern(events: list[Event], von: datetime, bis: datetime,
                 mit_trainings: bool = True) -> list[Event]:
    """Wie filtern(), aber unbestätigte Sessions zählen nach Kalendertag (Uhrzeit ist Platzhalter)."""
    ergebnis = []
    for e in events:
        sessions = []
        for s in e.sessions:
            if not (mit_trainings or not s.training):
                continue
            if s.bestaetigt:
                if von <= s.start < bis:
                    sessions.append(s)
            elif von.date() <= s.start.date() < bis.date():
                sessions.append(s)
        if sessions:
            ergebnis.append(Event(e.serie, e.name, e.strecke, sessions))
    return ergebnis


# ---------------------------------------------------------------------------
# Formatierung
# ---------------------------------------------------------------------------
def serien_info(serie: str) -> dict:
    return SERIEN.get(serie, {"name": serie, "emoji": "🏁", "farbe": 0x888888})


def wochenende(heute: date) -> tuple[datetime, datetime]:
    """Freitag 00:00 bis Montag 00:00 (Berliner Zeit) des aktuellen/nächsten Wochenendes."""
    wd = heute.weekday()  # Mo=0 ... So=6
    freitag = heute - timedelta(days=wd - 4) if wd >= 4 else heute + timedelta(days=4 - wd)
    start = datetime.combine(freitag, time(0, 0), BERLIN)
    return start, start + timedelta(days=3)


def zeitraum_text(start: datetime) -> str:
    fr, so = start.date(), start.date() + timedelta(days=2)
    if fr.month == so.month:
        return f"{fr.day}.–{so.day}. {MONATE[so.month - 1]} {so.year}"
    return f"{fr.day}. {MONATE[fr.month - 1]} – {so.day}. {MONATE[so.month - 1]} {so.year}"


def session_zeile(s: Session) -> str:
    tag = WOCHENTAGE[s.start.weekday()]
    fett = s.name.startswith("Rennen") or s.name == "Sprint"
    name = f"**{s.name}**" if fett else s.name
    if not s.bestaetigt and "Zeitplan folgt" in s.name:
        return f"🗓️ {s.name}"
    if not s.bestaetigt:
        return f"`{tag} {s.start:%d.%m.} · --:--` {name} *(Zeit folgt)*"
    return f"`{tag} {s.start:%d.%m.} · {s.start:%H:%M}` {name}"


def uebersicht(events: list[Event], start: datetime, leer_posten: bool) -> dict | None:
    kopf = f"## 🏁 Rennwochenende {zeitraum_text(start)}\n*Alle Zeiten in Berliner Zeit*"
    if not events:
        if not leer_posten:
            return None
        return {"content": f"{kopf}\n\nDieses Wochenende stehen keine Rennen in F1, WEC, IMSA "
                           f"oder GT World Challenge an. 😴"}

    events.sort(key=lambda e: e.erster_start)
    embeds = []
    for e in events[:10]:  # Discord erlaubt max. 10 Embeds pro Nachricht
        info = serien_info(e.serie)
        beschreibung = "\n".join(session_zeile(s) for s in sorted(e.sessions, key=lambda s: s.start))
        if e.strecke:
            beschreibung = f"📍 {e.strecke}\n{beschreibung}"
        embeds.append({
            "title": f"{info['emoji']} {info['name']} – {e.name}",
            "description": beschreibung,
            "color": info["farbe"],
        })
    return {"content": kopf, "embeds": embeds}


def erinnerung(e: Event, s: Session, laeuft_bereits: bool = False) -> dict:
    info = serien_info(e.serie)
    unix = int(s.start.timestamp())
    tag = WOCHENTAGE[s.start.weekday()]
    zeilen = [
        f"🕒 **{tag} {s.start:%d.%m.} · {s.start:%H:%M} Uhr** (Berliner Zeit)",
        # Discord zeigt das als „in 30 Minuten“ bzw. „vor 20 Minuten“ an
        f"🟢 **Läuft bereits** – gestartet <t:{unix}:R>" if laeuft_bereits
        else f"⏳ Start <t:{unix}:R>",
    ]
    if e.strecke:
        zeilen.append(f"📍 {e.strecke}")
    return {
        "embeds": [{
            "title": f"{info['emoji']} {info['name']} – {e.name}: {s.name}",
            "description": "\n".join(zeilen),
            "color": info["farbe"],
        }]
    }


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
def senden(webhook: str, payload: dict, versuche: int = 4) -> None:
    """Postet an den Webhook. ?wait=true sorgt dafür, dass Discord Fehler zurückmeldet.
    Bei Rate-Limit (429) oder Serverfehlern (5xx) wird mit Pause erneut versucht."""
    url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    daten = json.dumps(payload).encode()
    for versuch in range(1, versuche + 1):
        req = urllib.request.Request(
            url, data=daten, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=20):
                return
        except urllib.error.HTTPError as e:
            if versuch < versuche and (e.code == 429 or e.code >= 500):
                pause = 2.0 * versuch
                try:
                    pause = max(pause, float(e.headers.get("Retry-After", 0)))
                except ValueError:
                    pass
                print(f"⚠️  Discord {e.code}, neuer Versuch in {pause:.0f} s …", file=sys.stderr)
                zeit.sleep(min(pause, 60))
                continue
            text = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Discord antwortete mit Status {e.code}: {text}") from None


def webhook_url(*namen: str) -> str:
    """Erste gesetzte Webhook-URL aus den angegebenen Umgebungsvariablen."""
    for name in (*namen, "DISCORD_WEBHOOK_URL"):
        url = (os.getenv(name) or "").strip()
        if url:
            return url
    print("❌ DISCORD_WEBHOOK_URL ist nicht gesetzt.", file=sys.stderr)
    sys.exit(1)


def rollen_id() -> str | None:
    """Rollen-ID aus DISCORD_ROLLEN_ID (leer = niemand wird gepingt)."""
    wert = (os.getenv("DISCORD_ROLLEN_ID") or "").strip().removeprefix("<@&").removesuffix(">")
    if not wert:
        return None
    if not wert.isdigit():
        print(f"⚠️  DISCORD_ROLLEN_ID '{wert}' ist keine gültige ID – es wird nicht gepingt.",
              file=sys.stderr)
        return None
    return wert


def mit_ping(payload: dict, rolle: str | None) -> dict:
    """Setzt den Rollen-Ping vor die Nachricht und erlaubt NUR diese eine Erwähnung."""
    if rolle:
        alt = payload.get("content", "")
        payload["content"] = f"<@&{rolle}>" + (f"\n{alt}" if alt else "")
        payload["allowed_mentions"] = {"parse": [], "roles": [rolle]}
    else:
        payload["allowed_mentions"] = {"parse": []}  # sicherstellen, dass niemand gepingt wird
    return payload


# ---------------------------------------------------------------------------
# Modi
# ---------------------------------------------------------------------------
def modus_uebersicht(args) -> int:
    heute = date.fromisoformat(args.datum) if args.datum else datetime.now(BERLIN).date()
    start, ende = wochenende(heute)
    mit_trainings = ja(os.getenv("F1_TRAININGS"), False)
    leer_posten = ja(os.getenv("LEERES_WOCHENENDE_POSTEN"), True)

    events = tage_filtern(alle_events(start, ende, Path(args.datei)), start, ende, mit_trainings)
    payload = uebersicht(events, start, leer_posten)

    if payload is None:
        print("Keine Rennen an diesem Wochenende – nichts gepostet.")
        return 0
    payload = mit_ping(payload, rollen_id())
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    senden(webhook_url(), payload)
    print(f"✅ Wochenübersicht mit {len(events)} Event(s) gepostet.")
    return 0


def status_laden() -> dict[str, str]:
    try:
        return json.loads(STATUS_DATEI.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def status_speichern(status: dict[str, str], jetzt: datetime) -> None:
    grenze = jetzt - timedelta(days=7)  # alte Einträge aufräumen
    status = {k: v for k, v in status.items() if datetime.fromisoformat(v) >= grenze}
    STATUS_DATEI.write_text(json.dumps(status, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")


def modus_erinnerungen(args) -> int:
    jetzt = (datetime.strptime(args.jetzt, "%Y-%m-%d %H:%M").replace(tzinfo=BERLIN)
             if args.jetzt else datetime.now(BERLIN))
    vorlauf = timedelta(minutes=int(os.getenv("VORLAUF_MINUTEN", "30")))
    # GitHub startet geplante Läufe oft nur etwa einmal pro Stunde statt alle 15 Minuten.
    # Deshalb: (1) verpasste Sessions bis NACHHOL_MINUTEN nach dem Start nachträglich posten,
    # (2) Sessions, die erst nach dem Vorlauf dran sind, bis WARTEN_MINUTEN vorausschauen und
    #     im laufenden Job bis zum richtigen Zeitpunkt (Start − Vorlauf) warten.
    nachholen = timedelta(minutes=int(os.getenv("NACHHOL_MINUTEN", "60")))
    warten_max = timedelta(minutes=int(os.getenv("WARTEN_MINUTEN", "50")))
    von, bis = jetzt - nachholen, jetzt + vorlauf + warten_max

    faellig = filtern(alle_events(von, bis, Path(args.datei)), von, bis)
    status = status_laden()
    offen = []
    for e in faellig:
        for s in e.sessions:
            if not s.bestaetigt:
                continue  # Uhrzeit ist nur ein Platzhalter – keine Erinnerung
            schluessel = f"{e.serie}|{e.name}|{s.name}|{s.start.isoformat()}"
            if schluessel not in status:
                offen.append((schluessel, e, s))
    offen.sort(key=lambda x: x[2].start)

    if not offen:
        print("Keine neuen Sessions in den nächsten Minuten.")
        return 0

    webhook = None if args.dry_run else webhook_url("ERINNERUNGEN_WEBHOOK_URL")
    rolle = rollen_id()
    fehler = 0
    for schluessel, e, s in offen:
        ziel = s.start - vorlauf  # gewünschter Zeitpunkt der Erinnerung
        if args.dry_run or args.jetzt:
            aktuell = jetzt
            if ziel > aktuell:
                print(f"⏸️  würde bis {ziel:%H:%M} warten: {e.serie} {e.name} – {s.name}")
                aktuell = ziel
        else:
            warte = (ziel - datetime.now(BERLIN)).total_seconds()
            if warte > 0:
                print(f"⏸️  Warte {warte / 60:.0f} min bis {ziel:%H:%M}: {e.serie} {e.name} – {s.name}",
                      flush=True)
                zeit.sleep(warte)
            aktuell = datetime.now(BERLIN)
        payload = mit_ping(erinnerung(e, s, laeuft_bereits=s.start <= aktuell), rolle)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            continue
        try:
            senden(webhook, payload)
        except (RuntimeError, urllib.error.URLError, TimeoutError) as fehlermeldung:
            # Nicht abbrechen: die anderen Sessions trotzdem posten, diese beim nächsten Lauf erneut
            print(f"❌ {e.serie} {e.name} – {s.name}: {fehlermeldung}", file=sys.stderr)
            fehler += 1
            continue
        status[schluessel] = s.start.isoformat()
        status_speichern(status, jetzt)  # sofort merken, falls der Job später abbricht
        print(f"✅ Erinnerung gepostet: {e.serie} {e.name} – {s.name}", flush=True)
        zeit.sleep(1)  # Discord-Limit freundlich behandeln

    if not args.dry_run:
        status_speichern(status, jetzt)
    return 1 if fehler else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Rennwochenende-Bot für Discord")
    p.add_argument("--erinnerungen", action="store_true",
                   help="Erinnerungen für bald startende Sessions posten")
    p.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht senden")
    p.add_argument("--datum", help="Übersicht: Stichtag JJJJ-MM-TT (Standard: heute)")
    p.add_argument("--jetzt", help='Erinnerungen: so tun, als wäre es "JJJJ-MM-TT HH:MM" (Berlin)')
    p.add_argument("--datei", default=str(HIER / "rennen.toml"), help="Pfad zur Renn-Datei")
    args = p.parse_args()
    return modus_erinnerungen(args) if args.erinnerungen else modus_uebersicht(args)


if __name__ == "__main__":
    sys.exit(main())
