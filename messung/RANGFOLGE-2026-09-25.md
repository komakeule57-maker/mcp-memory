# Rangfolge 2026-09-25: acht Hebel, acht Messungen, kein Gewinner

Fortsetzung von `ERGEBNIS-2026-09-25.md`, das mit dem Satz schloss,
man solle **aufhoeren, an der Rangfolge zu drehen**. Diese Datei ist der
Gegenversuch dazu: erst vier Hebel am Ranking selbst, dann — nach einer
Zweitmeinung von aussen — vier weitere, darunter einer, der den Pruefstand
angreift statt die Suche.

Alles hier ist gemessen. Gebaut wurde nichts, weil nichts die Schwelle nahm.

---

## Der Messaufbau

**Bestand.** Eine frische Kopie des lebenden Speichers (`frische_kopie.py`:
`VACUUM INTO`, danach die Rueckkopplungspaare der Messung entfernen). Nie
gegen `memory.db` selbst — ein Lauf, der fuer jede Frage das Gold per `zeige`
holt, traegt die Loesung ein und misst beim naechsten Mal die eigene
Vorarbeit. Das ist am 2026-09-21 passiert und hat 92 % statt 72 %
Trefferquote gemeldet.

**Fragen.** `aufrufe.json` — 2.465 mitgeschnittene MCP-Aufrufe aus dem
Echtbetrieb, samt der jeweils **gespeicherten Antwort**. Davon sind 591
`recall`, 285 mit Gold.

**Gold.** Die Ids, die im Betrieb unmittelbar nach einer `recall`-Frage per
`zeige` geholt wurden (`gold.py`). Keine erfundenen Fragen: die faellen
zugunsten des Systems aus, das sie erfindet.

**Vorgaben in jedem Arm.** `RUECKKOPPLUNG = False` (sonst misst der Betrieb
mit statt des Werkzeugs), `marke=` gesetzt (seit #2248 die Anweisung),
`limit=8`, sofern nicht anders angegeben.

**Ueberanpassung.** Wo ein Parameter gesucht wird, wird er auf den Fragen mit
**ungerader** Position bestimmt und auf den **geraden** bewertet. Nur die
zweite Zahl zaehlt. Zusaetzlich wird der **Spielraum der Parameterwahl**
(Spannweite der Lernhaelfte ueber alle probierten Werte) gegen den Abstand
gehalten: ist er groesser, ist der Abstand Rauschen.

**Erheblichkeitsschwelle.** Unter 10 % relativem Unterschied ist Gleichstand,
und Gleichstand ist ein vollwertiges Ergebnis. Das Kriterium steht in jedem
Skript im Kopf, **vor** dem Ergebnis.

---

## Teil 1: Wo ueberhaupt Kopfraum ist

275 Fragen, `marke=` gesetzt, Rueckkopplung aus, Kaskade bis 60 Treffer:

| bester Gold-Rang | Anteil | kumuliert |
|---|---|---|
| 1 | 36,4 % | 36,4 % |
| 2 | 19,3 % | 55,7 % |
| 3 | 10,2 % | 65,9 % |
| 4–8 | 12,7 % | 78,5 % |
| 9–60 | 12,4 % | 90,9 % |
| nie gefunden | 9,1 % | — |

**Bei 42 % der Fragen liegt das Gesuchte auf Rang 2–8.** Die Kandidaten sind
da, die Sortierung stimmt nicht — das ist der Kopfraum, auf den alles
Folgende zielt.

**Merkmalsdiagnose** (Lernhaelfte, 293 Gold gegen 3.184 andere Kandidaten in
den Top 30):

| Merkmal | Gold | Nicht-Gold |
|---|---|---|
| Rang (Median) | 6 | 15 |
| Laenge (Median) | 823 Z | 1.130 Z |
| Bruchstueck einer Kette | **13,0 %** | **4,8 %** |
| Datum (Median) | 2026-09 | 2026-09 |
| Art `gemischt` | 25,6 % | 12,4 % |
| Art `fallstrick` | 13,7 % | 27,5 % |

Zwei Ergebnisse gegen die Erwartung: **Bruchstuecke abzuwerten waere falsch**
(sie sind unter Gold fast dreimal so haeufig), und **Aktualitaet traegt
nichts**.

---

## Teil 2: Vier Hebel am Ranking

| Hebel | Skript | Ergebnis |
|---|---|---|
| BM25-Spaltengewichte `content`:`tags`, 0,1 bis 4,0 | — | Vorgabe 1:1 am besten (R@1 37,2 %). Tot. |
| Umsortieren eines 30er-Topfs nach Art und Laenge, 64 Kombinationen | — | bewertet **+6,1 %** — unter der Schwelle, und 3 Fragen von 138 gegen 64 probierte Kombinationen |
| Wortpaar-Naehe (Bigramm woertlich im Text) | — | trennt (15,3 % gegen 5,7 %), wirkt **+0,0 %** |
| `limit` erhoehen | `limit_erwartung.py` | 8 = 2.923 Z Erwartungswert; 10 **+5,0 %**, 12 **+13,0 %**, 16 **+27,4 %** |

Der lehrreichste Fehlschlag ist die Wortnaehe: das Merkmal **trennt** sauber
und aendert trotzdem nichts, weil die Phrasenstufe der Kaskade es laengst
ausschoepft. Ein Signal kann vorhanden und zugleich schon geerntet sein.

`limit = 8` ist damit **bestaetigt optimal**, gegen die Rettungskette von
6.592 Z gerechnet.

---

## Teil 3: Zweitmeinung von aussen, und was davon standhielt

Am 2026-09-25 offen befragt (Gemini, ueber `mcp-gemini-research`, ohne
Vorgabe eigener Hypothesen). Vier konkrete Vorschlaege, drei Messkritiken.
Gegengeprueft mit `stufen_diagnose.py`, 275 Fragen:

```
K1  Harte Kaskade: Gold in der UND-Stufe, nicht in der Phrasenstufe:  89
      davon durch die Vorrangfolge nach hinten geschoben:              6
      Median der Verschiebung:                             2 Plaetze
      dadurch aus den ersten 8 gefallen:                    0 = 0.0 %

K2  Kettenglieder auf mehreren der 8 Plaetze:              8/275 = 2.9 %
      Gold waere nachgerueckt:                             5/275 = 1.8 %

K3  Datum, NUR Eintraege mit echter Uhrzeit (783 tragen den Importstempel):
      Gold      n= 70   Median 2026-09
      Nichtgold n=622   Median 2026-09

K4  Anfragen mit einem Begriff in >10 % aller Eintraege:  120/275 = 43.6 %
```

- **K1 tot.** Der Vorschlag mit dem hoechsten Zutrauen — die harte
  Vorrangfolge der Phrasenstufe aufbrechen — kostet **null** Fragen. Ein
  Phrasentreffer ist selten und spezifisch; die Vorrangfolge ist hart, hat
  aber kaum Masse zum Verdraengen. Beide Seiten hatten aus der Codestruktur
  geschlossen statt gezaehlt. *(In Teil 9 sauber wiederholt: bestaetigt, und
  die Vermutung „kaum Masse" ist jetzt beziffert — 5,4 % Abdeckung.)*
- **K3 tot, und zwar sauber.** Der Einwand war methodisch richtig: 783
  Eintraege tragen den Importstempel `00:00:00` und koennten jeden
  Datumsbefund verwischen. Nur auf den 692 echten Uhrzeiten gerechnet:
  gleicher Median. Aktualitaet traegt auch exponentiell gedacht nichts.
- **K2 zu klein fuer einen Hebel** (1,8 %), aber es ist ein **Fehler**: drei
  Glieder derselben Notiz auf drei von acht Plaetzen sagen dreimal dasselbe.
  > **Nachtrag 2026-09-25 (Teil 8): die 2,9 % sind zu klein.** Dieses Skript
  > baut die Kaskade nach und kennt nur Phrasen- und UND-Stufe. Am echten
  > Einstiegspunkt gemessen sind es **8,5 % der Fragen**. K1, K3 und K4 standen
  > auf derselben Grundlage und sind in **Teil 9** am echten `_kaskade`
  > wiederholt — alle drei bestaetigt, K1 mit ausgetauschter Begruendung.
  > Die Zahlen in diesem Kasten sind damit historisch; es gelten die aus Teil 9.
- BM25 `k1`/`b` zu drehen geht in SQLite FTS5 technisch nicht; sie sind
  ueber `bm25()` nicht erreichbar.

---

## Teil 4: D — misst der Pruefstand sich selbst?

> „Ihr definiert Gold ueber das, was der Nutzer damals tatsaechlich
> nachgeholt hat. Ihr optimiert darauf, historisches Suchverhalten zu
> reproduzieren."

Der Einwand trennt zwei Behauptungen, die unterschiedlich daran haengen:

- **Rangfolge** („Gold gehoert nach vorn") — haengt nicht daran. Ob ein
  Eintrag die richtige Antwort ist, ist unabhaengig davon, ob er angezeigt
  wurde.
- **Obergrenze** („90,9 % sind unter 60 Treffern findbar") — haengt voll
  daran. Waere Gold nur, was gezeigt wurde, misst die Zahl sich selbst.

**D1** (`gold_pruefung.py`): Von 971 Gold-Ids standen **334 (34,4 %) nicht
in der Antwort, die der Aufrufer damals sah.** Gold ist also nachweislich
keine reine Funktion der Trefferliste.

**D1b** (`gold_herkunft.py`) schluesselt die 334 auf:

| Herkunft | Anteil |
|---|---|
| frueher in einer Trefferliste derselben Sitzung gesehen | 182 = 54,5 % |
| in dieser Sitzung selbst per `remember` angelegt | 29 = 8,7 % |
| Kettengeschwister eines sichtbaren Glieds | 20 = 6,0 % |
| **nirgends gesehen — echtes Versagen** | **103 = 30,8 %** |

**69,2 % kannte der Aufrufer bereits.** Die Rangfolge an solchen Ids zu
messen, misst nicht die Suche: er holte sie mit, weil er sie im Kopf hatte.

> Die Gruppe „selbst angelegt" fehlte im ersten Lauf. `remember` gibt die
> neue Id in der Bestaetigung zurueck („Gespeichert #1914 […]"), und 1.350
> der 2.465 Aufrufe sind `remember`. Ohne diese Gruppe landeten solche
> Faelle faelschlich unter „echtes Versagen".

**D2** (`gold_rein.py`) baut daraus den bereinigten Pruefstand. Eine Gold-Id
faellt heraus, wenn sie in der Antwort dieses Aufrufs nicht sichtbar war
**und** der Aufrufer sie schon kannte. Sie bleibt, wenn sie sichtbar war
(dann hat die Suche geliefert) oder wenn er sie nirgends gesehen hatte (im
Zweifel gegen die Suche gerechnet). Das entfernt 201 von 971 Ids (−20,7 %)
und 25 von 285 Fragen.

| | altes Gold | bereinigt | relativ |
|---|---|---|---|
| R@1 | 36,5 % | 39,6 % | +8,6 % |
| R@8 | 76,5 % | 81,2 % | +6,1 % |
| R@60 | 88,4 % | 91,2 % | +3,1 % |

**Alles unter 10 %. Die veroeffentlichten Zahlen bleiben gueltig.** Der
Einwand ist beziffert statt bestritten: die Verzerrung existiert, geht
durchweg **zu Lasten** der Suche, und ist zu klein, um einen Schluss zu
kippen.

`ergebnis_rein.json` ist ab hier der Pruefstand — nicht wegen des
Ergebnisses, sondern weil das sauberere Instrument nichts kostet.

**Nebenbefund:** wie der Betrieb wirklich ruft (285 recall-Aufrufe mit Gold):
`limit=` in 42,1 %, `marke=` in 41,4 %, `art=` in 21,8 %.

---

## Teil 5: A — `art=` als Aufruferregel

`marke=` als Regel brachte +41 % (#2248). Dieselbe Idee fuer die zweite
Achse. 260 Fragen, bereinigter Pruefstand.

| Arm | R@1 | R@8 | Leerlauf | gegen A0 |
|---|---|---|---|---|
| A0 nur `marke=` | 39,6 % | 81,2 % | 18,8 % | — |
| A1 `art=` der Gold-Art (**Orakel**) | 55,0 % | 86,5 % | 13,5 % | **+38,8 %** |
| A2 `art=` aller Gold-Arten (Obergrenze) | 56,2 % | 87,7 % | — | +41,7 % |
| A4 `art=` **vorhergesagt** | 28,1 % | 52,3 % | 47,7 % | **−29,1 %** |
| A5 vorhergesagt + `gemischt` | 35,0 % | 68,8 % | 31,2 % | **−11,7 %** |

Weicher Bonus statt Filter (30er-Topf, 31 Gewichte, gelernt/bewertet
getrennt): mit Orakel-Art **+42,9 %**, mit vorhergesagter Art **+4,1 %** —
und der Spielraum der Gewichtswahl (9,2 %) ist groesser als der Abstand
(1,5 %).

**Der Engpass ist allein die Vorhersage.** Die 260 Fragen wurden von einem
unabhaengigen Modell klassifiziert, das **nur** den Fragetext und die sechs
Artdefinitionen sah — nicht den Bestand, nicht das Gold:

| | Anteil |
|---|---|
| alle Gold-Arten getroffen | 33,8 % |
| teilweise getroffen | 30,0 % |
| Gold ist nur `gemischt`, also unratbar | 13,5 % |
| daneben | 22,7 % |

**Gegenprobe aus unabhaengiger Quelle:** bei den 62 realen Aufrufen mit
`art=` fiel das Gold in **63 %** durch den Filter, den der Aufrufer selbst
gesetzt hatte (`artfilter_probe.py`). Zwei Quellen, dieselbe Groessenordnung
— es liegt nicht am Klassifikator.

**Warum `marke=` wirkt und `art=` nicht:** Die Marke muss der Aufrufer nicht
raten, er **weiss** sie — eine Sitzung gehoert zu einem Projekt. Die Art ist
eine Eigenschaft der **Antwort**, nicht der Frage; sie zu kennen hiesse, die
Antwort schon zu haben. Das ist kein Messfehler, sondern der Unterschied
zwischen den beiden Achsen.

Skripte: `art_regel.py`, `art_vorhergesagt.py`, `art_bonus.py`,
Vorhersage in `art_vorhersage.json`.

---

## Teil 6: B — `marke=` als Bonus statt als Filter

Die Regel gewinnt 35 Fragen und **verliert 6** — quer liegende Marken, wo
das Wissen nicht am Projekt haengt. Ein Bonus wuerde sie nur nach hinten
schieben statt wegzuwerfen, und die Ausnahmeregel in der Anweisung
ueberfluessig machen. 130 lernen / 130 bewerten, 41 Gewichte
(`marke_weich.py`):

| Arm | R@1 | R@8 |
|---|---|---|
| B0 ohne Marke | 22,3 % | 65,4 % |
| B1 harter Filter (heute) | **37,7 %** | **78,5 %** |
| B2 weicher Bonus (Gewicht 1,7) | 35,4 % | 78,5 % |

**B2 gegen B1: R@1 −6,1 %, R@8 ±0,0 %; gepaart 2 gewonnen, 4 verloren.**
Spielraum der Gewichtswahl 8,5 % gegen einen Abstand von 2,3 %.

Der harte Filter bleibt. Der Grund ist sichtbar an B0: ohne Einschraenkung
faellt R@1 auf 22,3 %. Das Ausschliessen leistet echte Arbeit — es raeumt
die Konkurrenz der Schwesterprojekte weg, die ein Bonus nicht ueberbieten
kann.

---

## Teil 7: C — Begriffe, die in diesem Bestand ueberall stehen

43,6 % der Anfragen enthalten einen Begriff mit ueber 10 %
Dokumenthaeufigkeit. **Abgrenzung:** eine feste deutsche Stoppwortliste wurde
zweimal gemessen und bewegte nichts — die strich Funktionswoerter, die BM25
ueber die inverse Dokumenthaeufigkeit ohnehin fast auf null gewichtet. Hier
geht es um Inhaltswoerter, die nur **in diesem Bestand** allgegenwaertig
sind, und nicht um ihr Gewicht, sondern um ihre Wirkung als **Bedingung** in
der UND-Stufe.

Diagnose (`haeufige_begriffe.py`):

```
UND liefert nichts:                          200/260 = 76.9 %
davon gerettet, wenn haeufige Begriffe raus:   4/200 =  2.0 %
```

**Die UND-Stufe liefert bei drei von vier echten Anfragen gar nichts** — die
Arbeit machen ODER und die Morphologie. Das liegt aber nicht an haeufigen
Begriffen, sondern daran, dass echte Anfragen lange Stichwortlisten sind.

Hebel C1, haeufige Begriffe aus der UND-Stufe gestrichen, gegen die **echte**
Kaskade gemessen: **R@1 +0,0 %, R@8 −1,0 %.**

> Der erste Anlauf war falsch. Das Messskript baute die Kaskade nach und
> liess dabei ODER und Stufe 4 weg; der Vergleichswert lag dadurch bei
> R@8 18,5 % statt 81,2 %, und der Hebel meldete „+14,3 %". Korrigiert,
> indem `memory_server.py` an genau der einen Zeile geaendert und die Kopie
> als Modul geladen wird.

---

## Fazit

Acht Hebel, acht Messungen, **kein einziger ueber der Schwelle**. Das ist
kein Ideenmangel, sondern ein Befund mit einem gemeinsamen Grund: bei 42 %
der Fragen liegt das Gesuchte auf Rang 2–8, und **kein Merkmal trennt es
dort von seinen Nachbarn** — nicht Laenge, nicht Alter, nicht Art, nicht
Wortnaehe, nicht Dokumenthaeufigkeit. Sie sehen fuer BM25 gleich aus, weil
sie es sind: dieselben Woerter, dieselbe Marke, dasselbe Thema.

Das Bild ist ueber die Messungen hinweg konsistent. `frage()` scheiterte an
p = 34 %; der bedingte Kopf scheiterte daran, dass es kein Mass fuer
Sicherheit gibt; die Rangfolge scheitert daran, dass BM25 die Information
gar nicht hat. Dreimal dieselbe Wand, aus drei Richtungen angelaufen.

**Die klarste Einsicht kam aus dem Hebel, der scheiterte, ohne schwach zu
sein.** Die `art`-Achse traegt enorm viel Signal — mit bekannter Art steigt
R@1 um 38,8 %. Sie ist nur nicht ratbar, weil sie eine Eigenschaft der
Antwort ist und nicht der Frage. Das ist die schaerfste Formulierung der
Wand, die wir haben: **was die Kandidaten trennen wuerde, weiss man erst,
wenn man die Antwort hat.**

Was daraus folgt:

1. **An Gewichten, Schwellen und `limit` ist nichts mehr zu holen.**
   Weiteres Drehen daran ist Zeitverschwendung. Das gilt fuer dieses
   Verfahren — BM25 ueber Terme plus deutsche Morphologie —, nicht fuer die
   Aufgabe. Dass semantische Merkmale helfen wuerden, ist damit nicht
   widerlegt; es war eine bewusste Entwurfsentscheidung, sie nicht zu bauen.
2. **Der einzige Hebel, der zieht, ist die Rueckkopplung** (1,74 → 1,62
   Runden). Sie ist das einzige Signal, das nicht aus dem Text stammt,
   sondern aus der Benutzung. Ihre Schwaeche ist Abdeckung, nicht Wirkung:
   sie feuert bei 6 % der Fragen, weil sie nur auf wortgleiche
   Wiederholungen anspricht. Unscharfes Nachschlagen wurde am 2026-09-21
   gemessen und verworfen (#1918) — die naechste Fassung muesste die
   **Fragenhistorie** aehnlich machen, nicht die Dokumente.
3. ~~**Wer den Art-Hebel doch will, muss die 422 lebenden
   `gemischt`-Eintraege einordnen.**~~ **In Teil 10 gemessen und verworfen:**
   der Betriebsschaden der 422 ist *eine* Kette in *einer* von 28 echten
   `art=`-Anfragen (3,6 %), waehrend ein Sammeldurchgang bei 80 %
   Treffsicherheit rund 14 Eintraege nach `verlauf` und damit aus der
   Vorgabeansicht schiebt. Die Art-Achse hat keine Vorbedingung — sie hat ein
   Hindernis, und das ist die Vorhersagbarkeit, nicht die Vollstaendigkeit.
4. **Die 9,1 % nie gefundenen sind nicht angefasst.** Das sind
   Vokabelluecken, keine Sortierfehler; dagegen hilft die zweisprachige
   Nachfrage, die als Aufruferregel schon in der CLAUDE.md steht.
5. **K2 ist gebaut** — siehe Teil 8. Nicht, weil eine Zahl gestiegen waere
   (keine ist), sondern weil ein zerschnittenes Memo nun einen Platz belegt
   statt bis zu vier. Der Fehler war dabei fast dreimal so gross wie hier
   gemeldet: **8,5 % der Fragen**, nicht 2,9 %.

Und eine Notiz zur eigenen Trefferquote in dieser Sitzung: von den Hebeln,
die ich selbst vorgeschlagen habe, war der BM25-Abstand als Sicherheitsmass
der **schlechteste** der vier geprueften Signale (p = 18,8 % gegen 33,6 %
ohne jedes Signal), und meine Vermutung zur harten Kaskade war schlicht
falsch. Beide Male hatte ich aus der Codestruktur geschlossen statt zu
zaehlen. Das ist der Grund, warum in dieser Datei jede Zahl an einem Skript
haengt.

---

# Teil 8 — K2 gebaut: ein zerschnittenes Memo belegt einen Platz

Nachtrag vom 2026-09-25, nach der Rutsche. K2 stand oben als **Fehler, nicht
als Hebel**; gebaut wurde er auf ausdrueckliche Ansage hin. Die Messung hat
deshalb eine andere Aufgabe als die Teile 4 bis 7: sie soll den Bau nicht
rechtfertigen, sondern ausschliessen, dass er schadet.

## Was geaendert wurde

`memory_server.py`, drei Stellen:

1. **`_ketten_entdoppeln(conn, rows, limit)`** ist neu. Das bestbewertete
   Glied einer Kette bleibt stehen, jedes weitere faellt heraus. Die
   Reihenfolge von `rows` bleibt unangetastet.
2. **`_kaskade_roh` trennt `holen` von `limit`.** `limit` ist die Zahl der
   **Plaetze**, `holen` die der **Kandidaten**; beide waren dasselbe. Der
   Deckel der Morphologiestufe bleibt ausdruecklich `limit` — er entscheidet
   ueber das Mischungsverhaeltnis exakter und morphologischer Treffer und ist
   in dieser Hoehe gemessen worden (2026-09-15, 64 → 77 %).
3. **`_kaskade` holt `2 × limit` Kandidaten und entdoppelt am Ende**, nach
   der Rueckkopplung. Ohne den Vorrat waere die Liste nur **kuerzer** statt
   besser — genau das war der Zustand in `frage()`, das seit 2026-09-21 eine
   eigene Entdoppelung hatte, aber keine Nachbesetzung. Die ist jetzt raus,
   `frage` erbt die aus der Kaskade und kommt damit wieder mit `limit`
   Treffern zurueck.

Die Entdoppelung greift auch bei selbstgeschriebener FTS5-Syntax. Sie
erweitert keine Anfrage; sie sagt dasselbe nur nicht mehrfach.

**Verloren geht nichts.** Der Kettenvermerk an der verbliebenen Zeile nennt
die ganze Spanne — `[Stueck 2 von 4, zerschnittenes Memo #872-#875]` —, und
eine Kette ist ohnehin nur am Stueck zu lesen.

## Messaufbau

`messung/ketten_entdoppelung.py`, Kriterium im Kopf der Datei, **vor** der
Messung festgelegt.

- **Pruefstand:** `ergebnis_rein.json` (Teil 4), 260 Fragen mit bereinigtem
  Gold und bekannter Marke.
- **Bestand:** frische Kopie des lebenden Speichers per `VACUUM INTO`.
- **Aufruf:** `_kaskade(conn, frage, 8, _filter(), marke)` — der echte
  Einstiegspunkt, `marke=` gesetzt, `RUECKKOPPLUNG = False`.
- **Vergleichsarm:** **derselbe Quelltext**, an genau zwei Stellen entschaerft
  (`vorrat = limit`, `_ketten_entdoppeln` gibt `rows[:limit]` zurueck). Die
  Kaskade wird **nicht** im Messskript nachgebaut — dieser Versuch hat in
  Teil 7 schon einmal eine Grundlinie von R@8 18,5 % statt 81,2 % erzeugt.
- **Schwelle:** unter 10 % ist Gleichstand.

## Ergebnis

```
                                      vorher   nachher   relativ   Urteil
M1  Fragen mit doppeltem Platz          8.5%      0.0%   -100.0%   ERHEBLICH
M1  doppelt belegte Plaetze            18.5%      0.0%   -100.0%   ERHEBLICH
M2  R@1                                39.6%     39.6%     +0.0%   Gleichstand
M2  R@8                                81.2%     80.0%     -1.4%   Gleichstand
M2  Leerlauf (kein Gold in 8)          18.8%     20.0%     +6.1%   Gleichstand
M2  Gold ODER Kettengeschwister in 8   81.2%     81.2%     +0.0%   Gleichstand
M3  Zeichen je recall (Mittel)         1,508     1,511     +0.2%   Gleichstand
M4  ms je Kaskade (Median x5)           1.88      2.01     +6.8%   Gleichstand

    gepaart: Gold steigt bei 0 Fragen, faellt bei 3, unveraendert bei 257
```

Ein Beispiel aus dem Bestand, eine Anfrage aus sechs Stichwoertern in ihrem
Projekt:

```
vorher : 1769, 191, 1722, 189, 190, 193, 1539, 2066
nachher: 1769, 191, 1722, 1539, 2066, 1908, 1684, 1815
```

Vier der acht Plaetze gingen an dieselbe Kette #189-#194. Nachher steht sie
einmal da (#191, mit dem Vermerk auf die Spanne), und drei Eintraege, die
vorher gar nicht zu sehen waren, sind es jetzt.

## Drei Befunde, die vorher nicht dastanden

**Der Fehler war fast dreimal so gross wie gemeldet.** K2 stand oben mit
2,9 % der Fragen. Diese Zahl kam aus `stufen_diagnose.py`, und die hat die
Kaskade im Messskript nachgebaut — mit **nur** der Phrasen- und der
UND-Stufe, ohne ODER und ohne Morphologie. Da die UND-Stufe bei 76,9 % der
echten Anfragen leer ist (Teil 7), wurde ueber eine meist leere Liste
gezaehlt. Am echten Einstiegspunkt gemessen sind es **8,5 % der Fragen** und
**0,185 verschwendete Plaetze je Frage**. Es ist derselbe Fehler, der in Teil
7 schon einmal zugeschlagen hat, nur in die andere Richtung: dort machte er
einen Hebel zu gut, hier einen Fehler zu klein.

**Die drei „verlorenen" Fragen sind keine.** R@8 faellt von 81,2 auf 80,0 %,
weil bei drei Fragen das Gold ausgerechnet ein zweites Kettenglied war. Der
Pruefstand zaehlt exakte Ids; der Aufrufer liest den Vermerk. Deshalb steht
in der Tabelle eine zweite Zeile: **Gold oder ein Geschwister seiner Kette in
den acht** — die bleibt bei **81,2 % gegen 81,2 %, ±0,0 %**. Der Verlust ist
ein Artefakt des Masses, nicht der Suche. Das ist genau die Verzerrung, die
in Teil 4 beziffert wurde, nur diesmal in einem einzelnen Hebel sichtbar.

**Die Laufzeit musste zweimal gemessen werden.** Das Mittel ueber einen
einzelnen Durchlauf schwankte zwischen +5,2 % und +16,0 % — einmal ueber,
einmal unter der Schwelle. Es wird von wenigen sehr teuren Anfragen gezogen.
Fuenf **abwechselnde** Durchlaeufe je Arm, Median statt Mittel: 1,88 → 2,01 ms,
**+6,8 %**, und die Streuung je Lauf liegt unter 0,1 ms. Abwechselnd, damit
kein Arm den kalten Seitenpuffer allein bezahlt.

## Regressionsnetz

`test_memory.py`: `test_kette_bekommt_einen_platz_und_der_rest_wird_nachbesetzt`.
Drei Kettenglieder und drei lange Einzeleintraege mit demselben Suchwort —
lang, weil BM25 Laenge straft und die Glieder sonst gar nicht erst oben
stuenden. Geprueft wird **beides**: dass die Kette nur einen Platz belegt,
**und** dass drei Treffer zurueckkommen. Gegen den Stand vor dem Bau laufen
gelassen faellt der Test; die Kette belegte dort alle drei Plaetze. 50/50
gruen.

## Fazit zu Teil 8

Gebaut, gemessen, behalten — aber nicht, weil eine Zahl gestiegen waere.
**Keine ist gestiegen.** R@1 steht auf der Stelle, R@8 faellt um 1,4 % und
das nachweislich nur am Mass. Die Begruendung ist M1 und sonst nichts: was
dreimal dasselbe sagte, sagt es jetzt einmal, und die frei gewordenen Plaetze
gehen an Eintraege, die der Aufrufer vorher nicht zu sehen bekam. Bei 8,5 %
der Fragen ist das der Fall.

Das ist ein anderer Typ Aenderung als die Teile 4 bis 7, und es lohnt, den
Unterschied festzuhalten: **dort wurde gefragt „wird es besser?" und viermal
nein geantwortet. Hier wurde gefragt „wird es schlechter?" und nein
geantwortet — und das genuegt, weil der Fehler unabhaengig von der Messung
feststeht.** Ein Hebel braucht einen Gewinn, eine Fehlerbehebung nicht.
Sonst waere jeder Fehler, der unter 10 % kostet, unbehebbar.

Der Nebenbefund wiegt schwerer als der Bau: **zum dritten Mal in dieser
Sitzung hat eine im Messskript nachgebaute Kaskade eine falsche Zahl
geliefert.** In Teil 7 zu gut, hier zu klein, und beide Male sah die Zahl
plausibel aus. Die Regel aus #2256 ist damit keine Vorsichtsmassnahme mehr,
sondern ein belegter Befund: **den Server patchen und importieren, nie eine
Stufe nachbauen.** `messung/stufen_diagnose.py` steht weiter da wie gehabt —
seine K1-, K3- und K4-Zahlen haengen an derselben verkuerzten Kaskade und
sind bis zu einer Wiederholung am echten Einstiegspunkt **nicht belastbar**.

---

# Teil 9 — K1, K3 und K4 wiederholt, diesmal am echten Einstiegspunkt

Nachtrag vom 2026-09-25. Teil 8 hat gezeigt, dass `stufen_diagnose.py` die
Kaskade nachbaut und nur Phrasen- und UND-Stufe kennt. K2 war dadurch um den
Faktor drei zu klein. K1, K3 und K4 standen auf derselben Grundlage und waren
damit **nicht belastbar** — K1 besonders unangenehm, weil auf seiner Null einer
der Hebel aus Teil 2 für tot erklärt wurde.

## Messaufbau

`messung/harte_kaskade.py`. Der entscheidende Kunstgriff: **nicht zwei Kopien,
sondern eine mit einem Stellrad.** Die Messkopie unterscheidet sich vom Server
in genau einer Zeile —

```python
if folge:
    _SPUR.append(len(folge))
    folge = folge[:_PHRASENDECKEL]
    rows = (folge + [r for r in rows if r not in folge])[:holen]
```

— und bei `_PHRASENDECKEL = 10**9` ist es Zeile für Zeile das heutige
Verhalten. Damit ist ausgeschlossen, dass sich zwischen den Armen noch etwas
anderes unterscheidet. `_SPUR` misst die Abdeckung aus dem echten Codepfad
heraus, statt sie im Skript nachzurechnen.

Pruefstand `ergebnis_rein.json`, 260 Fragen, frische Kopie, `marke=` gesetzt,
Rückkopplung aus, `limit=8`. Deckel gewählt auf ungeraden Indizes, bewertet auf
geraden; bei Gleichstand gewinnt der heutige Stand.

## K1 — die harte Vorrangfolge ist bestätigt

```
    Deckel   R@1 lern   R@8 lern   R@1 pruef   R@8 pruef
         0      41.5%      83.8%       36.2%       76.2%
         1      41.5%      83.8%       37.7%       76.2%
       ...      41.5%      83.8%       37.7%       76.2%
     heute      41.5%      83.8%       37.7%       76.2%

    Spannweite R@8 ueber alle Deckel (Lernhaelfte): 0.0 %
    auf der Bewertungshaelfte gegen heute:          +0.0 %  Gleichstand
```

**Die entscheidende Zahl ist die, die der alte K1-Lauf gar nicht erhoben hat:
die Phrasenstufe feuert bei 5,4 % der Fragen** (14 von 260), im Median mit vier
Treffern, und nur bei zwei Fragen springen überhaupt mehr als acht Treffer vor.
Damit ist der Hebel nach oben gedeckelt, bevor man ihn dreht. Kein Deckelwert
bewegt R@8 um auch nur einen Fall.

Ein Nebenbefund, der gegen die Erwartung läuft: **Deckel 1 ist gepaart strikt
besser** — Gold steigt bei 5 Fragen, fällt bei 0. Der Mechanismus ist genau
der vermutete: steht Gold auf UND-Rang 2 und springen vier Phrasentreffer
davor, rutscht es auf Rang 6; mit Deckel 1 nur auf Rang 3. **Gebaut wird es
trotzdem nicht**, und zwar nach der vorher festgelegten Regel: die Verschiebung
findet ausschließlich *innerhalb* der acht Plätze statt. R@1 und R@8 rühren
sich nicht, die Vorschau zeigt ohnehin alle acht Zeilen, es werden keine
Zeichen und keine Runden gespart. Ein Rangwechsel von 5 auf 3, den niemand
bemerkt, ist kein Gewinn — er ist eine Zeile mehr Code.

Die Gegenrichtung ist das eigentlich Nützliche: **Deckel 0 kostet R@1 1,5
Punkte** (37,7 → 36,2 %). Die Phrasenstufe selbst verdient also weiter ihr Brot
— der Deck-5-Fix vom 2026-09-15 steht, jetzt auch über die ganze Kaskade
gemessen.

## K3 und K4 — bestätigt

```
K3  Datum, nur Eintraege mit echter Uhrzeit, ganze Kaskade bis 30
          Gold  n=  389  Median 2026-09
     Nichtgold  n= 4930  Median 2026-09

K4  Anfragen mit einem Begriff in mehr als 212 Eintraegen: 121/285 = 42.5 %
```

K3 steht jetzt auf 5.319 Beobachtungen statt 692 und sagt dasselbe: **das
Datum trennt nicht**, auch nicht, wenn man den Importstempel aussortiert. K4
ist eine reine Bestandszahl und war vom Aufbau nie betroffen (42,5 % gegen
43,6 % früher, der Unterschied ist der gewachsene Bestand).

## Fazit zu Teil 9

**Die Wiederholung hat das Urteil nicht gekippt, aber die Begründung
ausgetauscht — und das ist der Unterschied zwischen einer Zahl und einem
Befund.** Vorher hieß es „die harte Vorrangfolge verdrängt null Fragen",
gezählt über eine Liste, die bei drei Vierteln der Anfragen leer ist. Jetzt
heißt es: sie greift bei 5,4 % der Fragen, mit median vier Treffern, und
verschiebt Gold dabei nie über Platz 8 hinaus. Das erste war ein Zufallstreffer
ins Richtige, das zweite ist eine Messung.

Für das weitere Vorgehen heißt das dreierlei. **Erstens: der Schaden aus dem
nachgebauten Messaufbau ist begrenzt und jetzt abgeschlossen.** Von den sieben
Skripten, die eigene `suche MATCH`-Abfragen schreiben, zog nur
`stufen_diagnose.py` Qualitätsschlüsse daraus; `bedingter_kopf.py` benutzt
Stufenabfragen legitim zum Partitionieren echter `frage()`-Ergebnisse,
`kopfraum.py` bestimmt Ränge über `ms.recall()`, der Rest ist Infrastruktur.
Die Teile 4 bis 7 liefen sämtlich über `_kaskade_roh`. **Es steht nichts mehr
aus.**

**Zweitens: die Rangfolge ist jetzt ohne Vorbehalt zu Ende gemessen.** Acht
Hebel aus Teil 2 bis 7, dazu K1 bis K4 — keiner über der Schwelle, und beim
letzten offenen Zweifel ist die Obergrenze selbst beziffert: 5,4 % Abdeckung.
Weiteres Drehen an dieser Stelle ist nicht mehr eine Einschätzung, sondern ein
Rechenfehler.

**Drittens, und das ist die eigentliche Lehre dieser beiden Nachträge:** der
Unterschied zwischen „Diagnose" und „Messung" ist keiner. `stufen_diagnose.py`
war als schneller Blick gedacht und hat anschließend die ganze
Brainstorming-Runde grundiert. Eine Zahl, die zitiert wird, ist eine Messung —
und trägt dieselbe Pflicht, das Original zu benutzen statt es nachzubauen.

---

# Teil 10 — Die 422 `gemischt` einordnen? Gemessen: nein

Nachtrag vom 2026-09-25. In den Fazits von Teil 7 und Teil 9 steht, das
Einordnen der 422 lebenden `gemischt`-Einträge sei die **Vorbedingung** für
einen zweiten Anlauf an der Art-Achse. Das war eine Behauptung ohne Zahl. Hier
ist die Zahl, und sie widerlegt sie.

## Was zu prüfen war

Zwei Dinge, beide vor der Messung festgelegt:

1. **Trägt mein eigenes Urteil überhaupt?** 60 bereits eingeordnete Einträge,
   geschichtet über die sechs Arten (je 10), Art verdeckt, blind eingeordnet,
   gegen den Bestand verglichen. Schwelle: ab 80 % Übereinstimmung ordne ich
   die 422 ein, darunter nicht. Vorbehalt, vorher notiert: die bestehende Art
   ist selbst ein Urteil, keine Wahrheit.
2. **Was kostet `gemischt` im Betrieb?** `_filter(art=...)` schließt
   `gemischt` **strikt** aus. Jeder echte Aufruf mit `art=` verliert also alle
   422. Gemessen an den echten Aufrufen aus `aufrufe.json`.

## Die Eichprobe: 80,0 %, genau auf der Schwelle

```
 Art (bestehend)   n  getroffen        Verwechslungen (bestehend -> meins)
   schnittstelle  10      10/10        3x  entscheidung -> schnittstelle
      fallstrick  10       9/10        2x  arbeitsweise -> verlauf
    entscheidung  10       6/10        1x  messwert     -> fallstrick
        messwert  10       9/10        1x  verlauf      -> schnittstelle
    arbeitsweise  10       7/10        1x  arbeitsweise -> entscheidung
         verlauf  10       7/10        ... und vier weitere Einzelfälle
```

Die systematische Schwäche ist benennbar: **`entscheidung` → `schnittstelle`,
drei von zehn.** Kommt eine Entscheidung mit Dateinamen und Konstanten daher,
lese ich sie als Schnittstelle. Bei mehreren der zwölf Abweichungen ist
allerdings offen, wer recht hat — `#1586` („Architektur, bindend für
Erweiterungen", mit Pfaden und brechendem Test) trägt heute `entscheidung`,
und `#794` (Wurzelanalyse eines Parsing-Bugs) trägt `verlauf`. Die Probe misst
Übereinstimmung, nicht Richtigkeit.

## Der Nutzen: eine Frage in 28

```
echte Aufrufe mit art= und Gold:                            62
  davon mit EINSCHRAENKENDEM art= (ohne art="alle"):         28
  davon durch den gemischt-Ausschluss geschaedigt:  1 = 3,6 %
```

Der eine Fall ist `art="messwert"` auf eine Kette (#580–#586, ein Memo in
sieben Stücken). **Der gesamte Betriebsschaden von 422 unsortierten Einträgen
ist eine einzige Kette in einer einzigen Frage.** Der Grund, warum es so wenig
ist: von 62 Aufrufen mit `art=` benutzten **34 den Wert `alle`** — der hebt
den Ausschluss auf. Wer einschränkt, schränkt selten so ein, dass es weh tut.

## Der Preis: ~14 Einträge verschwinden lautlos

Die Verwechslungen sind nicht gleich teuer. `recall` blendet in der
Vorgabeansicht **nur `verlauf`** aus; `gemischt` ist sichtbar. Eine Verwechslung
zwischen `schnittstelle` und `entscheidung` ist damit kosmetisch — beide stehen
weiter in jeder Trefferliste. **Eine Verwechslung nach `verlauf` hinein ist es
nicht: der Eintrag fällt aus der Vorgabeansicht.**

In der Probe habe ich zweimal `verlauf` vergeben, wo `arbeitsweise` steht —
3,3 %. Auf 422 Einträge hochgerechnet: **rund 14 Einträge, die nach dem
Einordnen lautlos aus der Vorgabeansicht fallen.** Das ist die einzige Sorte
Schaden in dieser Rechnung, die man nicht sofort sieht.

## Fazit zu Teil 10

**Vierzehn gegen eins. Das Einordnen am Stück wird nicht gemacht.**

Die Behauptung „Vorbedingung für die Art-Achse" hält der Prüfung nicht stand,
und sie hätte es nie in ein Fazit schaffen dürfen — sie klang plausibel, weil
23,6 % unsortierter Bestand nach einem Missstand aussieht. Er ist einer, aber
ein anderer als gedacht: `gemischt` ist **kein Rückstand, der die Suche
behindert**, sondern eine fehlende Auskunft in der Vorschauzeile. Das ist ein
Lesbarkeits-, kein Trefferproblem, und es rechtfertigt keinen Sammeldurchgang
mit 80 % Treffsicherheit.

Damit ist auch die Reihenfolge geklärt, die in den Fazits von Teil 7 und 9
stand: **ein zweiter Anlauf an der Art-Achse hat keine Vorbedingung — er hat
ein Hindernis, und das ist ein anderes.** Die Achse scheiterte daran, dass die
Art eine Eigenschaft der Antwort ist (33,8 % Vorhersagegenauigkeit), nicht
daran, dass 422 Einträge sie nicht tragen. Diese 422 zu sortieren hätte die
Vorhersage um keinen Punkt verbessert.

Und eine Regel, die schon dastand, hat jetzt ihre Begründung: die `CLAUDE.md`
sagt zu `einordnen` „**wird beim Lesen nachgezogen, nicht am Stück**". Das war
bislang eine Stilfrage. Es ist keine: wer beim Lesen einordnet, hat den Eintrag
im Zusammenhang vor sich und braucht die 80-%-Quote gar nicht erst — wer 422 am
Stück einordnet, hat nichts als den Text und verschiebt vierzehn davon ins
Unsichtbare, um eine Frage zu retten.
