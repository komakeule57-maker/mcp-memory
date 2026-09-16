# Das Schema: der Reinigersinn hat recht, aber nicht aus dem naheliegenden Grund

Gemessen am 2026-09-15, Prototyp in `schema_probe.py`, Vorfuehrung in
`vorfuehrung.py`.

## Der Wurzelfehler

`mem` **ist** die virtuelle FTS5-Tabelle und zugleich die Quelle der
Wahrheit. Ein Suchindex wird als Speicher benutzt. Alles, was am Aufbau
klobig wirkt, folgt daraus — und zwar zwangslaeufig:

- **Kein `ALTER`** ("virtual tables may not be altered"). Jede neue
  Eigenschaft muss eine Nebentabelle werden: `art`, `kette`, `marken`,
  `vokabel`. Vier Tabellen, die nur existieren, weil man keine Spalte
  hinzufuegen kann.
- **Kein Fremdschluessel, kein echter Primaerschluessel.** Die Rowid ist der
  einzige Bezug, und FTS5 erzwingt sie nicht — daher die Falle beim Neubau
  und ein eigener Regressionstest dafuer.
- **Jede Spalte wird indiziert.** Deshalb musste `ts` als `UNINDEXED`
  hineingezwungen werden, und deshalb brauchte es `_auf_inhalt()`, das jede
  Anfrage an `content`+`tags` bindet.
- **Abgeleitete Spalten liegen im Speicher statt im Index.** `stems` und
  `teile` sind reines Indexmaterial und werden trotzdem als Daten
  aufbewahrt — und muessen von Hand nachgezogen werden.
- **Filter koennen nicht joinen.** Ein Filter auf `art` lief als
  `rowid IN (…)` neben dem MATCH und trieb die Abfrage; der EXISTS-Kunstgriff
  ist die Narbe davon.

Das steht als [[1453]] schon im Gedaechtnis. Neu ist, was es kostet.

## Was es kostet, in Zahlen

**Indexmaterial, das als Daten gespeichert wird:**

| in `mem_content` (2.260 KB) | |
|---|---:|
| `content` — der Nutztext | 963 KB |
| `tags` | 29 KB |
| `stems` — nie zurueckgegeben, reines Indexmaterial | **675 KB** |
| `teile` — dito | **25 KB** |

**41 % von `mem_content` sind Index, der als Nutzlast herumliegt.** Die
ganze Datei traegt 991 KB Nutztext bei 3,70 MB Groesse — Faktor 3,7.

**Quelltext, der nur wegen des Umwegs existiert:**

| | Zeilen |
|---|---:|
| `_schema_sicherstellen` + `_migrieren` + `_stand_setzen` + `_art_sicherstellen` (kein ALTER) | 140 |
| `_ketten_nachtragen`, `_marken_nachtragen`, `_vokabel_nachtragen` (Nebentabellen nachziehen) | 71 |
| `_arten_von`, `_veraltungen`, `_ketten_von` (Extraabfragen statt JOIN) | 48 |
| `_mem_neu_bauen` (Rowid von Hand), `_ableitungen`, `_auf_inhalt` | 45 |
| **im Server** | **304 von 1750 = 17 %** |
| dazu `nachziehen.py` und drei Migrationsskripte | 460 |

**9 der 25 Regressionstests** sichern Fallen ab, die es in einem sauberen
Schema nicht gaebe.

## Der Prototyp

Zwei saubere Fassungen, beide mit denselben 1331 Zeilen gefuellt, beide
ergebnisgleich (132 Treffer auf 200 echten Fragen, wie das jetzige Schema):

```sql
CREATE TABLE eintrag (
  id INTEGER PRIMARY KEY, inhalt TEXT NOT NULL, marke TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL, art TEXT NOT NULL DEFAULT 'gemischt' CHECK (art IN (…)),
  kopf INTEGER REFERENCES eintrag(id), nr INTEGER, abgeloest_am TEXT);
CREATE VIRTUAL TABLE suche USING fts5(inhalt, marke, stems, teile,
                                      content='eintrag', content_rowid='id');
```

`art`, `kette` und der Veraltungsvermerk werden **Spalten**. `veraltet`
bleibt als anfuegendes Protokoll zu Recht eine eigene Tabelle.

| | Groesse | MATCH |
|---|---:|---:|
| jetzt (vacuumiert) | 3,70 MB | 0,12 ms + 0,02 ms Nebenabfragen |
| **V1 external content** | **3,41 MB (−8 %)** | **0,06 ms**, ein JOIN |
| V2 Index als eigene Tabelle | 4,56 MB (+23 %) | 0,06 ms |

**Der Gewinn ist weder Platz noch Zeit.** −8 % auf der Platte ist nichts,
und 0,06 gegen 0,12 ms verschwindet neben einer Modellrunde von Sekunden —
nach dem eigenen Messkriterium dieser Reihe ist das kein Argument. V2 ist
sogar groesser, weil der Text dort doppelt liegt.

## Der Gewinn ist, dass Fallen unmoeglich werden

Am Prototyp vorgefuehrt, nicht behauptet:

```
[ok]  ALTER TABLE ... ADD COLUMN geht        -> keine Nebentabelle je Eigenschaft
[ok]  Kette ins Leere abgewiesen             (FOREIGN KEY constraint failed)
[ok]  unbekannte Art abgewiesen              CHECK sitzt an der Spalte
[ok]  MATCH '2026' trifft 487 statt alle     ts liegt nicht mehr im Index
[ok]  art-Filter als gewoehnliches WHERE     0,05 ms (alt 52 ms, 1,7 ms nach dem Kunstgriff)
```

## Was **nicht** geloest wird — damit die Bilanz ehrlich bleibt

| Falle | sauberes Schema |
|---|---|
| Rowid/Fremdschluessel (#1423) | **weg** |
| `ts` als Suchwort (#1425) | **weg** |
| Filter treibt die Abfrage (#1454) | **weg** |
| Nebentabelle je Eigenschaft | **weg** |
| CHECK eingefroren (#1426) | **halb** — der CHECK greift sofort, ihn zu *aendern* braucht in SQLite weiter einen Tabellenumbau. Ganz weg erst mit einer Vokabeltabelle `art_vokabular` + Fremdschluessel; dann ist eine neue Art ein `INSERT`. |
| `stems`/`teile` driften (#1424) | **halb** — der Trigger haelt den Index am Speicher, aber die abgeleiteten Spalten fuellt weiter Python. Ein SQL-`UPDATE` auf `inhalt` laesst sie weiter veralten. `nachziehen.py` schrumpft, verschwindet nicht. |

## Der Umbau, in Groessenordnungen

27 Stellen greifen auf `mem` zu, 31 auf `rowid` als Schluessel, 9 auf die
Nebentabelle `art`. Das ist ein Schemastand 4 → 5 mit einer Migration in
einem Rutsch und einer Durchsicht aller Abfragepfade — **kein v2 und kein
Neubau.** Die 25 Regressionstests sind dabei das Netz; 9 davon duerfen danach
ersatzlos wegfallen.

## Folgerung

Der Reinigersinn trifft etwas Echtes, und es ist nicht "zu klobig", sondern
genau benennbar: **ein Index wird als Speicher benutzt, und die Klobigkeit
ist der Preis dafuer.** Nur zahlt sich der Umbau nicht in Millisekunden oder
Megabyte aus, sondern in 300 Zeilen Umgehungscode, vier ueberfluessigen
Tabellen und neun Regressionstests, die dann keinen Gegenstand mehr haben.

Gegen die andere offene Baustelle abgewogen — 38 % Umformulierungsquote bei
der Suche (#1468) — ist das **die kleinere Wirkung fuer den groesseren
Aufwand**. Der Schemaumbau macht den Code sauber; die Suche zu verbessern
macht das System besser.
