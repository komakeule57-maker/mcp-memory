#!/usr/bin/env python3
"""Lokaler MCP-Server fuer persistentes KI-Memory (SQLite + FTS5, stdio)."""

import difflib
import math
import re
import sqlite3
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from morphologie import kandidaten, stamm_spalte, stem, teile_spalte, wortschatz

# Zweitmeinung zum Dublettenhinweis, optional. Der Import ist gekapselt, damit
# eine fehlende, kaputte oder halb bearbeitete faktencheck.py den ganzen Server
# nicht startunfaehig macht - das Memory ist das Wichtige, die Zweitmeinung die
# Zugabe. Ab hier heisst "faktencheck is None" schlicht: gibt es nicht.
try:
    import faktencheck
except Exception:  # pragma: no cover - Notausgang, kein Normalfall
    faktencheck = None

DB_PATH = Path(__file__).resolve().parent / "memory.db"

# Die Spalten des INDEX. `ts` steht nicht darin - das Datum ist zum Anzeigen
# da, nie ein Suchwort. Bis Stand 4 war das eine Verabredung (`UNINDEXED`) in
# einer Tabelle, die alles indiziert; seit Stand 5 ist es Bauart, weil der
# Index eine eigene Sache ist und `eintrag` der Speicher (#1425, #1453).
INDEXSPALTEN = ("content", "tags", "stems", "teile")

# Aus `content`+`tags` gerechnete Spalten. Wer eine der beiden Quellen
# schreibt, MUSS diese beiden nachziehen - sonst driften sie lautlos (#1424).
ABGELEITET = ("stems", "teile")

# Stand des Datenbankaufbaus. Ohne diese Zahl merkt keine Migration, dass sie
# faellig ist - das Schema aus dem Code abzuleiten reicht nicht, denn
# `CREATE TABLE IF NOT EXISTS` sieht eine veraltete Tabelle fuer voll an (#1426).
SCHEMA_STAND = 5

# SQLites Vorgabe sind 5 s, danach fliegt "database is locked" (#1427). Der
# Wert gilt JE VERBINDUNG und muss bei jedem Oeffnen neu gesetzt werden.
SPERRFRIST = 30.0

# Wie viele Paare `pruefe` je Aufruf ans Geraet gibt. Jedes kostet zwei
# Anfragen, weil beide Richtungen gefragt werden - bei rund 5 s je Anfrage sind
# 5 Paare schon knapp eine Minute.
DECKEL_PRUEFE = 5

# Ab so vielen eigenen Eintraegen gilt eine Marke als gesetzt und der
# Markenwaechter schweigt. Eine Warnung, die nur beim allerersten Eintrag
# kommt, verhindert den Zerfall gerade nicht - der zweite Tippfehler ist der,
# der ihn festschreibt (#1459).
MARKE_ETABLIERT = 3

# Zweite Achse neben den Marken: die Marke sagt WO (Projekt), die Art sagt
# WELCHE SORTE Wissen. Bewusst ein geschlossenes, kurzes Vokabular - ein
# freies Feld zerfaellt binnen Wochen in "fallstrick", "fallstricke", "pitfall"
# und filtert dann nichts mehr. Die Datenbank erzwingt es per CHECK.
ARTEN = (
    "schnittstelle",  # Signatur, Dateiname, Befehl, Datenformat - woertlich gebraucht
    "fallstrick",     # der naheliegende Weg ist falsch, weil ...
    "entscheidung",   # so und nicht anders gewaehlt, samt Begruendung
    "messwert",       # Zahl samt Messkriterium
    "arbeitsweise",   # wie mit diesem Nutzer zu arbeiten ist
    "verlauf",        # Chronik: was wann gebaut wurde
)
# Kein Eintrag in der Nebentabelle heisst "noch nicht einsortiert". Damit
# braucht die Umstellung keinen Nachtrag ueber 984 Zeilen, und der Rueckstand
# bleibt sichtbar, statt sich als stiller Vorgabewert zu verstecken.
UNSORTIERT = "gemischt"
# Chronik faellt aus der Vorgabeansicht - sie ist das Beiwerk, das jede
# Suche nach einer Einzelheit zudeckt. Nicht geloescht, nur stumm: art="verlauf"
# holt sie zurueck. Dasselbe Muster wie bei veralteten Eintraegen.
STUMM = ("verlauf",)

# Das Markenfeld ist mehrwertig, und im Bestand stehen BEIDE Trenner
# nebeneinander ("spiel3d-test Nachtfrost" neben "spiel3d-test,Nachtfrost").
# Deshalb wird an beiden getrennt, statt sich auf einen zu verlassen.
_TRENNER = re.compile(r"[\s,]+")

server = MCPServer("memory")


def _marken(tags: str) -> list:
    """Das Markenfeld in einzelne Marken zerlegen."""
    return [m for m in _TRENNER.split((tags or "").strip()) if m]


def _marken_klausel(marke: str) -> str:
    """FTS5-Zusatz, der auf eine oder mehrere Marken einschraenkt - oder "".

    **Bewusst in die MATCH-Anfrage statt in die WHERE-Klausel.** Ein positiver
    Zeilenfilter der Form `rowid IN (SELECT ...)` neben `ORDER BY rank LIMIT n`
    kostet auf diesem Bestand das Zwanzigfache (#1126): die Liste sieht fuer
    SQLite wie ein Index aus, und dann treibt sie die Abfrage. Fuer die Marke
    gibt es diesen Ausweg nicht - also gehoert sie dorthin, wo FTS5 sie ohnehin
    indiziert hat.

    Fuer die Art dagegen schon: seit 2026-09-15 steht dort `EXISTS (... WHERE
    a.id = mem.rowid ...)`, das laesst die Volltextsuche treiben und probt je
    Treffer. Die Regel lautet also nicht mehr "alle Filter negativ", sondern
    "kein Filter darf die Abfrage treiben".

    Die Marke wird als Phrase gesucht. Das ist keine exakte Gleichheit: der
    Tokenisierer trennt am Bindestrich, `tags:"leuchtturm"` trifft also auch
    `leuchtturm-project`. Fuer einen Filter ist das die nuetzlichere Lesart -
    wer nach dem Projekt fragt, will die Untermarken mit. Umgekehrt trifft
    `tags:"mcp-memory-server"` NICHT `mcp-memory`, die Phrase braucht alle drei
    Token in Folge.
    """
    gewollt = _marken(marke)
    if not gewollt:
        return ""
    return "(" + " OR ".join(f'tags : "{m}"' for m in gewollt) + ")"


def _mit_marke(fts: str, klausel: str) -> str:
    return f"({fts}) AND {klausel}" if klausel else fts


# --------------------------------------------------------------------------
# Datenbank
# --------------------------------------------------------------------------
def _connect() -> sqlite3.Connection:
    """Verbindung pro Tool-Call: oeffnen, Schema sicherstellen, Aufrufer schliesst.

    `timeout` ist SQLites busy_timeout. Er gilt JE VERBINDUNG, muss also bei
    jedem Oeffnen mit. WAL dagegen haftet an der Datei und wirkt ein fuer alle
    Mal - aber ohne ihn sperrt ein Schreiber auch saemtliche Leser (#1427).
    """
    conn = sqlite3.connect(DB_PATH, timeout=SPERRFRIST)
    conn.execute("PRAGMA journal_mode = WAL")
    # Gilt JE VERBINDUNG und ist in SQLite per Vorgabe aus - ohne diese Zeile
    # steht der Fremdschluessel im Schema und tut nichts.
    conn.execute("PRAGMA foreign_keys = ON")
    _schema_sicherstellen(conn)
    return conn


def _stand(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema (schluessel TEXT PRIMARY KEY, wert TEXT)")
    zeile = conn.execute("SELECT wert FROM schema WHERE schluessel = 'stand'").fetchone()
    return int(zeile[0]) if zeile else 0


def _stand_setzen(conn: sqlite3.Connection, stand: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema (schluessel, wert) VALUES ('stand', ?)", (str(stand),)
    )


def _gibt_es(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _schema_sicherstellen(conn: sqlite3.Connection) -> None:
    """Legt an, was fehlt, und zieht einen Altbestand auf den heutigen Stand.

    Seit Stand 5 ist `eintrag` eine GEWOEHNLICHE Tabelle und `suche` nur noch
    ein Index darueber (`content='eintrag'`). Das behebt den Wurzelfehler, aus
    dem vier Fallen zugleich folgten (#1453): es gibt wieder ALTER, echte
    Fremdschluessel, ein aenderbares Vokabular und Filter, die ein
    gewoehnliches WHERE sind statt eines Kunstgriffs.
    """
    stand = _stand(conn)
    _nebentabellen(conn)
    if _gibt_es(conn, "eintrag") and _gibt_es(conn, "mem"):
        _schattenbestand_bergen(conn)
    if not _gibt_es(conn, "eintrag"):
        if _gibt_es(conn, "mem"):
            if stand < 4:
                raise RuntimeError(
                    f"Diese Datenbank steht auf Schemastand {stand}. Die Stufen davor "
                    "sind mit Stand 5 entfallen - es gab keine Datenbank mehr, die sie "
                    "braucht. Mit einem Checkout vor dem Umbau auf Stand 4 bringen, "
                    "dann hier weiter."
                )
            _umzug_auf_5(conn)
        else:
            _speicher_anlegen(conn)
    # Nur schreiben, wenn sich etwas geaendert hat. Die Versionsnummer bei
    # jeder Verbindung neu zu setzen ist ein INSERT OR REPLACE je
    # Werkzeugaufruf - unter WAL ein fsync, und der schlaegt mit rund 5,5 ms
    # auf JEDEN Aufruf durch, gleich ob er sonst 0,7 oder 8 ms braucht.
    if stand != SCHEMA_STAND:
        _stand_setzen(conn, SCHEMA_STAND)
        conn.commit()


def _schattenbestand_bergen(conn: sqlite3.Connection) -> int:
    """Holt Eintraege zurueck, die ein Prozess mit ALTEM Code geschrieben hat.

    Der Fall ist eng, aber er tritt garantiert ein: nach dem Umzug auf Stand 5
    laeuft der MCP-Server noch mit dem Code von vorher im Speicher. Der findet
    kein `mem`, haelt die Datenbank fuer neu, legt `mem` leer an, schreibt
    dorthin und setzt den Schemastand auf 4 zurueck - **ohne Fehlermeldung**.
    Der Eintrag ist damit fuer den neuen Code unsichtbar, und der Nutzer hat
    eine Bestaetigung gesehen.

    Gegen den Datenverlust hilft kein Hinweis in einer Datei, denn der alte
    Prozess liest sie nicht mehr. Also raeumt der neue Code beim naechsten
    Start hinter ihm auf: was in `mem` steht, wandert nach `eintrag`, die
    Schattentabellen fliegen raus. Ids koennen nicht uebernommen werden - die
    des Schattens beginnen wieder bei 1 und waeren besetzt.
    """
    zeilen = conn.execute(
        "SELECT rowid, content, tags, ts, stems, teile FROM mem ORDER BY rowid"
    ).fetchall()
    for rid, content, tags, ts, stems, teile in zeilen:
        art = UNSORTIERT
        if _gibt_es(conn, "art"):
            gesetzt = conn.execute("SELECT art FROM art WHERE id = ?", (rid,)).fetchone()
            if gesetzt and gesetzt[0] in (*ARTEN, UNSORTIERT):
                art = gesetzt[0]
        conn.execute(
            "INSERT INTO eintrag (content, tags, ts, stems, teile, art, art_am)"
            " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (content, tags or "", ts, stems or "", teile or "", art),
        )
    conn.execute("DROP TABLE IF EXISTS mem_vocab")
    conn.execute("DROP TABLE mem")
    conn.execute("DROP TABLE IF EXISTS art")
    conn.execute("DROP TABLE IF EXISTS kette")
    conn.commit()
    if zeilen:
        sys.stderr.write(
            f"mcp-memory: {len(zeilen)} Eintraege aus einem Schattenbestand geborgen "
            "- sie stammen von einem Serverprozess mit Code vor Schemastand 5. "
            "Sie haben neue Ids bekommen.\n"
        )
    return len(zeilen)


def _nebentabellen(conn: sqlite3.Connection) -> None:
    """Die Tabellen neben dem Speicher. Jede steht aus einem eigenen Grund da."""
    # Veraltete Eintraege sind ein ANFUEGENDES Protokoll, kein Zustand: eine
    # Zeile je Vorgang, nicht je Eintrag. Wird derselbe Eintrag zweimal
    # abgeloest, sind das zwei Vermerke - mit `INSERT OR REPLACE` haette der
    # zweite die Herkunft des ersten geloescht (#1428). Das ist der eine Fall,
    # in dem eine Nebentabelle richtig ist und bleibt.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS veraltet ("
        " vermerk INTEGER PRIMARY KEY AUTOINCREMENT,"
        " id INTEGER NOT NULL, durch INTEGER, am TEXT, grund TEXT)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS veraltet_nach_id ON veraltet(id)")
    # Verzeichnis der vergebenen Marken. Die Marke bleibt Freitext - erzwingen
    # laesst sie sich nicht, ohne neue Projekte zu verbieten. Aber sie zerfaellt
    # unbemerkt (#1418), und dagegen haelt `remember` jede neue dagegen.
    conn.execute("CREATE TABLE IF NOT EXISTS marken (marke TEXT PRIMARY KEY, seit TEXT)")
    # Woerterbuch fuer die Kompositazerlegung, mit Schluessel und damit einzeln
    # abfragbar statt nur am Stueck (#1455).
    conn.execute("CREATE TABLE IF NOT EXISTS vokabel (wort TEXT PRIMARY KEY) WITHOUT ROWID")
    # Die Wissenssorten stehen als ZEILEN, nicht als CHECK. Ein CHECK friert
    # sein Vokabular ein und laesst sich nur durch einen Tabellenumbau aendern
    # (#1426) - eine neue Art ist so ein INSERT, und der Fremdschluessel auf
    # `eintrag.art` haelt trotzdem jeden Tippfehler ab.
    conn.execute("CREATE TABLE IF NOT EXISTS art_vokabular (art TEXT PRIMARY KEY)")
    # Erst lesen, dann nur das Fehlende schreiben. Ein `INSERT OR IGNORE` je
    # Verbindung sieht harmlos aus, ist aber eine SCHREIBtransaktion bei jedem
    # Werkzeugaufruf - unter WAL ein fsync, gemessen 2,4 -> 7,8 ms je recall.
    # Im Normalfall steht hier jetzt eine Leseabfrage und sonst nichts.
    da = {z[0] for z in conn.execute("SELECT art FROM art_vokabular")}
    fehlt = [(a,) for a in (*ARTEN, UNSORTIERT) if a not in da]
    if fehlt:
        conn.executemany("INSERT INTO art_vokabular (art) VALUES (?)", fehlt)


def _speicher_anlegen(conn: sqlite3.Connection) -> None:
    """`eintrag` als Speicher, `suche` als Index darueber, Trigger dazwischen.

    Der Index kann jetzt nicht mehr vom Speicher abweichen - das erledigen die
    drei Trigger, nicht mehr die Sorgfalt des Aufrufers. `ts` steht gar nicht
    erst darin: dass das Datum kein Suchwort ist, war bis Stand 4 eine
    Verabredung (`UNINDEXED`) und ist jetzt Bauart (#1425).
    """
    conn.executescript(f"""
        CREATE TABLE eintrag (
          id      INTEGER PRIMARY KEY,
          content TEXT NOT NULL,
          tags    TEXT NOT NULL DEFAULT '',
          ts      TEXT NOT NULL,
          stems   TEXT NOT NULL DEFAULT '',
          teile   TEXT NOT NULL DEFAULT '',
          art     TEXT NOT NULL DEFAULT '{UNSORTIERT}' REFERENCES art_vokabular(art),
          art_am  TEXT,
          kopf    INTEGER REFERENCES eintrag(id),
          nr      INTEGER
        );
        CREATE INDEX eintrag_nach_art  ON eintrag(art);
        CREATE INDEX eintrag_nach_ts   ON eintrag(ts);
        CREATE INDEX eintrag_nach_kopf ON eintrag(kopf) WHERE kopf IS NOT NULL;

        CREATE VIRTUAL TABLE suche USING fts5(
            content, tags, stems, teile,
            content='eintrag', content_rowid='id');

        CREATE TRIGGER eintrag_ai AFTER INSERT ON eintrag BEGIN
          INSERT INTO suche(rowid, content, tags, stems, teile)
          VALUES (new.id, new.content, new.tags, new.stems, new.teile);
        END;
        CREATE TRIGGER eintrag_ad AFTER DELETE ON eintrag BEGIN
          INSERT INTO suche(suche, rowid, content, tags, stems, teile)
          VALUES ('delete', old.id, old.content, old.tags, old.stems, old.teile);
        END;
        CREATE TRIGGER eintrag_au AFTER UPDATE ON eintrag BEGIN
          INSERT INTO suche(suche, rowid, content, tags, stems, teile)
          VALUES ('delete', old.id, old.content, old.tags, old.stems, old.teile);
          INSERT INTO suche(rowid, content, tags, stems, teile)
          VALUES (new.id, new.content, new.tags, new.stems, new.teile);
        END;

        CREATE VIRTUAL TABLE suche_vocab USING fts5vocab(suche, col);
    """)


def _umzug_auf_5(conn: sqlite3.Connection) -> int:
    """Stand 4 -> 5: aus der FTS-Tabelle wird ein Speicher mit einem Index.

    `art` und `kette` werden dabei zu Spalten - sie waren nie eigene Dinge,
    sondern Eigenschaften eines Eintrags, die nur deshalb danebenstanden, weil
    eine virtuelle Tabelle kein ALTER kennt. `veraltet` bleibt, weil es
    wirklich ein Protokoll ist.
    """
    _speicher_anlegen(conn)
    conn.execute(
        "INSERT INTO eintrag (id, content, tags, ts, stems, teile, art, art_am, kopf, nr)"
        " SELECT m.rowid, m.content, coalesce(m.tags,''), m.ts,"
        "        coalesce(m.stems,''), coalesce(m.teile,''),"
        "        coalesce(a.art, ?), a.am, k.kopf, k.nr"
        "   FROM mem m"
        "   LEFT JOIN art a   ON a.id = m.rowid"
        "   LEFT JOIN kette k ON k.id = m.rowid"
        "  ORDER BY m.rowid",
        (UNSORTIERT,),
    )
    umgezogen = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS mem_vocab")
    conn.execute("DROP TABLE mem")
    conn.execute("DROP TABLE IF EXISTS art")
    conn.execute("DROP TABLE IF EXISTS kette")
    return umgezogen


def _marken_nachtragen(conn: sqlite3.Connection) -> int:
    """Traegt jede im Bestand vorkommende Marke ins Verzeichnis ein.

    Zugleich der Weg, das Verzeichnis nach einer Umbenennung wieder in Deckung
    zu bringen: Marken ohne einen einzigen Eintrag fallen heraus. Dasselbe gilt
    fuer Marken, die nur noch veraltete Eintraege tragen, und fuer Art-Woerter -
    beide haben in der Vorschlagsliste des Waechters nichts zu suchen (#1459).
    """
    tot = {r[0] for r in conn.execute("SELECT id FROM veraltet")}
    gefunden = {}
    for rowid, tags, ts in conn.execute("SELECT id, tags, ts FROM eintrag"):
        if rowid in tot:
            continue
        for m in _marken(tags):
            if m.lower() in ARTEN:
                continue
            gefunden[m] = min(gefunden.get(m, ts), ts)
    conn.execute("DELETE FROM marken")
    conn.executemany(
        "INSERT INTO marken (marke, seit) VALUES (?, ?)", sorted(gefunden.items())
    )
    return len(gefunden)


# SQLite nimmt je Anfrage nur begrenzt viele Platzhalter (aeltere Uebersetzungen
# 999). Die Kandidaten eines langen Eintrags gehen darueber hinaus, also in
# Haeppchen - das bleibt eine Handvoll indizierter Abfragen statt eines Scans.
# --------------------------------------------------------------------------
# Zerschnittene Memos zusammenbinden (#1463)
# --------------------------------------------------------------------------
# Der Import trennte an ". " und hielt dabei deutsche Abkuerzungen und
# Ordnungszahlen fuer Satzenden ("z.B. ", "inkl. ", "10. Aussenkarte").
# Erkennbar ist der Schnitt an beiden Enden zugleich: der Vorgaenger bricht
# ohne Satzzeichen ab UND der Nachfolger faengt klein an.
_KETTE_ENDE = re.compile(r"[.!?:;)\]\"]\s*$")
# Fuehrende Auszeichnung zaehlt nicht: `applyItemsSync` lautlos verschwanden
# ist ein Bruchstueck, auch wenn das erste Zeichen ein Backtick ist.
_KETTE_VORSATZ = re.compile(r"^[`\"'*_\[(]+")


def _setzt_fort(text: str) -> bool:
    """Faengt der Text mitten im Satz an?"""
    kern = _KETTE_VORSATZ.sub("", text.lstrip())
    return bool(kern) and (kern[:1].islower() or kern[:1] in ")]},")


# Zweites Merkmal, nachgetragen 2026-09-16 (#1483). Der Import schnitt an
# ". " - und das trifft meistens genau die Absatzgrenze VOR einer Fettzeile.
# "**Werkzeuge:**" faengt sauber gross an und ist trotzdem ein Bruchstueck:
# die Zeile benennt eine ROLLE im Text, kein Thema. Mit nur _setzt_fort blieben
# alle sechs Stuecke der LOEVE-Notiz (#189-#194) unerkannt; wer #190 und #191
# las, bekam Werkzeuge und Ablauf, aber nicht die Warnung aus #192 - und keinen
# Hinweis, dass daneben noch etwas steht.
_ROLLE = (
    r"how to apply|how it works|why|nicht vergessen|ablauf|werkzeuge|hardware|"
    r"praktische folge|merke|merksatz|fazit|beides|dabei"
)
# a) Fettzeile (oder blanke Zeile) mit Rollenwort statt Betreff.
# b) Rueckbezugswort am Anfang: das Bezugswort steht im Vorgaenger.
_ABSCHNITT_FORT = re.compile(
    rf"^\s*(?:\*\*\s*)?(?:{_ROLLE})\b[^\n]{{0,30}}?(?:\*\*|:)"
    r"|^\s*(?:Enth(?:ä|ae)lt|Deshalb|Damit|Ausserdem|Au\u00dferdem|Trotzdem|"
    r"Stattdessen|Das hei(?:ß|ss)t|Das erkl(?:ä|ae)rt)\b",
    re.IGNORECASE,
)


def _setzt_abschnitt_fort(text: str) -> bool:
    """Faengt der Text mit einer Rolle oder einem Rueckbezug statt mit einem
    Thema an? Dann haengt er am Vorgaenger, auch wenn er grammatisch sauber
    beginnt."""
    return bool(_ABSCHNITT_FORT.match(text.lstrip()))


def _ketten_nachtragen(conn: sqlite3.Connection) -> int:
    """Findet zerschnittene Memos und traegt ihre Glieder in `kette` ein.

    Zwei Sicherungen gegen Fehlalarm: die Stuecke muessen dicht beieinander
    liegen (der Import schrieb sie hintereinander) und dieselbe erste Marke
    tragen. Ohne die zweite kleben sonst die letzte Notiz eines Projekts und
    die erste des naechsten zusammen.

    Ein Stueck gilt als Fortsetzung, wenn es mitten im Satz anfaengt
    (`_setzt_fort`) ODER mit einer Rolle statt einem Betreff
    (`_setzt_abschnitt_fort`, nachgetragen 2026-09-16). Die Kette waechst nur
    ueber solche Glieder weiter - ein Eintrag mit eigenem Betreff beendet sie.
    Deshalb wird aus einer 240 Eintraege langen Projektdatei keine 240er Kette.
    """
    zeilen = conn.execute("SELECT id, content, tags FROM eintrag ORDER BY id").fetchall()
    schnitt = {}
    for (a, ca, ta), (b, cb, tb) in zip(zeilen, zeilen[1:]):
        if b - a > 3:
            continue
        if _marken(ta)[:1] != _marken(tb)[:1]:
            continue
        # Zwei Wege zum selben Schluss. Der erste verlangt, dass der
        # Vorgaenger offen endet - ein sauber endender Satz bricht die Kette.
        # Der zweite braucht das nicht: eine Rollenzeile haengt am Vorgaenger,
        # gerade WEIL der ordentlich zu Ende ist (#1483).
        if _setzt_fort(cb) and not _KETTE_ENDE.search(ca.rstrip()):
            schnitt[a] = b
        elif _setzt_abschnitt_fort(cb):
            schnitt[a] = b
    glieder = []
    nachfolger = set(schnitt.values())
    for anfang in sorted(schnitt):
        if anfang in nachfolger:
            continue  # steht selbst schon in einer Kette
        glied, nr = anfang, 1
        while True:
            glieder.append((glied, anfang, nr))
            if glied not in schnitt:
                break
            glied, nr = schnitt[glied], nr + 1
    conn.execute("UPDATE eintrag SET kopf = NULL, nr = NULL WHERE kopf IS NOT NULL")
    conn.executemany("UPDATE eintrag SET kopf = ?, nr = ? WHERE id = ?",
                     [(kopf, nr, glied) for glied, kopf, nr in glieder])
    conn.commit()
    return len(glieder)


def _ketten_von(conn: sqlite3.Connection, ids) -> dict:
    """Vermerk je Id, die zu einem zerschnittenen Memo gehoert."""
    ids = list(ids)
    if not ids:
        return {}
    platz = ",".join("?" * len(ids))
    teil = {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            f"SELECT id, kopf, nr FROM eintrag WHERE kopf IS NOT NULL AND id IN ({platz})",
            tuple(ids),
        )
    }
    if not teil:
        return {}
    koepfe = {kopf for kopf, _ in teil.values()}
    platz = ",".join("?" * len(koepfe))
    ganz = {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            f"SELECT kopf, count(*), max(id) FROM eintrag WHERE kopf IN ({platz})"
            " GROUP BY kopf",
            tuple(koepfe),
        )
    }
    # Der Betreff steht im KOPF, nicht im Stueck. Ohne ihn liest die Vorschau
    # eines Fortsetzungsstuecks sich als Relativsatz ohne Hauptsatz - "#704
    # Enthaelt: Auth-Verhalten (Token liegt unter `password`)" sagt nicht,
    # wovon das der Inhalt ist (#1483).
    platz = ",".join("?" * len(koepfe))
    betreff = {
        r[0]: _betreff(r[1])
        for r in conn.execute(
            f"SELECT id, content FROM eintrag WHERE id IN ({platz})", tuple(koepfe)
        )
    }
    aus = {}
    for i, (kopf, nr) in teil.items():
        anzahl, letzte = ganz[kopf]
        if nr == 1:
            aus[i] = f" [Stueck {nr} von {anzahl}, zerschnittenes Memo #{kopf}-#{letzte}]"
        else:
            aus[i] = (f" [Stueck {nr} von {anzahl} von \"{betreff[kopf]}\","
                      f" zerschnittenes Memo #{kopf}-#{letzte}]")
    return aus


_BETREFF_VORSATZ = re.compile(r"^[\s*#`>_-]+")


def _betreff(text: str, laenge: int = 60) -> str:
    """Die erste Zeile eines Eintrags als Titel - Auszeichnung weg, gekuerzt."""
    zeile = _BETREFF_VORSATZ.sub("", text.strip().splitlines()[0] if text.strip() else "")
    zeile = zeile.replace("**", "").strip()
    return zeile if len(zeile) <= laenge else zeile[: laenge - 1].rstrip() + "\u2026"


_HAEPPCHEN = 900


def _vokabular(conn: sqlite3.Connection, zusatz: str = "") -> set:
    """Woerterbuch fuer die Zerlegung EINES Textes - gezielt geholt, nicht ganz.

    Frueher las diese Funktion das gesamte Vokabular aus `mem_vocab`. Das ist
    eine fts5vocab-Tabelle ohne Schluessel: die Abfrage durchwanderte bei jedem
    `remember` den ganzen Termindex, einschliesslich der `stems`- und
    `teile`-Spalten, die dabei gar nicht gesucht sind. Gemessen 18,5 ms bei
    1315 Eintraegen, linear mit dem Bestand wachsend (#1455).

    `zerlege` fragt aber nur nach Teilzeichenketten des Wortes, das es gerade
    zerlegt - `kandidaten()` sagt, nach welchen. Also werden genau die geholt.
    Der Aufwand haengt damit am Eintrag statt am Bestand.

    Der neue Text kommt ungefragt dazu: sonst koennte sich der erste Eintrag
    einer leeren Datenbank nie an seinem eigenen Wortschatz zerlegen.
    """
    gesucht = sorted(kandidaten(zusatz))
    gefunden = set()
    for i in range(0, len(gesucht), _HAEPPCHEN):
        haeppchen = gesucht[i:i + _HAEPPCHEN]
        platz = ",".join("?" * len(haeppchen))
        gefunden.update(
            r[0] for r in conn.execute(
                f"SELECT wort FROM vokabel WHERE wort IN ({platz})", haeppchen
            )
        )
    return gefunden | wortschatz(zusatz)


def _vokabular_ganz(conn: sqlite3.Connection) -> set:
    """Das ganze Woerterbuch - nur fuer den Stapellauf.

    `_nachziehen` fasst ohnehin jede Zeile an; dort ist einmal alles zu lesen
    billiger als je Zeile gezielt zu fragen. Fuer den Einzelfall ist es
    umgekehrt, und der ist der haeufige.
    """
    return {r[0] for r in conn.execute("SELECT wort FROM vokabel")}


def _vokabel_eintragen(conn: sqlite3.Connection, text: str) -> None:
    """Die Woerter eines neuen Eintrags ins Woerterbuch aufnehmen."""
    conn.executemany(
        "INSERT OR IGNORE INTO vokabel (wort) VALUES (?)",
        [(w,) for w in wortschatz(text)],
    )


def _vokabel_nachtragen(conn: sqlite3.Connection) -> int:
    """Baut das Woerterbuch aus dem Inhalt neu.

    Gegenstueck zu `_marken_nachtragen` und aus demselben Grund noetig: das
    Verzeichnis wird beim Schreiben fortgeschrieben und driftet deshalb, sobald
    jemand `content` oder `tags` an `remember` vorbei anfasst.
    """
    woerter = set()
    for c, t in conn.execute("SELECT content, tags FROM eintrag"):
        woerter |= wortschatz(f"{c} {t}")
    conn.execute("DELETE FROM vokabel")
    conn.executemany(
        "INSERT INTO vokabel (wort) VALUES (?)", [(w,) for w in sorted(woerter)]
    )
    return len(woerter)


def _ableitungen(conn: sqlite3.Connection, text: str, tags: str, vokab=None) -> tuple:
    """(stems, teile) aus Inhalt und Marken - die EINZIGE Stelle, die sie rechnet.

    Bewusst eine Funktion und nicht zwei Zeilen im INSERT: die Ableitungen
    doppelt zu fuehren war der Weg, auf dem sie auseinanderliefen (#1424).

    `vokab` vorzugeben ist fuer den Stapellauf: das Woerterbuch einmal zu holen
    statt je Zeile macht aus 1290 Abfragen ueber 18.000 Vokabeln eine. Die
    eigenen Woerter des Eintrags kommen trotzdem JE ZEILE dazu - ohne sie kann
    sich ein Eintrag nicht an seinem eigenen Wortschatz zerlegen, und der
    Stapellauf machte die Bestandsspalten aermer statt reicher.
    """
    volltext = f"{text} {tags}"
    vokab = _vokabular(conn, volltext) if vokab is None else vokab | wortschatz(volltext)
    return stamm_spalte(volltext), teile_spalte(volltext, vokab)


def _nachziehen(conn: sqlite3.Connection, rids=None) -> list:
    """Rechnet `stems`/`teile` neu und meldet, welche Eintraege sich geaendert haben.

    Braucht es, weil beide Spalten Momentaufnahmen sind: `teile` haengt am
    Vokabular des Augenblicks, `stems` an den Regeln in morphologie.py. Ohne
    diesen Weg gibt es nach einer Regelaenderung oder einem UPDATE auf `tags`
    keine Moeglichkeit, den Bestand wieder in Deckung zu bringen.
    """
    wo, args = "", ()
    if rids:
        wo = f" WHERE id IN ({','.join('?' * len(rids))})"
        args = tuple(rids)
    zeilen = conn.execute(
        f"SELECT id, content, tags, stems, teile FROM eintrag{wo}", args
    ).fetchall()
    # Einmal fuer den ganzen Lauf: waehrend des Nachziehens aendert sich nur
    # `stems`/`teile`, nie `content`/`tags` - das Woerterbuch bleibt also stehen.
    vokab = _vokabular_ganz(conn)
    geaendert = []
    for rid, c, t, stems_alt, teile_alt in zeilen:
        stems, teile = _ableitungen(conn, c, t, vokab)
        if stems != (stems_alt or "") or teile != (teile_alt or ""):
            conn.execute(
                "UPDATE eintrag SET stems = ?, teile = ? WHERE id = ?", (stems, teile, rid)
            )
            geaendert.append(rid)
    return geaendert


# --------------------------------------------------------------------------
# Suche
# --------------------------------------------------------------------------
_SYNTAX_ZEICHEN = set('"*():^')  # Bindestrich NICHT: kommt in normalen Fragen vor
_OPERATOREN = {"AND", "OR", "NOT", "NEAR"}
_WORT = re.compile(r"\w+", re.UNICODE)


# Nennt die Anfrage selbst eine Spalte, wird sie nicht angefasst - sonst
# widersprachen sich aeussere und innere Einschraenkung.
_NENNT_SPALTE = re.compile(r"[:{]")


def _auf_inhalt(fts: str) -> str:
    """Bindet eine FTS5-Anfrage an content+tags, wenn sie keine Spalte nennt.

    Eine unqualifizierte MATCH-Anfrage durchsucht ALLE Spalten, also auch die
    Morphologiespalten - die Staffelung der Kaskade waere hinfaellig und die
    Suche heimlich schon gestemmt (#1052). Die Kaskade schreibt ihre Stufen
    deshalb selbst mit `{content tags}`; der Ausweg fuer handgeschriebene
    Syntax tat es nicht und umging damit genau diese Sperre (#1425).
    """
    return fts if _NENNT_SPALTE.search(fts) else f"{{content tags}} : ({fts})"


def _ist_explizite_syntax(query: str) -> bool:
    return any(c in _SYNTAX_ZEICHEN for c in query) or any(
        w in _OPERATOREN for w in query.split()
    )


def _terme(query: str) -> list:
    """Einzelbuchstaben fallen weg, einzelne ZIFFERN nicht.

    Die Laengenschwelle soll Rauschen wie "a" abwerfen. Sie traf aber auch
    die Ziffer, und damit ausgerechnet das unterscheidende Token: `recall`
    nach "Deck 5" suchte faktisch nur nach "Deck" und lieferte Deck 4 und
    Deck 9 (gemessen 2026-09-15, #1420). Zweistellig ging es durch - der
    Fehler hing an der Stellenzahl.
    """
    gesehen, terme = set(), []
    for w in _WORT.findall(query):
        k = w.lower()
        if (len(k) > 1 or k.isdigit()) and k not in gesehen:
            gesehen.add(k)
            terme.append(w)
    return terme


def _suche(conn: sqlite3.Connection, query: str, limit: int, filter_=("", ())):
    """Gibt (zeilen, fehlertext) zurueck - ungueltige Syntax wirft nicht."""
    wo, args = filter_
    try:
        return conn.execute(
            "SELECT e.id, e.ts, e.content, e.tags, e.art"
            " FROM suche s JOIN eintrag e ON e.id = s.rowid"
            f" WHERE suche MATCH ?{wo} ORDER BY rank LIMIT ?",
            (query, *args, limit),
        ).fetchall(), None
    except sqlite3.OperationalError as exc:
        return [], str(exc)


def _arten_lesen(art: str):
    """'' -> None (Vorgabe), 'alle' -> 'alle', sonst Liste. Wirft bei Unbekanntem."""
    namen = [w for w in re.split(r"[\s,]+", (art or "").strip().lower()) if w]
    if not namen:
        return None
    if "alle" in namen:
        return "alle"
    unbekannt = [n for n in namen if n not in ARTEN and n != UNSORTIERT]
    if unbekannt:
        raise ValueError(
            f"Unbekannte Art: {', '.join(unbekannt)}. "
            f"Moeglich: {', '.join(ARTEN)}, {UNSORTIERT}, alle."
        )
    return namen


def _filter(art: str = "", mit_veraltet: bool = False):
    """Baut (SQL-Zusatz, Parameter) fuer die WHERE-Klausel der Suche.

    Seit Stand 5 ist `art` eine Spalte, der Filter also ein gewoehnlicher
    Spaltenvergleich. Bis dahin stand die Art in einer Nebentabelle, und der
    naheliegende `rowid IN (SELECT ...)`-Filter trieb die Abfrage statt sie
    zu proben - 52 ms gegen 1,4 ms, geheilt durch einen EXISTS-Kunstgriff
    (#1454). Der Kunstgriff ist mit der Nebentabelle weggefallen.

    Fuer `veraltet` bleibt EXISTS, und zwar richtig: das ist ein anfuegendes
    Protokoll und keine Eigenschaft des Eintrags. Korreliert geschrieben
    treibt es die Abfrage nicht.
    """
    wo, args = "", []
    if not mit_veraltet:
        wo += " AND NOT EXISTS (SELECT 1 FROM veraltet v WHERE v.id = e.id)"
    gewaehlt = _arten_lesen(art)
    if gewaehlt is None:
        wo += f" AND e.art NOT IN ({','.join('?' * len(STUMM))})"
        args += list(STUMM)
    elif gewaehlt != "alle":
        wo += f" AND e.art IN ({','.join('?' * len(gewaehlt))})"
        args += list(gewaehlt)
    return wo, tuple(args)


# --------------------------------------------------------------------------
# Darstellung: Vorschau gegen Volltext
# --------------------------------------------------------------------------
_KOPFZEILE = re.compile(r"^\*\*(.+?)\*\*", re.S)


def _titel(content: str, breite: int = 120) -> str:
    """Eine Zeile, die den Eintrag kenntlich macht.

    Nicht die erste Textzeile: die Eintraege sind auf ~75 Zeichen hart
    umbrochen, eine Zeile endet also mitten im Satz. Eine fette Ueberschrift
    am Anfang ist dagegen eine Aussage und bekommt den Vortritt.
    """
    text = " ".join(content.split())
    kopf = _KOPFZEILE.match(text)
    if kopf and 20 <= len(kopf.group(1)) <= breite:
        return kopf.group(1).strip()
    if len(text) <= breite:
        return text
    schnitt = text.rfind(" ", 0, breite)
    return text[: schnitt if schnitt > breite * 0.6 else breite].rstrip(" ,;:—-") + "…"


def _zeile(rid, ts, content, tags, art, voll: bool, vermerk: str = "") -> str:
    """Eine Trefferzeile - als Vorschau oder im Volltext."""
    if voll:
        kopf = f"#{rid} [{ts}] ({art}" + (f", {tags}" if tags else "") + ")"
        return f"{kopf}{vermerk}\n{content}"
    marke = f" ({tags})" if tags else ""
    return f"#{rid} [{art}] {ts[:10]} {_titel(content)}{marke}{vermerk}"


def _staemme(text: str) -> set:
    return {stem(w) for w in _WORT.findall(text) if len(w) > 2}


def _gewichte(conn, staemme: set) -> dict:
    """Seltenheit je Stamm aus dem Index selbst. Ein Stamm, der in fast jedem
    Eintrag vorkommt, sagt nichts ueber Aehnlichkeit aus."""
    if not staemme:
        return {}
    gesamt = conn.execute("SELECT count(*) FROM eintrag").fetchone()[0] or 1
    platz = ",".join("?" * len(staemme))
    haeufig = dict(
        conn.execute(
            f"SELECT term, doc FROM suche_vocab WHERE col='stems' AND term IN ({platz})",
            tuple(staemme),
        )
    )
    return {s: math.log(1 + gesamt / (1 + haeufig.get(s, 0))) for s in staemme}


def _ueberschneidung(neu: set, alt: set, gew: dict) -> float:
    """Wie viel vom Gehalt des NEUEN Textes steckt schon im alten - nach
    Seltenheit gewichtet. Billiger Ersatz fuer Aehnlichkeit; er soll Dubletten
    nur ZEIGEN, entschieden wird nicht hier."""
    summe = sum(gew.get(s, 0) for s in neu)
    if summe <= 0:
        return 0.0
    return sum(gew.get(s, 0) for s in neu & alt) / summe


# Ein Datum ist EINE Zahl - sonst zerfaellt "2026-09-10" in drei, und jeder
# Datumswechsel meldet drei Abweichungen. Versionen (0.4, lua5.1) und
# Kommazahlen (0,55) bleiben aus demselben Grund ein Stueck.
_ZAHL = re.compile(r"\d{4}-\d{2}-\d{2}|\d+(?:[.,]\d+)*\s*%?")


def _zahlen(text: str) -> set:
    return {"".join(z.split()) for z in _ZAHL.findall(text)}


def _knapp(zahlen: set, hoechstens: int = 3) -> str:
    geordnet = sorted(zahlen, key=lambda z: (len(z), z))
    aus = ", ".join(geordnet[:hoechstens])
    rest = len(geordnet) - hoechstens
    return aus + (f" (+{rest})" if rest > 0 else "")


def _zahlabweichung(neu: str, alt: str) -> str:
    """Welcher Zahlwert des alten Eintrags durch welchen neuen abgeloest wird.

    KEIN eigener Melder: das schmueckt nur einen Treffer aus, der wegen der
    Wortueberschneidung ohnehin schon angezeigt wird. Der Zahlvergleich fuer
    sich genommen hat auf dem Bestand gemessen keine Praezision - von 6 Paaren
    mit abweichenden Zahlen war keines ein Widerspruch, alle waren
    Fortschrittsstaende. Er sagt aber, WARUM man hinsehen soll, und das ist
    der Weg zum ersetzt=.

    Beidseitig verlangt: hat nur der neue Text Zahlen, ist das ein Zusatz und
    kein abgeloester Wert - und die Bedingung wuerde bei jedem Datum feuern.
    """
    zn, za = _zahlen(neu), _zahlen(alt)
    nur_neu, nur_alt = zn - za, za - zn
    if not nur_neu or not nur_alt:
        return ""
    return f", Zahlen {_knapp(nur_alt)} -> {_knapp(nur_neu)}"


# Wie das Urteil in der Zeile erscheint. Mit Fragezeichen, und das ist keine
# Hoeflichkeit: gemessen wurden 9 von 15 richtig bei n=15 (#1327), der
# Standardfehler liegt bei rund 13 Punkten. Das ist ein Hinweis, wo hinzusehen
# ist - kein Befund. Fehlt das Board, fehlt der Vermerk, sonst aendert sich nichts.
_VERMERKE = {
    "WIDERSPRUCH": ", Widerspruch?",
    "FORTSCHRITT": ", Fortschritt?",
    "UNABHAENGIG": ", unabhaengig?",
}


def _urteile(text: str, aehnlich: list) -> list:
    """Urteile zu den Dublettentreffern - oder lauter None, wenn es nicht geht.

    Faengt ausdruecklich JEDEN Fehler ab. Ein `remember`, das wegen einer
    Zweitmeinung scheitert, waere schlimmer als gar keine Zweitmeinung: der
    Eintrag ist zu diesem Zeitpunkt laengst geschrieben und committet, nur die
    Rueckmeldung an den Aufrufer steht noch aus.
    """
    if faktencheck is None or not aehnlich:
        return [None] * len(aehnlich)
    try:
        return faktencheck.urteile([(text, inhalt) for _, _, inhalt in aehnlich])
    except Exception:
        return [None] * len(aehnlich)


@server.tool()
def remember(text: str, tags: str = "", art: str = "", ersetzt: str = "") -> str:
    """Stores a text permanently in memory.

    Reports back which existing entries resemble the new one - so
    contradictions get noticed instead of silently sitting side by side.

    Args:
        text: The content to remember.
        tags: Optional keywords, separated by spaces or commas. Convention:
            the project, i.e. WHERE the knowledge belongs.
        art: WHICH KIND of knowledge - exactly one of: schnittstelle
            (interface: signature, file name, command, data format),
            fallstrick (pitfall: the obvious approach is wrong because ...),
            entscheidung (decision, made this way, with rationale), messwert
            (measurement: a number plus its measurement criterion),
            arbeitsweise (way of working), verlauf (chronicle - excluded
            from recall's default view).
        ersetzt: Ids of outdated entries that this one supersedes (e.g.
            "12,34"). They are not deleted, only removed from the default
            view.
    """
    text = text.strip()
    if not text:
        return "Fehler: 'text' ist leer - nichts gespeichert."
    tags = tags.strip()
    try:
        gewaehlt = _arten_lesen(art)
    except ValueError as exc:
        return f"Fehler: {exc} - nichts gespeichert."
    if gewaehlt in (None, "alle"):
        gewaehlt = []
    if len(gewaehlt) > 1:
        return (
            f"Fehler: genau eine Art, nicht {len(gewaehlt)} ({', '.join(gewaehlt)}) - "
            "nichts gespeichert. Gehoert der Text zu mehreren, sind es mehrere Eintraege."
        )
    meine_art = gewaehlt[0] if gewaehlt else UNSORTIERT

    conn = _connect()
    try:
        # Alles in EINER Transaktion, und alles Fehlbare gefangen: frueher lief
        # der mem-INSERT vor dem art-INSERT, und scheiterte der zweite, bekam
        # der Nutzer einen rohen Traceback - der Text war weg (#1426).
        try:
            markenhinweise = _markenpruefung(conn, tags)
            stems, teile = _ableitungen(conn, text, tags)
            # EIN Einfuegen, nicht zwei: bis Stand 4 lief der mem-INSERT vor
            # dem art-INSERT, und scheiterte der zweite, war der Text weg
            # (#1426). Seit die Art eine Spalte ist, gibt es den zweiten nicht.
            cur = conn.execute(
                "INSERT INTO eintrag (content, tags, ts, stems, teile, art, art_am)"
                " VALUES (?, ?, datetime('now'), ?, ?, ?, datetime('now'))",
                (text, tags, stems, teile, meine_art),
            )
            neu_id = cur.lastrowid
            ts = conn.execute(
                "SELECT ts FROM eintrag WHERE id = ?", (neu_id,)
            ).fetchone()[0]
            _marken_eintragen(conn, tags)
            # NACH _ableitungen: der Eintrag soll sich am Bestand von VORHER
            # zerlegen plus am eigenen Wortschatz, den `_vokabular` ohnehin
            # dazunimmt. Umgekehrt waere dasselbe Ergebnis, nur unklarer.
            _vokabel_eintragen(conn, f"{text} {tags}")
            abgeloest = _veralten(conn, ersetzt, durch=neu_id, grund="ersetzt")
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            return f"Fehler beim Speichern: {exc} - nichts gespeichert."

        # NACH dem Commit, und ausdruecklich jeder Fehler gefangen. Der
        # Dublettenhinweis ist reine Lesearbeit und nur eine Zugabe; lief er
        # in derselben Transaktion, nahm jeder Fehler in ihm den eben
        # geschriebenen Text mit - genau der Schaden aus #1426, nur durch eine
        # andere Tuer, und von `except sqlite3.Error` nicht gedeckt.
        try:
            aehnlich = _dubletten(conn, text, ausser=neu_id)
        except Exception:  # pragma: no cover - Notausgang, kein Normalfall
            aehnlich = []
    finally:
        conn.close()

    zeilen = [
        f"Gespeichert #{neu_id} [{ts}] als {meine_art}"
        + (f" (Tags: {tags})" if tags else "")
    ]
    if meine_art == UNSORTIERT:
        zeilen.append(
            "Ohne Art gespeichert. Bitte art= setzen, sonst ist der Eintrag nur "
            f"ueber die Volltextsuche zu finden: {', '.join(ARTEN)}."
        )
    for mahnung in _zuschnitt(text) + markenhinweise:
        zeilen.append(mahnung)
    if abgeloest:
        zeilen.append(f"Als veraltet markiert: {', '.join('#'+str(i) for i in abgeloest)}")
    if aehnlich:
        zeilen.append("Aehnliche Eintraege - pruefen, ob einer davon ersetzt gehoert:")
        gesagt = _urteile(text, aehnlich)
        for (rid, anteil, inhalt), wie in zip(aehnlich, gesagt):
            zeilen.append(
                f"  #{rid} ({anteil:.0%} Ueberschneidung"
                f"{_zahlabweichung(text, inhalt)}{_VERMERKE.get(wie, '')}) "
                f"{_titel(inhalt)}"
            )
        if any(gesagt):
            zeilen.append(
                "  (die Vermerke mit ? sind die Einschaetzung eines kleinen "
                "Sprachmodells, kein Befund - selbst nachsehen)"
            )
    return "\n".join(zeilen)


# Nur ein Datum am ANFANG ist die Chronik-Konvention der alten Memo-Dateien.
# Ein Datum irgendwo in den ersten 200 Zeichen zu suchen war zu grob: ein
# Eintrag mit fetter Titelzeile und "geprueft am 2026-09-11" in Zeile 2 ist
# keine Chronik. Gleiches Muster wie DATUMSKOPF in migration_art.py.
_DATUMSKOPF = re.compile(r"^\**\s*20\d\d-\d\d-\d\d")


def _zuschnitt(text: str) -> list:
    """Weist auf Eintraege hin, die mehrere Sorten in einem Absatz mischen.

    Zeigen, nicht entscheiden - wie beim Dublettenhinweis. Der Grenzwert 900
    liegt ueber dem Mittel des Bestands (599) und trifft damit die Ausreisser,
    nicht den Normalfall.
    """
    hinweise = []
    if len(text) > 900:
        hinweise.append(
            f"Eintrag ist {len(text)} Zeichen lang (Mittel im Bestand: ~600). "
            "recall gibt ganze Eintraege zurueck - lieber zwei daraus machen."
        )
    if _DATUMSKOPF.match(text.lstrip()) and len(text) > 400:
        hinweise.append(
            "Faengt mit einem Datum an: das ist meist Chronik plus Wissen in einem "
            "Absatz. Die Chronik als art=verlauf trennen haelt die Suche sauber."
        )
    return hinweise


def _veralten(conn, ids: str, durch=None, grund="") -> list:
    """Markiert Ids als veraltet. Nie loeschen - nur aus der Vorgabeansicht nehmen.

    Jeder Vorgang ist ein eigener Vermerk. Frueher ersetzte ein zweites
    Abloesen die Zeile des ersten und loeschte damit genau die Herkunft, die
    die Tabelle festhalten soll (#1428).
    """
    gewollt = [int(x) for x in re.findall(r"\d+", ids or "")]
    getan = []
    for i in gewollt:
        if not conn.execute("SELECT 1 FROM eintrag WHERE id = ?", (i,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO veraltet (id, durch, am, grund) VALUES (?, ?, datetime('now'), ?)",
            (i, durch, grund),
        )
        getan.append(i)
    return getan


def _veraltungen(conn) -> dict:
    """Je veraltetem Eintrag der JUENGSTE Vermerk: {id: (durch, grund)}."""
    return {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            "SELECT id, durch, grund FROM veraltet "
            "WHERE vermerk IN (SELECT max(vermerk) FROM veraltet GROUP BY id)"
        )
    }


def _markenzahl(conn, marke: str, deckel: int = MARKE_ETABLIERT) -> int:
    """Wie viele LEBENDE Eintraege GENAU diese Marke tragen, hoechstens `deckel`.

    Zwei Dinge sind hier anders als beim Suchen, und beide mit Grund:

    **Exakt, ohne Untermarken.** `recall(marke="mcp-memory")` nimmt
    `mcp-memory-server` bewusst mit - wer nach dem Projekt fragt, will den
    Zweig. Der Waechter darf das nicht: `mcp-memory` neben `mcp-memory-server`
    ist genau der Zerfall in Schreibvarianten, vor dem er warnen soll (#1418).
    Zaehlte er den Zweig mit, saehe die Variante auf der Stelle gesetzt aus.
    Der Index engt deshalb nur ein - ob die Marke wirklich so dasteht, prueft
    `_marken` danach zeichengenau.

    **Mit Deckel.** Gefragt ist nie die Zahl, sondern nur "schon gesetzt?" und
    "mehr als jene?". Beides ist bei `MARKE_ETABLIERT` entschieden, und der
    Waechter laeuft in jedem `remember` - eine grosse Marke soll ihn nicht
    ihre 315 Zeilen lang beschaeftigen.
    """
    klausel = _marken_klausel(marke)
    if not klausel:
        return 0
    zeilen = conn.execute(
        "SELECT e.tags FROM suche s JOIN eintrag e ON e.id = s.rowid"
        " WHERE suche MATCH ? AND NOT EXISTS (SELECT 1 FROM veraltet v WHERE v.id = e.id)",
        (klausel,),
    )
    zahl = 0
    for (tags,) in zeilen:
        if marke in _marken(tags):
            zahl += 1
            if zahl >= deckel:
                break
    return zahl


def _nachbarmarken(m: str, bekannt: list) -> list:
    """Bekannte Marken, die dieselbe Sache meinen koennten wie `m`."""
    nah = [b for b in bekannt if b != m and b.lower() == m.lower()]
    nah += [
        b for b in bekannt
        if b != m and b not in nah
        and (b.lower().startswith(f"{m.lower()}-") or m.lower().startswith(f"{b.lower()}-"))
    ]
    nah += [
        b for b in difflib.get_close_matches(m, bekannt, n=3, cutoff=0.8)
        if b != m and b not in nah
    ]
    return nah


def _markenpruefung(conn, tags: str) -> list:
    """Warnt vor einer Marke, die im Bestand noch kaum jemand traegt.

    Die Marke bleibt Freitext; erzwingen liesse sie sich nur um den Preis,
    kein neues Projekt mehr anlegen zu koennen. Aber sie zerfaellt unbemerkt in
    Schreibvarianten (#1418), und der Zerfall faellt erst beim Aufraeumen auf.
    Also zeigen, im Augenblick des Schreibens - entscheiden darf der Mensch.

    **Gefragt wird nach der Zahl der Eintraege, nicht nach dem Eintrag im
    Verzeichnis** (#1459). Frueher stieg die Pruefung bei jeder bekannten Marke
    aus - und weil `_marken_eintragen` unmittelbar danach auch die eben
    bemaengelte Marke eintrug, kam die Warnung genau einmal: der zweite
    Tippfehler derselben Sorte lief wortlos durch. Der Waechter pruefte gegen
    ein Verzeichnis, das er selbst mit dem verschmutzte, wovor er warnte.
    Jetzt schweigt er erst, wenn die Marke `MARKE_ETABLIERT` Eintraege traegt -
    ein Tippfehler kommt nie dorthin, ein echtes neues Projekt nach drei
    Eintraegen. Aus demselben Grund wird als Nachbar nur vorgeschlagen, was
    mehr Eintraege traegt als die fragliche Marke: sonst empfiehlt der Waechter
    den Tippfehler von gestern.

    Das Art-Wort steht VOR dieser Abwaegung: eine Art ist nie eine Marke, also
    gibt es auch nichts, woran sie sich bewaehren koennte.
    """
    bekannt = [r[0] for r in conn.execute("SELECT marke FROM marken")]
    hinweise = []
    for m in _marken(tags):
        if m.lower() in ARTEN:
            hinweise.append(
                f"Marke '{m}' ist ein Art-Wort. Die Marke sagt WO, die Art WELCHE "
                "SORTE - dafuer ist art= da."
            )
            continue
        eigene = _markenzahl(conn, m)
        if eigene >= MARKE_ETABLIERT:
            continue
        nah = [b for b in _nachbarmarken(m, bekannt) if _markenzahl(conn, b) > eigene]
        if nah and eigene:
            hinweise.append(
                f"Marke '{m}' traegt erst {eigene} "
                f"{'Eintrag' if eigene == 1 else 'Eintraege'} - dem Bestand bekannt "
                f"ist: {', '.join(nah[:3])}. Dieselbe Sache?"
            )
        elif nah:
            hinweise.append(
                f"Neue Marke '{m}' - dem Bestand schon bekannt ist: "
                f"{', '.join(nah[:3])}. Dieselbe Sache?"
            )
        elif not eigene:
            hinweise.append(f"Neue Marke '{m}' - bisher traegt sie kein Eintrag.")
    return hinweise


def _marken_eintragen(conn, tags: str) -> None:
    """Traegt die Marken eines Eintrags ins Verzeichnis - Art-Woerter nicht.

    Das Verzeichnis ist die Vorschlagsliste des Waechters. Ein Art-Wort darf
    dort nie hinein, sonst schlaegt er es spaeter selbst als Marke vor.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO marken (marke, seit) VALUES (?, datetime('now'))",
        [(m,) for m in _marken(tags) if m.lower() not in ARTEN],
    )


def _dubletten(conn, text: str, ausser: int, schwelle: float = 0.55) -> list:
    """Sucht vorhandene Eintraege, die den Gehalt des neuen schon abdecken."""
    terme = _terme(text)[:20]
    if not terme:
        return []
    # Ueber ALLE Arten suchen: ein neuer Fallstrick kann sehr wohl das
    # wiederholen, was schon in einem Chronikeintrag steht.
    zeilen, _ = _suche(
        conn,
        " OR ".join(f'{{content tags}} : "{t}"' for t in terme),
        12,
        _filter(art="alle"),
    )
    neu = _staemme(text)
    gew = _gewichte(conn, neu)
    treffer = []
    for rid, _, inhalt, _ in zeilen:
        if rid == ausser:
            continue
        anteil = _ueberschneidung(neu, _staemme(inhalt), gew)
        if anteil >= schwelle:
            treffer.append((rid, anteil, inhalt))
    return sorted(treffer, key=lambda x: -x[1])[:3]


@server.tool()
def verdichten(marke: str = "", art: str = "alle", schwelle: float = 0.5, gruppen: int = 5) -> str:
    """Finds groups of entries that say largely the same thing.

    Does not summarize anything itself - that's a judgment call. The tool
    delivers the groups; the caller writes a new entry and supersedes the old
    ones via remember(..., ersetzt="...").

    Args:
        marke: Only consider entries from this project (empty = all). Same
            reading as recall and themen: the tag is searched as a phrase in
            the tag field, so multi-tagged entries and sub-tags are included
            ("spiel3d-test" also matches "spiel3d-test Nachtfrost"). Used to
            be called `tags` and compared the whole tag column for equality -
            that silently missed exactly the specifically tagged entries
            where duplicates tend to sit (#1448).
        art: Only consider entries of this kind/these kinds. Default "alle"
            (all) - for consolidation the chronicle is the most worthwhile
            case; art="verlauf" tackles it on its own.
        schwelle: The similarity threshold above which two entries count as
            the same.
        gruppen: Maximum number of groups reported.
    """
    conn = _connect()
    try:
        try:
            wo_art, art_args = _filter(art=art)
        except ValueError as exc:
            return f"Fehler: {exc}"
        wo = f"WHERE 1=1{wo_art}"
        args = list(art_args)
        klausel = _marken_klausel(marke)
        if klausel:
            # Ueber den FTS-Index statt per Spaltenvergleich - sonst zaehlt nur,
            # wer GENAU diese eine Marke traegt, und "spiel3d-test Nachtfrost"
            # faellt heraus (#1448).
            wo += " AND e.id IN (SELECT rowid FROM suche WHERE suche MATCH ?)"
            args.append(klausel)
        zeilen = conn.execute(
            f"SELECT e.id, e.ts, e.content, e.tags, e.art FROM eintrag e {wo}", tuple(args)
        ).fetchall()
        if len(zeilen) < 2:
            return "Zu wenige Eintraege fuer einen Vergleich."

        staemme = {r[0]: _staemme(r[2]) for r in zeilen}
        alle = set().union(*staemme.values())
        gew = _gewichte(conn, alle)
        arten = {r[0]: r[4] for r in zeilen}
    finally:
        conn.close()

    # Rueckwaertsindex nur auf seltene Staemme: haeufige verbinden alles mit
    # allem und wuerden den paarweisen Vergleich quadratisch aufblasen.
    selten = max(2, len(zeilen) // 20)
    wo_kommt_vor = {}
    for rid, st in staemme.items():
        for s in st:
            wo_kommt_vor.setdefault(s, []).append(rid)
    kandidaten = set()
    for s, ids in wo_kommt_vor.items():
        if 1 < len(ids) <= selten:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    kandidaten.add((a, b) if a < b else (b, a))

    paare = []
    for a, b in kandidaten:
        sa, sb = staemme[a], staemme[b]
        gemeinsam = sum(gew.get(s, 0) for s in sa & sb)
        vereint = sum(gew.get(s, 0) for s in sa | sb)
        if vereint and gemeinsam / vereint >= schwelle:
            paare.append((gemeinsam / vereint, a, b))
    if not paare:
        return (
            f"{len(zeilen)} Eintraege geprueft ({len(kandidaten)} Paare verglichen) - "
            f"nichts ueber {schwelle:.0%} Uebereinstimmung."
        )

    # Zusammenhaengende Gruppen bilden
    eltern = {}
    def wurzel(x):
        while eltern.get(x, x) != x:
            x = eltern[x]
        return x
    for _, a, b in paare:
        ra, rb = wurzel(a), wurzel(b)
        if ra != rb:
            eltern[ra] = rb
    haufen = {}
    for _, a, b in paare:
        for x in (a, b):
            haufen.setdefault(wurzel(x), set()).add(x)

    text = {r[0]: (r[1], r[2], r[3]) for r in zeilen}
    aus = [f"{len(zeilen)} Eintraege, {len(kandidaten)} Paare verglichen, "
           f"{len(haufen)} Gruppe(n) ab {schwelle:.0%} Uebereinstimmung:"]
    for k, ids in sorted(haufen.items(), key=lambda x: -len(x[1]))[:gruppen]:
        beste = max(w for w, a, b in paare if a in ids or b in ids)
        aus.append(f"\nGruppe ({len(ids)} Eintraege, bis {beste:.0%} deckungsgleich):")
        for i in sorted(ids):
            ts, inhalt, marke = text[i]
            aus.append(f"  {_zeile(i, ts, inhalt, marke, arten[i], voll=False)}")
    aus.append("\nZum Verdichten: neuen Eintrag schreiben und die alten per "
               "remember(..., ersetzt=\"...\") abloesen.")
    return "\n".join(aus)


@server.tool()
def pruefe(ids: str) -> str:
    """Has a small language model judge how the named entries relate to each other.

    Counterpart to verdichten (consolidate): that one finds groups by word
    overlap, this one says whether a contradiction is behind it or just a
    newer state of affairs. All pairs from the named ids are judged.

    Does NOT judge authoritatively. Measured against 70 pairs: 67 % correct,
    9 % false contradiction alarms, but only 2 of 6 real ones caught - and
    the model says FORTSCHRITT (progress) in 50 of 70 cases. The result says where to look
    closer, not what the actual case is.

    Each pair is asked in BOTH directions, and only what comes back the same
    both times is reported; otherwise it says "uneinig" (disputed/unclear).
    Without this, the order of the supplied ids would influence the outcome
    (measured: 2 of 5 pairs were symmetric). This costs double, i.e. roughly
    10 seconds per pair, which is why the cap is 5 pairs asked per call.

    Opt-in: needs MEMORY_FC_URL and MEMORY_FC_MODELL pointing at any
    OpenAI-compatible endpoint (local model, LAN device, or cloud provider;
    MEMORY_FC_SCHLUESSEL for providers that want a key). Without both set,
    this tool does nothing and says so - there are no defaults, so nothing is
    contacted unless it was set up deliberately. Note that when it IS set up,
    up to 200 characters of each note are sent to that endpoint. If it is
    unreachable, the tool says so and returns nothing - all other tools are
    unaffected.

    Args:
        ids: Two or more entry ids, e.g. "249,255".
    """
    if faktencheck is None:
        return "Kein Faktencheck-Modul vorhanden (faktencheck.py fehlt oder ist fehlerhaft)."
    gewollt = []
    for i in (int(x) for x in re.findall(r"\d+", ids or "")):
        if i not in gewollt:
            gewollt.append(i)
    if len(gewollt) < 2:
        return "Fehler: mindestens zwei Ids noetig, z.B. pruefe(\"249,255\")."

    conn = _connect()
    try:
        platz = ",".join("?" * len(gewollt))
        text = dict(
            conn.execute(
                f"SELECT id, content FROM eintrag WHERE id IN ({platz})", tuple(gewollt)
            )
        )
    finally:
        conn.close()
    fehlt = [i for i in gewollt if i not in text]
    da = [i for i in gewollt if i in text]
    if len(da) < 2:
        return f"Zu wenige vorhandene Eintraege: {', '.join('#'+str(i) for i in fehlt)} gibt es nicht."

    alle = [(a, b) for n, a in enumerate(da) for b in da[n + 1:]]
    # Zeichengleiche Notizen gar nicht erst fragen - das Modell antwortet auch
    # auf zweimal denselben Satz, und zwar mitunter mit WIDERSPRUCH.
    gleich = {p for p in alle if faktencheck.deckungsgleich(text[p[0]], text[p[1]])}
    # Gedeckelt, weil jedes Paar zwei Anfragen kostet: 5 Paare sind schon rund
    # 50 s. Wer mehr will, ruft mehrfach mit kleineren Gruppen.
    zu_fragen = [p for p in alle if p not in gleich][:DECKEL_PRUEFE]

    # Hin und zurueck abwechselnd, nicht erst alle Hinrichtungen: laeuft das
    # Zeitbudget aus, fehlt dann ein ganzes Paar statt aller Rueckrichtungen.
    richtungen = []
    for a, b in zu_fragen:
        richtungen += [(text[a], text[b]), (text[b], text[a])]
    gesagt = [None] * len(richtungen)
    if richtungen:
        try:
            gesagt = faktencheck.urteile(richtungen, budget=len(richtungen) * 25)
        except Exception as exc:
            return f"Faktencheck nicht moeglich: {exc}"
        if not any(gesagt):
            return (
                f"Kein Urteil - Geraet nicht erreichbar oder zu langsam ({faktencheck.zustand()}). "
                "Am Memory selbst aendert das nichts."
            )
    beidseitig = {p: (gesagt[2 * i], gesagt[2 * i + 1]) for i, p in enumerate(zu_fragen)}

    aus = []
    for a, b in alle:
        if (a, b) in gleich:
            aus.append(
                f"#{a} <-> #{b}: als Notiz zeichengleich, nicht beurteilbar - "
                "entweder Dublette (dann verdichten), oder der Unterschied steckt "
                f"jenseits der ersten {faktencheck.MAXZ} Zeichen und das Modell sieht ihn nicht"
            )
        elif (a, b) not in beidseitig:
            aus.append(f"#{a} <-> #{b}: nicht gefragt (Deckel bei {DECKEL_PRUEFE} Paaren je Aufruf)")
        else:
            hin, her = beidseitig[(a, b)]
            if hin and her:
                aus.append(
                    f"#{a} <-> #{b}: {hin}"
                    if hin == her
                    else f"#{a} <-> #{b}: uneinig - {hin} in der einen, {her} in der anderen Richtung"
                )
            elif hin or her:
                aus.append(f"#{a} <-> #{b}: {hin or her}, aber nur eine Richtung geprueft - unbestaetigt")
            else:
                aus.append(f"#{a} <-> #{b}: kein Urteil")
    if fehlt:
        aus.append(f"Nicht vorhanden: {', '.join('#'+str(i) for i in fehlt)}")
    if any(gesagt):
        aus.append("Einschaetzung eines kleinen Sprachmodells, kein Befund - selbst nachsehen.")
    return "\n".join(aus)


@server.tool()
def vergessen(ids: str, grund: str = "") -> str:
    """Marks entries as outdated, without a replacement.

    They disappear from recall's default view but remain findable with
    mit_veraltet=True. Nothing is deleted.

    Args:
        ids: One or more entry ids, e.g. "12,34".
        grund: Why - appears later in the display of outdated entries.
    """
    conn = _connect()
    try:
        getan = _veralten(conn, ids, grund=grund.strip() or "veraltet")
        conn.commit()
    finally:
        conn.close()
    if not getan:
        return "Keine passenden Ids gefunden - nichts geaendert."
    return f"Als veraltet markiert: {', '.join('#'+str(i) for i in getan)}"


@server.tool()
def recall(
    query: str,
    limit: int = 8,
    art: str = "",
    marke: str = "",
    voll: bool = False,
    mit_veraltet: bool = False,
) -> str:
    """Searches memory via full-text search, best matches first.

    Also finds inflected forms ("Rangliste" -> "Ranglisten"/rankings) and
    word parts of compounds ("Katalysator" -> "Fusionskatalysator").

    By default returns a PREVIEW per hit (id, kind, date, title line). Get
    the full text of the interesting ones afterwards with zeige("376,481") -
    or set voll=True right away if the question is narrow enough.

    Args:
        query: Search term(s), FTS5 syntax allowed (e.g. "sqlite AND fts5", "proj*").
        limit: Maximum number of hits (default 8). Measured: below this,
            exact matches drop out due to morphology blending them in; above
            it, mostly just the returned payload grows.
        art: Restrict to kinds of knowledge, e.g. "fallstrick,entscheidung".
            Possible values: schnittstelle (interface), fallstrick (pitfall),
            entscheidung (decision), messwert (measurement), arbeitsweise
            (way of working), verlauf (chronicle), gemischt (mixed/not yet
            classified), alle (all). Default: everything except verlauf -
            otherwise the chronicle drowns out every search for a specific
            detail.
        marke: Restrict to a project, e.g. "raumschiff-project". Multiple
            tags separated by comma or space are OR-combined. Sub-tags are
            included: "leuchtturm" also matches "leuchtturm-project", but
            conversely "mcp-memory-server" does not match "mcp-memory".
            themen() lists which tags exist.
        voll: Full text instead of preview (default: no).
        mit_veraltet: Also show superseded entries (default: no).
    """
    query = query.strip()
    if not query:
        return "Fehler: 'query' ist leer."
    limit = max(1, min(int(limit), 50))
    try:
        filter_ = _filter(art=art, mit_veraltet=mit_veraltet)
    except ValueError as exc:
        return f"Fehler: {exc}"

    conn = _connect()
    try:
        rows, fehler, hinweis = _kaskade(conn, query, limit, filter_, marke)
        status = _veraltungen(conn) if mit_veraltet else {}
        ketten = _ketten_von(conn, [r[0] for r in rows])
        # Stilles Ausblenden waere schlimmer als das Rauschen: bei drei
        # mittelmaessigen Treffern merkt man sonst nie, dass der gute in der
        # Chronik liegt.
        zurueckgehalten = 0
        if _arten_lesen(art) is None and not fehler:
            zurueckgehalten = _stumm_zaehlen(conn, query, mit_veraltet, marke)
    finally:
        conn.close()

    if fehler:
        return (
            f"Ungueltige Suchanfrage: {fehler}\n"
            'Tipp: Sonderzeichen in doppelte Anfuehrungszeichen setzen, '
            'z.B. recall(query=\'"C++"\'). Operatoren: AND, OR, NOT, praefix*, "phrase".'
        )
    in_marke = f" in {marke}" if _marken(marke) else ""
    if not rows:
        leer = f"Keine Treffer fuer: {query}{in_marke}"
        if in_marke:
            leer += " - ohne marke= noch einmal probieren, die Marke koennte anders heissen (themen())."
        if zurueckgehalten:
            leer += (
                f' - aber {zurueckgehalten} in der ausgeblendeten Chronik.'
                ' art="verlauf" holt sie.'
            )
        return leer

    lines = []
    for rid, ts, content, tags, art in rows:
        vermerk = ""
        if rid in status:
            durch, grund = status[rid]
            vermerk = f" [VERALTET: {grund}" + (f", ersetzt durch #{durch}" if durch else "") + "]"
        vermerk += ketten.get(rid, "")
        lines.append(_zeile(rid, ts, content, tags, art, voll, vermerk))
    kopf = f"{len(lines)} Treffer fuer '{query}'{in_marke}{hinweis}"
    if zurueckgehalten:
        kopf += f", {zurueckgehalten} in der Chronik ausgeblendet (art=\"verlauf\")"
    if not voll:
        kopf += ' - Vorschau, Volltext per zeige("' + ",".join(str(r[0]) for r in rows[:2]) + '")'
    return kopf + ":\n" + "\n".join(lines)


def _stumm_zaehlen(conn, query: str, mit_veraltet: bool, marke: str = "") -> int:
    """Wie viele ausgeblendete Chronikeintraege die Anfrage getroffen haette.

    Bewusst nur die erste Stufe (alle Begriffe) und bewusst ein `count(*)`
    ohne `ORDER BY rank`: die Rangfolge braucht es nicht, es geht um die Frage
    "ist dort ueberhaupt etwas", nicht um die Reihenfolge. Untertreibt damit
    eher, als dass es falschen Alarm schlaegt.

    Billig ist er trotzdem erst seit dem EXISTS in `_filter`. Weil er auf
    art="verlauf" einschraenkt, nimmt er dort den POSITIVEN Zweig - und der
    trieb frueher die Abfrage ueber die Chronik-Rowids statt ueber die
    Volltextsuche. Gemessen 2026-09-15 auf 1315 Eintraegen: 7,0 ms, also
    81 % einer ganzen recall-Anfrage, gegen 0,09 ms danach.
    """
    if _ist_explizite_syntax(query):
        fts = query
    else:
        terme = _terme(query)
        if not terme:
            return 0
        fts = " AND ".join(f'{{content tags}} : "{t}"' for t in terme)
    wo, args = _filter(art=",".join(STUMM), mit_veraltet=mit_veraltet)
    fts = _mit_marke(fts, _marken_klausel(marke))
    try:
        return conn.execute(
            "SELECT count(*) FROM suche s JOIN eintrag e ON e.id = s.rowid"
            f" WHERE suche MATCH ?{wo}", (fts, *args)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _kaskade(conn, query: str, limit: int, filter_=("", ()), marke: str = ""):
    """Stufen von genau nach grosszuegig.

    1. die Wortfolge als Phrase - setzt sich vor Stufe 2, verdraengt sie nicht
    2. alle Begriffe (FTS5 verknuepft implizit mit AND)
    3. irgendein Begriff (ODER) - nur wenn Stufe 2 nichts fand
    4. Stamm und Kompositateil - fuellt nur die noch freien Plaetze auf

    Wer selbst FTS5-Syntax schreibt, bekommt genau die und keine Erweiterung.
    Die Stufen 1 bis 3 durchsuchen ausdruecklich nur content und tags: eine
    unqualifizierte Anfrage wuerde sonst die Morphologiespalten mitlesen und
    die Staffelung waere hinfaellig.
    """
    kl = _marken_klausel(marke)
    if _ist_explizite_syntax(query):
        rows, fehler = _suche(conn, _mit_marke(_auf_inhalt(query), kl), limit, filter_)
        return rows, fehler, ""

    terme = _terme(query)
    if not terme:
        return [], None, ""

    genau = " AND ".join(f'{{content tags}} : "{t}"' for t in terme)
    rows, fehler = _suche(conn, _mit_marke(genau, kl), limit, filter_)
    hinweis = ""
    if len(terme) > 1:
        # Die Wortfolge nach vorn. AND ueber getrennte Token laesst BM25 nur
        # Haeufigkeit werten, nicht Nachbarschaft: bei "Deck 5" stand der
        # Eintrag mit genau dieser Folge auf Rang 7 hinter Eintraegen, die
        # "Deck" oft und irgendwo eine 5 nennen (#1422). Als Phrase steht er
        # auf Rang 1. Nicht als eigene Stufe mit Abbruch - die Folge ist
        # enger, aber nicht immer die gesuchte Lesart, also Vortritt statt
        # Alleinherrschaft.
        folge, _ = _suche(
            conn,
            _mit_marke(f'{{content tags}} : "{" ".join(terme)}"', kl),
            limit,
            filter_,
        )
        if folge:
            rows = (folge + [r for r in rows if r not in folge])[:limit]
    if not rows and len(terme) > 1:
        oder = " OR ".join(f'{{content tags}} : "{t}"' for t in terme)
        rows, fehler = _suche(conn, _mit_marke(oder, kl), limit, filter_)
        if rows:
            hinweis = " (ODER - kein Eintrag enthaelt alle Begriffe)"

    # Stufe 4: exakte Treffer behalten den Vortritt, werden aber auf einen
    # Teil der Plaetze gedeckelt, damit die Morphologie ueberhaupt sichtbar
    # wird. Nichts geht verloren - Gedeckeltes rutscht nur nach hinten.
    # Wortteil vor Stamm: "Katalysator" in einem Kompositum zu finden ist
    # spezifischer als irgendeine gebeugte Form desselben Stammes.
    teil, _ = _suche(
        conn, _mit_marke(" OR ".join(f'teile:"{t.lower()}"' for t in terme), kl), limit, filter_
    )
    stamm, _ = _suche(
        conn, _mit_marke(" OR ".join(f'stems:"{stem(t)}"' for t in terme), kl), limit, filter_
    )
    morph = teil + [r for r in stamm if r not in teil]
    if not morph:
        return rows, fehler, hinweis

    # Der Deckel ist `limit`, die Morphologie fuellt also nur FREIE Plaetze.
    # Bis 2026-09-15 stand hier `limit * 0,6`, damit die Morphologie sichtbar
    # wird - und genau das warf exakte Treffer von Rang 6 bis 8 hinaus.
    # Gemessen an zwei Pruefstaenden aus Betriebsdaten: bei 47 echten
    # Umformulierungen stieg die Trefferquote 64 -> 77 %, bei den 117 Fragen,
    # die schon beim ersten Anlauf trugen, 82 -> 85 %. Der Preis waere, dass
    # die Morphologie seltener zu sehen ist; er faellt nicht an, weil sie nur
    # bei 2 % der Faelle der einzige Weg zum Eintrag ist.
    deckel = limit
    aus, gesehen = [], set()
    for gruppe in (rows[:deckel], morph, rows[deckel:]):
        for r in gruppe:
            if r[0] not in gesehen:
                gesehen.add(r[0])
                aus.append(r)
    neu = [r for r in aus[:limit] if r not in rows]
    if neu:
        hinweis += " (+ Stamm-/Wortteiltreffer)"
    return aus[:limit], None, hinweis


@server.tool()
def themen(marke: str = "", limit: int = 40) -> str:
    """Shows which projects exist - or the title index of one project.

    Counterpart to recall: that searches for words, this browses. Without an
    argument, the tag board (which project, how many entries, how they're
    distributed across kinds of knowledge); with an argument, that project's
    title lines grouped by kind.

    What this is for: recall only finds what you already know to ask for.
    Someone picking a project back up after months doesn't remember the
    terms anymore - and needs a list first, from which to pull up the entry.
    Follow up with `recall(query, marke="...")` or straight to `zeige("...")`.

    Outdated entries don't count, as everywhere in the default view. The
    chronicle does count here though: when browsing it's the scaffolding,
    not the filler that drowns out every search.

    Args:
        marke: Project, e.g. "raumschiff-project". Empty = tag board.
        limit: Number of rows for the board; number of entries per kind of
            knowledge for the title index (default 40).
    """
    limit = max(1, min(int(limit), 200))
    conn = _connect()
    try:
        zeilen = conn.execute(
            "SELECT e.id, e.ts, e.content, e.tags, e.art FROM eintrag e "
            "WHERE NOT EXISTS (SELECT 1 FROM veraltet v WHERE v.id = e.id)"
        ).fetchall()
        arten = {z[0]: z[4] for z in zeilen}
    finally:
        conn.close()
    if not zeilen:
        return "Das Gedaechtnis ist leer."

    sorten = list(ARTEN) + [UNSORTIERT]
    gesucht = _marken(marke)

    if not gesucht:
        tafel = {}
        for rid, _, _, tags, _art in zeilen:
            for m in _marken(tags):
                tafel.setdefault(m, dict.fromkeys(sorten, 0))[arten[rid]] += 1
        geordnet = sorted(tafel.items(), key=lambda x: (-sum(x[1].values()), x[0]))
        breite = max(len(m) for m, _ in geordnet[:limit])
        aus = [
            f"{len(tafel)} Marken ueber {len(zeilen)} lebende Eintraege. "
            f'Titelindex eines Projekts per themen("<marke>"), '
            f'darin suchen per recall(query, marke="<marke>").',
            "",
            f"{'Marke':<{breite}} {'ges.':>5}  " + " ".join(f"{k[:6]:>6}" for k in sorten),
        ]
        for m, c in geordnet[:limit]:
            aus.append(
                f"{m:<{breite}} {sum(c.values()):>5}  "
                + " ".join((f"{c[k]:>6}" if c[k] else f"{'.':>6}") for k in sorten)
            )
        rest = len(tafel) - min(limit, len(tafel))
        if rest:
            aus.append(f"... und {rest} weitere Marken mit weniger Eintraegen (limit= erhoeht).")
        return "\n".join(aus)

    treffer = [z for z in zeilen if set(_marken(z[3])) & set(gesucht)]
    if not treffer:
        # Der haeufigste Fall ist ein Tippfehler oder eine Namensvariante,
        # nicht ein leeres Projekt - also gleich die naheliegenden nennen.
        alle = sorted({m for _, _, _, t in zeilen for m in _marken(t)})
        # Teilstring UND Aehnlichkeit: das eine faengt die Untermarke
        # ("leuchtturm" -> "leuchtturm-project"), das andere den Vertipper
        # ("leuchttur"), und keines von beiden faengt den Fall des anderen.
        nah = {a for a in alle
               if any(g.lower() in a.lower() or a.lower() in g.lower() for g in gesucht)}
        for g in gesucht:
            nah.update(difflib.get_close_matches(g, alle, n=4, cutoff=0.7))
        nah = sorted(nah)
        hinweis = f" Gemeint vielleicht: {', '.join(nah[:8])}?" if nah else ""
        return f"Keine Eintraege unter der Marke {marke}.{hinweis} Alle Marken: themen()."

    aus = [f"{len(treffer)} Eintraege unter {', '.join(gesucht)} "
           f'- Volltext per zeige("<id>"), suchen per recall(query, marke="{gesucht[0]}").']
    for sorte in sorten:
        gruppe = sorted((z for z in treffer if arten[z[0]] == sorte),
                        key=lambda z: z[1], reverse=True)
        if not gruppe:
            continue
        mehr = f", davon die {limit} juengsten" if len(gruppe) > limit else ""
        aus.append(f"\n{sorte} ({len(gruppe)}{mehr}):")
        for rid, ts, content, tags, _art in gruppe[:limit]:
            weitere = [m for m in _marken(tags) if m not in gesucht]
            dazu = f"  +{','.join(weitere)}" if weitere else ""
            aus.append(f"  #{rid:<5} {ts[:10]}  {_titel(content, 76)}{dazu}")
    return "\n".join(aus)


@server.tool()
def zeige(ids: str) -> str:
    """Returns the named entries in full text.

    Counterpart to recall's preview: first see which entry is meant, then
    read only that one. Outdated entries are explicitly included here -
    whoever asks for the id means that one too, even if it's outdated.

    Args:
        ids: One or more entry ids, e.g. "376,481".
    """
    gewollt = [int(x) for x in re.findall(r"\d+", ids or "")]
    if not gewollt:
        return "Fehler: keine Id angegeben, z.B. zeige(\"376,481\")."

    conn = _connect()
    try:
        platz = ",".join("?" * len(gewollt))
        gefunden = {
            r[0]: r
            for r in conn.execute(
                f"SELECT e.id, e.ts, e.content, e.tags, e.art FROM eintrag e"
                f" WHERE e.id IN ({platz})",
                tuple(gewollt),
            )
        }
        arten = {i: z[4] for i, z in gefunden.items()}
        ketten = _ketten_von(conn, gefunden)
        status = _veraltungen(conn)
    finally:
        conn.close()

    aus = []
    for i in gewollt:
        if i not in gefunden:
            aus.append(f"#{i} - kein solcher Eintrag.")
            continue
        rid, ts, content, tags, _art = gefunden[i]
        vermerk = ""
        if rid in status:
            durch, grund = status[rid]
            vermerk = f" [VERALTET: {grund}" + (f", ersetzt durch #{durch}" if durch else "") + "]"
        vermerk += ketten.get(rid, "")
        aus.append(_zeile(rid, ts, content, tags, arten[rid], voll=True, vermerk=vermerk))
    return "\n\n".join(aus)


@server.tool()
def einordnen(ids: str, art: str) -> str:
    """Sets the kind of knowledge for existing entries.

    Meant for doing in passing: whatever recall surfaces anyway gets its
    kind assigned along the way. The backlog doesn't have to be sorted in
    one sitting.

    Args:
        ids: One or more entry ids, e.g. "376,481".
        art: Exactly one of: schnittstelle (interface), fallstrick (pitfall),
            entscheidung (decision), messwert (measurement), arbeitsweise
            (way of working), verlauf (chronicle). "gemischt" (mixed) undoes
            the classification.
    """
    try:
        gewaehlt = _arten_lesen(art)
    except ValueError as exc:
        return f"Fehler: {exc}"
    if gewaehlt in (None, "alle") or len(gewaehlt) != 1:
        return (
            "Fehler: genau eine Art angeben. Moeglich: "
            f"{', '.join(ARTEN)}, {UNSORTIERT} (nimmt die Einordnung zurueck)."
        )
    ziel = gewaehlt[0]
    gewollt = [int(x) for x in re.findall(r"\d+", ids or "")]
    if not gewollt:
        return "Fehler: keine Id angegeben."

    conn = _connect()
    try:
        getan, fehlt = [], []
        for i in gewollt:
            if not conn.execute("SELECT 1 FROM eintrag WHERE id = ?", (i,)).fetchone():
                fehlt.append(i)
                continue
            conn.execute(
                "UPDATE eintrag SET art = ?, art_am = datetime('now') WHERE id = ?",
                (ziel, i),
            )
            getan.append(i)
        offen = conn.execute(
            "SELECT count(*) FROM eintrag e WHERE e.art = ?"
            " AND NOT EXISTS (SELECT 1 FROM veraltet v WHERE v.id = e.id)",
            (UNSORTIERT,),
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    if not getan:
        return "Keine passenden Ids gefunden - nichts geaendert."
    aus = f"{ziel}: {', '.join('#'+str(i) for i in getan)}"
    if fehlt:
        aus += f" (nicht gefunden: {', '.join('#'+str(i) for i in fehlt)})"
    return aus + f"\nNoch {offen} Eintraege ohne Art."


if __name__ == "__main__":
    server.run(transport="stdio")
