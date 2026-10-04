#!/usr/bin/env python3
"""Regressionsnetz: je ein Fall pro Fallstrick, der schon einmal zugeschlagen hat.

Jeder Test hier steht fuer einen Fehler, der in Produktion aufgefallen ist und
dessen Begruendung als Notiz im Memory liegt. Die Nummer im Namen der
Behauptung ist die Eintrags-Id - wer wissen will, WARUM der Fall so aussieht,
liest dort nach.

Laufen lassen: `.venv/bin/python test_memory.py`

Bewusst ohne pytest: das Projekt kommt sonst ohne Fremdbibliothek aus
(morphologie.py schreibt sich das ausdruecklich auf die Fahne), und ein
Testlauf ist kein Grund, damit anzufangen.

**Jeder Test bekommt eine frische Wegwerfdatenbank.** Der echte Bestand wird
nie geoeffnet; der Laeufer prueft das, bevor er irgendetwas aufruft.
"""

import contextlib
import importlib
import io
import os
import re
import sqlite3
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Vor dem Import: das Board soll bei keinem remember angefragt werden. Sonst
# kostet jeder Test die Vorprobe, und das Ergebnis haengt am Netz.
os.environ["MEMORY_FC_AUS"] = "1"

import import_memos as im  # noqa: E402
import memory_server as ms  # noqa: E402
import nachziehen  # noqa: E402
import pruefstand_fc  # noqa: E402
from morphologie import teile_spalte, wortschatz  # noqa: E402

ECHTE_DB = Path(__file__).resolve().parent / "memory.db"

# Sofort beim Import weg vom echten Bestand, nicht erst in `main()`. Bis
# 2026-09-26 bog erst der Laeufer den Pfad um: wer einen einzelnen Test aus
# der REPL rief oder die Datei an pytest gab, schrieb in die echte memory.db.
# `main()` setzt je Test eine eigene frische Datei, das hier ist nur der Boden.
ms.DB_PATH = Path(tempfile.mkdtemp(prefix="memtest-import-")) / "memory.db"


# --------------------------------------------------------------------------
# Suche
# --------------------------------------------------------------------------
def test_terme_nimmt_einzelne_ziffern_mit():
    """#1421: die Laengenschwelle verschluckte die Ziffer, also gerade das
    unterscheidende Token - `recall("Deck 5")` war faktisch `recall("Deck")`."""
    assert ms._terme("Deck 5") == ["Deck", "5"], ms._terme("Deck 5")
    assert ms._terme("Faktor 3") == ["Faktor", "3"]
    # Einzelbuchstaben sollen weiterhin herausfallen - das war der Sinn der Schwelle.
    assert ms._terme("a Deck") == ["Deck"]


def test_wortfolge_steht_vor_der_haeufigkeit():
    """#1422: bei AND ueber getrennte Token wertet BM25 nur Haeufigkeit, nicht
    Nachbarschaft. Der Eintrag mit genau der gesuchten Folge stand auf Rang 7."""
    ms.remember("Deck 4 hat eine Schleuse", tags="schiff", art="schnittstelle")
    ms.remember("Deck 9 Maschinenraum, Deck 9 ist gross, Deck 9 laut",
                tags="schiff", art="schnittstelle")
    ms.remember("Deck 5 beherbergt die Krankenstation", tags="schiff", art="schnittstelle")
    erster_treffer = ms.recall("Deck 5", limit=3).split("\n")[1]
    assert "Krankenstation" in erster_treffer, erster_treffer


def test_themen_nennt_bei_unbekannter_marke_die_naheliegenden():
    """2026-10-04: der Zweig "Marke nicht gefunden" entpackte vier Spalten aus
    fuenf und warf ValueError - ausgerechnet dort, wo ein Tippfehler oder eine
    Kurzform ("leuchtturm" statt "leuchtturm-project") aufgefangen werden soll.
    Im Betrieb kam nur "Error executing tool themen" an."""
    ms.remember("Das Feuer dreht alle zwoelf Sekunden", tags="leuchtturm-project",
                art="schnittstelle")
    aus = ms.themen("leuchtturm")
    assert "Keine Eintraege" in aus and "leuchtturm-project" in aus, aus
    assert "Keine Eintraege" in ms.themen("gibtesnicht")


def _nummern(ausgabe: str) -> list:
    """Die Ids am Zeilenanfang einer Ausgabe, in der Reihenfolge der Ausgabe."""
    return [int(n) for n in re.findall(r"^\s*#(\d+)", ausgabe, re.M)]


def test_themen_zeigt_eine_seite_und_nennt_den_weg_zum_rest():
    """2026-10-04: "alles zu <Projekt>" lieferte den Titelindex von 351
    Eintraegen, bis zu 40 je Art - 26.506 Zeichen, bevor ein einziger Eintrag
    gelesen war. Vorgabe ist jetzt eine Seite mit den juengsten; der Rest wird
    gezaehlt und der Aufruf genannt, der ihn holt."""
    for n in range(1, 36):
        ms.remember(f"Bojennummer {n} liegt im Fahrwasser Abschnitt {n}",
                    tags="hafen-project", art="fallstrick" if n % 2 else "schnittstelle")
    erste = ms.themen("hafen-project")
    assert _nummern(erste) == list(range(35, 5, -1)), _nummern(erste)
    assert "35 Eintraege" in erste and "schnittstelle 17, fallstrick 18" in erste, erste
    assert '5 aeltere nicht gezeigt - themen("hafen-project", seite=2)' in erste, erste
    zweite = ms.themen("hafen-project", seite=2)
    assert _nummern(zweite) == [5, 4, 3, 2, 1], zweite
    assert "nicht gezeigt" not in zweite, zweite
    assert "gibt es nicht" in ms.themen("hafen-project", seite=3)
    # alle=True: der ganze Index, nach Art gruppiert, nichts gedeckelt.
    ganz = ms.themen("hafen-project", alle=True)
    assert sorted(_nummern(ganz)) == list(range(1, 36)), _nummern(ganz)
    assert "fallstrick (18):" in ganz and "nicht gezeigt" not in ganz, ganz
    # limit= bleibt die Seitengroesse.
    assert _nummern(ms.themen("hafen-project", limit=10, seite=4)) == [5, 4, 3, 2, 1]
    # Ein kleines Projekt passt auf eine Seite und bekommt keinen Blaetterhinweis.
    ms.remember("Die Mole ist 40 Meter lang", tags="mole-project", art="messwert")
    klein = ms.themen("mole-project")
    assert "Seite" not in klein and "nicht gezeigt" not in klein, klein


def test_zeige_deckelt_den_aufruf_und_nennt_was_fehlt():
    """2026-10-04: 16 Volltexte in einem Aufruf kosteten im Median 24.595
    Zeichen. Lang war dabei kein einzelner Eintrag - teuer war die Anzahl.
    Der Deckel gilt deshalb je Aufruf, und was nicht hineinpasst, steht als
    Titelzeile samt fertigem Folgeaufruf da."""
    for n in range(1, 6):
        ms.remember(f"Leuchtfeuer {n}: " + f"Kennung{n} blinkt. " * 150,
                    tags="hafen-project", art="schnittstelle")
    aus = ms.zeige("5,4,3,2,1")
    kopf, _, rest = aus.partition("weitere verlangt, nicht gezeigt")
    assert rest, aus
    gezeigt = _nummern(kopf)
    assert gezeigt and gezeigt == [5, 4, 3, 2, 1][:len(gezeigt)] and len(gezeigt) < 5, gezeigt
    offen = [5, 4, 3, 2, 1][len(gezeigt):]
    assert f'zeige("{",".join(map(str, offen))}")' in rest, rest
    assert _nummern(rest) == offen, rest
    # Gezeigtes steht ganz da, Aufgeschobenes nur als Titelzeile.
    assert kopf.count("blinkt.") == 150 * len(gezeigt), kopf.count("blinkt.")
    assert rest.count("blinkt.") < 10 * len(offen), rest
    assert len(aus) < ms.DECKEL_ZEIGE + 1500, len(aus)
    # Der genannte Folgeaufruf fuehrt bis ans Ende, ohne etwas zu verlieren.
    gesehen, runden = list(gezeigt), 0
    while offen:
        folge = ms.zeige(",".join(map(str, offen)))
        kopf, _, rest = folge.partition("weitere verlangt, nicht gezeigt")
        gesehen += _nummern(kopf)
        offen = _nummern(rest)
        runden += 1
        assert runden < 6, "Fortsetzung kommt nicht ans Ende"
    assert gesehen == [5, 4, 3, 2, 1], gesehen
    # voll=True: alles auf einmal.
    ganz = ms.zeige("5,4,3,2,1", voll=True)
    assert ganz.count("blinkt.") == 750 and "nicht gezeigt" not in ganz
    # Unter dem Deckel aendert sich nichts.
    assert "nicht gezeigt" not in ms.zeige("1,2") and ms.zeige("1,2").count("blinkt.") == 300


def test_zeige_kuerzt_einen_ueberlangen_eintrag_nur_mit_ansage():
    """Der einzige Fall, in dem mitten im Text Schluss ist: ein Eintrag, der
    allein ueber dem Deckel liegt. Dann an einer Zeilengrenze, mit Zahlen und
    dem Aufruf, der den Rest holt - nie stumm."""
    lang = "\n".join(f"Zeile {n}: der Pegel steht bei {n} Zentimetern" for n in range(250))
    assert len(lang) > ms.DECKEL_ZEIGE
    ms.remember(lang, tags="hafen-project", art="messwert")
    aus = ms.zeige("1")
    assert f"von {len(lang)} Zeichen gezeigt" in aus and 'zeige("1", voll=True)' in aus, aus[-300:]
    assert "Zeile 0:" in aus and "Zeile 249:" not in aus
    assert len(aus) < ms.DECKEL_ZEIGE + 300, len(aus)
    assert "Zeile 249:" in ms.zeige("1", voll=True)
    assert "gekuerzt" not in ms.zeige("1", voll=True)


def test_zeige_trennt_die_stuecke_einer_kette_nicht():
    """CLAUDE.md verlangt, ein zerschnittenes Memo erst GANZ zu lesen. Ein
    Deckel, der zwischen Stueck 1 und 2 faellt, lieferte genau das Bruchstueck,
    vor dem der Vermerk warnt. Eine Kette ist deshalb eine Einheit: ganz
    gezeigt oder ganz aufgeschoben, und nie gekappt."""
    fuell = "Die Tonne schwojt im Strom und zerrt an der Kette, " * 30
    ms.remember("Das Namensschema ist fest, " + fuell + "gilt fuer den Rest (z.B",
                tags="schiff", art="schnittstelle")
    ms.remember("raumschiff_alpha_0-2.apk), " + fuell + "gebumpt in tools/build.sh.",
                tags="schiff", art="schnittstelle")
    ms.remember("Ankerplatz: " + "Der Grund ist Schlick und haelt schlecht. " * 110,
                tags="schiff", art="fallstrick")
    conn = ms._connect()
    assert ms._ketten_nachtragen(conn) == 2
    conn.close()
    # Die Kette passt nach dem langen Eintrag nicht mehr: BEIDE Stuecke warten.
    aus = ms.zeige("3,1,2")
    kopf, _, rest = aus.partition("weitere verlangt, nicht gezeigt")
    assert _nummern(kopf) == [3] and _nummern(rest) == [1, 2], aus[-600:]
    assert 'zeige("1,2")' in rest and "Stueck 2 von 2" in rest, rest
    # Die Stuecke ruecken zusammen, auch wenn etwas dazwischen verlangt war.
    aus = ms.zeige("1,3,2")
    kopf, _, rest = aus.partition("weitere verlangt, nicht gezeigt")
    assert _nummern(kopf) == [1, 2] and _nummern(rest) == [3], aus[-600:]
    assert "gebumpt in tools/build.sh" in kopf
    # Eine Kette ueber dem Deckel kommt trotzdem ganz - gekappt wird sie nie.
    alt = ms.DECKEL_ZEIGE
    ms.DECKEL_ZEIGE = 1000
    try:
        aus = ms.zeige("1,2")
        assert "gebumpt in tools/build.sh" in aus and "gekuerzt" not in aus, aus[-300:]
        assert "nicht gezeigt" not in aus
    finally:
        ms.DECKEL_ZEIGE = alt


def test_recall_nennt_den_besseren_treffer_ausserhalb_der_marke():
    """2026-10-04: 40 Fragen nach allgemeinem Wissen, gestellt mit einer
    Projektmarke - 0 von 880 gefunden, ohne Marke 37 von 40. Der Filter ist
    hart, und in 83 % der Faelle kam statt "Keine Treffer" der ODER-Rueckfall:
    eine volle Liste aus dem Projekt, die wie ein Ergebnis aussieht.
    Der blosse Rat an dieser Stelle war gemessen wertlos (93 % Fehlalarm bei
    Projektfragen); geraten wird deshalb nur, wenn der beste Treffer ohne
    Marke wirklich draussen liegt, und der wird genannt."""
    ms.remember("Die Schleuse oeffnet nur bei Hochwasser", tags="hafen-project", art="fallstrick")
    ms.remember("Der Kran hebt zwanzig Tonnen", tags="hafen-project", art="messwert")
    ms.remember("Die Shell bricht bei Umlauten im Pfad ab, also Pfade quoten",
                tags="shell-fallen", art="fallstrick")
    # Allgemeine Frage in der Projektsitzung: ein Wort trifft im Projekt, alle nirgends.
    aus = ms.recall("Schleuse Umlaute Pfad quoten", marke="hafen-project")
    assert "(ODER" in aus and "Hochwasser" in aus, aus
    letzte = aus.splitlines()[-1]
    assert letzte.startswith("Ausserhalb von hafen-project passt besser: #3 "), aus
    assert "ohne marke= noch einmal probieren" in letzte, aus
    # Der Treffer von draussen steht NUR in der Ratszeile, nicht in der Liste.
    assert aus.count("#3 ") == 1, aus
    # Kein Fehlalarm: ODER-Rueckfall, aber der beste Treffer liegt im Projekt.
    still = ms.recall("Schleuse Hochwasser Gezeiten Pegel", marke="hafen-project")
    assert "(ODER" in still and "Ausserhalb" not in still, still
    # Und keiner ohne Marke oder bei einem Treffer, der alle Begriffe enthaelt.
    assert "Ausserhalb" not in ms.recall("Schleuse Umlaute Pfad quoten")
    assert "Ausserhalb" not in ms.recall("Schleuse Hochwasser", marke="hafen-project")


def test_chronik_faellt_aus_der_vorgabeansicht_wird_aber_gemeldet():
    """Stilles Ausblenden waere schlimmer als Rauschen: man merkt sonst nie,
    dass der gute Treffer in der Chronik liegt."""
    ms.remember("Flauschige Katzen am Dienstag", tags="probe", art="verlauf")
    ohne = ms.recall("flauschige")
    assert "Keine Treffer" in ohne and "Chronik" in ohne, ohne
    mit = ms.recall("flauschige", art="verlauf")
    assert "Katzen" in mit, mit


# --------------------------------------------------------------------------
# Aufbau der Datenbank
# --------------------------------------------------------------------------
def test_fremdschluessel_haelt_die_verweise():
    """#1423 hatte keinen Gegenstand mehr, seit `eintrag` eine gewoehnliche
    Tabelle ist: die Id ist ein echter Primaerschluessel, ein Neubau der
    Tabelle findet nicht mehr statt, und was frueher nur Sorgfalt war, erzwingt
    jetzt die Datenbank. Geprueft wird deshalb nicht mehr, ob der Umbau die
    Rowid mitnimmt, sondern dass ein Verweis ins Leere abgewiesen wird."""
    conn = ms._connect()
    conn.execute("INSERT INTO eintrag (content, ts) VALUES ('erster', datetime('now'))")
    conn.commit()
    try:
        conn.execute("INSERT INTO eintrag (content, ts, kopf) VALUES ('x', datetime('now'), 4711)")
        raise AssertionError("Kette auf einen nicht existierenden Eintrag wurde angenommen")
    except sqlite3.IntegrityError:
        pass
    try:
        conn.execute("INSERT INTO eintrag (content, ts, art) VALUES ('x', datetime('now'), 'quatsch')")
        raise AssertionError("unbekannte Art wurde angenommen")
    except sqlite3.IntegrityError:
        pass
    conn.close()


def test_schattenbestand_wird_geborgen():
    """Nach dem Umzug auf Stand 5 laeuft der MCP-Server noch mit dem Code von
    vorher. Der findet kein `mem`, haelt die Datenbank fuer neu, legt `mem`
    leer an, schreibt dorthin und setzt den Stand auf 4 zurueck - **ohne
    Fehlermeldung**. Der Nutzer sieht eine Bestaetigung, der Eintrag ist
    unsichtbar. Der neue Code raeumt beim naechsten Start hinter ihm auf."""
    ms.remember("Ein ordentlicher Eintrag", tags="probe", art="fallstrick")
    conn = ms._connect()
    # Den alten Code nachstellen: Schattentabellen samt Eintrag.
    conn.executescript("""
        CREATE VIRTUAL TABLE mem USING fts5(content, tags, ts UNINDEXED, stems, teile);
        CREATE TABLE art (id INTEGER PRIMARY KEY, art TEXT NOT NULL, am TEXT);
        INSERT INTO mem (content, tags, ts, stems, teile)
        VALUES ('Im Schatten geschrieben', 'probe', datetime('now'), '', '');
        INSERT INTO art (id, art, am) VALUES (1, 'entscheidung', datetime('now'));
    """)
    conn.execute("INSERT OR REPLACE INTO schema (schluessel, wert) VALUES ('stand','4')")
    conn.commit()
    conn.close()

    conn = ms._connect()          # hier muss die Bergung greifen
    inhalte = [z[0] for z in conn.execute("SELECT content FROM eintrag ORDER BY id")]
    stand = conn.execute("SELECT wert FROM schema WHERE schluessel='stand'").fetchone()[0]
    uebrig = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE name IN ('mem','art','kette')"
    ).fetchone()[0]
    art = conn.execute(
        "SELECT art FROM eintrag WHERE content = 'Im Schatten geschrieben'"
    ).fetchone()[0]
    conn.close()
    assert "Im Schatten geschrieben" in inhalte, inhalte
    assert art == "entscheidung", f"Art ging verloren: {art}"
    assert stand == str(ms.SCHEMA_STAND), f"Stand blieb bei {stand}"
    assert uebrig == 0, "Schattentabellen stehen noch da"
    # Und die Suche findet ihn auch, der Index ist also mitgezogen.
    assert "Im Schatten" in ms.recall("Schatten geschrieben", limit=3)


def test_zeitstempel_ist_kein_suchwort():
    """#1425: als gewoehnliche FTS5-Spalte zerlegte der Tokenisierer das Datum
    in nackte Zahlen. `MATCH '2026'` traf damit jeden einzelnen Eintrag.

    Seit Stand 5 ist das Bauart statt Verabredung: `ts` ist eine Spalte von
    `eintrag` und steht im Index gar nicht. Der Test bleibt trotzdem stehen -
    er kostet nichts und faengt den Tag, an dem jemand sie mit aufnimmt."""
    ms.remember("Ein Text voellig ohne Jahreszahl", tags="probe", art="fallstrick")
    ms.remember("Noch so einer", tags="probe", art="fallstrick")
    conn = ms._connect()
    jahr = conn.execute("SELECT strftime('%Y', 'now')").fetchone()[0]
    treffer = conn.execute("SELECT count(*) FROM suche WHERE suche MATCH ?", (jahr,)).fetchone()[0]
    conn.close()
    assert treffer == 0, f"{jahr} trifft {treffer} Eintraege - ts steckt wieder im Index"


def test_neue_art_besteht_den_check_der_datenbank():
    """#1426: `CREATE TABLE IF NOT EXISTS` friert den CHECK ein. Eine siebte
    Art bestand die Pruefung im Code und scheiterte danach an der Datenbank -
    und zwar NACH dem mem-INSERT, der Text war weg.

    Seit Stand 5 steht das Vokabular als ZEILEN in `art_vokabular`: eine neue
    Art ist ein INSERT, kein Tabellenumbau. Der Fremdschluessel haelt trotzdem
    jeden Tippfehler ab."""
    ms.remember("Erster Eintrag", tags="probe", art="fallstrick")
    original = ms.ARTEN
    ms.ARTEN = original + ("kochrezept",)
    try:
        aus = ms.remember("Mit nagelneuer Art", tags="probe", art="kochrezept")
        assert "Gespeichert" in aus, aus
        conn = ms._connect()
        gesetzt = conn.execute("SELECT art FROM eintrag WHERE id = 2").fetchone()
        conn.close()
        assert gesetzt and gesetzt[0] == "kochrezept", gesetzt
    finally:
        ms.ARTEN = original


def test_zweimaliges_abloesen_gibt_zwei_vermerke():
    """#1428: frueher ersetzte das zweite Abloesen die Zeile des ersten und
    loeschte damit genau die Herkunft, die die Tabelle festhalten soll."""
    ms.remember("Alpha", tags="probe", art="fallstrick")
    ms.vergessen("1", grund="erster Grund")
    ms.remember("Beta loest ab", tags="probe", art="fallstrick", ersetzt="1")

    conn = ms._connect()
    anzahl = conn.execute("SELECT count(*) FROM veraltet WHERE id = 1").fetchone()[0]
    durch, grund = ms._veraltungen(conn)[1]
    conn.close()
    assert anzahl == 2, f"{anzahl} Vermerk(e) statt 2 - der zweite hat den ersten ueberschrieben"
    assert (durch, grund) == (2, "ersetzt"), (durch, grund)


def test_gezieltes_woerterbuch_ist_so_gut_wie_das_ganze():
    """#1455: `_vokabular` holt nur noch die Teilzeichenketten, die `zerlege`
    fuer DIESEN Text nachschlagen kann, statt das ganze Woerterbuch zu lesen.

    Das steht und faellt damit, dass `kandidaten()` nichts auslaesst - eine
    Luecke dort waere eine still ausbleibende Zerlegung, kein Fehler. Also
    Zeile fuer Zeile gegen das vollstaendige Woerterbuch gestellt.
    """
    for satz in (
        "Der Fusionskatalysator im Reaktor",
        "Eine Bildschirmflaeche mit gutem Seitenverhaeltnis",
        "Die Qualitaetsmechanik der Datenbankverbindung",
        "Kompositazerlegung und Rangfolgeberechnung im Zwischenspeicher",
        "Der Bildschirm und die Flaeche und das Verhaeltnis",
    ):
        ms.remember(satz, tags="probe", art="fallstrick")

    conn = ms._connect()
    ganz = ms._vokabular_ganz(conn)
    for rid, c, t in conn.execute("SELECT id, content, tags FROM eintrag").fetchall():
        voll = f"{c} {t}"
        gezielt = teile_spalte(voll, ms._vokabular(conn, voll))
        komplett = teile_spalte(voll, ganz | wortschatz(voll))
        assert gezielt == komplett, f"#{rid}: gezielt '{gezielt}' gegen ganz '{komplett}'"
    conn.close()


def test_kompositum_mit_umlaut_zerfaellt():
    """Das Woerterbuch kam bis 2026-09-15 aus `mem_vocab`, also aus dem
    FTS5-Tokenisierer - und der entfernt Diakritika ("abgeloest" statt
    "abgeloest" mit oe). `zerlege` schlaegt aber die Form MIT Umlaut nach.
    634 deutsche Woerter waren damit unerreichbar, 81 Eintraege des Bestands
    betroffen. Kein Fehler, keine Meldung - nur eine Zerlegung, die ausblieb.
    """
    ms.remember("Der Bildschirm und die Fläche sind zwei Dinge", tags="probe", art="fallstrick")
    ms.remember("Die Bildschirmfläche ist zu klein geraten", tags="probe", art="fallstrick")
    conn = ms._connect()
    teile = conn.execute("SELECT teile FROM eintrag WHERE id = 2").fetchone()[0]
    conn.close()
    assert "bildschirm" in teile and "fläche" in teile, f"teile = '{teile}'"


def test_woerterbuch_waechst_beim_speichern_mit():
    """Das Verzeichnis wird beim Schreiben fortgeschrieben - sonst kennt der
    naechste Eintrag die Woerter des vorigen nicht."""
    ms.remember("Ein Reaktor und ein Katalysator", tags="probe", art="fallstrick")
    conn = ms._connect()
    drin = {r[0] for r in conn.execute("SELECT wort FROM vokabel")}
    conn.close()
    assert {"reaktor", "katalysator"} <= drin, sorted(drin)
    # und nichts Kurzes oder Nichtalphabetisches
    assert all(5 <= len(w) <= 12 and w.isalpha() for w in drin), sorted(drin)


def test_kompositum_zerfaellt_auch_wenn_es_selbst_im_woerterbuch_steht():
    """Der eigene Wortschatz eines Eintrags steht immer im Woerterbuch. Bis
    2026-09-29 fand `zerlege` deshalb auf oberster Ebene das Wort selbst und
    verwarf es als unzerlegbar: "Ablaufdatum" (11 Buchstaben) bekam nie ein
    "datum" - die ganze Laengenklasse 11-12 fiel so aus."""
    from morphologie import zerlege
    assert zerlege("Sonnenschein", {"sonnen", "schein", "sonnenschein"}) == ["sonnen", "schein"]
    text = "Das Ablaufdatum beachten"
    assert "datum" in teile_spalte(text, wortschatz(text) | {"ablauf", "datum"}).split()


def test_unterstrich_trennt_fuers_woerterbuch():
    """`\\w` schliesst den Unterstrich ein - `profil_validierung` bliebe damit
    EIN Wort, scheiterte an isalpha() und fiele ganz aus dem Woerterbuch.
    Genau daran war das alte, aus fts5vocab gelesene Verzeichnis reicher: der
    FTS5-Tokenisierer trennt am Unterstrich. Beim Umbau fiel deshalb an einem
    Eintrag eine Zerlegung weg, die es vorher gab (Bezeichner aus Code sind in
    diesem Bestand haeufig). In einem deutschen Wort steht kein Unterstrich.
    """
    ms.remember("Im Code heisst es profil_validierung als Bezeichner",
                tags="probe", art="schnittstelle")
    conn = ms._connect()
    drin = {r[0] for r in conn.execute("SELECT wort FROM vokabel")}
    conn.close()
    assert {"profil", "validierung"} <= drin, sorted(drin)


def test_nachziehen_konvergiert():
    """#1424: `stems`/`teile` sind Momentaufnahmen des Vokabulars. Sie duerfen
    driften - aber ein zweiter Lauf muss nichts mehr zu tun finden, sonst ist
    der Bestand nie in Deckung zu bringen."""
    ms.remember("Fusionskatalysator und Katalysator im Reaktor", tags="probe", art="fallstrick")
    ms.remember("Der Katalysator wurde gesperrt und sperrte weiter", tags="probe", art="fallstrick")
    conn = ms._connect()
    ms._nachziehen(conn)
    conn.commit()
    zweiter_lauf = ms._nachziehen(conn)
    conn.close()
    assert zweiter_lauf == [], f"zweiter Lauf aendert noch {len(zweiter_lauf)} Eintraege"


def test_bruchstueck_wird_in_der_vorschau_als_solches_gemeldet():
    """#1463: Der Import trennte an ". " und hielt "z.B." fuer ein Satzende.
    Die Vorschau zeigt dann ein Satzfragment, und der Treffer sieht unbrauchbar
    aus, obwohl er es nicht ist - der Verweis muss VOR dem Volltext da sein."""
    ms.remember("Das Namensschema ist fest, gilt fuer den Rest des Projekts (z.B",
                tags="schiff", art="schnittstelle")
    ms.remember("raumschiff_alpha_0-2.apk), gebumpt in tools/build.sh",
                tags="schiff", art="schnittstelle")
    conn = ms._connect()
    assert ms._ketten_nachtragen(conn) == 2
    conn.close()
    vorschau = ms.recall("Namensschema", limit=3)
    assert "Stueck 1 von 2" in vorschau, vorschau
    assert "Stueck 2 von 2" in ms.zeige("2"), ms.zeige("2")


def test_kette_bekommt_einen_platz_und_der_rest_wird_nachbesetzt():
    """K2, gemessen am 2026-09-25: bei 2,9 % der echten Fragen belegten mehrere
    Glieder DESSELBEN zerschnittenen Memos mehrere der acht Plaetze. Sie sagen
    dasselbe, der Aufrufer muss die Kette ohnehin am Stueck lesen, und der
    Kettenvermerk nennt die ganze Spanne - der zweite Platz traegt also nichts
    und fehlt einem anderen Eintrag. Entdoppeln allein genuegt aber nicht: wird
    der frei gewordene Platz nicht nachbesetzt, ist die Liste nur kuerzer."""
    # Die Kettenglieder muessen die besten Treffer sein, sonst misst der Test
    # nichts: BM25 straft Laenge, also sind die Einzeleintraege lang.
    lang = ("Dieser Eintrag beschreibt ausfuehrlich weitere Dinge des Hafens"
            " und der Anlagen, damit er laenger ist als die Kettenglieder.")
    for i in range(3):
        ms.remember(f"Schleuse {i} wurde geprueft. {lang}",
                    tags="schiff", art="schnittstelle")
    ms.remember("Schleuse klemmt", tags="schiff", art="schnittstelle")
    ms.remember("an der Schleuse steht Wasser,", tags="schiff", art="schnittstelle")
    ms.remember("die Schleuse bleibt zu.", tags="schiff", art="schnittstelle")
    conn = ms._connect()
    assert ms._ketten_nachtragen(conn) == 3
    conn.close()

    aus = ms.recall("Schleuse", limit=3)
    ids = re.findall(r"^#(\d+) \[", aus, re.M)
    assert len(ids) == 3, f"Platz nicht nachbesetzt: {aus}"
    aus_kette = [i for i in ids if i in ("4", "5", "6")]
    assert len(aus_kette) == 1, f"Kette belegt mehrere Plaetze: {aus}"
    # Gegenprobe: ohne Entdoppelung fuellte diese eine Kette ALLE drei Plaetze.
    assert "#1" in aus or "#2" in aus or "#3" in aus, aus


def test_kette_bindet_nur_zusammengehoeriges():
    """Zwei Sicherungen gegen Fehlalarm: ein sauber endender Eintrag bricht die
    Kette, und die Marke muss dieselbe sein - sonst klebt die letzte Notiz
    eines Projekts an der ersten des naechsten."""
    ms.remember("Ein vollstaendiger Satz endet hier.", tags="schiff", art="verlauf")
    ms.remember("und dieser faengt klein an", tags="schiff", art="verlauf")
    ms.remember("Ein abgebrochener Satz ohne Ende", tags="schiff", art="verlauf")
    ms.remember("und diese Fortsetzung traegt eine andere Marke",
                tags="hafen", art="verlauf")
    conn = ms._connect()
    gebunden = ms._ketten_nachtragen(conn)
    conn.close()
    assert gebunden == 0, f"{gebunden} Glieder gebunden, erwartet keine"


def test_kette_erkennt_rollenzeile_ohne_betreff():
    """#1483: Der Import schnitt an ". ", und das trifft meist genau die
    Absatzgrenze VOR einer Fettzeile. "**Werkzeuge:**" faengt sauber gross an
    und ist trotzdem ein Bruchstueck - die Zeile benennt eine Rolle, kein
    Thema. Mit nur `_setzt_fort` blieben alle sechs Stuecke der LOEVE-Notiz
    (#189-#194) unerkannt: wer #190 und #191 las, bekam Werkzeuge und Ablauf,
    aber nicht die Warnung aus #192 - und keinen Hinweis, dass da noch etwas
    steht. Das Ausbleiben des Vermerks sah aus wie Vollstaendigkeit."""
    ms.remember("Auf diesem Rechner laesst sich eine Fenstergroesse simulieren.",
                tags="schiff", art="arbeitsweise")
    ms.remember("**Werkzeuge:** `Xvfb`, `xdotool` und ImageMagick `import`.",
                tags="schiff", art="arbeitsweise")
    ms.remember("**Nicht vergessen:** conf.lua danach zwingend zuruecksetzen.",
                tags="schiff", art="arbeitsweise")
    conn = ms._connect()
    assert ms._ketten_nachtragen(conn) == 3
    conn.close()
    # Und das Stueck nennt in der Vorschau den Betreff seines Kopfes, sonst
    # liest es sich als Relativsatz ohne Hauptsatz.
    vermerk = ms.zeige("3")
    assert "Stueck 3 von 3" in vermerk, vermerk
    assert "Fenstergroesse simulier" in vermerk, vermerk  # bei 60 Zeichen gekappt


def test_rollenzeile_mit_eigenem_betreff_bindet_nicht():
    """Gegenprobe: eine Fettzeile, die ein Thema benennt statt einer Rolle,
    ist ein eigener Eintrag. Ohne diese Grenze wuerde aus einer 240 Eintraege
    langen Projektdatei eine 240er Kette, und der Vermerk hiesse "lies 240
    Eintraege" - das waere schlechter als gar keiner."""
    ms.remember("Ein vollstaendiger Satz endet hier.", tags="schiff", art="verlauf")
    ms.remember("**Harte Leitplanken:** gelten fuer alles Weitere.",
                tags="schiff", art="verlauf")
    conn = ms._connect()
    gebunden = ms._ketten_nachtragen(conn)
    conn.close()
    assert gebunden == 0, f"{gebunden} Glieder gebunden, erwartet keine"


def test_fortsetzung_erkennt_fuehrende_auszeichnung():
    """Ein Bruchstueck faengt nicht immer mit einem Kleinbuchstaben an:
    `applyItemsSync` lautlos verschwanden beginnt mit einem Backtick."""
    assert ms._setzt_fort("`applyItemsSync` lautlos verschwanden")
    assert ms._setzt_fort("*any* room that already had content")
    assert ms._setzt_fort("raumschiff_alpha_0-2.apk), gilt fuer den Rest")
    assert not ms._setzt_fort("**Harte Leitplanken:** gelten fuer alles")
    assert not ms._setzt_fort("Der Eintrag faengt sauber an")


def test_recall_gibt_einer_kette_nur_einen_platz():
    """Zwei Treffer aus demselben zerschnittenen Memo belegen EINEN Platz
    (#2257); der Vermerk an der verbliebenen Zeile nennt die ganze Spanne.
    Bis 2026-10-01 pruefte das nur ein Test von `frage()` - mit dem Werkzeug
    waere auch die einzige Deckung der Entdoppelung gegangen."""
    ms.remember("Das Display braucht nach dem Standby eine Pause von 20 ms (z.B",
                tags="turing35-display", art="fallstrick")
    ms.remember("gemessen am Pruefstand), sonst flackert das Panel beim ersten Bild.",
                tags="turing35-display", art="fallstrick")
    ms.remember("Ein voellig anderer Eintrag ueber das flackernde Panel am Pruefstand.",
                tags="turing35-display", art="messwert")
    conn = ms._connect()
    assert ms._ketten_nachtragen(conn) == 2
    conn.close()
    # Kein Eintrag enthaelt beide Woerter - die ODER-Stufe trifft alle drei.
    aus = ms.recall("Display Panel", limit=5)
    assert aus.count("[fallstrick]") == 1, aus
    assert "zerschnittenes Memo #1-#2" in aus, aus
    assert "voellig anderer Eintrag" in aus, aus


# --------------------------------------------------------------------------
# Werkzeuge
# --------------------------------------------------------------------------
def test_verdichten_nimmt_untermarken_mit():
    """#1448: `tags = ?` verglich die ganze Tag-Spalte auf Gleichheit und
    uebersah stumm gerade die mehrfach getaggten Eintraege."""
    ms.remember("Ein Text ueber Katzen und Hunde", tags="proj", art="fallstrick")
    ms.remember("Ein Text ueber Katzen und Hunde", tags="proj extra", art="fallstrick")
    aus = ms.verdichten(marke="proj")
    assert "2 Eintraege" in aus, aus


def test_remember_zeigt_die_dublette():
    """Der Hinweis selbst, nicht nur sein Scheitern. Vom 15. bis 26.09.2026
    schwieg er bei jedem `remember`: `_dubletten` entpackte vier Spalten,
    `_suche` lieferte seit Stand 5 fuenf, und den ValueError schluckte der
    Notausgang in `remember`. Der einzige Test dazu ersetzte `_dubletten`
    durch eine Attrappe und sah es deshalb nie."""
    ms.remember("Der Dampfkessel im Keller braucht jeden Winter Frostschutz der Sorte Glysantin",
                tags="haus", art="fallstrick")
    aus = ms.remember("Der Dampfkessel im Keller braucht jeden Winter Frostschutz der Sorte Glysantin G48",
                      tags="haus", art="fallstrick")
    assert "Aehnliche Eintraege" in aus, aus
    assert "  #1 (" in aus, aus


def test_faktencheck_uebersteht_eine_leere_antwort():
    """`content: null` ist eine gueltige Antwort, typisch fuer ein Denkmodell,
    das seine 16 Token im Denken verbraucht. Frueher warf `urteil` dann einen
    TypeError AUSSERHALB seines try - an `urteile()` vorbei, womit auch die
    schon erhaltenen Urteile der anderen Paare verloren waren."""
    fc = ms.faktencheck
    assert fc is not None
    echt = fc._post
    fc._post = lambda *a, **k: {"choices": [{"message": {"content": None}}]}
    try:
        assert fc.urteil("Notiz A", "Notiz B") is None
    finally:
        fc._post = echt


def test_remember_behaelt_den_text_wenn_der_dublettenhinweis_platzt():
    """Die Lehre aus #1426 lautet: was nach dem Schreiben noch scheitern kann,
    darf das Geschriebene nicht mitnehmen. Der Dublettenhinweis ist reine
    Lesearbeit und lief trotzdem in derselben Transaktion."""
    ms.remember("Erster Eintrag ueber Katzen", tags="probe", art="fallstrick")

    def platzt(*args, **kwargs):
        raise RuntimeError("geplatzt")

    echt, ms._dubletten = ms._dubletten, platzt
    try:
        aus = ms.remember("Zweiter Eintrag ueber Katzen", tags="probe", art="fallstrick")
    finally:
        ms._dubletten = echt

    assert "Gespeichert" in aus, aus
    conn = ms._connect()
    anzahl = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0]
    conn.close()
    assert anzahl == 2, f"{anzahl} Eintraege - der zweite ist beim Rollback verlorengegangen"


def test_remember_verweigert_zwei_arten():
    """Gehoert ein Text zu zwei Sorten, sind es zwei Eintraege - das ist der
    Zweck des Zwangs und darf nicht stillschweigend eine davon waehlen."""
    aus = ms.remember("Irgendwas", tags="probe", art="fallstrick,entscheidung")
    assert "Fehler" in aus and "nichts gespeichert" in aus, aus
    conn = ms._connect()
    anzahl = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0]
    conn.close()
    assert anzahl == 0


def test_positiver_artfilter_bremst_die_suche_nicht():
    """#1126 an der art-Tuer: `rowid IN (SELECT id FROM art ...)` sieht fuer
    SQLite wie ein Index aus und treibt dann die Abfrage - je gefilterter
    Rowid ein Zugriff auf mem samt MATCH-Auswertung, statt die Volltextsuche
    treiben zu lassen. Gemessen am Bestand: recall(art="fallstrick") 52 ms
    gegen 1,4 ms ohne art-Filter.

    Geprueft wird ein VERHAELTNIS, nie eine absolute Zeit - sonst haengt der
    Test an der Maschine. Der echte Abstand war Faktor 38, dieser Test
    scheitert ab Faktor 8: weit genug weg, dass Schwankung unter Last ihn
    nicht ausloest, und eng genug, dass der Rueckfall auffliegt.
    """
    conn = ms._connect()
    for i in range(400):
        conn.execute(
            "INSERT INTO eintrag (content, tags, ts, stems, teile, art)"
            " VALUES (?, 'probe', datetime('now'), '', '', ?)",
            (f"Eintrag {i} ueber Katalysator und Reaktor und Sperrfrist",
             "fallstrick" if i % 3 == 0 else ms.UNSORTIERT),
        )
    conn.commit()
    conn.close()

    def dauer(ruf, n=15):
        ruf()
        t = time.perf_counter()
        for _ in range(n):
            ruf()
        return (time.perf_counter() - t) / n

    ohne = dauer(lambda: ms.recall("Katalysator Reaktor", art="alle"))
    mit = dauer(lambda: ms.recall("Katalysator Reaktor", art="fallstrick"))
    assert mit < ohne * 8, (
        f"art-Filter kostet {mit * 1000:.1f} ms gegen {ohne * 1000:.1f} ms ohne "
        f"- Faktor {mit / ohne:.0f}. Treibt der Filter wieder die Abfrage?"
    )


def test_markenwaechter_meldet_die_nachbarmarke():
    """#1418: die Marke bleibt Freitext, zerfaellt aber unbemerkt in
    Schreibvarianten. Zeigen, nicht entscheiden."""
    ms.remember("Erster", tags="mcp-memory-server", art="fallstrick")
    aus = ms.remember("Zweiter", tags="mcp-memory", art="fallstrick")
    assert "mcp-memory-server" in aus and "Neue Marke" in aus, aus


def test_markenwaechter_meldet_auch_beim_zweiten_mal():
    """#1459: die Warnung kam genau einmal - `_marken_eintragen` machte die
    eben bemaengelte Marke zur bekannten. Gerade der zweite Eintrag unter dem
    Tippfehler ist der, der ihn festschreibt."""
    for _ in range(3):
        ms.remember("Bestand", tags="raumschiff-project", art="fallstrick")
    erst = ms.remember("Erster", tags="raumschif-project", art="fallstrick")
    zweit = ms.remember("Zweiter", tags="raumschif-project", art="fallstrick")
    assert "raumschiff-project" in erst, erst
    assert "raumschif-project" in zweit and "raumschiff-project" in zweit, zweit


def test_markenwaechter_schweigt_bei_gesetzter_marke():
    """Die Kehrseite: ein echtes neues Projekt soll nicht ewig gemahnt werden.
    Nach MARKE_ETABLIERT Eintraegen hat die Marke sich bewaehrt."""
    ms.remember("Bestand", tags="mcp-memory-server", art="fallstrick")
    for _ in range(ms.MARKE_ETABLIERT):
        ms.remember("Eigener Zweig", tags="mcp-memory-cli", art="fallstrick")
    aus = ms.remember("Noch einer", tags="mcp-memory-cli", art="fallstrick")
    # Jede Form der Mahnung nennt die Marke in Anfuehrungszeichen. Die fruehere
    # Pruefung fragte nach einer ZEILE, die genau "mcp-memory-cli" lautet - die
    # gibt es nie, der Test bestand also auch, wenn der Waechter ewig mahnte.
    assert "'mcp-memory-cli'" not in aus, aus
    assert "Dieselbe Sache" not in aus, aus


def test_artwort_als_marke_wird_jedes_mal_gemeldet():
    """#1459: schlimmer als beim Tippfehler - ein Art-Wort ist NIE eine
    zulaessige Marke, wurde aber genauso ins Verzeichnis uebernommen und
    danach nie wieder gemeldet."""
    erst = ms.remember("Erster", tags="fallstrick", art="messwert")
    zweit = ms.remember("Zweiter", tags="fallstrick", art="messwert")
    assert "Art-Wort" in erst, erst
    assert "Art-Wort" in zweit, zweit


def test_artwort_kommt_nicht_ins_markenverzeichnis():
    """Sonst schlaegt der Waechter es spaeter selbst als Nachbarmarke vor."""
    ms.remember("Erster", tags="fallstrick", art="messwert")
    conn = ms._connect()
    try:
        drin = [r[0] for r in conn.execute("SELECT marke FROM marken")]
    finally:
        conn.close()
    assert "fallstrick" not in drin, drin


def test_verzeichnis_vergisst_marken_veralteter_eintraege():
    """Der Weg, eine Fehlschreibung wieder loszuwerden: den Eintrag ablegen und
    nachziehen. Zaehlte `_marken_nachtragen` veraltete Eintraege mit, bliebe
    der Tippfehler fuer immer in der Vorschlagsliste."""
    aus = ms.remember("Tippfehler-Eintrag", tags="mcp-memry-server", art="messwert")
    rid = int(aus.split("#")[1].split()[0])
    ms.vergessen(str(rid), "Testeintrag")
    conn = ms._connect()
    try:
        ms._marken_nachtragen(conn)
        drin = [r[0] for r in conn.execute("SELECT marke FROM marken")]
        conn.commit()
    finally:
        conn.close()
    assert "mcp-memry-server" not in drin, drin


# --------------------------------------------------------------------------
# Laeufer
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def test_import_schreibt_in_den_speicher_von_stand_5():
    """Der Import schrieb nach `mem` - der Tabelle VOR Schemastand 5.

    Auf einer heutigen Datenbank brach er damit schon beim Einlesen des
    vorhandenen Bestandes ab ("no such table: mem"), `--trocken`
    eingeschlossen. Unbemerkt blieb das, weil kein Test ihn je aufrief: er
    galt als einmaliges Werkzeug, das nie wieder laeuft - fuer jeden Fremden
    ist er aber der erste Befehl ueberhaupt. Der Test prueft den ganzen Weg
    bis in den FTS-Index, denn den fuellen seit Stand 5 die Trigger und nicht
    mehr der Aufrufer.
    """
    ordner = ms.DB_PATH.parent / "memos"
    ordner.mkdir()
    (ordner / "beispiel.md").write_text(
        "---\nmodified: 2026-01-02\n---\n\n"
        "Ein Absatz, lang genug fuer die Mindestzeichenzahl von vierzig Zeichen.\n"
    )

    def lauf(*argumente):
        alt = sys.argv
        sys.argv = ["import_memos.py", str(ordner), *argumente]
        try:
            return im.main()
        finally:
            sys.argv = alt

    assert lauf("--trocken") == 0
    conn = ms._connect()
    assert conn.execute("SELECT count(*) FROM eintrag").fetchone()[0] == 0
    conn.close()

    assert lauf() == 0
    conn = ms._connect()
    zeilen = conn.execute("SELECT content, tags, ts, art FROM eintrag").fetchall()
    treffer = conn.execute(
        "SELECT rowid FROM suche WHERE suche MATCH 'Mindestzeichenzahl'"
    ).fetchall()
    conn.close()
    assert len(zeilen) == 1, zeilen
    assert zeilen[0][1] == "beispiel", zeilen
    assert zeilen[0][2] == "2026-01-02 00:00:00", zeilen
    assert zeilen[0][3] == ms.UNSORTIERT, zeilen
    assert len(treffer) == 1, "der Trigger hat den Index nicht gefuellt"

    # Mehrfach aufrufbar: derselbe Absatz kommt kein zweites Mal herein.
    assert lauf() == 0
    conn = ms._connect()
    assert conn.execute("SELECT count(*) FROM eintrag").fetchone()[0] == 1
    conn.close()


def test_import_ohne_argument_nennt_die_vorhandenen_ordner():
    """Ohne Pfad wird der Ordner aus dem Arbeitsverzeichnis geraten - und
    trifft fast nie, weil man im Repo steht und nicht im gemeinten Projekt.
    Das blosse "Kein Ordner" liess den Fremden dann raten; der Hinweis muss
    die tatsaechlich vorhandenen Ordner nennen."""
    wurzel = ms.DB_PATH.parent / "projects"
    (wurzel / "-ein-projekt" / "memory").mkdir(parents=True)
    (wurzel / "-ein-projekt" / "memory" / "a.md").write_text("Text")
    (wurzel / "-leer" / "memory").mkdir(parents=True)  # ohne *.md: kein Kandidat
    alt_wurzel, alt_argv = im.PROJEKTWURZEL, sys.argv
    im.PROJEKTWURZEL = wurzel
    sys.argv = ["import_memos.py"]
    try:
        assert im.main() == 1
        kandidaten = im._kandidaten()
    finally:
        im.PROJEKTWURZEL, sys.argv = alt_wurzel, alt_argv
    assert kandidaten == [wurzel / "-ein-projekt" / "memory"], kandidaten


# --------------------------------------------------------------------------
# Die Skripte neben dem Server
# --------------------------------------------------------------------------
# Sie kennen Tabellennamen, laufen selten und hatten bis 2026-09-19 keinen
# einzigen Test. Genau darum rosteten `import_memos.py`, `migration_art.py`
# und `pruefstand_fc.py` beim Umzug auf Schemastand 5 lautlos weg: der Server
# wurde mitgenommen, sie nicht. Jedes Skript, das eine Tabelle beim Namen
# nennt, bekommt hier einen Fall - und der Waechter darunter faengt das
# naechste, an das niemand gedacht hat.
def test_nachziehen_laeuft_als_skript_durch():
    """`nachziehen.py` fragt `marken` und `eintrag.kopf` selbst ab, nicht ueber
    memory_server. test_nachziehen_konvergiert prueft die Bibliotheksfunktion
    dahinter - nicht die vier Zeilen SQL im Skript, und genau die sind es, die
    beim naechsten Schemaschritt brechen."""
    ms.remember("Fusionskatalysator im Reaktor, ein Eintrag mit Marke", tags="probe",
                art="fallstrick")
    alt = sys.argv
    sys.argv = ["nachziehen.py", "--probe"]
    try:
        assert nachziehen.main() == 0
        sys.argv = ["nachziehen.py"]
        assert nachziehen.main() == 0
    finally:
        sys.argv = alt
    conn = ms._connect()
    marken = {r[0] for r in conn.execute("SELECT marke FROM marken")}
    conn.close()
    assert "probe" in marken, marken


def test_pruefstand_baut_den_satz_aus_dem_speicher():
    """`pruefstand_fc.satz()` las `mem` und brach damit auf jeder heutigen
    Datenbank ab - auch bei `--trocken`, das gar kein Board braucht. Der Fall
    kommt ohne Geraet aus: gemessen wird nur, dass der Satz aus dem Bestand
    entsteht und die `ersetzt=`-Beziehung aus `veraltet` ankommt."""
    a = ms.remember("Die Lernrate bleibt konstant, weil der Zerfall die Schritte erstickt.",
                    tags="probe", art="entscheidung")
    # Bewusst OHNE Korrekturvokabel ("Korrektur", "widerlegt"): sonst nimmt
    # ZWEIFELHAFT das Paar aus dem Satz, und geprueft waere nichts. Genau so
    # bestand der Test bis 2026-09-26 - leben tat er von der Handliste daneben.
    b = ms.remember("Die Lernrate faellt jetzt nach dem Aufwaermen linear auf null ab.",
                    tags="probe", art="entscheidung", ersetzt=re.search(r"#(\d+)", a).group(1))
    ms.remember("Ein harmloser Absatz ueber ganz andere Dinge, naemlich Schiffe.",
                tags="probe", art="verlauf")
    alt_gebaut = pruefstand_fc.GEBAUT
    # Die echte Handliste im Projektordner bleibt draussen - der Satz soll aus
    # DIESEM Bestand entstehen, nicht aus einer Datei neben dem Test.
    pruefstand_fc.GEBAUT = ms.DB_PATH.parent / "keine_handliste.json"
    conn = ms._connect()
    try:
        paare = pruefstand_fc.satz(conn, leicht=2, schwer=2)
        bestand = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0]
    finally:
        conn.close()
        pruefstand_fc.GEBAUT = alt_gebaut
    assert bestand == 3
    id_a, id_b = (int(re.search(r"#(\d+)", t).group(1)) for t in (a, b))
    ersetzt = [(p.id_a, p.id_b) for p in paare if p.quelle == "ersetzt"]
    assert ersetzt == [(id_a, id_b)], (ersetzt, [p.quelle for p in paare])


def test_jedes_skript_laeuft_trocken_gegen_eine_stand_5_datenbank():
    """Die Probe, die kein Muster ist: SQLite antwortet, nicht die Regex.

    Der Waechter darunter liest Quelltext und sitzt damit in derselben
    Werkzeugklasse, die hier zweimal danebengriff - ein Muster prueft nur,
    woran der Schreiber schon gedacht hat. Beim ersten Mal war es die
    Gross-/Kleinschreibung, beim zweiten eine Anfrage, die in einer Variablen
    stand. Ein Tabellenname aus einem f-String oder einer importierten
    Konstante geht an jeder Textsuche vorbei, so fein sie auch ist.

    Dieser Fall sucht darum nicht nach Namen. Er ruft jedes Skript einmal
    trocken gegen eine frische Stand-5-Datenbank auf - jedes hat einen
    Trockenlauf, das ist kein Zufall, sondern die Bauart des Projekts. Nennt
    eines eine Tabelle, die es nicht mehr gibt, meldet das die Datenbank
    selbst, ganz gleich, wie der Name zustande kam.

    Die Grenze dieser Probe ist die andere als die des Waechters, und darum
    stehen beide da: ausgefuehrt wird nur, was der Trockenlauf anfaesst. Der
    INSERT-Zweig von import_memos.py etwa haengt am Fall darueber, nicht an
    diesem hier.
    """
    ordner = Path(__file__).resolve().parent
    erst = ms.remember("Die Lernrate bleibt konstant, weil der Zerfall die Schritte erstickt.",
                       tags="probe", art="entscheidung")
    ms.remember("Korrektur: der geometrische Zerfall ist widerlegt, es lag am Aufwaermen.",
                tags="probe", art="entscheidung", ersetzt=re.search(r"#(\d+)", erst).group(1))
    memos = ms.DB_PATH.parent / "memos"
    memos.mkdir()
    (memos / "beispiel.md").write_text(
        "Ein Absatz, lang genug fuer die Mindestzeichenzahl von vierzig Zeichen.\n"
    )

    proben = {
        "import_memos.py": [str(memos), "--trocken"],
        "nachziehen.py": ["--probe"],
        "pruefstand_fc.py": ["--db", str(ms.DB_PATH), "--trocken"],
        "migration_art.py": ["--db", str(ms.DB_PATH), "--trocken"],
    }
    # Wer hier steht, hat nichts auszufuehren - mit Grund, nicht aus Bequemlichkeit.
    ohne_probe = {
        "memory_server.py": "der Server selbst; die 30 Faelle darueber sind seine Probe",
        "morphologie.py": "rechnet auf Zeichenketten, oeffnet nie eine Datenbank",
        "faktencheck.py": "spricht HTTP mit dem Board, kein SQL",
        "zg.py": "fremdes Werkzeug (ZeroGit-Sicherung), gehoert nicht zum Projekt"
                 " und spricht beim Trockenlauf das Netz an",
        Path(__file__).name: "diese Datei",
    }

    # Ein neues Skript darf nicht unbemerkt dazukommen: es muss entweder eine
    # Probe haben, begruendet befreit oder ausdruecklich eingefroren sein.
    vorhanden = {pfad.name for pfad in ordner.glob("*.py")}
    eingefroren = {
        pfad.name for pfad in ordner.glob("*.py")
        if "SCHEMASTAND 4 - eingefroren" in pfad.read_text(encoding="utf-8")
    }
    unbekannt = vorhanden - set(proben) - set(ohne_probe) - eingefroren
    assert not unbekannt, (
        "Skript ohne Trockenlauf-Probe: " + ", ".join(sorted(unbekannt))
        + " - in `proben` eintragen, in `ohne_probe` begruenden oder einfrieren."
    )

    for name in sorted(set(proben) & vorhanden):
        modul = importlib.import_module(name[:-3])
        alt = sys.argv
        sys.argv = [name, *proben[name]]
        gesagt = io.StringIO()
        try:
            with contextlib.redirect_stdout(gesagt):
                ergebnis = modul.main()
        except Exception as fehler:
            raise AssertionError(f"{name} laeuft nicht trocken durch: {fehler!r}") from fehler
        finally:
            sys.argv = alt
        assert ergebnis == 0, f"{name} meldet {ergebnis}:\n{gesagt.getvalue()[-400:]}"


def test_kein_lebendes_skript_liest_die_tabellen_vor_stand_5():
    """Das zweite Netz, und ausdruecklich das schwaechere.

    Ein Grep von Hand hatte `pruefstand_fc.py` uebersehen, weil dort `from
    mem` klein geschrieben steht und in `migration_zeitstempel.py` sogar in
    einer Variablen - eine Vermutung ist kein Test. Dieser Fall ist die
    breitere Suche, aber er bleibt eine Suche: einen Namen aus einem f-String
    findet er nicht. Das tut die Ausfuehrungsprobe darueber, und sie steht
    deshalb zuerst. Was dieser hier dafuer kann: er sieht auch die Zeilen, die
    kein Trockenlauf je betritt - kein Skript im Ordner nennt `mem`, `art`
    oder `kette`, die Tabellen vor Schemastand 5.

    Zwei Ausnahmen, beide begruendet: `memory_server.py` MUSS die alten Namen
    kennen, es zieht die Datenbank um (`_umzug_auf_5`, `_schattenbestand_bergen`),
    und diese Datei nennt sie in den Regressionsfaellen dazu. Ein Einmal-Skript,
    das bewusst auf dem alten Stand einfriert, sagt das mit der Zeile
    'SCHEMASTAND 4 - eingefroren' und ist damit heraus - aber ausdruecklich,
    nicht aus Versehen."""
    alt = re.compile(r"\b(from|into|update|join)\s+(mem|art|kette)\b", re.I)
    ausnahmen = {"memory_server.py", Path(__file__).name}
    gefunden = []
    for pfad in sorted(Path(__file__).resolve().parent.glob("*.py")):
        if pfad.name in ausnahmen:
            continue
        text = pfad.read_text(encoding="utf-8")
        if "SCHEMASTAND 4 - eingefroren" in text:
            continue
        for nr, zeile in enumerate(text.splitlines(), 1):
            if alt.search(zeile):
                gefunden.append(f"  {pfad.name}:{nr}: {zeile.strip()}")
    assert not gefunden, (
        "Tabellen von vor Schemastand 5 in einem lebenden Skript:\n"
        + "\n".join(gefunden)
    )


# --------------------------------------------------------------------------
# Rueckkopplung
# --------------------------------------------------------------------------
def _lerne(frage: str, ids: str) -> None:
    """Was im Betrieb geschieht: suchen, dann das Richtige holen."""
    ms.recall(frage)
    ms.zeige(ids)


def _raenge(ausgabe: str) -> list:
    """Ids NUR aus den Kopfzeilen der Treffer (#1899)."""
    return re.findall(r"^#(\d+) ", ausgabe, re.M)


def test_rueckkopplung_hebt_die_wiederholte_frage_nach_vorn():
    """#1917: wortgleich wiederholte Fragen meinen im Betrieb denselben
    Eintrag - 46 von 46 gemessen. Genau darauf ruht der Mechanismus."""
    ms.remember("Sensor Sensor Sensor am Mast, dreifach erwaehnt", tags="schiff",
                art="schnittstelle")
    ms.remember("Die Kalibrierung des Sensors laeuft ueber die Werkbank",
                tags="schiff", art="fallstrick")
    vorher = _raenge(ms.recall("Sensor Kalibrierung"))
    ziel = vorher[-1]
    assert len(vorher) > 1 and vorher[0] != ziel, vorher

    _lerne("Sensor Kalibrierung", ziel)

    nachher = ms.recall("Sensor Kalibrierung")
    assert _raenge(nachher)[0] == ziel, nachher
    assert "schon einmal so gesucht" in nachher, nachher


def test_rueckkopplung_feuert_nur_bei_wortgleichheit():
    """#1918: unscharfes Nachschlagen verdraengte Geschwisterfragen von Rang 1.
    Eine aehnliche, aber nicht wortgleiche Frage darf nichts erben."""
    ms.remember("Flackern im Eis, Kapitel zur Moeblierung", tags="eis",
                art="entscheidung")
    ms.remember("Flackern im Eis, Kapitel zur Werkstatt", tags="eis",
                art="entscheidung")
    _lerne("Flackern Eis Moeblierung", "1")

    geschwister = ms.recall("Flackern Eis Werkstatt")
    assert "schon einmal so gesucht" not in geschwister, geschwister
    # Dieselbe Frage in anderer Reihenfolge ist dagegen dieselbe Frage.
    gedreht = ms.recall("Moeblierung Eis Flackern")
    assert "schon einmal so gesucht" in gedreht, gedreht


def test_rueckkopplung_achtet_die_filter_des_aufrufers():
    """Ein durch art= oder marke= ausgeschlossener Eintrag darf auch ueber die
    Rueckkopplung nicht hereinkommen - sonst umgeht sie die Einschraenkung."""
    ms.remember("Der Rumpf traegt die Antenne", tags="schiff", art="schnittstelle")
    ms.remember("Der Rumpf rostet an der Naht", tags="werft", art="fallstrick")
    _lerne("Rumpf Antenne", "1")

    assert "schon einmal so gesucht" in ms.recall("Rumpf Antenne")
    assert "1" not in _raenge(ms.recall("Rumpf Antenne", art="fallstrick"))
    assert "1" not in _raenge(ms.recall("Rumpf Antenne", marke="werft"))
    # Die eigene Marke trifft weiterhin.
    assert "1" in _raenge(ms.recall("Rumpf Antenne", marke="schiff"))


def test_rueckkopplung_zeigt_keinen_veralteten_eintrag():
    """Abgeloest ist abgeloest - auch fuer ein gemerktes Paar."""
    ms.remember("Der Kompass weicht um zwei Strich ab", tags="schiff", art="messwert")
    _lerne("Kompass Abweichung Strich", "1")
    assert "1" in _raenge(ms.recall("Kompass Abweichung Strich"))
    ms.vergessen("1", grund="nachgemessen")
    assert "1" not in _raenge(ms.recall("Kompass Abweichung Strich"))


def test_rueckkopplung_verwirft_den_themenwechsel():
    """Die Relevanzprobe aus zielsicher.py: ein `zeige`, das nach der Suche
    etwas ganz anderes nachschlaegt, ist kein Paar. Ohne sie sammelt der
    Mechanismus genau das Gift ein, das er nicht vertraegt (#1917)."""
    ms.remember("Die Ankerwinde klemmt bei Frost", tags="schiff", art="fallstrick")
    ms.remember("Der Proviant reicht vier Wochen", tags="schiff", art="messwert")
    ms.recall("Ankerwinde Frost")
    ms.zeige("2")          # etwas voellig anderes nachgeschlagen
    assert "schon einmal so gesucht" not in ms.recall("Ankerwinde Frost")


def test_zeige_ohne_vorherige_suche_merkt_nichts():
    """Wer die Id schon kennt, beantwortet damit keine Frage."""
    ms.remember("Das Ruderblatt sitzt fest", tags="schiff", art="fallstrick")
    ms.zeige("1")
    conn = ms._connect()
    try:
        assert conn.execute("SELECT count(*) FROM nachfrage").fetchone()[0] == 0
    finally:
        conn.close()


def test_rueckkopplung_laesst_explizite_syntax_in_ruhe():
    """Wer FTS5-Syntax schreibt, bekommt genau die - wie bei der Kaskade."""
    ms.remember("Der Kessel steht unter Druck", tags="schiff", art="fallstrick")
    ms.recall("Kessel Druck")
    ms.zeige("1")
    assert "schon einmal so gesucht" not in ms.recall("Kessel AND Druck")


# --------------------------------------------------------------------------
# Fixkosten der Werkzeugdefinitionen
# --------------------------------------------------------------------------
# Die neun Definitionen gehen in JEDER Sitzung in den Kontext, bevor die erste
# Frage gestellt ist. Sie sind zwischen dem 2026-09-15 und dem 2026-09-25 von
# 7.313 auf 12.215 Zeichen gewachsen, und es ist niemandem aufgefallen, weil
# nichts sie angesehen hat (messung/FIXKOSTEN-AUDIT.md).
#
# Der Deckel ist keine Qualitaetsaussage, sondern eine Bremse: er laesst kleine
# Korrekturen an einer Beschreibung durch und faengt ab, was eine Groessenordnung
# hat - ein neues Werkzeug, oder ein Absatz Entwurfsbegruendung. Ihn anzuheben
# ist erlaubt; er soll nur erzwingen, dass es eine Entscheidung ist und kein
# Nebeneffekt. Wer anhebt, schreibt den Grund dazu.
FIXKOSTEN_DECKEL = 11_800     # Stand 2026-09-25: 11.492 Z ueber neun Werkzeuge


def _werkzeugdefinitionen():
    """Die Definitionen so, wie `list_tools()` sie ueber die Leitung schickt."""
    import asyncio
    import json
    werkzeuge = asyncio.run(ms.server.list_tools())
    return {
        w.name: json.dumps(
            {"name": w.name, "description": w.description or "",
             "inputSchema": w.input_schema},
            ensure_ascii=False)
        for w in werkzeuge
    }


def test_fixkosten_der_werkzeuge_bleiben_unter_dem_deckel():
    """Jedes Wachstum hier zahlt jede Sitzung mit, auch die, die das Werkzeug
    nie aufruft - deshalb gehoert es unter Beobachtung statt unter Vertrauen."""
    teile = _werkzeugdefinitionen()
    summe = sum(len(t) for t in teile.values())
    if summe > FIXKOSTEN_DECKEL:
        groesste = sorted(teile.items(), key=lambda kv: -len(kv[1]))[:3]
        raise AssertionError(
            f"Werkzeugdefinitionen {summe:,} Z, Deckel {FIXKOSTEN_DECKEL:,} Z "
            f"({summe - FIXKOSTEN_DECKEL:+,} Z, ~{(summe - FIXKOSTEN_DECKEL)/2:.0f} "
            f"Token je Sitzung). Groesste: "
            + ", ".join(f"{n} {len(t):,}" for n, t in groesste)
            + ". Entweder kuerzen oder FIXKOSTEN_DECKEL mit Begruendung anheben.")


def test_die_parameterschemata_tragen_keine_title_felder():
    """#2235: pydantic wiederholt im `title` nur den Feldnamen - ein Drittel
    aller Schema-Zeichen fuer nichts. `_schema_entrumpeln()` raeumt das beim
    Import weg; faellt der Aufruf weg oder aendert das SDK die Stelle, an der
    das Schema haengt, kommen die 723 Zeichen lautlos zurueck."""
    import asyncio
    for w in asyncio.run(ms.server.list_tools()):
        assert "title" not in w.input_schema, w.name
        for feld, angaben in w.input_schema.get("properties", {}).items():
            assert "title" not in angaben, f"{w.name}.{feld}"


def test_ein_entrumpeltes_schema_nimmt_die_argumente_weiter_an():
    """Die Gegenprobe zum Kuerzen: die Pruefung der Argumente haengt an
    `fn_metadata`, nicht am ausgelieferten Schema - aber behauptet ist das
    schnell, und ein kaputter Aufrufpfad waere ein teurer Preis fuer 723 Z."""
    import asyncio
    ms.remember("Die Ankerkette ist zu kurz", tags="schiff", art="fallstrick")
    aus = asyncio.run(ms.server.call_tool("recall", {"query": "Ankerkette", "limit": 3}))
    # Nach dem Treffer fragen, nicht nach dem Suchwort - das steht auch in
    # "Keine Treffer fuer: Ankerkette".
    assert "#1 [" in str(aus), aus
    aus = asyncio.run(ms.server.call_tool("zeige", {"ids": "1"}))
    assert "Ankerkette" in str(aus)


# --------------------------------------------------------------------------
# Gastbetrieb: eine Sitzung von einem anderen Rechner liest mit
# --------------------------------------------------------------------------
@contextlib.contextmanager
def _als_gast():
    ms.GAST = True
    try:
        yield
    finally:
        ms.GAST = False


def _zaehle(tabelle: str) -> int:
    conn = sqlite3.connect(ms.DB_PATH)
    try:
        return conn.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0]
    finally:
        conn.close()


def test_gast_liest_und_hinterlaesst_nichts():
    """Auch die Suche schreibt: `recall` -> `zeige` legt ein Paar in `nachfrage`.
    Deshalb zuerst die Gegenprobe im Hausbetrieb - ohne sie koennte dieser Test
    nicht scheitern."""
    ms.remember("Das Ruderblatt sitzt fest", tags="schiff", art="fallstrick")
    ms.recall("Ruderblatt")
    ms.zeige("1")
    davor = _zaehle("nachfrage")
    assert davor > 0, "Gegenprobe: im Hausbetrieb muss das Paar gemerkt werden"
    with _als_gast():
        aus = ms.recall("Ruderblatt fest")
        assert f"{ms.NAME}#1 [" in aus, aus
        assert "Ruderblatt" in ms.zeige(f"{ms.NAME}#1")
    assert _zaehle("nachfrage") == davor
    assert _zaehle("eintrag") == 1


def test_gast_kann_nicht_schreiben():
    """Die Garantie ist die nur lesend geoeffnete Datei, nicht die Werkzeugliste."""
    ms.remember("Die Ankerkette ist zu kurz", tags="schiff", art="fallstrick")
    with _als_gast():
        assert "nichts gespeichert" in ms.remember("Neu", tags="schiff", art="fallstrick")
        for versuch in (lambda: ms.vergessen("1"), lambda: ms.einordnen("1", "messwert")):
            try:
                versuch()
            except sqlite3.OperationalError as exc:
                assert "readonly" in str(exc), exc
            else:
                raise AssertionError("Schreibzugriff im Gastbetrieb ging durch")
    assert _zaehle("eintrag") == 1 and _zaehle("veraltet") == 0
    assert "[fallstrick]" in ms.recall("Ankerkette")


def test_gast_sieht_nur_suchen_lesen_blaettern():
    """Und der Hausbetrieb behaelt alle acht - die Kuerzung gilt nur dem Gast."""
    import subprocess
    haus = {w.name for w in ms.server._tool_manager.list_tools()}
    assert {"remember", "vergessen", "einordnen", "verdichten", "pruefe"} <= haus, haus
    assert len(haus) == 8, haus
    aus = subprocess.run(
        [sys.executable, "-c",
         "import memory_server as ms; ms._gast_einrichten();"
         "print(' '.join(sorted(t.name for t in ms.server._tool_manager.list_tools())))"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parent,
        env={**os.environ, "MEMORY_FC_AUS": "1"},
    )
    assert aus.stdout.split() == ["recall", "themen", "zeige"], (
        aus.stdout, aus.stderr)


def test_gast_migriert_nicht():
    """Ein fremder Schemastand wird abgelehnt statt umgebaut."""
    ms.remember("Die Ankerkette ist zu kurz", tags="schiff", art="fallstrick")
    conn = sqlite3.connect(ms.DB_PATH)
    conn.execute("UPDATE schema SET wert = '4' WHERE schluessel = 'stand'")
    conn.commit()
    conn.close()
    with _als_gast():
        try:
            ms.recall("Ankerkette")
        except RuntimeError as exc:
            assert "Schemastand 4" in str(exc), exc
        else:
            raise AssertionError("Gast hat einen fremden Schemastand angenommen")


def test_nummer_eines_fremden_gedaechtnisses_wird_abgewiesen():
    """#2386: dieselbe Nummer bezeichnet auf jedem Rechner einen anderen Eintrag.
    Der Name schuetzt nur, wenn ihn auch das Gedaechtnis prueft, dem er NICHT gilt."""
    ms.remember("Die Ankerkette ist zu kurz", tags="schiff", art="fallstrick")
    assert "Ankerkette" in ms.zeige(f"{ms.NAME}#1")
    assert "Ankerkette" in ms.zeige("#1") and "Ankerkette" in ms.zeige("1")
    for aus in (ms.zeige("anderswo#1"), ms.vergessen("anderswo#1"),
                ms.einordnen("anderswo#1", "messwert"), ms.pruefe("anderswo#1,2"),
                ms.remember("Neu", tags="schiff", art="fallstrick", ersetzt="anderswo#1")):
        assert aus.startswith("Fehler") and "anderswo" in aus, aus
    assert _zaehle("eintrag") == 1 and _zaehle("veraltet") == 0


def test_namen_kommen_nur_vor_nummern():
    n = ms.NAME
    assert ms._mit_namen("#72 und (#73), #74-#75") == f"{n}#72 und ({n}#73), {n}#74-{n}#75"
    assert ms._mit_namen("siehe [[2382]]") == f"siehe [[{n}#2382]]"
    for bleibt in ("&#72;", "Farbe #202020", f"{n}#72", "a#72", "## Kopf", "Nr. 72"):
        assert ms._mit_namen(bleibt) == bleibt, bleibt


def main() -> int:
    faelle = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f)]
    breite = max(len(n) for n, _ in faelle)
    fehler = []

    for name, fall in faelle:
        ordner = Path(tempfile.mkdtemp(prefix="memtest-"))
        ms.DB_PATH = ordner / "memory.db"
        # Die offenen Fragen haengen am Prozess, nicht an der Datenbank - ohne
        # dieses Zuruecksetzen traegt ein Test die Suche des vorigen weiter.
        del ms._OFFENE_FRAGEN[:]
        assert ms.DB_PATH.resolve() != ECHTE_DB, "Testlauf zeigt auf den echten Bestand - abgebrochen"
        try:
            fall()
            print(f"  ok    {name}")
        except Exception:
            print(f"  FEHLT {name}")
            fehler.append((name, traceback.format_exc()))
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    print()
    for name, spur in fehler:
        print(f"--- {name} ---")
        print(spur)
    print(f"{len(faelle) - len(fehler)}/{len(faelle)} bestanden"
          + (f", {len(fehler)} gescheitert" if fehler else ""))
    return 1 if fehler else 0


if __name__ == "__main__":
    raise SystemExit(main())
