# Audit: die Fixkosten der neun Werkzeugdefinitionen

Stand 2026-09-25. Anlass: die Fixkosten von A sind von **7.313 Z** (acht
Werkzeuge, 2026-09-15) auf **12.215 Z** (neun) gewachsen, +67 % in zehn Tagen.
Sie fallen in **jeder** Sitzung an, vor der ersten Frage, auch fuer Werkzeuge,
die nie aufgerufen werden. Bei fuenf Fragen je Sitzung (realer Median) sind
das rund ein Drittel der A-Kosten.

Alle Zahlen hier sind gemessen, nicht geschaetzt: die Ersatztexte fuer Hebel 2
stehen ausformuliert in `fixkosten_audit.py` und werden dort gezaehlt.

## Woraus die 12.215 Zeichen bestehen

| | Zeichen | Anteil |
|---|---:|---:|
| Beschreibungen (Docstrings) | 9.256 | 76 % |
| JSON-Schemata der Parameter | 2.219 | 18 % |
| Namen und JSON-Geruest | 740 | 6 % |

## Was jedes Werkzeug kostet und was es bringt

Bezahlt wird je Sitzung; benutzt wird sehr ungleich. Ueber die 89 geernteten
Sitzungen:

| Werkzeug | Definition | in 89 Sitzungen | benutzt in | Aufrufe | Z je Aufruf |
|---|---:|---:|---:|---:|---:|
| **frage** | 2.570 | 228.730 | **0/89** | **0** | **∞** |
| pruefe | 1.691 | 150.499 | 3/89 | 11 | 13.682 |
| verdichten | 1.472 | 131.008 | 6/89 | 13 | 10.078 |
| einordnen | 754 | 67.106 | 3/89 | 15 | 4.474 |
| vergessen | 535 | 47.615 | 11/89 | 23 | 2.070 |
| themen | 1.245 | 110.805 | 42/89 | 107 | 1.036 |
| recall | 2.131 | 189.659 | 86/89 | 591 | 321 |
| zeige | 489 | 43.521 | 75/89 | 355 | 123 |
| remember | 1.328 | 118.192 | 84/89 | 1.350 | 88 |

## Die vier Hebel, gemessen

| Hebel | danach | spart | |
|---|---:|---:|---:|
| 1 Schema-`title`-Felder weg | 11.492 | 723 | 6 % |
| 2 Beschreibungen ohne Entwurfsbegruendung | 9.889 | 2.326 | 19 % |
| 1+2 zusammen | **9.166** | **3.049** | **25 %** |
| 3 dazu `frage()` streichen | **8.057** | **4.158** | **34 %** |

### Hebel 1 — die `title`-Felder der Schemata (723 Z, risikolos)

Pydantic erzeugt zu jedem Parameter ein `"title"`, das den Parameternamen in
Grossschreibung wiederholt: `{"query": {"title": "Query", "type": "string"}}`.
Dazu je Werkzeug ein `"title": "recallArguments"`. Das ist ein Drittel aller
Schema-Zeichen und traegt null Information — der Feldname steht daneben.

**Erprobt, nicht vermutet:** `ms.server._tool_manager.list_tools()` liefert die
`Tool`-Objekte, `t.parameters` ist genau das Dict, das `list_tools()` als
`input_schema` ausliefert. Nach dem Entfernen der `title`-Schluessel meldet der
Server 11.492 Z, und `recall` wie `zeige` laufen unveraendert durch. Gehoert
als vier Zeilen hinter die Registrierung der Werkzeuge.

### Hebel 2 — Entwurfsbegruendung raus (2.326 Z)

Die Docstrings leisten zwei Dienste zugleich: sie erklaeren dem **Aufrufer**,
wann und wie das Werkzeug zu rufen ist, und sie erklaeren dem **Quelltextleser**,
warum es so gebaut ist. Nur das Erste wird in jede Sitzung geladen.

Schnittregel: drin bleibt, was die Entscheidung des Aufrufers aendert (wann
rufe ich das, wie baue ich den Aufruf, welche Falle gibt es). Raus faellt
Messhistorie, verworfene Alternativen, Ticketnummern und Verweise auf Stellen
im Quelltext. Beispiele aus `frage` (2.570 → 1.109):

> *"A German stop word list used to sit in front of the cascade here. It was
> measured twice, moved nothing either time, and has been removed — see the
> note above `_kette_texte` before putting it back."*

Das ist eine Notiz an den naechsten, der den Quelltext oeffnet. Ein Aufrufer
kann daraus nichts ableiten; er zahlt sie in jeder Sitzung.

> *"Returning everything in full was measured and rejected: it costs 98 % more
> characters than `recall` plus a targeted `zeige` …"*

Der Aufrufer braucht den Satz davor ("nur der beste Treffer kommt im
Volltext"), nicht die Begruendung.

**Der Ort dafuer ist nicht der Papierkorb, sondern der Quelltext.**
`@server.tool(description=...)` nimmt einen eigenen Text entgegen; der
Docstring bleibt vollstaendig stehen und wird nur nicht mehr ausgeliefert.
Besser noch eine Konvention — Absaetze, die mit `Hintergrund:` anfangen,
werden beim Registrieren abgeschnitten —, dann bleibt es **eine** Quelle und
kann nicht auseinanderlaufen.

**Dreifache Nennung des Art-Vokabulars.** `recall`, `remember` und
`einordnen` zaehlen die sechs Arten samt englischer Glosse je einzeln auf,
zusammen rund 1.050 Z. Die Glossen gehoeren dorthin, wo ein Wert **erzeugt**
wird (`remember`); `recall` filtert nur und `einordnen` kann auf `remember`
verweisen. Das ist kein Informationsverlust: alle neun Beschreibungen stehen
gleichzeitig im Kontext.

### Hebel 3 — `frage()` streichen (1.109 Z nach Hebel 2, 2.570 Z heute)

**`frage()` ist in 86 Sitzungen seit seiner Einfuehrung kein einziges Mal
aufgerufen worden** — nachgezaehlt an den `tool_use`-Bloecken selbst, nicht am
Vorkommen des Namens im Text. Es ist zugleich die teuerste Definition von
allen.

Der gemessene Nutzen (#1882) war **96/117 gegen 94/117 fuer `recall`**, also
+1,7 Prozentpunkte — nach der Regel des Projekts ("unter 10 % ist
Gleichstand") kein Ergebnis. Und der Eintrag sagt selbst, woher die zwei
Treffer kamen: **aus der Kettenaufloesung**, nicht aus der Form der Antwort.

Damit ist der Schnitt sauber: **die Kettenaufloesung nach `zeige` verlegen**
(wer eine Id aus einer zerschnittenen Kette holt, bekommt die ganze Kette) und
`frage()` streichen. Der gesamte gemessene Vorteil bleibt erhalten, die
Definition faellt weg. Das ist kein Sparen auf Kosten der Qualitaet, sondern
das Verschieben einer Eigenschaft von einem ungenutzten Werkzeug in ein
taeglich genutztes.

### Hebel 4 — die Grenze pruefbar machen (spart nichts, verhindert das Naechste)

Keiner der 46 Tests sieht die Werkzeugdefinitionen an. Die 7.313 → 12.215 sind
niemandem aufgefallen, weil nichts sie beobachtet. Ein Test, der die Summe aus
`list_tools()` gegen eine Obergrenze haelt, macht jedes weitere Wachstum zu
einer bewussten Entscheidung statt zu einem Nebeneffekt.

## Was nicht angefasst gehoert

`recall`, `remember` und `zeige` tragen die Fallen, die einen Aufruf
misslingen lassen — dass `mcp-memory-server` **nicht** `mcp-memory` trifft,
dass die Chronik per Vorgabe ausgeblendet ist, dass `zeige` auch Veraltetes
zeigt. Gemessen an der Nutzung sind sie ohnehin die billigsten: `remember`
kostet 88 Z je Aufruf, `zeige` 123, `recall` 321. Wer hier kuerzt, spart am
falschen Ende.

Ebenso bleibt bei `pruefe` der Hinweis, dass bis zu 200 Zeichen jeder Notiz an
einen fremden Endpunkt gehen. Das ist kein Entwurfsgeschwaetz, sondern das
Einzige, was einen Aufrufer vom Aufruf abhalten koennte.

## Fazit

Ein Drittel der Fixkosten ist ohne Qualitaetsverlust zu haben, und die
Haelfte davon ohne jede Ermessensfrage: 723 Z sind maschinell erzeugte
`title`-Felder, die den Parameternamen wiederholen, und 2.570 Z gehoeren einem
Werkzeug, das in 86 Sitzungen nie gerufen wurde und dessen gemessener Vorteil
von +2 auf 117 Fragen aus einer Eigenschaft stammt, die man nach `zeige`
verlegen kann. Zusammen mit dem Beschneiden der Entwurfsbegruendungen stehen
**8.057 statt 12.215 Zeichen**, also unter dem Stand von vor dem Wachstum.

Die Ursache ist aber nicht die Groesse, sondern dass sie unbeobachtet war. Die
Docstrings sind der einzige Text des Projekts, der zwei unvereinbare Leser
zugleich bedient — den Quelltextleser, der die Begruendung will, und das
Modell, das sie in jeder Sitzung bezahlt. Solange beide dieselben Zeichen
teilen, waechst der zweite Posten immer dann, wenn jemand den ersten gut
bedient. **Das zu trennen ist der eigentliche Hebel; die 4.158 Zeichen sind
nur die Nachzahlung.**

Wo diese Rechnung nicht hinreicht: ob eine kuerzere Beschreibung das Modell
schlechter waehlen laesst, ist hier **nicht** gemessen und mit den
Betriebsdaten auch nicht zu messen — es gibt keinen Fall, in dem eine gekuerzte
Fassung im Einsatz war. Hebel 1 und 3 sind davon unberuehrt (kein Text geht
verloren beziehungsweise nur ein nie benutztes Werkzeug); Hebel 2 ist eine
Ermessensentscheidung und sollte als solche dastehen. Wer sie absichern will,
braucht einen Pruefstand fuer die Werkzeugwahl, und den gibt es noch nicht.

---

## Nachtrag 2026-09-25: Hebel 3 war falsch — `frage()` gehoert nicht gestrichen

Hebel 1 und 4 sind umgesetzt (`_schema_entrumpeln()` im Server, drei Tests im
Netz, 11.492 statt 12.215 Z). Vor Hebel 3 stand die Frage, warum `frage()` nie
gerufen wurde — und die Antwort faengt eine Stufe frueher an: **haette es
gerufen werden sollen?** Gemessen (`frage_probe.py`, 275 Fragen, frische Kopie):

| | Zeichen je Frage | Runden |
|---|---:|---:|
| `frage()`, ehrlich gerechnet | **4.007** | **1,59** |
| `recall` → `zeige` | 4.467 | 2,00 |
| | −10 % (Summe −14 %) | **−21 %** |

"Ehrlich gerechnet" heisst: `frage()` antwortet nur dann in einer Runde, wenn
das Gold auf **Rang 1** steht — das ist in **41 %** der Faelle so. In den
uebrigen 59 % folgt trotzdem ein `zeige`, und der Volltextkopf ist an den
falschen Eintrag gezahlt. Genau so ist gerechnet.

Das Ergebnis kippt den Hebel. −10 % Zeichen im Median sind an der
Gleichstandsschwelle und allein kein Befund; **−21 % Runden sind einer**, und
zwar auf dem Mass, das MESSKRITERIUM.md selbst als das eigentliche benennt
("Runden bis zur Antwort. Die eigentliche Zeit. Jede Runde ist eine
Modell-Inferenz ueber den ganzen Kontext"). Beide Verzerrungen gehen dabei
**gegen** `frage`: die Vergleichsseite holt per `zeige` genau die Gold-Ids,
was ein realer Aufrufer nicht kann, und der 59-%-Fall wird mit dem vollen
`zeige` belastet statt mit den fehlenden Ids.

**`frage()` ist also nicht zu teuer, sondern unbenutzt — und das sind zwei
verschiedene Krankheiten.**

### Warum es nie gerufen wurde

Was belegbar ist: **`frage` steht in keiner der beiden Dateien, die jede
Sitzung laedt.** `CLAUDE.md` (zuletzt am 2026-09-23 geaendert, also zwei Tage
*nach* der Einfuehrung) nennt `remember`, `vergessen`, `recall`, `zeige`,
`themen`, `einordnen`, `verdichten` und `pruefe` beim Namen — `frage` kein
einziges Mal; die vier Fundstellen sind das deutsche Wort. `MEMORY.md` (Stand
2026-09-16) ebenso. Dokumentiert ist es nur in `docs/TOOLS.md`, und die wird
nicht geladen.

Und `CLAUDE.md` bleibt nicht bei einer Aufzaehlung, sie gibt eine Anweisung:

> **Suchen:** `mcp__memory__recall(query)` — vor jeder Dateisuche nach
> früheren Projekten, Entscheidungen oder Fallstricken. […] den Volltext der
> interessanten dann per `mcp__memory__zeige("376,481")`.

Die Werkzeugliste ist eine Speisekarte, `CLAUDE.md` ist eine Hausordnung. Die
Hausordnung gewinnt. Dazu passt die Verteilung ueber alle neun: **jedes in
`CLAUDE.md` genannte Werkzeug hat mindestens 11 Aufrufe, das eine nicht
genannte hat null.**

Was **nicht** belegt ist, und das gehoert dazu: dass die fehlende Nennung die
*Ursache* ist. Zwei andere Erklaerungen sind mit denselben Daten vereinbar und
lassen sich rueckwirkend nicht trennen:

- **Die Beschreibung fuehrt mit einer Verneinung.** Erster Satz: "Answers a
  question from the dataset […] it does NOT write the answer itself." Wer
  zwischen Werkzeugen waehlt, liest zuerst, was es *nicht* kann; der
  Unterschied, der zaehlt (eine Runde statt zwei, Ketten aufgeloest), steht im
  dritten Absatz von sechs.
- **Gewohnheit.** `recall` ist seit Wochen der Weg, und das Gedaechtnis selbst
  beschreibt den Arbeitsablauf mit `recall` — die Eintraege verstaerken, was
  `CLAUDE.md` vorgibt.

### Was daraus folgt

1. **`frage()` bleibt.** Der Deckel von 11.800 Z traegt es.
2. **In `CLAUDE.md` und `MEMORY.md` aufnehmen**, mit der Regel, die aus der
   Messung folgt: erst `frage()`, und `zeige()` nur, wenn der Volltextkopf
   nicht traegt (in 59 % der Faelle).
3. **Die Beschreibung mit dem Nutzen anfangen lassen**, nicht mit der
   Verneinung — das ist ohnehin Hebel 2.
4. **Danach nachzaehlen.** Aufrufe je Sitzung in zwei bis drei Wochen: bleibt
   es bei null, war die Werbung nicht die Ursache und die Beschreibung ist es.
   Das ist der Versuch, der die drei Erklaerungen trennt; vorher ist jede
   davon eine Vermutung.
