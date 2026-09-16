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

import os
import sqlite3
import shutil
import tempfile
import time
import traceback
from pathlib import Path

# Vor dem Import: das Board soll bei keinem remember angefragt werden. Sonst
# kostet jeder Test die Vorprobe, und das Ergebnis haengt am Netz.
os.environ["MEMORY_FC_AUS"] = "1"

import memory_server as ms  # noqa: E402
from morphologie import teile_spalte, wortschatz  # noqa: E402

ECHTE_DB = Path(__file__).resolve().parent / "memory.db"


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
    ms._schema_geprueft = None  # Schemapruefung erneut erzwingen
    try:
        aus = ms.remember("Mit nagelneuer Art", tags="probe", art="kochrezept")
        assert "Gespeichert" in aus, aus
        conn = ms._connect()
        gesetzt = conn.execute("SELECT art FROM eintrag WHERE id = 2").fetchone()
        conn.close()
        assert gesetzt and gesetzt[0] == "kochrezept", gesetzt
    finally:
        ms.ARTEN = original
        ms._schema_geprueft = None


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
    assert "mcp-memory-cli" not in aus.split("Tags:")[-1].split("\n")[1:], aus
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
def main() -> int:
    faelle = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f)]
    breite = max(len(n) for n, _ in faelle)
    fehler = []

    for name, fall in faelle:
        ordner = Path(tempfile.mkdtemp(prefix="memtest-"))
        ms.DB_PATH = ordner / "memory.db"
        ms._schema_geprueft = None
        assert ms.DB_PATH != ECHTE_DB, "Testlauf zeigt auf den echten Bestand - abgebrochen"
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
