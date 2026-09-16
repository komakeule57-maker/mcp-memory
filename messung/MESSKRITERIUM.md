# Messkriterium: mcp-memory gegen das .md-Gedaechtnis des Harness

Festgelegt am 2026-09-15, **vor** der Messung. Wer das Kriterium nach dem
Ergebnis schreibt, misst nur noch die eigene Erwartung.

## Die Frage

Lohnt der mcp-memory-Server gegenueber dem, was das Harness von sich aus
vorschreibt — eine Datei je Fakt in `~/.claude/projects/<projekt>/memory/`,
gefunden per `grep`, gelesen per `Read`? Gemessen in **Tokens** und in
**Zeit**, mit dem Recht, danach den Stecker zu ziehen.

## Was gegeneinander antritt

| | Suche | Lesen | Index |
|---|---|---|---|
| **A: mcp-memory** | `recall(query)` → Vorschau | `zeige(ids)` → Volltext | `themen()` auf Abruf |
| **B1: Harness-Vorgabe** | `grep -Eril` ueber eine Datei je Fakt | `Read` der Treffer | `MEMORY.md`, immer geladen |
| **B2: das reale Archiv** | dasselbe ueber die 37 eingefrorenen Memo-Dateien | `Read` | dito |

B1 ist der faire Gegner: die Harness-Vorgabe lautet woertlich "Each memory is
one file holding one fact". Dafuer werden alle 1171 lebenden Eintraege als
je eine `.md` mit Frontmatter exportiert — **derselbe Inhalt**, andere Form.
B2 kommt dazu, weil es den Zustand zeigt, der vor dem Server tatsaechlich da
war: wenige grosse Dateien statt vieler kleiner.

## Die Abfragemenge ist nicht ausgedacht

**265 echte `recall`-Fragen** aus 30 Sitzungen, geerntet aus den
Transkripten (`ernte.py`). Davon tragen **117 ein Gold**: die Ids, die im
Betrieb unmittelbar danach per `zeige` geholt wurden — also die Eintraege,
die die Frage wirklich beantwortet haben. Erfundene Fragen fielen zugunsten
des Systems aus, das sie erfindet.

Die Fragen gehen unveraendert an beide Seiten. B bekommt eine faire
Suchstrategie: Inhaltswoerter der Frage mit `|` verodert, `grep -Eril`,
danach die ersten Treffer lesen — das, was ein Agent ohne Werkzeug tut.

## Gemessen wird je Frage

1. **Zeichen in den Kontext.** Exakt zaehlbar und nachpruefbar. Alles
   Weitere ist Umrechnung.
2. **Tokens.** Kein Tokenizer und kein API-Schluessel auf dieser Maschine,
   also geeicht: `cache_creation_input_tokens` der Transkripte gegen die in
   derselben Runde zugefuegten Zeichen, lineare Regression, R² wird
   mitberichtet. Eine Naeherung, die als solche ausgewiesen ist — keine
   erfundene Zahl und keine geliehene Faustregel.
3. **Runden bis zur Antwort.** Die eigentliche Zeit. Jede Runde ist eine
   Modell-Inferenz ueber den ganzen Kontext (Sekunden); ob die Suche darin
   0,7 ms oder 40 ms braucht, verschwindet im Rauschen. Wer Millisekunden
   vergleicht, misst am Nutzer vorbei.
4. **Trefferquote.** Steht das Gold in dem, was das System liefert — und auf
   welchem Rang? Ein billiges System, das nichts findet, ist nicht billig:
   der Preis steht dann nur woanders (falsche Antwort, oder eine
   Dateisuche hinterher).
5. **Fixkosten je Sitzung.** A zahlt die Werkzeugdefinitionen, B den immer
   geladenen Index. Das faellt an, bevor eine einzige Frage gestellt ist.

## Was hier nicht gemessen wird

- **Der Schreibpfad** (542 `remember`-Aufrufe liegen in den Transkripten)
  wird **getrennt** ausgewiesen, nicht in die Suchbilanz gemischt. Sonst
  verrechnet sich ein Vorteil beim Lesen mit einem Nachteil beim Schreiben
  zu einer Zahl, die nichts mehr aussagt.
- **Die Qualitaet der Antwort.** Nicht ohne Urteil messbar, also nicht
  behauptet.
- **Millisekunden der Suchmaschine.** Stehen schon in #1456 und sind fuer
  diese Frage die falsche Groesse (siehe Punkt 3).

## Die Entscheidungsregel, vorher festgelegt

- **B gewinnt**, wenn es bei **gleicher oder besserer** Trefferquote weniger
  Tokens je Frage braucht und nicht mehr Runden. Dann ist der Server
  ueberfluessig und gehoert abgeschaltet.
- **A gewinnt** im umgekehrten Fall.
- **Bei gemischtem Bild entscheidet die Trefferquote**, nicht der Preis: ein
  Eintrag, der nicht gefunden wird, haette gar nicht erst geschrieben werden
  muessen.
- **Ein Unterschied unter 10 % gilt als keiner.** Die Token-Eichung ist eine
  Regression, keine Zaehlung; sie traegt keine feineren Aussagen.
