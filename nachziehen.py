#!/usr/bin/env python3
"""Rechnet die abgeleiteten Spalten neu und bringt das Markenverzeichnis in Deckung.

Warum es das braucht: `mem.stems` und `mem.teile` sind Momentaufnahmen.
`teile` haengt am Vokabular des Augenblicks, `stems` an den Regeln in
morphologie.py - und beide werden nur beim Einfuegen gerechnet. Ein UPDATE auf
`tags` (so geschehen in migration_marken.py) oder eine geaenderte Stemmer-Regel
laesst sie lautlos driften; gemessen waren es 27 Eintraege, davon 20, deren
Projektmarke fuer die Stammsuche unsichtbar war (#1424).

Nach jedem Eingriff laufen lassen, der `content` oder `tags` ausserhalb von
`remember` anfasst, und nach jeder Aenderung an morphologie.py.

    python3 nachziehen.py [--probe]

--probe zeigt nur an, was sich aendern wuerde.
"""

import sys

from memory_server import (
    _connect, _ketten_nachtragen, _marken_nachtragen, _nachziehen,
    _vokabel_nachtragen,
)


def main() -> int:
    probe = "--probe" in sys.argv
    conn = _connect()
    try:
        # ZUERST das Woerterbuch: `_nachziehen` zerlegt die Komposita dagegen,
        # ein veraltetes Verzeichnis wuerde also in die Spalten geschrieben.
        woerter = _vokabel_nachtragen(conn)
        print(f"Woerterbuch: {woerter} Woerter")
        geaendert = _nachziehen(conn)
        print(f"Abgeleitete Spalten: {len(geaendert)} Eintraege weichen ab"
              + (f" ({', '.join('#'+str(i) for i in geaendert[:12])}"
                 + (", ..." if len(geaendert) > 12 else "") + ")" if geaendert else ""))
        vorher = {r[0] for r in conn.execute("SELECT marke FROM marken")}
        anzahl = _marken_nachtragen(conn)
        nachher = {r[0] for r in conn.execute("SELECT marke FROM marken")}
        print(f"Marken im Verzeichnis: {anzahl}"
              + (f", neu: {', '.join(sorted(nachher - vorher))}" if nachher - vorher else "")
              + (f", entfallen: {', '.join(sorted(vorher - nachher))}" if vorher - nachher else ""))
        # Die Kettenspalten gehoeren zur selben Familie: `kopf`/`nr` werden aus
        # `content`+`tags` gerechnet und driften nach jedem Eingriff. Bis
        # 2026-09-16 hatte `_ketten_nachtragen` ausserhalb der Tests gar keinen
        # Aufrufer - die Erkennung lief einmal und veraltete danach still.
        if probe:
            print("Ketten: uebersprungen (--probe), die Erkennung schreibt selbst.")
        else:
            vorher = conn.execute(
                "SELECT count(*) FROM eintrag WHERE kopf IS NOT NULL").fetchone()[0]
            glieder = _ketten_nachtragen(conn)
            print(f"Zerschnittene Memos: {glieder} Kettenglieder"
                  + (f" (vorher {vorher})" if glieder != vorher else ""))
        if probe:
            conn.rollback()
            print("--probe: nichts geschrieben.")
        else:
            conn.commit()
            print("Geschrieben.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
