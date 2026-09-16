#!/usr/bin/env python3
"""Pruefstand fuer den Faktencheck: misst, was `faktencheck.urteil` trifft.

    .venv/bin/python pruefstand_fc.py --trocken      # nur den Satz zeigen
    .venv/bin/python pruefstand_fc.py                # messen (braucht das Board)
    .venv/bin/python pruefstand_fc.py --vergleich anweisung_b.txt

**Warum das Ding ueberhaupt existiert.** Die Zahl, auf der der ganze Faktencheck
steht (9/15 richtig, #1327), wurde von Hand erhoben und ist nirgends
reproduzierbar. Deshalb steht in `faktencheck.py` die Warnung, wer die Anweisung
umformuliert, mache #1327 ungueltig - richtig, aber es gab keinen Weg, sie neu zu
erheben. Und bei n=15 liegt der Standardfehler bei rund 13 Punkten: zwei
Varianten, die sich um 10 Punkte unterscheiden, sind damit nicht zu trennen.

**Woher die Gold-Etiketten kommen - drei Quellen, keine davon nachtraeglich
geraten:**

1. `FORTSCHRITT` **faellt im Betrieb an.** Jede `ersetzt=`-Beziehung in
   `veraltet(id, durch)` ist genau das: der Nutzer hat im Moment der
   Entscheidung gesagt, dass der neue Eintrag den alten ablOEst. Das Etikett
   ist damit aelter als die Messung und waechst mit dem Bestand mit.
2. `WIDERSPRUCH` steckt **auch schon drin** - in den Ersetzungen, deren neuer
   Text sich als Korrektur zu erkennen gibt ("Korrektur zu #1168", "Revidiert
   #1272", "der geometrische Zerfall ist widerlegt"). Das sind echte
   Widersprueche aus dem Bestand und besseres Material als gebaute. Gebaute
   kommen aus `pruefpaare_gebaut.json` dazu, weil drei echte zu wenig sind.
3. `UNABHAENGIG` wird **nicht behauptet.** Fuer die harmlosen Paare steht im
   Gold nur "darf keinen Alarm ausloesen", nicht welche der beiden harmlosen
   Klassen richtig waere. Das ist keine Bequemlichkeit: ein Paar mit hoher
   Wortueberschneidung und ohne `ersetzt=`-Beziehung KANN ein unbemerkter
   Widerspruch sein - genau den soll das Werkzeug ja finden. Wer es als
   `UNABHAENGIG` ins Gold schreibt, misst dem Modell einen Fehler an, der
   vielleicht ein Fund ist.

**Zwei Sorten harmloser Paare**, weil sie Verschiedenes messen: *schwere* mit
hoher Wortueberschneidung (die kosten die Fehlalarme) und *leichte*, zufaellig
gezogen (die zeigen, ob das Modell ueberhaupt etwas trennt - ein Melder, der auf
Zufallspaare anschlaegt, war der Befund gegen das NLI-Modell, #1301).

Die Ziehung ist mit festem Startwert gesaet: derselbe Bestand gibt denselben
Satz. Waechst der Bestand, waechst der Satz - die Zahlen sind dann nicht mehr
mit den alten vergleichbar, deshalb meldet der Kopf immer n und Bestandsgroesse.

**Vergleich zweier Anweisungen:** `--vergleich` faehrt beide ueber DIESSELBEN
Paare und meldet nicht zwei Genauigkeiten, sondern die **uneinigen Paare** (A
richtig/B falsch gegen B richtig/A falsch). Bei dieser Groessenordnung von n ist
das der einzige Vergleich, der etwas taugt: die gemeinsamen Treffer und die
gemeinsamen Fehler kuerzen sich heraus, statt die Streuung aufzublaehen.
"""

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import faktencheck  # noqa: E402
from memory_server import _gewichte, _staemme, _ueberschneidung  # noqa: E402

DB = HIER / "memory.db"
GEBAUT = HIER / "pruefpaare_gebaut.json"
SAAT = 20260914

# Ab hier gelten zwei Eintraege als "derselbe Text, nur anders eingerueckt".
# Das sind die Artefakte des absatzweisen Imports (#1092) - als Pruefmaterial
# wertlos, weil die Antwort schon an der Zeichengleichheit abzulesen waere.
# Gemessen ueber `_ueberschneidung` (Anteil des einen im anderen), NICHT ueber
# das Jaccard-Mass von `verdichten` - die beiden Zahlen sind nicht dasselbe
# (#1193), und hier ist die Enthaltensein-Frage die richtige.
GLEICH_AB = 0.90

# Woran eine Ersetzung ZWEIFELHAFT wird - nicht, woran sie eine Korrektur ist.
# Der erste Entwurf hat diese Paare automatisch als WIDERSPRUCH etikettiert und
# lag damit in 2 von 3 Faellen falsch (gemessen 2026-09-14): "Revidiert #1272"
# und "der geometrische Zerfall ist widerlegt" markieren eine HYPOTHESE, die
# eine Messung abloest - beide Staende waren zu ihrer Zeit richtig, also
# FORTSCHRITT. Nur #1169 ("die Framing war falsch") nimmt eine Aussage als
# damals schon falsch zurueck, und das ist der Widerspruch.
#
# Per Stichwort ist das nicht zu trennen, also etikettiert die Automatik hier
# gar nicht mehr. Die Treffer fliegen aus dem Gold und werden gemeldet, damit
# sie von Hand nach `pruefpaare_gebaut.json` wandern koennen. Lieber ein Paar
# weniger im Satz als eines mit falschem Soll: an falschem Gold misst man das
# Modell schlecht und merkt es nicht.
ZWEIFELHAFT = re.compile(r"korrektur|revidier|widerlegt|war falsch|stimmt nicht", re.I)


# --------------------------------------------------------------------------
# Den Satz bauen
# --------------------------------------------------------------------------
class Paar:
    """Ein Pruefpaar. `soll` ist die erwartete Klasse oder None.

    None heisst NICHT "egal", sondern "nur kein Alarm" - siehe Quelle 3 im
    Modulkopf. Solche Paare zaehlen bei der Fehlalarmquote mit und bei der
    Treffergenauigkeit nicht.
    """

    def __init__(self, a, b, soll, quelle, id_a=None, id_b=None):
        self.a, self.b, self.soll, self.quelle = a, b, soll, quelle
        self.id_a, self.id_b = id_a, id_b

    @property
    def name(self):
        if self.id_a:
            return f"#{self.id_a}<->#{self.id_b}"
        return f"{self.quelle}:{self.a[:24]}..."

    @property
    def harmlos(self):
        return self.soll != "WIDERSPRUCH"


def _aehnlich(conn, sa, sb):
    gew = _gewichte(conn, sa | sb)
    return max(_ueberschneidung(sa, sb, gew), _ueberschneidung(sb, sa, gew))


def _von_hand_benannt() -> set:
    """Ids-Paare, die in `pruefpaare_gebaut.json` schon ein Handetikett haben.

    Ohne das stuende ein Paar zweimal im Satz: einmal mit dem Automatiketikett
    und einmal mit dem von Hand gesetzten. Das Handetikett gewinnt - es hat
    jemand angesehen.
    """
    if not GEBAUT.exists():
        return set()
    return {
        (e["a_id"], e["b_id"])
        for e in json.loads(GEBAUT.read_text(encoding="utf-8"))
        if "a_id" in e
    }


def satz(conn, leicht=12, schwer=12, schwelle=0.30):
    """Baut den Pruefsatz aus dem Bestand. Deterministisch bei gleichem Bestand."""
    txt = dict(conn.execute("SELECT rowid, content FROM mem"))
    ersetzt = [
        (a, b)
        for a, b in conn.execute("SELECT id, durch FROM veraltet WHERE durch IS NOT NULL")
        if a in txt and b in txt
    ]
    staemme = {i: _staemme(t) for i, t in txt.items()}

    paare, in_beziehung, zweifelhaft = [], set(), []
    von_hand = _von_hand_benannt()
    for a, b in ersetzt:
        in_beziehung.add((min(a, b), max(a, b)))
        if _aehnlich(conn, staemme[a], staemme[b]) >= GLEICH_AB:
            continue  # Import-Artefakt
        if (a, b) in von_hand:
            continue  # steht schon mit Handetikett in pruefpaare_gebaut.json
        if ZWEIFELHAFT.search(txt[b][:400]):
            zweifelhaft.append((a, b))
            continue
        paare.append(Paar(txt[a], txt[b], "FORTSCHRITT", "ersetzt", a, b))
    if zweifelhaft:
        print("Aus dem Gold genommen (Korrekturverdacht, Soll unklar) - von Hand "
              "nach pruefpaare_gebaut.json, wenn sie in den Satz sollen:",
              ", ".join(f"#{a}<->#{b}" for a, b in zweifelhaft), file=sys.stderr)

    # Schwere harmlose Paare: hohe Wortueberschneidung, aber keine Ersetzung.
    # Rueckwaertsindex nur ueber seltene Staemme, wie in `verdichten` - haeufige
    # verbinden alles mit allem.
    selten = max(2, len(txt) // 20)
    vorkommen = {}
    for rid, st in staemme.items():
        for s in st:
            vorkommen.setdefault(s, []).append(rid)
    kandidaten = set()
    for ids in vorkommen.values():
        if 1 < len(ids) <= selten:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    kandidaten.add((a, b) if a < b else (b, a))
    gew_alle = _gewichte(conn, set().union(*staemme.values()))
    bewertet = []
    for a, b in kandidaten:
        if (a, b) in in_beziehung:
            continue
        sa, sb = staemme[a], staemme[b]
        gemeinsam = sum(gew_alle.get(s, 0) for s in sa & sb)
        vereint = sum(gew_alle.get(s, 0) for s in sa | sb)
        if vereint and gemeinsam / vereint >= schwelle:
            bewertet.append((gemeinsam / vereint, a, b))
    bewertet.sort(key=lambda x: (-x[0], x[1], x[2]))
    # Zwei Siebe, beide gegen dasselbe Uebel - dass der schwere Teil aus einem
    # einzigen Nest stammt. Beinah-Dubletten fliegen raus (die gehoeren
    # verdichtet, nicht geprueft), und kein Eintrag darf mehr als zweimal
    # vorkommen: ein Dreier-Haufen wie #185/#734/#1084 lieferte sonst drei
    # Paare, die dieselbe Frage dreimal stellen.
    genommen, wie_oft = 0, {}
    for w, a, b in bewertet:
        if genommen >= schwer:
            break
        if _aehnlich(conn, staemme[a], staemme[b]) >= GLEICH_AB:
            continue
        if wie_oft.get(a, 0) >= 2 or wie_oft.get(b, 0) >= 2:
            continue
        wie_oft[a] = wie_oft.get(a, 0) + 1
        wie_oft[b] = wie_oft.get(b, 0) + 1
        genommen += 1
        paare.append(Paar(txt[a], txt[b], None, "schwer", a, b))

    # Leichte harmlose Paare: zufaellig, fester Startwert.
    wuerfel = random.Random(SAAT)
    ids = sorted(txt)
    gezogen, versuche = set(), 0
    while len(gezogen) < leicht and versuche < leicht * 50:
        versuche += 1
        a, b = wuerfel.sample(ids, 2)
        a, b = min(a, b), max(a, b)
        if (a, b) in in_beziehung or (a, b) in gezogen:
            continue
        if _aehnlich(conn, staemme[a], staemme[b]) >= schwelle:
            continue  # kein Zufallspaar mehr, gehoert zu den schweren
        gezogen.add((a, b))
    for a, b in sorted(gezogen):
        paare.append(Paar(txt[a], txt[b], None, "leicht", a, b))

    # Die Handarbeit-Datei traegt zweierlei: gebaute Paare (Text direkt) und
    # echte, die von Hand gefunden wurden (nur die Ids). Die zweite Form ist
    # der Weg fuer alles, was die Automatik nicht sieht - ein Widerspruch ohne
    # `ersetzt=`-Beziehung zum Beispiel, der beim Lesen auffaellt.
    if GEBAUT.exists():
        for e in json.loads(GEBAUT.read_text(encoding="utf-8")):
            if "a_id" in e:
                a_id, b_id = e["a_id"], e["b_id"]
                if a_id not in txt or b_id not in txt:
                    print(f"Uebersprungen: #{a_id}/#{b_id} steht nicht im Bestand",
                          file=sys.stderr)
                    continue
                paare.append(Paar(txt[a_id], txt[b_id], e["soll"], "handfund", a_id, b_id))
            else:
                paare.append(Paar(e["a"], e["b"], e["soll"], "gebaut"))
    return paare


# --------------------------------------------------------------------------
# Messen und berichten
# --------------------------------------------------------------------------
def wilson(treffer: int, n: int, z: float = 1.96):
    """Wilson-Intervall. Fuer kleine n ehrlicher als Treffer/n +- z*Wurzel(...),
    das bei 0 oder n Treffern eine Breite von null behauptet."""
    if n == 0:
        return 0.0, 1.0
    p = treffer / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    rand = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / nenner
    return max(0.0, mitte - rand), min(1.0, mitte + rand)


def messen(paare, zeichen=None):
    """Fragt das Board zu jedem Paar. Gibt die Liste der Urteile (oder None)."""
    alt = faktencheck.MAXZ
    if zeichen:
        faktencheck.MAXZ = zeichen
    try:
        return [faktencheck.urteil(p.a, p.b) for p in paare]
    finally:
        faktencheck.MAXZ = alt


def bericht(paare, urteile, bestand: int) -> str:
    mit_soll = [(p, u) for p, u in zip(paare, urteile) if p.soll]
    harmlos = [(p, u) for p, u in zip(paare, urteile) if p.harmlos]
    echte = [(p, u) for p, u in zip(paare, urteile) if p.soll == "WIDERSPRUCH"]
    ohne_urteil = sum(1 for u in urteile if u is None)

    richtig = sum(1 for p, u in mit_soll if u == p.soll)
    fehlalarm = sum(1 for _, u in harmlos if u == "WIDERSPRUCH")
    erkannt = sum(1 for _, u in echte if u == "WIDERSPRUCH")
    lo, hi = wilson(richtig, len(mit_soll))

    aus = [
        f"Bestand {bestand} Eintraege, {len(paare)} Pruefpaare "
        f"({len(mit_soll)} mit exaktem Soll, {len(harmlos)} harmlos, "
        f"{len(echte)} echte Widersprueche)",
        f"Notizlaenge {faktencheck.MAXZ} Zeichen, Modell {faktencheck.MODELL}",
        "",
        f"Richtig:              {richtig}/{len(mit_soll)}"
        f"  ({richtig / max(1, len(mit_soll)):.0%}, 95 %: {lo:.0%}-{hi:.0%})",
        f"Falsche Alarme:       {fehlalarm}/{len(harmlos)} harmlosen Paaren",
        f"Echte erkannt:        {erkannt}/{len(echte)}",
    ]
    if ohne_urteil:
        aus.append(f"Ohne Urteil:          {ohne_urteil} (Board still - Zahlen oben ohne sie lesen)")

    aus.append("\nVerwechslungstafel (Zeile = Soll, Spalte = gesagt):")
    klassen = list(faktencheck.URTEILE) + [None]
    aus.append(f"{'':>14}" + "".join(f"{str(k or 'kein')[:8]:>13}" for k in klassen))
    for soll in ("WIDERSPRUCH", "FORTSCHRITT", None):
        gesagt = [u for p, u in zip(paare, urteile) if p.soll == soll]
        if not gesagt:
            continue
        aus.append(
            f"{soll or 'kein Alarm':>14}"
            + "".join(f"{gesagt.count(k):>13}" for k in klassen)
        )
    aus.append("  Die Zeile 'kein Alarm' hat kein exaktes Soll - dort zaehlt nur, "
               "dass nichts in der Spalte WIDERSPRUCH steht.")

    falsch = [(p, u) for p, u in zip(paare, urteile)
              if u is not None and ((p.soll and u != p.soll) or (not p.soll and u == "WIDERSPRUCH"))]
    if falsch:
        aus.append("\nFehler zum Nachsehen:")
        for p, u in falsch:
            aus.append(f"  {p.name:<24} [{p.quelle}] soll {p.soll or 'kein Alarm'}, gesagt {u}")
        aus.append("  Ein Alarm auf einem 'schweren' Paar muss kein Fehler sein - "
                   "vielleicht ist es ein unbemerkter Widerspruch. Nachsehen, dann "
                   "entweder ersetzt= setzen oder das Paar hier als Fehler zaehlen.")
    return "\n".join(aus)


def vergleich(paare, a_urteile, b_urteile) -> str:
    """Uneinige Paare zweier Varianten. Siehe Modulkopf: bei diesem n ist der
    gepaarte Vergleich der einzige, der etwas taugt."""
    def trifft(p, u):
        return u == p.soll if p.soll else u != "WIDERSPRUCH"

    nur_a = [p for p, ua, ub in zip(paare, a_urteile, b_urteile) if trifft(p, ua) and not trifft(p, ub)]
    nur_b = [p for p, ua, ub in zip(paare, a_urteile, b_urteile) if trifft(p, ub) and not trifft(p, ua)]
    aus = [
        "",
        f"Gepaarter Vergleich ueber {len(paare)} Paare:",
        f"  nur A richtig: {len(nur_a)}   nur B richtig: {len(nur_b)}   "
        f"einig: {len(paare) - len(nur_a) - len(nur_b)}",
    ]
    if len(nur_a) + len(nur_b) < 6:
        aus.append("  Zu wenige uneinige Paare fuer eine Aussage - die Varianten "
                   "sind auf diesem Satz nicht zu trennen.")
    for titel, gruppe in (("nur A", nur_a), ("nur B", nur_b)):
        for p in gruppe:
            aus.append(f"  {titel}: {p.name} [{p.quelle}]")
    return "\n".join(aus)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--trocken", action="store_true",
                    help="nur den Pruefsatz zeigen, das Board nicht fragen")
    ap.add_argument("--zeichen", type=int, default=None,
                    help=f"Notizlaenge (Vorgabe {faktencheck.MAXZ}, ausgemessen in #1327)")
    ap.add_argument("--leicht", type=int, default=12)
    ap.add_argument("--schwer", type=int, default=12)
    ap.add_argument("--vergleich", metavar="DATEI",
                    help="zweite Anweisung aus DATEI, gepaart gegen die eingebaute")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        bestand = conn.execute("SELECT count(*) FROM mem").fetchone()[0]
        paare = satz(conn, leicht=args.leicht, schwer=args.schwer)
    finally:
        conn.close()

    if args.trocken:
        nach_quelle = {}
        for p in paare:
            nach_quelle.setdefault(p.quelle, []).append(p)
        print(f"Bestand {bestand} Eintraege, {len(paare)} Pruefpaare:")
        for quelle, gruppe in sorted(nach_quelle.items()):
            # Das Soll je Paar, nicht je Gruppe: `handfund` mischt beides, und
            # ein Gruppenetikett vom ersten Paar abzulesen log genau dort.
            sollwerte = {p.soll or "nur kein Alarm" for p in gruppe}
            print(f"\n{quelle} ({len(gruppe)}, Soll {' / '.join(sorted(sollwerte))}):")
            for p in gruppe:
                print(f"  {p.name:<22} [{p.soll or 'kein Alarm'}]")
                print(f"  {'':<22} {' '.join(p.a.split())[:58]}")
                print(f"  {'':<22} {' '.join(p.b.split())[:58]}")
        return 0

    if not faktencheck.erreichbar():
        print(f"Board nicht erreichbar ({faktencheck.zustand()}). "
              f"Mit --trocken laesst sich der Satz trotzdem ansehen.")
        return 1

    urteile = messen(paare, args.zeichen)
    print(bericht(paare, urteile, bestand))
    if args.vergleich:
        anweisung_b = Path(args.vergleich).read_text(encoding="utf-8").strip()
        alt = faktencheck.ANWEISUNG
        faktencheck.ANWEISUNG = anweisung_b
        try:
            urteile_b = messen(paare, args.zeichen)
        finally:
            faktencheck.ANWEISUNG = alt
        print("\n" + "=" * 60 + "\nVariante B:\n")
        print(bericht(paare, urteile_b, bestand))
        print(vergleich(paare, urteile, urteile_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
