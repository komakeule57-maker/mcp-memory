#!/usr/bin/env python3
"""Uebernimmt ein Datei-Memory (ein Ordner voller *.md) in die memory.db.

Absatzweise, weil das gemessen die brauchbare Koernung ist: ganze Dateien als
je ein Eintrag liefern bei limit=10 rund 261 KB zurueck statt 5,7 KB.

Mehrfach aufrufbar - bereits vorhandene Absaetze werden uebersprungen.

Geschrieben wird in `eintrag`, den Speicher ab Schemastand 5; den FTS-Index
`suche` ziehen die Trigger nach. Die neuen Eintraege tragen die Art 'gemischt'
und bekommen sie beim Lesen per einordnen().

    python3 import_memos.py [ordner] [--trocken] [--mit-index]

--mit-index nimmt zusaetzlich MEMORY.md auf, und zwar zeilenweise statt
absatzweise: jeder Listenpunkt ist ein eigener Eintrag. Das ist noetig, bevor
man den Index kuerzt - manche Fakten stehen NUR dort und in keiner Memo-Datei.
Danach nicht mehr verwenden: die gekuerzten Zeilen kaemen sonst zusaetzlich zu
den ausfuehrlichen in die Datenbank, ohne etwas beizutragen.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import memory_server as ms
from morphologie import stamm_spalte, teile_spalte

# Claude Code legt sein Datei-Gedaechtnis unter ~/.claude/projects/<projekt>/memory
# ab, wobei <projekt> der Arbeitsordner mit Schraegstrichen als Bindestrich ist.
# Ohne Argument wird daraus der Ordner fuer das aktuelle Verzeichnis geraten -
# das trifft aber nur zu, wenn man IM gemeinten Projekt steht, und fast niemand
# tut das, weil das Skript hier im Repo liegt. Der Rateschluss bleibt trotzdem
# richtig; was fehlte, war die Hilfe beim Danebenliegen: statt nur "Kein Ordner"
# zeigt `_kandidaten()` die tatsaechlich vorhandenen Memory-Ordner des Rechners.
PROJEKTWURZEL = Path.home() / ".claude/projects"


def standard_ordner() -> Path:
    return PROJEKTWURZEL / ("-" + str(Path.cwd()).strip("/").replace("/", "-")) / "memory"


def _kandidaten() -> list:
    """Alle Memory-Ordner auf diesem Rechner, die ueberhaupt Memos enthalten."""
    if not PROJEKTWURZEL.is_dir():
        return []
    return sorted(
        p for p in PROJEKTWURZEL.glob("*/memory")
        if p.is_dir() and any(p.glob("*.md"))
    )


INDEX = "MEMORY.md"          # der Index selbst gehoert nicht in die Datenbank
MIN_ZEICHEN = 40             # Ueberschriften und Fragmente bringen nichts
MAX_ZEICHEN = 1200           # darueber zerteilen: ein einziger Riesenabsatz frisst
                             # sonst die ganze Rueckgabe von recall
# Trennstellen nach Vorliebe - erst Absaetze, zuletzt Kommas
TRENNER = ("\n\n", "\n", ". ", "; ", ", **", ", ")


def zerteile(text: str, grenze: int = MAX_ZEICHEN) -> list:
    """Schneidet zu lange Stuecke an der obersten passenden Trennstelle."""
    if len(text) <= grenze:
        return [text]
    for sep in TRENNER:
        if sep not in text:
            continue
        stuecke, puffer = [], ""
        for teil in text.split(sep):
            kandidat = f"{puffer}{sep}{teil}" if puffer else teil
            if puffer and len(kandidat) > grenze:
                stuecke.append(puffer)
                puffer = teil
            else:
                puffer = kandidat
        if puffer:
            stuecke.append(puffer)
        if len(stuecke) > 1:
            fertig = []
            for s in stuecke:
                fertig.extend(zerteile(s, grenze) if len(s) > grenze else [s])
            return fertig
    return [text[i:i + grenze] for i in range(0, len(text), grenze)]


def zeitstempel(pfad: Path, text: str) -> str:
    """Bevorzugt das 'modified' aus dem Frontmatter, sonst die Dateizeit."""
    m = re.search(r"^\s*modified:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, re.M)
    if m:
        return f"{m.group(1)} 00:00:00"
    return datetime.fromtimestamp(pfad.stat().st_mtime, timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def rumpf(text: str) -> str:
    teile = text.split("---", 2)
    return (teile[2] if len(teile) >= 3 else text).strip()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trocken = "--trocken" in sys.argv
    mit_index = "--mit-index" in sys.argv
    ordner = Path(args[0]).expanduser() if args else standard_ordner()
    if not ordner.is_dir():
        print(f"Kein Ordner: {ordner}")
        if not args:
            print("Ohne Argument wird der Ordner aus dem Arbeitsverzeichnis geraten -")
            print("gemeint ist das Projekt, dessen Memory importiert werden soll,")
            print("nicht der Ordner, in dem dieses Skript liegt.")
            gefunden = _kandidaten()
            if gefunden:
                print("Auf diesem Rechner liegen Memos in:")
                for k in gefunden:
                    print(f"    {k}")
                print(f"Also z.B.: python3 {Path(sys.argv[0]).name} {gefunden[0]}")
            else:
                print(f"Unter {PROJEKTWURZEL}/*/memory liegt keiner - Pfad mitgeben.")
        return 1

    dateien = sorted(p for p in ordner.glob("*.md") if p.name != INDEX)
    if mit_index and (ordner / INDEX).exists():
        dateien.append(ordner / INDEX)
    if not dateien:
        print(f"Keine *.md in {ordner} (ausser {INDEX})")
        return 1

    conn = ms._connect()
    try:
        # Vorhandenes einmal normalisiert einlesen. Ein exakter Vergleich
        # uebersieht Stuecke, die sich nur in der Einrueckung unterscheiden -
        # genau so sind am 2026-09-10 35 Doppler entstanden.
        bekannt = {
            re.sub(r"\s+", " ", r[0]).strip()
            for r in conn.execute("SELECT content FROM eintrag")
        }
        neu = uebersprungen = 0
        for pfad in dateien:
            text = pfad.read_text()
            ts = zeitstempel(pfad, text)
            ist_index = pfad.name == INDEX
            if ist_index:
                # Der Index ist eine Liste, kein Fliesstext - je Punkt ein Eintrag.
                stuecke = [z for z in text.splitlines() if z.lstrip().startswith("- ")]
            else:
                stuecke = re.split(r"\n\s*\n", rumpf(text))

            for stueck in stuecke:
                # Marke: bei Memo-Dateien der Dateiname, beim Index das Ziel des
                # Verweises ("- [Titel](slug.md) — ...") - sonst traegt der halbe
                # Bestand "index" und man sieht Treffern nicht an, worum es geht.
                marke = pfad.stem
                if ist_index:
                    m = re.search(r"\]\((.+?)\.md\)", stueck)
                    marke = m.group(1) if m else "index"
                for absatz in zerteile(stueck.strip()):
                    absatz = absatz.strip()
                    if len(absatz) < MIN_ZEICHEN:
                        continue
                    schluessel = re.sub(r"\s+", " ", absatz).strip()
                    if schluessel in bekannt:
                        uebersprungen += 1
                        continue
                    bekannt.add(schluessel)
                    if trocken:
                        neu += 1
                        continue
                    volltext = f"{absatz} {marke}"
                    conn.execute(
                        "INSERT INTO eintrag (content, tags, ts, stems, teile)"
                        " VALUES (?,?,?,?,?)",
                        (
                            absatz,
                            marke,
                            ts,
                            stamm_spalte(volltext),
                            teile_spalte(volltext, ms._vokabular(conn, volltext)),
                        ),
                    )
                    neu += 1
        if not trocken:
            conn.commit()
        gesamt = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0]
    finally:
        conn.close()

    vorsatz = "Wuerde uebernehmen" if trocken else "Uebernommen"
    print(
        f"{vorsatz}: {neu} Absaetze aus {len(dateien)} Dateien "
        f"({uebersprungen} schon vorhanden). Bestand jetzt: {gesamt}"
    )
    print(f"Datenbank: {ms.DB_PATH} ({ms.DB_PATH.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
