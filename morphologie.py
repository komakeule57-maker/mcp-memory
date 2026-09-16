"""Deutsche Beugung und Komposita fuer die FTS5-Suche - ohne Fremdbibliothek.

Zwei Verfahren, beide beim Speichern angewandt und bei der Suche gespiegelt:

* ``stem``    - regelbasierter Stemmer (Snowball-Deutsch, eingedampft).
                "gesperrt" und "sperrte" fallen beide auf "sperrt".
* ``zerlege`` - Kompositazerlegung gegen das Vokabular des Index selbst.
                "Fusionskatalysator" -> ["fusion", "katalysator"].
                Braucht bewusst kein Woerterbuch: was schon gespeichert wurde,
                ist das Woerterbuch.

Messwerte an 34 echten Memo-Dateien (728 Absaetze, je 60 belegte Testfaelle):
exakt allein 0/60 Beugung und 0/60 Komposita, mit diesen beiden Spalten
27/60 bzw. 32/60 - ohne Treffer bei echten Fragen zu verlieren.
"""

import re

_WORT = re.compile(r"\w+", re.UNICODE)

MIN_TEIL = 5        # kuerzere Bruchstuecke sind Rauschen ("ende", "aus")
MAX_TEIL = 12       # laengeres steht nie im Wortschatz, also nie nachzuschlagen
MIN_KOMPOSITUM = 11 # darunter lohnt der Zerlegeversuch nicht
_FUGEN = ("", "s", "n", "en", "es", "e")

_S_ENDUNG = set("bdfghklmnrt")
_ST_ENDUNG = set("bdfghklmnt")


def stem(wort: str) -> str:
    """Reduziert eine Wortform auf ihren Stamm. Nur fuer den Index gedacht,
    das Ergebnis muss kein echtes Wort sein - es muss nur kollidieren."""
    w = wort.lower().replace("ß", "ss")
    if len(w) < 4:
        return w
    # Partizip-Vorsilbe: gesperrt -> sperrt, geflusht -> flusht
    if len(w) > 6 and w.startswith("ge") and w[2] not in "aeiou":
        w = w[2:]
    for suf in ("ern", "em", "er", "en", "es", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    else:
        if w.endswith("s") and len(w) > 4 and w[-2] in _S_ENDUNG:
            w = w[:-1]
    for suf in ("est", "er", "en"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    else:
        if w.endswith("st") and len(w) > 5 and w[-3] in _ST_ENDUNG:
            w = w[:-2]
    for suf in ("keit", "heit", "lich", "isch", "ung", "end", "ig", "ik"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            break
    return w


def stamm_spalte(text: str) -> str:
    """Alle Woerter eines Textes gestemmt, ohne Wiederholungen."""
    return " ".join(dict.fromkeys(stem(t) for t in _WORT.findall(text)))


def zerlege(wort: str, vokabular: set, tiefe: int = 3) -> list:
    """Zerlegt ein Kompositum in bekannte Teile. Leere Liste, wenn es nicht geht."""
    w = wort.lower()
    if len(w) < MIN_KOMPOSITUM or not w.isalpha():
        return []

    def rek(rest, tief):
        if rest in vokabular and len(rest) >= MIN_TEIL:
            return [rest]
        if tief == 0:
            return None
        # laengstes passendes Praefix zuerst - "fusions|katalysator" statt "fus|..."
        for schnitt in range(len(rest) - MIN_TEIL, MIN_TEIL - 1, -1):
            if rest[:schnitt] not in vokabular:
                continue
            for fuge in _FUGEN:
                if fuge and not rest[schnitt:].startswith(fuge):
                    continue
                schwanz = rest[schnitt + len(fuge):]
                if len(schwanz) < MIN_TEIL:
                    continue
                weiter = rek(schwanz, tief - 1)
                if weiter:
                    return [rest[:schnitt]] + weiter
        return None

    teile = rek(w, tiefe)
    return teile if teile and len(teile) > 1 else []


def teile_spalte(text: str, vokabular: set) -> str:
    """Alle zerlegbaren Komposita eines Textes als Einzelteile."""
    teile = []
    for w in _WORT.findall(text):
        teile.extend(zerlege(w, vokabular))
    return " ".join(dict.fromkeys(teile))


# Fuer das Woerterbuch wird AUCH am Unterstrich getrennt, anders als bei _WORT.
# `\w` schliesst ihn ein, `binaer_datei` bliebe also ein Wort, scheiterte an
# isalpha() und fiele ganz heraus - obwohl beide Haelften taugliche Bausteine
# sind. Genau daran war das aus fts5vocab gelesene Woerterbuch reicher: der
# FTS5-Tokenisierer trennt am Unterstrich. In einem deutschen Wort steht keiner.
_WORTTEIL = re.compile(r"[^\W_]+", re.UNICODE)


def wortschatz(text: str) -> set:
    """Woerter aus einem Text, die als Kompositumsteil taugen."""
    return {
        w.lower()
        for w in _WORTTEIL.findall(text)
        if MIN_TEIL <= len(w) <= MAX_TEIL and w.isalpha()
    }


def kandidaten(text: str) -> set:
    """Alles, was `zerlege` fuer diesen Text ueberhaupt nachschlagen KANN.

    `zerlege` prueft ausschliesslich Teilzeichenketten des Wortes, das es
    gerade zerlegt (`rest` ist immer ein Suffix, `rest[:schnitt]` dessen
    Praefix), und im Wortschatz stehen nur Woerter von MIN_TEIL bis MAX_TEIL
    Zeichen. Mehr als diese Menge kann also nie gefragt werden.

    Das ist der Hebel, mit dem sich das Woerterbuch gezielt holen laesst statt
    ganz: der Umfang haengt am Text, nicht am Bestand. Bewusst eine etwas zu
    grosse Obermenge - welche Schnitte die Rekursion wirklich erreicht, haengt
    von den Fugen ab, und die hier nachzubilden hiesse, dieselbe Logik zweimal
    zu fuehren. Ein paar Kandidaten zu viel kosten nichts, ein fehlender waere
    eine stille Luecke in der Zerlegung.
    """
    aus = set()
    for w in _WORT.findall(text):
        if len(w) < MIN_KOMPOSITUM or not w.isalpha():
            continue  # kuerzere ruft zerlege gar nicht erst nach
        k = w.lower()
        for i in range(len(k) - MIN_TEIL + 1):
            for j in range(i + MIN_TEIL, min(i + MAX_TEIL, len(k)) + 1):
                aus.add(k[i:j])
    return aus
