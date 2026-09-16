"""Optionale Zweitmeinung zum Dublettenhinweis: Widerspruch oder Fortschritt?

Der Dublettenhinweis in `remember` sagt, DASS sich zwei Eintraege ueberschneiden.
Er sagt nicht, ob der neue dem alten widerspricht oder ihn nur fortschreibt -
und genau das ist die Frage, die ueber `ersetzt=` entscheidet. Das kleine
Sprachmodell auf dem M5Stack kann sie beantworten (gemessen #1327: 9/15 richtig,
1/12 falsche Widerspruchsmeldungen, 3/3 echte erkannt - n=15, Standardfehler
rund 13 Punkte, also ein Hinweis und kein Urteil).

**Grundsatz: das Memory laeuft vollstaendig ohne dieses Modul.** Faellt das Board
aus, ist es abgeschaltet oder antwortet es zu langsam, dann ist die Ausgabe von
`remember` exakt die von vorher - keine Fehlermeldung, kein Stacktrace, und vor
allem keine Wartezeit bei jedem weiteren Aufruf. Dafuer sorgen drei Dinge:

1. **Vorprobe** auf `/v1/models` mit kurzer Frist. Antwortet das Board (gemessen
   22 ms im LAN), wird gefragt; sonst nicht. Ein totes Geraet kostet einmal die
   Frist, nicht einmal je Paar.
2. **Sperrfrist** nach einem Fehlschlag: danach wird eine Weile gar nicht erst
   geprobt. Ohne sie zahlt jeder `remember` den Anlauf erneut. Wie lange
   geschwiegen wird, haengt davon ab, was der Fehlschlag gekostet hat - das
   entscheidet `_sperrdauer`.
3. **Zeitbudget** ueber alle Paare eines Aufrufs. Lieber zwei von drei Paaren
   beurteilt als ein `remember`, das eine halbe Minute haengt.

**Opt-in: ohne gesetztes `MEMORY_FC_URL` laeuft dieses Modul gar nicht an.** Es
gibt bewusst keine Vorgabeadresse - sonst spraeche jede fremde Installation bei
jedem `remember` ein Geraet im Netz des Nutzers an, das ihm nicht gehoert.

Einschalten: `MEMORY_FC_URL` **und** `MEMORY_FC_MODELL` setzen, bei Bedarf
`MEMORY_FC_SCHLUESSEL`. Voruebergehend abschalten, ohne die Adresse zu
verlieren: `MEMORY_FC_AUS=1`.

**Jede OpenAI-kompatible Gegenstelle geht**, nicht nur das Board: ein Modell auf
dem eigenen Rechner (llama.cpp, Ollama, vLLM), im eigenen Netz oder bei einem
Cloud-Anbieter. Gefragt wird `/v1/chat/completions` mit `max_tokens` und
`temperature: 0`; wessen Anbieter darauf besteht, diese Felder anders zu nennen,
bekommt hier keine Sonderbehandlung - der Aufruf scheitert dann und das Modul
schweigt, wie bei jedem anderen Fehlschlag auch.

**Die gemessenen Zahlen oben gelten NUR fuer das Board-Modell.** Sie stammen von
Qwen3-VL-2B mit genau dieser Anweisung. Ein anderes Modell kann besser sein -
gemessen ist es nicht, und die Anweisung ist auf Deutsch und woertlich
kalibriert. Wer das Modell wechselt, faengt beim Messen von vorn an
(`pruefstand_fc.py`).

**Was dabei den Rechner verlaesst:** je Paar bis zu `MAXZ` (200) Zeichen aus
beiden Notizen, als Prompt an die angegebene Adresse. Das ist die einzige Stelle
im ganzen Projekt, an der Inhalte den Prozess verlassen - wer hier statt eines
Geraets im eigenen Netz eine Cloud-Schnittstelle eintraegt, schickt seine
privaten Notizen dorthin.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

# OHNE VORGABE, und das ist Absicht: der Faktencheck ist ein Opt-in. Eine fest
# eingebaute Adresse hiesse, dass jede fremde Installation bei jedem `remember`
# ein Geraet im Netz des Nutzers anspricht, das ihm nicht gehoert - und falls
# dort zufaellig etwas OpenAI-Kompatibles antwortet, gingen bis zu MAXZ Zeichen
# privater Notizen dorthin. Ohne gesetztes MEMORY_FC_URL laeuft das Modul also
# gar nicht erst an.
#
# Eigenes Board eintragen: MEMORY_FC_URL=http://<adresse>:8000 in die
# MCP-Konfiguration. Das Board haengt typisch am DHCP und wechselt die Adresse;
# ein falscher Wert faellt NICHT auf - der Faktencheck schweigt dann einfach, so
# wie er es bei jedem Ausfall tut. Wiederfinden: Adressbereich anpingen und bei
# den Antwortenden `/v1/models` abfragen. Dauerhaft besser: feste Lease im Router.
URL = os.environ.get("MEMORY_FC_URL", "").strip().rstrip("/")

# Beide Schreibweisen der Basisadresse annehmen. Die Pfade unten lauten
# `/v1/models` und `/v1/chat/completions`; das Board wird als
# "http://<adresse>:8000" eingetragen und passt damit. Cloud-Anbieter
# dokumentieren ihre Basisadresse aber fast immer MIT dem Versionsteil
# ("https://api.example.com/v1"), und wer den so uebernimmt, landete sonst auf
# ".../v1/v1/chat/completions". Das faellt nicht auf: der 404 wird verschluckt,
# das Modul sperrt sich und schweigt - genau die Sorte Fehlschlag, die man
# stundenlang woanders sucht. Also hier einmal abschneiden und unten immer
# anfuegen; bei einer Adresse ohne Versionsteil aendert das nichts.
if URL.endswith("/v1"):
    URL = URL[: -len("/v1")]
# Ebenfalls ohne Vorgabe: die Adresse sagt noch nicht, welches Modell dort
# bedient wird, und ein eingebauter Name waere bei jedem anderen Anbieter falsch.
# Beispiele: das gemessene Board-Modell
# "AXERA-TECH/Qwen3-VL-2B-Instruct-GPTQ-Int4-AX630C-P320-CTX448", bei einem
# Cloud-Anbieter schlicht dessen Modellkennung.
MODELL = os.environ.get("MEMORY_FC_MODELL", "").strip()

# Nur fuer Anbieter, die einen Schluessel verlangen. Wird als
# `Authorization: Bearer ...` mitgeschickt und taucht nirgends in einer Ausgabe
# auf - weder in `zustand()` noch in einer Fehlermeldung, denn Fehler werden hier
# ohnehin verschluckt statt weitergereicht.
SCHLUESSEL = os.environ.get("MEMORY_FC_SCHLUESSEL", "").strip()
# Drei Wege zum selben Schweigen: keine Adresse, kein Modellname (beides der
# Normalfall - niemand hat das hier eingerichtet) oder ausdruecklich
# abgeschaltet, ohne die Adresse loeschen zu muessen.
AUS = bool(os.environ.get("MEMORY_FC_AUS", "").strip()) or not URL or not MODELL

# Die Vorprobe kostet gemessen 17 ms. Die Frist ist trotzdem auf 3 s gesetzt:
# `axllm` bedient nur eine Anfrage zugleich, eine noch laufende Antwort haelt
# also auch `/v1/models` auf. Einmal gemessen 1,57 s - mit 1,5 s Frist haette
# die Probe ein voellig gesundes Board fuer fuenf Minuten gesperrt.
PROBE_FRIST = float(os.environ.get("MEMORY_FC_PROBE", "3.0"))   # Sekunden
FRAGE_FRIST = float(os.environ.get("MEMORY_FC_FRIST", "20"))    # je Paar
BUDGET = float(os.environ.get("MEMORY_FC_BUDGET", "25"))        # je Aufruf
SPERRE = float(os.environ.get("MEMORY_FC_SPERRE", "300"))       # nach Fehlschlag

# Kurze Sperre fuer den abgelehnten Verbindungsversuch. Der kostet gemessen
# 2-3 ms, das Geraet lebt also und nur der Dienst fehlt - typisch laedt `axllm`
# gerade sein Modell. Zwischen Start und LISTEN vergehen gemessen 11-18 s
# (#1346), und genau so lang wird geschwiegen. Die lange Sperre waere hier
# falsch: fuenf Minuten ohne Vermerke wegen fuenfzehn Sekunden Anlauf.
SPERRE_KURZ = float(os.environ.get("MEMORY_FC_SPERRE_KURZ", "15"))

# 200 Zeichen je Notiz ist der ausgemessene Arbeitspunkt (#1327): bei 260 wurde
# das Ergebnis nicht besser, sondern minimal schlechter, und der Prompt naeher
# an die 384 Token Prefill des Boards.
MAXZ = int(os.environ.get("MEMORY_FC_ZEICHEN", "200"))

# Woertlich die gemessene Anweisung. Wer sie umformuliert, macht #1327 ungueltig -
# schon der Wechsel von der kurzen auf diese lange Fassung hat die Fehlalarme
# von 8/12 auf 4/12 halbiert. Auch das fehlende Datum ist Absicht: gemessen wurde
# ohne, und die Zeitachse steckt bereits in "verschiedenen Zeitpunkten".
ANWEISUNG = (
    "Du pruefst zwei Notizen aus einem Arbeitsgedaechtnis.\n"
    "WIDERSPRUCH: beide sagen ueber DIESELBE Sache zum GLEICHEN Zeitpunkt Unvereinbares.\n"
    "FORTSCHRITT: dieselbe Sache zu verschiedenen Zeitpunkten, ein neuerer Stand loest "
    "einen aelteren ab - beide waren zu ihrer Zeit richtig.\n"
    "UNABHAENGIG: verschiedene Themen, oder verschiedene Teile derselben Sache.\n"
    "Antworte mit GENAU EINEM Wort: WIDERSPRUCH, FORTSCHRITT oder UNABHAENGIG."
)

URTEILE = ("WIDERSPRUCH", "FORTSCHRITT", "UNABHAENGIG")

_THINK = re.compile(r"<think>.*?</think>", re.S)
_KOPF = re.compile(r"\*\*(.+?)\*\*")

_sperre_bis = 0.0   # monotone Uhr; 0 = keine Sperre


def _kurz(text: str, n: int = None) -> str:
    """Auf n Zeichen bringen - moeglichst die fette Titelzeile statt eines Schnipsels.

    `n=None` heisst MAXZ, und zwar der zur Aufrufzeit geltende. Als Vorgabewert
    `n: int = MAXZ` geschrieben waere die Zahl bei der Definition eingefroren -
    `pruefstand_fc.py` koennte die Notizlaenge dann nicht mehr variieren, und
    genau das ist der Arbeitspunkt, den #1327 ausgemessen hat."""
    n = MAXZ if n is None else n
    s = " ".join((text or "").split())
    m = _KOPF.match(s)
    if m and 20 <= len(m.group(1)) <= n:
        return m.group(1)
    return s[:n]


def deckungsgleich(a: str, b: str) -> bool:
    """Ob zwei Texte als Notiz zeichengleich werden.

    Dann sieht das Modell zweimal denselben Satz und hat nichts zu vergleichen -
    es antwortet aber trotzdem, gemessen auch mit WIDERSPRUCH. Solche Paare
    gehoeren abgefangen statt gefragt: ein Text widerspricht sich nicht selbst.

    Trifft nicht nur echte Dubletten. `_kurz` nimmt bevorzugt die fette
    Titelzeile, zwei Eintraege mit gleicher Titelzeile und verschiedenem Rumpf
    fallen also zusammen, obwohl sie es nicht sind (#1416/#1418, #1402/#1403).
    Auch dieser Fall ist nicht beurteilbar - nur eben aus dem anderen Grund.
    """
    return _kurz(a) == _kurz(b)


def _post(pfad: str, last, frist: float):
    d = json.dumps(last).encode() if last is not None else None
    kopf = {"Content-Type": "application/json"} if d else {}
    if SCHLUESSEL:
        kopf["Authorization"] = "Bearer " + SCHLUESSEL
    r = urllib.request.Request(URL + pfad, d, kopf)
    with urllib.request.urlopen(r, timeout=frist) as f:
        return json.load(f)


def _sperrdauer(fehler: BaseException) -> float:
    """Wie lange nach diesem Fehlschlag geschwiegen wird.

    Der abgelehnte Verbindungsversuch ist der einzige Fehler, der nachweislich
    nichts kostet (gemessen 2-3 ms) und zugleich sagt: der Rechner ist da, nur
    der Dienst nicht. Der ist meist gleich wieder da, also kurz sperren.

    Alles andere bekommt die lange Sperre. Eine tote IP faellt ausdruecklich
    darunter, auch wenn sie manchmal schnell antwortet: gemessen 72 ms (kein Weg
    zum Host) im einen Versuch, volle 3 s Zeitueberschreitung im naechsten. Nach
    der Dauer zu entscheiden waere also unzuverlaessig, nach der Fehlerart
    nicht - nur der abgelehnte Versuch kommt als `ConnectionRefusedError`, eine
    tote IP als nacktes `OSError`.
    """
    grund = getattr(fehler, "reason", fehler)
    return SPERRE_KURZ if isinstance(grund, ConnectionRefusedError) else SPERRE


def _sperren(dauer: float = SPERRE) -> None:
    global _sperre_bis
    _sperre_bis = time.monotonic() + dauer


def erreichbar() -> bool:
    """Kurze Vorprobe. Schweigt bei jedem Fehler und sperrt danach - kurz, wenn
    nur der Dienst fehlt, lang sonst (siehe `_sperrdauer`).

    `MEMORY_FC_PROBE=0` ueberspringt sie. Gedacht fuer Anbieter, bei denen sie
    nichts taugt: manche listen unter `/v1/models` hunderte Kennungen, andere
    eine einzige, die nicht die ist, die man beim Fragen angibt (ein Dateipfad
    etwa), und dann sperrt die Modellpruefung eine voellig gesunde Gegenstelle
    aus. Bei einem verlaesslichen Dienst spart das ausserdem eine Anfrage je
    Aufruf - der Sinn der Probe ist ein Geraet, das oft weg ist, nicht ein
    Rechenzentrum."""
    if AUS or time.monotonic() < _sperre_bis:
        return False
    if PROBE_FRIST <= 0:
        return True
    try:
        antwort = _post("/v1/models", None, PROBE_FRIST)
        namen = [m.get("id") for m in antwort.get("data", [])]
        if MODELL not in namen:
            # Falsches Modell geladen: die gemessenen Zahlen gelten dann nicht.
            _sperren()
            return False
        return True
    except Exception as fehler:
        _sperren(_sperrdauer(fehler))
        return False


def urteil(a: str, b: str, frist: float = FRAGE_FRIST):
    """Ein Paar beurteilen. Gibt WIDERSPRUCH / FORTSCHRITT / UNABHAENGIG - oder
    None, wenn das Board nicht antwortet oder etwas anderes sagt als die drei
    Worte. None heisst immer 'kein Hinweis', nie 'kein Widerspruch'."""
    prompt = f"{ANWEISUNG}\n\nNotiz A: {_kurz(a)}\nNotiz B: {_kurz(b)}\n\nAntwort:"
    last = {
        "model": MODELL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16,
        "temperature": 0,
    }
    try:
        antwort = _post("/v1/chat/completions", last, frist)
        roh = antwort["choices"][0]["message"]["content"]
    except Exception as fehler:
        _sperren(_sperrdauer(fehler))
        return None
    s = _THINK.sub("", roh).strip().upper().replace("Ä", "AE")
    for wort in URTEILE:
        if wort in s:
            return wort
    return None


def urteile(paare, budget: float = BUDGET) -> list:
    """Mehrere Paare unter einem gemeinsamen Zeitbudget.

    paare: Folge von (a, b). Rueckgabe: gleich lange Liste aus Urteil oder None.
    Ist das Budget aufgebraucht, sind die restlichen Eintraege None - die
    Reihenfolge des Aufrufers entscheidet also, was noch geprueft wird.
    """
    paare = list(paare)
    ergebnis = [None] * len(paare)
    if not paare or not erreichbar():
        return ergebnis
    ende = time.monotonic() + budget
    for i, (a, b) in enumerate(paare):
        rest = ende - time.monotonic()
        if rest <= 1.0:
            break
        ergebnis[i] = urteil(a, b, frist=min(FRAGE_FRIST, rest))
        if time.monotonic() < _sperre_bis:
            # urteil() hat gesperrt, das Board ist weggebrochen. Nicht noch
            # einmal in die volle Frist laufen - der Rest bleibt None.
            break
    return ergebnis


def zustand() -> str:
    """Einzeilige Auskunft fuer die Werkzeuge - ohne selbst zu fragen."""
    if not URL:
        return "nicht eingerichtet (MEMORY_FC_URL nicht gesetzt)"
    if not MODELL:
        return "nicht eingerichtet (MEMORY_FC_MODELL nicht gesetzt)"
    if AUS:
        return "abgeschaltet (MEMORY_FC_AUS)"
    rest = _sperre_bis - time.monotonic()
    if rest > 0:
        return f"gesperrt, noch {rest:.0f}s (letzter Versuch fehlgeschlagen)"
    return f"bereit an {URL}"
