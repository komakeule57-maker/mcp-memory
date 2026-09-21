# Messkriterium: Rueckkopplung aus gescheiterten Fragen

Festgelegt am 2026-09-21, **vor** der Messung. Der Prueffstand wurde gebaut,
bevor eine Zeile am Server geaendert wurde — genau darum geht es: erst das
Mass, dann der Eingriff.

## Die Frage

Der Befund aus #1912: fast jede Rettung bringt **neues Vokabular** (68 %
Tausch, 30 % voellig fremd, 0 % blosses Kuerzen), und **45 %** der
gescheiterten Erstfragen sind woertliche Wiederholungen einer frueher
gescheiterten Frage mit gleichem Gold. Daraus der Vorschlag:

> Wo im Betrieb auf einen `recall` ein weiterer folgte und die Kette mit
> einem `zeige` endete, ist die erste Frage gescheitert und der rettende
> Eintrag bekannt. Merkt man sich dieses Paar und macht den **Wortlaut der
> gescheiterten Frage** am rettenden Eintrag suchbar, findet dieselbe Frage
> beim naechsten Mal sofort.

Zu klaeren ist nicht, ob das bei den Wiederholungen wirkt — das ist
Mechanik. Zu klaeren ist: **was es kostet, wenn ein Paar falsch ist.** Genau
das konnte bisher kein Pruefstand beantworten.

## Was gegeneinander antritt

| | Was gemerkt wird | Wie gesucht wird |
|---|---|---|
| **A** | nichts | heutige Kaskade, unveraendert |
| **B1 schmal/exakt** | nur gescheiterte Ketten | Begriffsmenge der Frage **wortgleich** gegen gemerkte Fragen; bei Treffer deren Ids nach vorn, Rest wie A |
| **B2 schmal/unscharf** | nur gescheiterte Ketten | Volltextsuche ueber die gemerkten Fragen; die Ids der bestpassenden nach vorn, Rest wie A |
| **B3 breit/unscharf** | **jedes** `recall`→`zeige`-Paar, auch die gelungenen | wie B2 |

B1 gegen B2 entscheidet, ob Verallgemeinerung noetig ist oder ob der
Nachschlag der wortgleichen Wiederholung reicht. B3 ist die gierige Fassung:
mehr Paare, weniger Beleg je Paar — der Kandidat mit dem groessten
Vergiftungsrisiko.

Unscharf heisst hier praezise: die gemerkte Frage muss mindestens **zwei**
Begriffe mit der neuen teilen (bei einbegriffigen Fragen: einen), sonst
feuert die Rueckkopplung nicht. Diese Schwelle ist vorab gesetzt und wird
nicht nachtraeglich gedreht.

## Der Durchlauf ist zeitgeordnet, sonst misst er sich selbst

Die 30 Sitzungen werden nach ihrer **ersten Zeitmarke** sortiert, die Aufrufe
darin nach Zeilennummer. Dann laeuft der Strom von vorn nach hinten:

1. Kommt eine Frage mit bekanntem Gold, wird sie mit dem Speicher
   ausgewertet, **wie er in diesem Augenblick ist**.
2. Erst danach wird das Paar, das aus dieser Stelle entsteht, eingetragen.

Ein Paar kann also nur **spaeteren** Fragen helfen, nie sich selbst. Damit
ist die Schaetzung nicht zirkulaer — anders als jede Messung, die den
Speicher vorher fuellt.

## Vergiftung: zwei Arme, einer davon echt

- **Echt:** `zielsicher.py` verwirft Ketten, deren Gold **kein** Inhaltswort
  der ersten Frage enthaelt — das sind Themenwechsel, keine
  Umformulierungen. Genau diese Paare wuerde eine Rueckkopplung **ohne**
  Relevanzprobe einsammeln. Der Arm laeuft also einmal mit und einmal ohne
  die Probe. Das ist kein ausgedachtes Gift, sondern das, was der
  naheliegende Bau von selbst einsammelt.
- **Kuenstlich:** mit Wahrscheinlichkeit p ∈ {10 %, 25 %, 50 %} bekommt ein
  Paar zufaellige lebende Ids statt der richtigen (fester Startwert, also
  wiederholbar). Das ahmt nach, was ein `zeige` bedeutet, das nicht die
  Antwort holt, sondern nur nachsieht.

## Gemessen wird je Arm

1. **Trefferquote der ersten Runde** ueber alle Fragen mit Gold: steht das
   Gold in den 8 gelieferten Treffern?
2. **Rueckfall, gepaart.** Wie viele Fragen, die unter A tragen, tragen unter
   B nicht mehr. Jeder Verlust ist ein echter Preis — diese Fragen
   funktionieren heute.
3. **Erwartete Zeichen je Frage** nach dem Modell aus #1911:
   `Zeichen der ersten Runde + P(scheitern) × 6.592` (Median einer
   gemessenen Rettungskette). Beide Arme werden **gleich** formatiert, damit
   der Unterschied aus den Zeilen kommt und nicht aus der Kopfzeile.
4. **Fehlzuendungen.** Wie oft die Rueckkopplung greift, ohne dass ihre Ids
   das Gold enthalten. Das ist das Mass fuer Vergiftung, unabhaengig davon,
   ob am Ende noch jemand anderes den Treffer rettet.
5. **Groesse des Speichers** am Ende. Ein Mechanismus, der unbegrenzt
   waechst, ist eine andere Sache als einer, der sich saettigt.

## Die Entscheidungsregel, vorher festgelegt

- **Angenommen**, wenn ein Arm die erwarteten Zeichen je Frage um **≥ 10 %**
  gegenueber A senkt (die 10-%-Regel aus MESSKRITERIUM.md) **und** unter den
  Fragen, die heute tragen, **nicht mehr verliert als er gewinnt**.
- **Verworfen**, wenn der Gewinn unter 10 % bleibt. Dann ist der Aufwand
  nicht zu rechtfertigen, egal wie plausibel der Mechanismus klingt — so wie
  der stufenweise Abbau (#1912) und die Abdeckungssortierung (#1904)
  verworfen wurden.
- **Die Relevanzprobe ist Pflicht**, wenn der Arm ohne sie mehr als die
  Haelfte seines Gewinns verliert. Dann gehoert sie in den Bau und nicht in
  die Dokumentation.
- **Bricht schon p = 10 % kuenstliches Gift den Gewinn**, taugt der
  Mechanismus nur mit einem Beleg je Paar (z. B. mehrfache Bestaetigung),
  nicht in der einfachen Fassung. Das waere dann das Ergebnis, nicht der
  Anlass zum Nachbessern.

## Was hier nicht gemessen wird

- **Der Nutzen fuer nie gestellte Fragen.** Der Pruefstand kennt nur die
  265 echten Anfragen; ob die Rueckkopplung auch auf *aehnliche neue* Fragen
  wirkt, kann er nicht zeigen. Erfundene Fragen sind nach MESSKRITERIUM.md
  ausgeschlossen, und das gilt hier weiter.
- **Der Schreibpfad.** Was das Merken eines Paares kostet, ist eine
  SQL-Zeile; das faellt gegen 6.592 Zeichen Rettungskette nicht ins Gewicht
  und wird nicht mitgerechnet.
- **Die Umsetzung im Server.** Der Pruefstand baut den Mechanismus in sich
  selbst nach und laesst `memory_server.py` unberuehrt. Ein Arm, der hier
  gewinnt, ist damit noch nicht gebaut — nur begruendet.

## Laufen lassen

    .venv/bin/python messung/rueckkopplung.py

Voraussetzung: `messung/aufrufe.json` (aus `ernte.py`). **`ernte.py` nicht
neu laufen lassen**, um die Zahlen zu reproduzieren — es erntet inzwischen
mehr Sitzungen, und damit aendert sich die Grundgesamtheit unter der Hand.

## Nachtrag vom selben Tag: der vierte Arm

Das Kriterium oben nennt drei B-Arme und spielt die zweite Achse (wortgleich
gegen unscharf) nur an der schmalen Fassung durch. Nach dem ersten Durchlauf
war sichtbar, dass **saemtliche Verluste aus dem unscharfen Nachschlagen
kommen** und keiner aus dem breiten Merken — die fuenf Faelle, die B3
verliert, sind drei Geschwisterfragen derselben Familie („Fluestern im
Eis …"), bei denen die Ids der Nachbarfrage den richtigen Eintrag von Rang 1
verdraengen.

Daraufhin wurde **B4 (breit gemerkt, wortgleich nachgeschlagen)**
nachgetragen — nicht, weil ein Gewinner gesucht wurde, sondern weil das 2×2
der beiden Achsen sonst unvollstaendig bleibt und der fehlende Platz genau
der ist, auf den die Fehleranalyse zeigt. Die Entscheidungsregel bleibt
unveraendert; B4 wird an derselben gemessen wie die anderen.

Wer die Zahlen nachrechnet, sollte wissen: B4 hat bei sauberen Paaren **null
Fehlzuendungen**, und das ist kein Zufall, sondern gegengeprueft. Von 46
wiederholten direkten Fragen haben **46 ueberlappendes Gold** — eine
wortgleich wiederholte Frage meint im Betrieb denselben Eintrag. Genau
darauf ruht der Arm, und genau das ist es, was bei p > 0 wegbricht.
