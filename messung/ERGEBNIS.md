# Ergebnis: mcp-memory gegen das .md-Gedaechtnis

Gemessen am 2026-09-15 nach dem vorab festgelegten [Messkriterium](MESSKRITERIUM.md).
117 echte Fragen aus 30 Sitzungen, 1171 lebende Eintraege, derselbe Inhalt in
beiden Formen.

## Das Ergebnis in einem Satz

**Der Server gewinnt deutlich gegen beide .md-Formen — und seine Suche ist
trotzdem mittelmaessig.** Das eine widerlegt das Bauchgefuehl nicht, das
andere bestaetigt es: gemessen wurde ein Kostenvorteil, kein Gueteurteil.

## Je Frage

| | Zeichen | Runden | Gold in den gelesenen Dateien |
|---|---:|---:|---:|
| **A** mcp-memory (`recall` → `zeige`) | **4.152** | 2 | 100 % (per Konstruktion) |
| **B1** eine Datei je Fakt, `grep` + `Read` | 17.428 | 3 | 66 % |
| **B2** das reale 37-Dateien-Archiv | 286.049 | 3 | — |

B1 ist die woertliche Harness-Vorgabe, aus dem Bestand exportiert. B2 ist der
Zustand, der vor dem Server tatsaechlich dalag: wenige grosse Dateien, von
denen jede einzelne schon 40 KB in den Kontext traegt.

**B war dabei so stark gebaut, wie es ohne Suchmaschine geht:** zwei
Suchmuster (alle Begriffe / irgendeiner), das bessere zaehlt; die Treffer
nach Begriffsabdeckung geordnet statt alphabetisch; und das Einengen bei zu
vielen Treffern kostet eine Runde, statt dass B gratis raet. Der erste
Durchlauf las die fuenf Dateien mit der niedrigsten Id — das war unfair
gegenueber B und ist verworfen.

## Warum B verliert: grep kennt keine Rangfolge

`grep` wirft auf eine typische Frage **64 Dateien** aus (Median; Mittel 101,
schlimmster Fall alle 1171). Bei **84 %** der Fragen sind das mehr, als sich
lesen lassen. Das Gold ist bei 91 % der Fragen irgendwo in dieser Liste —
im Median auf Rang 2, im schlechtesten Fall auf Rang 186. Aber die Liste
**ist nicht sortiert**; wer fuenf Dateien liest, hat es in 66 % der Faelle
erwischt.

Das ist der eigentliche Unterschied, und er ist keiner der Datenhaltung: eine
Vorschau mit acht nach Rang sortierten Titelzeilen ist etwas anderes als 64
Dateinamen in alphabetischer Ordnung. Nicht die Datenbank gewinnt, sondern
**BM25 und die Vorschau**.

## Fixkosten je Sitzung — hier steht B am besten da

| | Zeichen | ~Token |
|---|---:|---:|
| A: acht Werkzeugdefinitionen | 7.313 | ~2.400 |
| B: Vollindex (`MEMORY.md` mit 1171 Zeilen) | 208.641 | ~69.500 |
| B: gepflegter Index, wie er heute real ist | 5.544 | ~1.800 |

Mit dem **Vollindex** braucht B gar kein `grep`: der Agent liest im Index die
richtige Datei ab und holt sie in einer Runde (856 Zeichen). Je Frage ist das
billiger als A. Nur zahlt er 208.641 Zeichen, bevor die erste Frage gestellt
ist.

**Die Gewinnschwelle liegt bei 61 Fragen je Sitzung. Der reale Median ist 5.**

Gesamtkosten einer Sitzung (Fixkosten + Fragen), in Zeichen:

| Fragen/Sitzung | A | B Vollindex | B grep |
|---:|---:|---:|---:|
| 1 | 11.465 | 209.497 | 22.972 |
| **5** (realer Median) | **28.073** | 212.921 (7,6x) | 92.684 (3,3x) |
| 9 (Mittel) | 44.681 | 216.345 (4,8x) | 162.396 (3,6x) |
| 61 | 260.585 | 260.857 | 1.068.652 |

## Schreiben: unentschieden

542 echte `remember`-Aufrufe. A: Text (932 Zeichen im Median) + Antwort
(180) in **einer** Runde. B: derselbe Text per `Write`, dazu eine Zeile in
`MEMORY.md` — ~1.150 Zeichen in **zwei** Runden. Im Token-Verbrauch nehmen
sich beide nichts; A spart eine Runde und den Pflegeschritt am Index.

## Was die Messung ueber A *nicht* sagt — und die eine Zahl, die es tut

Das Gold stammt aus A (die Ids, die im Betrieb nach einem `recall` geholt
wurden). A's 100 % sind deshalb eine Konstruktion, kein Befund: Faelle, in
denen A nichts fand und B etwas gefunden haette, kommen in dieser Messung
gar nicht vor.

Ein Mass, das **nicht** aus A abgeleitet ist, gibt es aber — was im Betrieb
auf einen `recall` folgte:

| | | |
|---|---:|---:|
| `zeige` (die Frage trug) | 114 | 43 % |
| **ein neuer `recall`** (umformuliert) | **100** | **38 %** |
| etwas anderes / nichts | 51 | 19 % |

- **38 % Umformulierungsquote**, im Mittel **1,61 Anlaeufe** je beantworteter
  Frage, hoechstens 5.
- Nur **58 %** der Fragen tragen beim ersten Anlauf.
- **8,3 %** der Aufrufe liefern **0 Treffer** — z. B. "Leitplanken Zielgruppe
  Konzept Grenzen", "Entscheidung Server Architektur Hosting Datenbank".

Ehrlich gerechnet kostet eine *beantwortete* Frage in A daher nicht 4.152,
sondern rund **5.060 Zeichen bei 2,6 Runden**. Der Abstand zu B bleibt, aber
**42 % der Fragen gehen beim ersten Mal daneben**, und jeder Fehlversuch
kostet eine volle Inferenz. Genau das ist das Bauchgefuehl, und es ist
belegt.

## Zur Token-Angabe

Auf dieser Maschine gibt es weder Tokenizer noch API-Schluessel. **Zwei
Eichversuche an den Transkripten sind gescheitert** und werden hier genannt,
damit sie niemand wiederholt:

1. `cache_creation_input_tokens` je Runde gegen die zugefuegten Zeichen —
   R² = 0,007. Der Cache wird in Bloecken geschrieben, nicht mit dem Zuwachs.
2. Kontextgroesse (`input + cache_read + cache_creation`) gegen die
   aufaddierten Zeichen einer Sitzung — ergibt 1,22 Zeichen je Token und
   einen negativen Systemteil, also Unsinn: Sidechains und Nicht-Text-Anteile
   zaehlen in den Tokens mit, in den Zeichen nicht.

Deshalb ist **Zeichen** das Mass dieser Messung — exakt und nachpruefbar —
und die Token-Spalte eine Umrechnung mit **3 Zeichen je Token**, ausgewiesen
als Annahme. Fuer das Verhaeltnis A:B ist sie ohne Belang: beide Seiten
tragen dieselbe Art deutschen Fachtexts, der Faktor kuerzt sich heraus.

## Folgerung nach der vorab festgelegten Regel

Die Regel lautete: *B gewinnt, wenn es bei gleicher oder besserer
Trefferquote weniger Tokens je Frage braucht und nicht mehr Runden.*

B braucht bei der realen Sitzungsgroesse das **3,3- bis 7,6-fache**, eine
Runde mehr, und findet in 66 % statt in 91+ % der Faelle. **B verliert auf
allen drei Achsen** — die 10-%-Gleichstandsschwelle ist um ein Vielfaches
verfehlt. Ein Schnitt zugunsten von .md-Dateien waere nach dieser Messung
falsch.

Zugleich ist die Schwachstelle benannt und sie sitzt **nicht** in der
Datenhaltung, sondern in der Suche: 38 % Umformulierungen, 8,3 % Leerlaeufe.
Was ein v2 zu verbessern haette, ist die Rangfolge und das Treffen der
Frage — nicht das Format.
