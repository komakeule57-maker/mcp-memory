# mcp-memory

Local MCP server for persistent AI memory. Python, SQLite with FTS5, stdio.
No third-party library except the official `mcp` SDK, no ORM, no vector
store, no auth, no HTTP — nothing leaves the machine. The single exception
is the **opt-in** fact check (`faktencheck.py`), which is off unless you
explicitly point `MEMORY_FC_URL` at a language model of your own; see
[`pruefe`](#pruefeids--opt-in-needs-a-language-model).

Built for **German-language notes**: the search understands inflection
("Rangliste" finds "Ranglisten") and compounds ("Katalysator" finds
"Fusionskatalysator").

This README is in English, but the tool itself is not: every string the
server actually prints or returns — status messages, the `art` (kind)
vocabulary (`schnittstelle`, `fallstrick`, `entscheidung`, `messwert`,
`arbeitsweise`, `verlauf`, `gemischt`), and the `pruefe` verdict words
(`WIDERSPRUCH`/contradiction, `FORTSCHRITT`/progress,
`UNABHAENGIG`/independent, `uneinig`/disputed) — stays German. Translating
those would mean touching the fact-check prompt and the fixed vocabulary
several other scripts compare against by exact string, which is out of
scope for a docs pass and would invalidate measurements tied to the exact
wording (see [Re-measuring the Fact Check](#re-measuring-the-fact-check)).
The example blocks below therefore show real, unmodified German output,
glossed in English where it first appears.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

claude mcp add memory -s user -- \
    /path/to/mcp-memory/.venv/bin/python \
    /path/to/mcp-memory/memory_server.py
```

`-s user` makes the server available in all projects; the entry ends up in
`~/.claude.json`. Restart Claude Code afterward — MCP servers are only
loaded at startup. The tools are then called `mcp__memory__recall` and
`mcp__memory__remember`.

For Claude Desktop, use `~/.config/Claude/claude_desktop_config.json`
instead:

```json
{
  "mcpServers": {
    "memory": {
      "command": "/path/to/mcp-memory/.venv/bin/python",
      "args": ["/path/to/mcp-memory/memory_server.py"]
    }
  }
}
```

## Two Axes: Tag and Kind

A memory sorted only by project answers the question "where does this
belong" and no other. At 984 entries, 340 sat under a single tag — that's
no longer a filter. Whoever looks for one specific detail gets the
chronicle thrown in for free.

Hence a second axis. The **tag** (`marke`) says WHERE (the project), the
**kind** (`art`) says WHICH SORT of knowledge:

| Kind (`art`) | What goes in |
|---|---|
| `schnittstelle` (interface) | signature, file name, command, data format — what you need verbatim |
| `fallstrick` (pitfall) | the obvious approach is wrong because … |
| `entscheidung` (decision) | chosen this way and not another, with rationale |
| `messwert` (measurement) | a number plus its measurement criterion |
| `arbeitsweise` (way of working) | how to work with this user |
| `verlauf` (chronicle) | chronicle: what was built when |
| `gemischt` (mixed) | not yet classified (no row in the side table) |

Three design decisions behind this:

**The vocabulary is closed and enforced via `CHECK`**, not by convention in
a free-text field. A free field decays within weeks into `fallstrick`,
`fallstricke`, and `pitfall`, and after that nothing filters anymore.

**`verlauf` (chronicle) is excluded from `recall`'s default view.** The
chronicle is what drowns out every search for a specific detail. Not
deleted, only muted — the same pattern as with outdated entries. **But not
silently:** `recall` reports in its header how many chronicle entries it
held back. Silently hiding them would be worse than the noise — with
three mediocre hits you'd otherwise never notice that the good one is
sitting in the chronicle.

**Exactly one kind per entry.** That's inconvenient, and that's the point:
it puts pressure, at write time, to separate the chronicle paragraph from
the knowledge paragraph. If a text belongs to two kinds, it's two entries.

**No row in the side table means `gemischt` (mixed).** This meant the
migration needed no backfill across 984 rows, and the backlog stays
visible instead of hiding as a silent default.

### The Tag Is a Free-Text Field — With Consequences

What's forbidden for the kind via `CHECK` is allowed for the tag, and the
data demonstrated it. Cleaned up on 2026-09-15, 176 → 166 tags
(`migration_marken.py`, 86 entries):

- **Two separators side by side** — `spiel3d-test Nachtfrost` and
  `spiel3d-test,Nachtfrost`. Unified to spaces. The space separator had
  also torn the two-word project name `DEEP HULL` into two tags.
- **Split project names** — `leuchtturm`(13) next to
  `leuchtturm-project`(14), arising from two different working habits: the
  imported memos carried the long name, the ones set by hand later
  carried the short one. Merging was **decided by hand**, not by a prefix
  rule: `atlas-kern-found` and `atlas-kern-16k-limit-absicht` share the
  same beginning too and are nevertheless different things.
- **Kind-words used as tags** — `fallstrick`(6), `arbeitsweise`(4): exactly
  the duplication the second axis was supposed to end. Removed only where
  the entry's kind said the same thing.

**What was left standing is the more interesting part.** In three entries
the tag says something *different* than the kind — `#1117` is classified
as `fallstrick` (pitfall) and carries the tag `messwert` (measurement),
because a calibration value sits in the middle of the text. The
single-valued kind axis can't capture that, the tag can. Strictly speaking
the entry should have been split ("if a text belongs to two kinds, it's
two entries"); until then, the facet tag is the more honest state than a
kind that hides half the story.

**Cleanup is not prevention.** The free-text field re-accumulates the same
clutter the moment nobody's watching — so, since the schema rebuild, the
database keeps a **directory of assigned tags** (`marken`), and `remember`
checks every new tag against it:

```
Gespeichert #1429 als messwert (Tags: mcp-memory)
Neue Marke 'mcp-memory' - dem Bestand schon bekannt ist: mcp-memory-server. Dieselbe Sache?

Gespeichert #1431 als messwert (Tags: fallstrick)
Marke 'fallstrick' ist ein Art-Wort. Die Marke sagt WO, die Art WELCHE SORTE - dafuer ist art= da.
```

(This is the tool's actual output, which stays German — see the note at the top of this README.)

Exactly the three decay patterns from above are recognized: spelling
variant (case, typos via `difflib`), split project name (`x` next to
`x-...`), and kind-word used as a tag. **Warned, not forbidden** — a tag
that never existed before is the normal case for the first entry of a new
project, and a tool that aborts over that would be worse than the
clutter. Same pattern as the duplicate hint: show it, let the human
decide.

**The guard asks about the number of entries, not about the entry's
presence in the directory** — and that's a correction to its own first
draft (`#1459`). That draft bailed out on every known tag and immediately
entered the just-flagged one into the directory itself. Result: the
warning appeared exactly once, the second typo of the same kind sailed
through silently — and the same for the kind-word, which can never be a
valid tag. After a few test runs, `fallstrick`, `messwert`,
`arbeitsweise`, and the misspelling `mcp-memry-server` sat in the
directory as accepted tags, and the guard offered them up as neighbors: it
checks against a list that it itself pollutes with what it's warning
about.

Since then the rule is: the kind-word is **always** flagged and never
entered, and the guard only goes quiet on a tag once it carries
`MARKE_ETABLIERT` (3) living entries. A typo never gets there; a genuine
new project does after three entries. Only something carrying more
entries than the tag in question gets suggested as a neighbor — otherwise
the guard would recommend yesterday's typo. Counting here is **exact by
character**, unlike search: `recall(marke="mcp-memory")` deliberately
picks up `mcp-memory-server` too, but for the guard those are two
spellings of the same thing, not confirmation. The index only narrows
down, `_marken` verifies; counting stops at the threshold at the latest,
so a 315-entry tag doesn't slow down `remember` (measured 2.7 → 3.6 ms).

After a rename outside of `remember`, `nachziehen.py` brings the directory
back into sync — tags without a single entry drop out in the process, as
do tags that only carry outdated entries, and kind-words. This is also
the way to get rid of a misspelling: retire the entry, then re-sync.

## Tools

### `remember(text, tags="", art="", ersetzt="")`

Creates an entry with the current timestamp and returns its **id**.
`tags` are free-form keywords and get searched too — convention: the
project. `art` is the kind of knowledge (see above). `ersetzt="12,34"`
supersedes the named entries.

Without `art`, the entry lands as `gemischt` (mixed) and the return value
flags it. It also flags the **scope**: over 900 characters, or a date as
the very first thing in the text (optional `**` asterisks before it) at
more than 400 characters. Both are signs that chronicle and knowledge are
stuck together in one paragraph. The date check is deliberately anchored
at the start of the text: it used to search the first 200 characters and
thereby flagged 232 entries of the dataset instead of 57 — a title line
with "checked on 2026-09-11" on line 2 is not a chronicle, and a warning
that's wrong three-quarters of the time gets ignored. As with the
duplicate hint, it only shows, never decides.

Afterward `remember` reports **similar existing entries** — so
contradictions get noticed instead of being silently placed side by side.
Nothing is decided automatically there: the tool shows, the caller
judges.

The similarity measure is the rarity-weighted share of the new text that's
already contained in the old one (rarity comes from `fts5vocab`, i.e. from
the index itself). Measured distribution across 60 samples: genuine
duplicate 1.00 — related paragraph from the same memo at most 0.49 —
unrelated at most 0.25. Threshold therefore **0.55**.

For every hit shown, it also states which numeric value is being
superseded:

```
Aehnliche Eintraege - pruefen, ob einer davon ersetzt gehoert:
  #249 (85% Ueberschneidung, Zahlen 186 -> 242) Gesamt jetzt 186 Checks, alle…
```

(Real, German, tool output — "similar entries, check whether one of them should be superseded" / "85% overlap, numbers 186 -> 242, total now 186 checks, all...".)

This is deliberately **not a second detector**, but a label on the first
one. The number comparison has no precision on its own: across 983
entries and 144,723 candidate pairs, only 11 pairs reach 30 % overlap or
more, and of the 6 with differing numbers, none is a contradiction —
they're progress snapshots, both true at their respective time. So it
finds nothing new; it only says why you should look at a hit that's
already shown, and that's the path to `ersetzt=`. It's only shown when
both sides have numbers the other side lacks — otherwise the condition
would fire on every newly added date.

**What it can't do:** recognize a genuine contradiction phrased
differently ("the limit is 8" vs. "the default is ten"). That needs
meaning, not word overlap — the same boundary as with language mixing.

That's exactly where the **opt-in fact check** comes in (see below): if
you have pointed `MEMORY_FC_URL` at a small language model of your own
and it answers, every line additionally gets a note on how the two
entries relate to each other. Unset — the default — none of this happens
and no network call is made.

```
  #249 (85% Ueberschneidung, Zahlen 186 -> 242, Fortschritt?) Gesamt jetzt 186 Checks, alle…
  (die Vermerke mit ? sind die Einschaetzung eines kleinen Sprachmodells, kein Befund - selbst nachsehen)
```

If the device isn't there, the note is missing and otherwise nothing
changes.

**One fact per call, not one document.** That's the most important rule of
the whole tool: `recall`'s return consists of whole entries. Whoever
saves a 180 KB file as a single entry also gets it back as a single hit —
and has gained nothing.

### `verdichten(tags="", art="alle", schwelle=0.5, gruppen=5)`

Finds groups of entries that say largely the same thing — typically: an
old state next to a new one ("version 0.2" next to "version 0.3", "186
checks" next to "242 checks"). **Doesn't summarize anything itself.** You
write a new entry from a group and supersede the old ones via
`remember(..., ersetzt=...)`.

`art="verlauf"` tackles the chronicle on its own — that's where most
duplicates sit, because the same piece of work gets described multiple
times.

Pairwise comparisons would be quadratic (400,000 pairs at 900 entries).
So only pairs sharing a **rare** word stem are compared — a stem that
occurs in more than 5 % of entries connects everything to everything and
is skipped. That leaves roughly 117,000 pairs and ~3 s across the whole
dataset.

### `pruefe(ids)` — opt-in, needs a language model

Counterpart to `verdichten`: that one finds groups by word overlap,
`pruefe` says whether a **contradiction** or just a **newer state of
affairs** is behind it. Each pair is asked in **both directions**
(rationale below), so it costs two requests and roughly 10 s. Hence the
cap of 5 pairs asked per call.

Any **OpenAI-compatible** endpoint works — a model on your own machine
(llama.cpp, Ollama, vLLM), a box on your LAN, or a cloud provider:

```bash
# local, no key needed
MEMORY_FC_URL=http://localhost:11434    MEMORY_FC_MODELL=qwen2.5:3b

# a cloud provider
MEMORY_FC_URL=https://api.example.com/v1  MEMORY_FC_MODELL=some-model \
MEMORY_FC_SCHLUESSEL=sk-…                 MEMORY_FC_PROBE=0
```

Both spellings of the base URL are accepted, with or without the trailing
`/v1` — the code normalizes it, because pasting a provider's documented
`…/v1` would otherwise produce `…/v1/v1/chat/completions`, and that 404
would be swallowed like any other failure and leave you with nothing but
silence.

> **This is the one place where note content leaves the machine, and it
> is off until you turn it on.** There is deliberately no default address
> and no default model: unless **both** `MEMORY_FC_URL` and
> `MEMORY_FC_MODELL` are set, `faktencheck.py` never starts up, makes no
> network call of any kind, and `remember`'s output is exactly what it is
> without the module. When it is on, each judged pair sends up to 200
> characters from each of the two notes to that endpoint as a prompt.
> Pointing it at a cloud provider therefore ships those excerpts of your
> private notes to a third party — a reasonable trade for some, the wrong
> one for others, which is why nothing is preconfigured and you have to
> say so explicitly.

> **The measured numbers below apply to the board model only.** They come
> from Qwen3-VL-2B with exactly the German prompt in `faktencheck.py`. A
> larger model is likely better — but that is an expectation, not a
> measurement, and the prompt is calibrated word for word — see "What was
> measured and discarded" further down, where adding one sentence to it
> halved the accuracy. If you swap the model, the numbers here stop
> applying and you start measuring again with `pruefstand_fc.py`.

```
pruefe("249,255")
#249 <-> #255: FORTSCHRITT
Einschaetzung eines kleinen Sprachmodells, kein Befund - selbst nachsehen.

pruefe("1421,1425")
#1421 <-> #1425: uneinig - WIDERSPRUCH in der einen, FORTSCHRITT in der anderen Richtung

pruefe("1416,1418")
#1416 <-> #1418: als Notiz zeichengleich, nicht beurteilbar - entweder Dublette
(dann verdichten), oder der Unterschied steckt jenseits der ersten 200 Zeichen
und das Modell sieht ihn nicht
```

(Real tool output, German: `FORTSCHRITT` = progress, `WIDERSPRUCH` = contradiction,
`UNABHAENGIG` = independent, `uneinig` = disputed/unclear. The three verdict words
are a fixed vocabulary shared with `faktencheck.py`'s prompt — see the note at the
top of this README on why they aren't translated.)

Everything measured from here on was queried against **Qwen3-VL-2B** on
an M5Stack Module LLM (AX630C NPU) — that is what the numbers describe,
not a claim that you need that board. Any OpenAI-compatible endpoint
works; the accuracy you get from a different model is unmeasured.

**On the larger set, the sensitivity doesn't hold up.** The first number
came from 15 hand-picked cases (9 correct, 1/12 false alarms, **3/3** real
ones caught). Against the 70 pairs from `pruefstand_fc.py` (2026-09-14):

| | 15 cases, by hand | 70 pairs, test rig |
|---|---|---|
| correct | 9/15 (60 %) | 31/46 (67 %, 95 %: 53–79 %) |
| false alarms | 1/12 (8 %) | 6/64 (9 %) |
| **real ones caught** | **3/3** | **2/6** |

So accuracy and false-alarm rate are confirmed, sensitivity is not — 3/3
at n=3 wasn't a statement to begin with. And on this set the alarm is
**not demonstrably informative**: it catches 33 % of real contradictions
against 9 % of harmless ones, which at these numbers means nothing
(Fisher's exact, one-sided, p = 0.14). Of eight alarms, two were real — a
base rate of 9 % lifted to 25 %, but without statistical backing.

The cause is visible in the table: the model says FORTSCHRITT in **50 of
70** cases, across all three intended classes. It has a preferred class,
the way the NLI model before it had a preference for "neutral" — just a
different one. That's exactly what the finding that spoke against the
NLI model comes down to.

**What follows from this:** the question mark in every output is not a
courtesy, it's the entire claim. The tool says where to look closer, not
what the actual case is — and a missing note says nothing. Before any
expansion, `--vergleich` is worth running: whether a different prompt
breaks the preferred-class bias can now be checked in one run instead of
guessed at.

#### Two Defects, Found 2026-09-15 During Retesting

**The verdict depended on the order of the supplied ids.** Five pairs
asked in both directions, only **2 of 5** symmetric — and it flipped
between WIDERSPRUCH and FORTSCHRITT, the two verdicts with opposite
consequences:

| Pair | forward | backward |
|---|---|---|
| #1421 ↔ #1425 | WIDERSPRUCH | FORTSCHRITT |
| #1426 ↔ #1427 | WIDERSPRUCH | FORTSCHRITT |
| #1420 ↔ #1421 | UNABHAENGIG | WIDERSPRUCH |
| #1387 ↔ #1393 | WIDERSPRUCH | WIDERSPRUCH |
| #1409 ↔ #1411 | FORTSCHRITT | FORTSCHRITT |

For WIDERSPRUCH and UNABHAENGIG that's simply wrong, both relations are
symmetric; only FORTSCHRITT has a direction, and it's carried by `ts`, not by
call order. Fixed by asking both directions and only accepting what says
the same thing twice. A fixed order (older id first) would have been the
cheaper fix, but would only have made the verdict reproducible, not more
correct.

**Notes identical in wording were reported as WIDERSPRUCH.** `_kurz`
truncates to `MAXZ` and prefers the bold title line — two entries with the
same title line thus collapse into each other. #1416/#1418 ended up
byte-identical afterward and got WIDERSPRUCH. Counter-test with four
texts against themselves: **1 of 4** contradicted itself. A logically
impossible verdict, hence a hard upper bound on reliability — and it hit
exactly the advertised use case, since `verdichten` by construction
delivers near-identical entries. Fixed with
`faktencheck.deckungsgleich(a, b)`: such pairs no longer go to the device
and instead get the note that there's nothing to assess here.

After the rework, the two former false alarms report `uneinig` (disputed),
the real contradiction #1387/#1393 remains WIDERSPRUCH in both
directions — the false alarms disappear without costing the true hit.

**Still open:** the A-against-A self-test belongs in `pruefstand_fc.py`.
Every entry against itself — anything other than FORTSCHRITT/UNABHAENGIG is
an error there with no room for judgment — gold that doesn't need
labeling.

**It fails without taking anything down with it.** That's the actual
requirement, not accuracy — a memory that stops writing whenever the
hobby hardware is off the network would be a bad trade. Three safeguards:

| | |
|---|---|
| **encapsulated import** | if `faktencheck.py` is missing or breaks, the server still runs |
| **pre-check** on `/v1/models`, 3 s deadline | measured 17 ms with the device running |
| **cooldown** after a failure | a dead device costs the deadline once, not on every `remember` |

Plus a time budget of 25 s across all pairs of one `remember` call —
better to have two of three pairs assessed than a call that hangs for
half a minute. Measured: dead IP 3.0 s on the first attempt, then 0.0 s;
connection refused, wrong model, powered off, and module missing all cost
0.0 s. In all cases the duplicate hint is unchanged from before.

**The cooldown isn't uniform**, it depends on the type of failure —
decided in `_sperrdauer`, not by the measured duration, because duration
doesn't work as a signal: a dead IP answered after 72 ms in one attempt
("no route to host"), and only after the full 3 s deadline in the next.

| Error | Python exception | measured | cooldown |
|---|---|---|---|
| service not running (port closed) | `ConnectionRefusedError` | 2–3 ms | **15 s** |
| dead IP, timeout, DNS | bare `OSError` etc. | 72 ms – 3 s | 300 s |
| wrong model loaded | none, HTTP 200 | 20 ms | 300 s |

The 15 s isn't a round number, it's the board's measured startup time:
between `systemctl start` and the first LISTEN on port 8000, 11–18 s
pass, because `axllm` loads the model first and only then binds. A board
that's just rebooting therefore costs 15 s without notes instead of 5
minutes — and the repeated startup attempt costs nothing, because the
refused connection attempt is practically free at 2–3 ms.

Most important side note: **a `None` means "no note", never "no
contradiction".** Reading the absence of a note as an all-clear
misunderstands the tool — and you'd notice at the next network outage.

Settings via the environment:

| Variable | Default | |
|---|---|---|
| `MEMORY_FC_URL` | **unset — the whole module stays off** | base address of an OpenAI-compatible endpoint, with or without a trailing `/v1`. A wrong address does not announce itself; the fact check simply stays silent as it does on any failure |
| `MEMORY_FC_MODELL` | **unset — the whole module stays off** | the model id to ask for. Both this and the URL are required; either one missing means the module never starts |
| `MEMORY_FC_SCHLUESSEL` | empty | sent as `Authorization: Bearer …` for providers that need it. Never appears in any output, not even in error messages |
| `MEMORY_FC_AUS` | empty | set to `1` to turn the fact check off without dropping the address |
| `MEMORY_FC_PROBE` | `3.0` | seconds for the `/v1/models` pre-check. **`0` skips it entirely** — useful where the endpoint lists hundreds of ids, or one that isn't the one you ask with, in which case the model check would lock out a perfectly healthy provider. It also saves one request per call; the pre-check exists for a device that is often gone, not for a datacenter |
| `MEMORY_FC_ZEICHEN` | `200` | note text per side; 200 is the measured sweet spot |
| `MEMORY_FC_BUDGET` | `25` | seconds across all pairs of one call |
| `MEMORY_FC_SPERRE` | `300` | seconds of cooldown after an expensive failure |
| `MEMORY_FC_SPERRE_KURZ` | `15` | seconds of cooldown when only the service is missing |

**What was measured and discarded:** including the entries' dates in the
prompt, plus the rule "same day and incompatible statement means
contradiction". Sounds compelling — the distinction
contradiction/progress *is* a matter of time — and it also solves the
constructed case. But across the whole set the result drops from 9/15 to
**5/15** and the false alarms rise from 1/12 to **7/12**: the extra
sentence pulls the model toward WIDERSPRUCH across the board. The
instruction in `faktencheck.py` therefore stands exactly as worded when it
was measured. Whoever rephrases it invalidates the numbers.

All of this can be re-measured with `pruefstand_fc.py` — see
[Re-measuring the Fact Check](#re-measuring-the-fact-check).

**Known limitation:** truncation happens at 200 characters, preferring
the bold title line. If two entries share the same title line and only
differ further down in the numbers, the model doesn't see the difference
at all and says "Fortschritt?". The number comparison on the same line then
still shows it — the two detectors cover for each other here.

### `vergessen(ids, grund="")`

Marks entries as outdated. **Nothing is ever deleted** — they only
disappear from the default view and remain findable with
`mit_veraltet=True`, along with a note of why and what replaced them.

### `recall(query, limit=8, art="", marke="", voll=False, mit_veraltet=False)`

Full-text search, best match first. The default is a **preview**:

```
#376 [schnittstelle] 2026-09-02 **Fusions-Katalysator** (`item.fusions_kata…  (raumschiff-project)
```

That is: id, kind, date, title line, tag. Get the full text of the
interesting ones afterward with `zeige("376,481")`, or set `voll=True`
right away if the question is narrow enough.

The title is **not** the first line of text: entries are hard-wrapped at
~75 characters, so a line ends mid-sentence. A bold heading at the start
takes priority; otherwise the cut happens at a word boundary.

If the title line starts mid-sentence **or with a role instead of a
subject** (`**Werkzeuge:**`/tools, `**How to apply:**`, `Enthaelt:
…`/contains), the preview appends a note —
`[Stueck 2 von 4, zerschnittenes Memo #872-#875]` ("piece 2 of 4, a memo
cut apart"), and from piece 2 onward it includes the head's subject line
too, since that's not in the piece itself. In that case the entry is a
fragment from the file import, the context does **not** live in it, and
the whole chain needs reading (`zeige("872,873,874,875")`). Why these
exist: [What the Import Broke](#what-the-import-broke).

`art="fallstrick,entscheidung"` restricts to kinds of knowledge,
`art="alle"` also lifts the chronicle's exclusion.

`marke="raumschiff-project"` restricts to one project — the usual case,
because a session almost always belongs to one project. Multiple tags are
OR-combined. **Sub-tags are included:** the tag is searched as a phrase
and the tokenizer splits on hyphens, so `marke="leuchtturm"` also matches
`leuchtturm-project`; conversely `marke="mcp-memory-server"` does not
match `mcp-memory`, because the phrase needs all three tokens in
sequence. `themen()` lists which tags exist.

The filter sits **in the MATCH query, not in the WHERE clause**. A
positive row filter alongside `ORDER BY rank LIMIT n` costs twenty times
as much on this dataset (see below); the existing filters are therefore
all negative (`NOT IN`), and for the tag that escape hatch doesn't exist.
Measured, it costs 4.3 → 10.3 ms this way, i.e. a factor of 2.4 instead of
20.

The search runs in **stages**, from exact to permissive:

1. **The word sequence** — all terms as a phrase, i.e. adjacent and in
   this order. Its hits are placed ahead of the next stage's, but don't
   crowd them out.
2. **All terms** — FTS5 implicitly joins multiple words with `AND`.
3. **Any term** (`OR`) — only if stage 2 found nothing. Also catches
   invalid FTS5 syntax, which is why you're allowed to type whole
   questions.
4. **Stem and word part** — fills whatever slots are still open.

Stage 1 exists because `AND` across separate tokens only lets BM25 score
frequency, not adjacency. With `recall("Deck 5")`, the entry with exactly
that sequence ended up at rank 7, behind entries that mention "Deck"
often and a 5 somewhere; the cap from stage 4 then pushed it entirely out
of the eight-result window. As a phrase, it's rank 1. Costs one extra FTS
query, measured at 1.1 ms per `recall`.

Stage 4 doesn't *replace* anything. Exact hits keep priority but are
capped at about 60 % of the slots, so morphology gets a chance to show up
at all; whatever's capped moves further back, nothing is lost. The
output notes which stage contributed.

Whoever writes FTS5 syntax themselves (`"`, `*`, `()`, `AND`/`OR`/`NOT`)
gets exactly that and no extension. The hyphen deliberately does **not**
count as syntax — it shows up constantly in German questions.

On `limit`: 8 is measured. Below that, morphology blending crowds out
exact hits; above it, mostly the returned payload grows.

### `themen(marke="", limit=40)`

Counterpart to `recall`: that searches for words, this **browses**.

```
themen()                      -> which projects exist, how big, how distributed
themen("mcp-memory-server")   -> this project's title lines, grouped by kind
```

**What's this for, when there's already a search:** `recall` only finds
what you already know to ask for. Whoever picks a project back up after
months doesn't remember the terms anymore — and needs a list first, from
which to pull up the entry. The sequence is then
`themen("project")` → `zeige("id")` or `recall(query, marke="project")`.

The board without an argument also shows, incidentally, where the kind
backlog sits. As of 2026-09-15 it's almost entirely in the legacy data
(raumschiff 278, lehrling-rpg 90, atlas-kern 46); the projects since
09-11 are fully classified. So the backlog isn't growing, it's just
sitting there.

A typo in the tag gets a suggestion instead of an empty list — substring
**and** similarity, because one catches the sub-tag (`leuchtturm` →
`leuchtturm-project`) and the other catches the typo (`leuchttur`), and
neither catches the other's case.

Unlike `recall`, the **chronicle is not hidden here**: when browsing it's
the scaffolding, not the filler that drowns out every search.

### `zeige(ids)`

Counterpart to the preview: `zeige("376,481")` returns exactly those
entries in full text. Outdated ones explicitly included — whoever asks
for the id means that one too. This output also carries the chain note:
it names the neighboring ids, and that's exactly when you want them —
when you're already looking at the full text.

### `einordnen(ids, art)`

Sets the kind of knowledge for existing entries and reports how many are
still without a kind. Meant for doing in passing: whatever `recall`
surfaces anyway gets its kind assigned along the way.
`einordnen(ids, "gemischt")` undoes the classification.

## How Inflection and Compounds Work

`morphologie.py`, no third-party library and no dictionary:

- **`stem`** — rule-based stemmer (Snowball German, condensed). Strips the
  participle `ge-` prefix and the usual endings. `gesperrt` and `sperrte`
  both fall to `sperrt`. The result doesn't have to be a real word, it
  only has to collide.
- **`zerlege`** (split) — splits long words against the dataset's own
  vocabulary, accounting for linking sounds. `Fusionskatalysator` ->
  `fusion` + `katalysator`. **What's already stored is the dictionary.**
- **`kandidaten`** (candidates) — says which substrings `zerlege` could
  even look up for a given text. This lets the dictionary be fetched
  selectively instead of read whole; the cost scales with the entry, not
  the dataset.

Since 2026-09-15 the dictionary lives in its own table `vokabel` (before
that it was read from `fts5vocab` on every write). Two reasons: there it
cost 18.5 ms per `remember` and grew with the dataset — and the words sat
in the FTS5 tokenizer's rendering, i.e. **without umlauts**, while
`zerlege` looks things up with umlauts. 634 German words were unreachable
because of this: `bildschirmflaeche` (with "ae" as an umlaut spelling)
didn't split, because `flaeche` was only in the dictionary without
diacritics.

Both get written into two extra FTS5 columns (`stems`, `teile`) on save
and mirrored during search.

**Cold start:** splitting needs a filled memory. In a fresh database, the
word-part search finds nothing, because the individual pieces don't occur
anywhere yet. This improves as the dataset grows and needs no index
rebuild.

## Importing an Existing File-Based Memory

```bash
.venv/bin/python import_memos.py [folder] [--trocken] [--mit-index]
```

Reads a folder full of `*.md` files paragraph by paragraph, tag = file
name, timestamp from the `modified` frontmatter (otherwise file time).
Callable repeatedly: paragraphs already present are skipped. Paragraphs
over 1200 characters are split at preferred break points (paragraph >
line > sentence > semicolon > comma).

`--mit-index` additionally ingests `MEMORY.md`, line by line instead of
paragraph by paragraph, and pulls the tag from the line's reference.
This is a **one-time** step before trimming the index — some facts only
live there and in no memo file. Don't use it afterward.

### What the Import Broke

The separator cascade above has a bug that only became visible once data
existed: when it matches `". "`, it regularly hits **no** sentence
boundary in German. `z.B. ` (e.g.), `inkl. ` (incl.), and especially
ordinal numbers (`10. Aussenkarte`, `5. `) look character-for-character
like a sentence end. In English that would be an edge case; in German
it's the normal case. Documented in the raumschiff block: #983 ends with
`… Namensschema <name>_<stufe>_<major>-<minor> (z.B` and #984 starts with
`raumschiff_alpha_0-2.apk), gilt fuer den Rest des Projekts**`.

**The damage isn't a bug, it's an overlooked hit.** The preview shows the
title line, and for a piece like this it's a sentence fragment without a
subject: the entry is there but looks useless and gets passed over — the
same failure pattern as a word the index splits differently than the
search does.

The fix is the `kette` table (schema version 4). `_ketten_nachtragen()`
finds the cuts and records `(id, kopf, nr)`; `recall` and `zeige` append
a note built from it:

```
#984 [verlauf] 2026-09-10 raumschiff_alpha_0-2.apk), gilt fuer den Rest…  [Stueck 2 von 3, zerschnittenes Memo #983-#985]
```

**The cut is checked at both ends at once:** the predecessor breaks off
without punctuation **and** the successor starts lowercase, both carry
the same first tag, and their rowids are at most 3 apart.

**Since 2026-09-16 there's a second path to the same conclusion**, because
the first one found too little: the import cut at `". "`, and that mostly
hits exactly the paragraph boundary **before** a bold line.
`**Werkzeuge:**` (tools) starts cleanly capitalized, so the predecessor
ends properly, and it's still a fragment — the line names a **role** in
the text, not a topic. Such links therefore bind without the break-off
check. The line to distinguish it from is the subject line:
`**Harte Leitplanken:**` (hard guardrails) names a topic and doesn't
bind. Only this way do the chains stay short — a 240-entry-long project
file would otherwise become a 240-long chain, and the note would say
"read 240 entries", which would be worse than no note at all.

Measured on 2026-09-15: 122 links in 54 chains, no false binding. After
the follow-up on 2026-09-16: **254 links in 108 chains**, longest 6,
average 2.4 — and all 75 entries that start with a role instead of a
subject now carry a note (previously 0 of them did). The one-sided
rule — only the break-off — would find 47 additional pairs, almost all of
them wrong: an entry ending in ``lua5.1`.**`` looks unfinished, but isn't.
Leading formatting conversely does **not** count for the successor,
otherwise `` `applyItemsSync` lautlos verschwanden`` would slip through as
a fragment. The tag is the second safeguard: without it, the last note of
one project would stick to the first note of the next.

This is a **one-time** repair of the legacy data, not ongoing maintenance
— `import_memos.py` never runs again, no new fragments are created.
Anyone who ever builds a text splitter again: check the character before
`". "` before treating it as a sentence end (digit or known abbreviation =
not a sentence end).

## Database

`memory.db` next to the script. Since **schema version 5** (2026-09-15),
`eintrag` is an **ordinary table** and `suche` is just an index over it:

```sql
CREATE TABLE eintrag (
  id      INTEGER PRIMARY KEY,
  content TEXT NOT NULL,  tags TEXT NOT NULL DEFAULT '',  ts TEXT NOT NULL,
  stems   TEXT NOT NULL DEFAULT '',  teile TEXT NOT NULL DEFAULT '',
  art     TEXT NOT NULL DEFAULT 'gemischt' REFERENCES art_vokabular(art),
  art_am  TEXT,
  kopf    INTEGER REFERENCES eintrag(id),  nr INTEGER)

CREATE VIRTUAL TABLE suche USING fts5(content, tags, stems, teile,
                                      content='eintrag', content_rowid='id')
-- three triggers keep `suche` in sync with `eintrag`

CREATE TABLE veraltet      (vermerk INTEGER PRIMARY KEY AUTOINCREMENT,
                            id INTEGER NOT NULL, durch INTEGER, am TEXT, grund TEXT)
CREATE TABLE art_vokabular (art TEXT PRIMARY KEY)
CREATE TABLE marken        (marke TEXT PRIMARY KEY, seit TEXT)
CREATE TABLE vokabel       (wort TEXT PRIMARY KEY) WITHOUT ROWID
CREATE TABLE schema        (schluessel TEXT PRIMARY KEY, wert TEXT)
```

### Why It Was Different Through Schema Version 4 — and What the Rebuild Brought

Through schema version 4, `mem` **was** the FTS5 table and, at the same
time, the source of truth: a search index doubling as storage. That
inevitably meant every new property became a side table (`art`, `kette`)
— FTS5 can't add a column after the fact — that no foreign key applied,
that every column was indexed and `ts` had to be forced in via
`UNINDEXED`, and that a filter on `art` stayed affordable only through an
EXISTS trick.

**Measured for the rebuild** (1332 entries, a copy of the real dataset,
median after warm-up, schema 4 vs. schema 5 on the same 40 real
questions):

| | schema 4 | schema 5 |
|---|---:|---:|
| `recall(query)` | 2.38 ms | **1.71 ms** |
| `recall(marke=…)` | 2.72 ms | **1.72 ms** |
| `recall(art=…)` | 2.29 ms | **1.78 ms** |
| `themen()` | 6.46 ms | **5.23 ms** |
| `remember()` | 12.0 ms | **10.3 ms** |
| `zeige()`, `verdichten()` | | same |
| file size | 3.71 MB | 3.65 MB |
| the migration itself | | 128 ms, one-time |

**The proof isn't the timing, it's the equality check:** the same 200 real
questions before and after the move, **200 line-for-line identical hit
lists**, 0 deviations.

**What the rebuild did NOT bring**, for the sake of an honest balance
sheet: the file is the same size as before (−1.6 %), the **number of
tables stayed the same** (`art` and `kette` became columns, but `suche`
and `art_vokabular` were added), and the source code shrank by a net 52
lines only. Whoever justifies the rebuild with space or code volume is
justifying it wrongly.

### Five Things That Are Different Than They First Appear

**`ts` is not in the index.** The date is there for display, never a
search term. As an ordinary FTS5 column, the tokenizer split it into bare
numbers, and `MATCH '2026'` thereby matched **every** one of 1284
entries, `'09'` still matched 1001. Through schema version 4, `UNINDEXED`
was the countermeasure — an agreement within a table that indexes
everything by default. Since schema version 5 it's structural: `ts` is a
column of `eintrag`, and `suche` doesn't know it exists.

**`veraltet` is append-only, not overwriting — and rightly stays a table
of its own.** One row per event, not per entry. If the same entry is
superseded twice, that's two notes; with `INSERT OR REPLACE` the second
would have erased the first's origin — in a table whose entire purpose is
preserving history. This is the one case where keeping it as a separate
table wasn't a stopgap: a log is not a property of the entry.

**The vocabulary of kinds lives as rows, not as a `CHECK`.** A `CHECK`
freezes its vocabulary: `CREATE TABLE IF NOT EXISTS` treats an outdated
table as complete, so a newly added kind would pass the check in Python
and then fail against the database — with a raw traceback and lost text.
In `art_vokabular`, a new kind is an `INSERT`, and the foreign key on
`eintrag.art` still catches every typo. `PRAGMA foreign_keys` applies
**per connection** and gets set on every open — without this line, the
foreign key sits in the schema and does nothing.

**`stems` and `teile` are derived — the index can no longer drift, the
columns can.** The three triggers keep `suche` in sync with `eintrag`, so
an `UPDATE` can no longer leave the index behind. What the triggers
**can't** do: recompute the columns themselves, because that needs
Python. After any intervention outside of `remember`, and after any
change to `morphologie.py`, this still applies:

```bash
.venv/bin/python nachziehen.py [--probe]
```

**No write in the connection path.** The server opens the database per
tool call. If anything writes there, **every** call pays an fsync for it:
during the rebuild, first an `INSERT OR IGNORE` into the kind vocabulary,
then an `INSERT OR REPLACE` of the version number, each cost around
5.5 ms — on everything, from `zeige` (0.7 ms) to `themen` (6.5 ms). The
telltale sign is the **constant** overhead across all tools, while
`verdichten`, with its single connection, stays unchanged. Hence: read
first, then write only what's missing.

**`kette` sits beside the text, not inside it** — nowadays as `kopf`/`nr`
directly on `eintrag`, with a foreign key to `eintrag(id)`. The note that
an entry is the fragment of a cut-apart memo could also live in
`content`; it's just that the cutting hurts in the **preview**, and a
hint inside the content would only become visible after the full text —
i.e. after exactly the expensive step the preview is meant to save.
Only `kopf` and `nr` are stored; the total count is computed, since a
carried-along length would be derived data and would drift apart on the
next intervention. Where the chains come from is covered under
[What the Import Broke](#what-the-import-broke).

**The setup carries a version number** (`schema.stand`, currently 5).
Without it, no migration would notice it's due. The move from 4 to 5 runs
by itself on first connect (`_umzug_auf_5`), takes 128 ms, and leaves
behind a file that's roughly twice as big until the next `VACUUM` — the
discarded pages are still in there. **Stages before 4 are gone**: there's
no longer a database that needs them. An older copy gets checked out to
schema version 4 before the rebuild, then continues from there; the
server states this itself, rather than silently touching it.

The connection is opened and closed per tool call — that keeps locks
short. Plus **WAL and a generous `busy_timeout`**: under SQLite's
defaults (`journal_mode=delete`, 5 s), one writer locks the whole file,
readers included, and eventually throws `database is locked`. Measured
5.0 s until the exception before, 0.002 s for the same reader under WAL.
`busy_timeout` applies per connection and is set fresh on every open, WAL
sticks to the file.

### Classifying the Legacy Backlog by Kind (historical note)

An internal one-off script (`migration_art.py`, not included in this
repository — it's tied to this user's specific historical data)
classified only the cases where the kind follows unambiguously from the
tag or the form — 166 of 984 entries, measured. Four rules, in this
order: index lines from the old `MEMORY.md` (34), tags that name the kind
unambiguously (50), kind-words used as free-text tags (13), a date header
at the start (69).

The order was deliberate: without the index-line rule running first, the
tag rule would catch them instead and turn a cross-reference into an
`arbeitsweise` (way-of-working) entry.

The rest deliberately stays `gemischt` (mixed) (714 living entries as of
2026-09-14 — outdated ones don't count as backlog; `einordnen` reports
the number on every call). A heuristic that guesses at this remainder
would be worse than none — it would produce wrong classifications that
nobody would ever double-check again. Instead, `einordnen()` catches up
while reading: whatever `recall` surfaces anyway gets its kind assigned
along the way, whatever never gets searched for rightly never does.
Callable repeatedly; anything already classified stays untouched.

### Correcting Legacy Timestamps (historical note)

An internal one-off script (`migration_zeitstempel.py`, not included in
this repository, for the same reason as above) addressed a problem where
the import had given 722 living entries the **import** date as their
timestamp, not the date of the actual thing — 61 % of the dataset. In the
`recall` preview, this date is shown prominently and misleads: a
retrospective memo from 2026-09-02 carries entries about work from
2026-08-23.

**Nothing was guessed.** A sample of 16 turned up around 6 wrong guesses,
almost all following the pattern "docs *since* 2026-08-19", where the
date is a property of the **subject matter**, not of the entry. So the
migration only picked up the chronicle pattern: exactly one date in the
whole text, in the head of the first line (45 characters), followed by a
dash, parenthesis, comma, or colon, not introduced by "since"/"from". Of
the 722: 104 were already correct, 493 carried no date in the text at
all, 4 had several, 121 had exactly one — and of those 121, only half
matched the pattern. So **70** were corrected; the remaining 548 were
left untouched: a wrongly guessed date would have been worse than a
recognizable placeholder, because it looks authoritative.

The time-of-day stays **`00:00:00`**. The day is known, not the hour — and
this way these entries stay recognizable as "accurate to the day, hour
unknown". So anyone seeing a timestamp with the time at zero doesn't know
two things: never the hour, and for the 548 untouched ones, also not
whether the day is the entry's day or the import's day. So for the legacy
data, never infer the order of events from the timestamp.

The script took a `VACUUM INTO` snapshot beforehand and was callable
repeatedly; afterward `nachziehen.py` needed to run, as after any manual
intervention.

## Re-measuring the Fact Check

The number `pruefe` stands on (9/15) was collected by hand and
reproducible nowhere — hence the warning above that rephrasing the prompt
invalidates it. True, but there was no way to re-collect it.
`pruefstand_fc.py` is that way.

```
.venv/bin/python pruefstand_fc.py --trocken           # just show the set
.venv/bin/python pruefstand_fc.py                     # measure
.venv/bin/python pruefstand_fc.py --vergleich b.txt   # two prompts, paired
```

**The gold labels aren't guessed after the fact, they fall out of normal
operation.** Three sources:

| Source | Label | where from |
|---|---|---|
| `ersetzt` | FORTSCHRITT | every `ersetzt=` relationship in `veraltet(id, durch)` — the user, at the moment of the decision, said the new one supersedes the old one |
| — | *excluded* | the same relationships, but the new text identifies itself as a correction ("correction to", "revised", "refuted"): label unclear, drops out of the gold set and gets reported |
| `gebaut` / `handfund` | both | `pruefpaare_gebaut.json` — by hand; `gebaut` (built) carries the text directly, `handfund` (hand-found) only the ids of a genuine pair. The hand label beats the automatic one |
| `schwer` / `leicht` | *no alarm only* | high word overlap without a supersede relationship, or drawn at random, respectively |

**For the harmless pairs, the gold set holds no exact label, only "must
not trigger an alarm".** That's not laziness: a pair with high word
overlap and no `ersetzt=` relationship *could* be an unnoticed
contradiction — exactly what the tool is supposed to find. Labeling it
UNABHAENGIG in the gold set would charge the model for an error that
might actually be a genuine find. The report explicitly notes this every
time there's an alarm on a "hard" pair.

Two kinds of harmless pairs, because they measure different things: the
*hard* ones cost the false alarms, the *easy* ones show whether anything
gets separated at all — a detector that fires on random pairs was the
finding against the NLI model.

Two filters keep the hard set clean: near-duplicates (over 90 % contained)
are dropped — those belong in `verdichten`, not `pruefe` — and no entry
appears more than twice, otherwise a group of three would ask the same
question three times.

**The set grows with the dataset.** As of 2026-09-14 there are **70 pairs
(46 with an exact label, 64 harmless, 6 genuine contradictions)** against
the 15 by hand — the standard error thereby drops from around 13 to
around 7 points. The draw is seeded, the same dataset gives the same set;
as it grows, numbers stop being comparable to older ones, which is why
every report header states n and dataset size.

**The first run refuted the test rig first, not the model.** The
automation labeled supersede relationships with "correction"/"revised"/
"refuted" in the new text as WIDERSPRUCH — and was wrong in **2 of 3**
cases. These words almost always mark a *hypothesis being superseded by a
measurement*: #1272 explicitly says "not production-ready with the
current quantization config", #1298 changes exactly that config; #1181
lays out two readings and says "segment 6 decides", #1332 reports the
outcome. Both were correct at their time, hence FORTSCHRITT — the model was
right and the gold label wasn't. Only #1169 ("the framing was wrong")
actually retracts a statement as having been wrong all along.

This can't be separated by keyword. The rule therefore no longer labels
automatically, it **pulls the hits out of the gold set and reports
them** — by hand into `pruefpaare_gebaut.json`, if they should be in the
set. Better one pair fewer than one with a wrong label: measuring the
model against wrong gold gives a bad reading and you wouldn't notice. The
three now sit there with a hand label, two of them explicitly as
counter-examples to the heuristic that produced them.

**Reproducible:** both runs from 2026-09-14 gave the same verdict on
every shared pair — `temperature: 0` holds, so a difference between two
runs is a real change, not noise.

**`--vergleich` doesn't report two accuracies, it reports the disputed
pairs** (A right/B wrong vs. B right/A wrong). At this order of magnitude
of n, that's the only comparison worth anything: shared hits and shared
misses cancel out instead of inflating the spread. Under six disputed
pairs, the report states that the variants can't be told apart on this
set.

## Measured

Against 898 real entries (34 memo files, paragraph by paragraph), 14
realistic questions, and 60 each of inflection and compound cases
generated from the dataset. The comparison is `grep -n` on the same
files, strictly judged.

| | `recall` | `grep -n` |
|---|---|---|
| keyword question found | 14/14 | 14/14 |
| of those, at rank 1 | 14/14 | — (unsorted) |
| whole question typed in | 14/14, rank 1 for 9/14 | 0/14 verbatim |
| return median | 4.4 KB | 13.0 KB |
| return max | 5.6 KB | 66.2 KB |
| latency | 0.6–2.0 ms | 3.3 ms |
| inflection | 42/60 | 23/60 |
| compounds | 31/60 | 57/60 |

For an open question ("tell me about project X"), the gap was bigger than
in these individual questions: 2 calls at 8.1 KB against 185 KB for
"find the file and read it whole" — a factor of 23.

### Preview vs. Full Text

14 realistic questions against 984 entries, 5 runs each after warm-up:

| | median | max | total | latency |
|---|---|---|---|---|
| before (full text, everything) | 4,217 B | 8,771 B | 61.6 KB | 1.0 ms |
| after (preview) | 1,250 B | 1,430 B | 16.9 KB | 6.7 ms |
| after (full, without chronicle) | 4,375 B | 8,771 B | 59.9 KB | 6.6 ms |

**The 73 % saving comes entirely from the preview, not from the chronicle
filter.** The filter doesn't make the return smaller — the freed-up slots
fill with the next hit. It changes *what's* in there, not *how much*.
Both were measured separately, because the intuitive expectation ("fewer
entries = smaller return") is wrong.

The `max` value is also notable: the preview is capped at 1,430 B, the
full text isn't. That makes the worst case calculable.

**The 6.7 ms is almost entirely the chronicle probe.** A first draft had
it run the full search cascade with ranking: 29.6 ms, i.e. 21 ms just for
a number in the header. A positive filter (`rowid IN`, only 103 of 984
entries) forces FTS5 to scan far more hits to fill `LIMIT 8`. As a
`count(*)` without `ORDER BY rank`, the same piece of information costs
0.3 ms.

An intermediate finding that nearly triggered a wrong optimization: the
subquery itself was never the problem. Measured on its own, it costs
0.03 ms, with and without an index, as a parameter and as a literal. Only
a measurement *per query inside* `recall` showed that the expensive
queries were the probe's, not the search's.

## What's Deliberately NOT in the Code

**"Is this worth remembering?"** is not scored automatically. Two cheap
signals were measured and discarded: rarity of word stems and identifier
density (paths, function names, numbers). Both separate technically
phrased text from vague text — but not valuable from worthless. Seven of
200 real entries have identifier density 0.00, among them the most
useful: "The obvious fix is wrong: putting the body in a function does
NOT help." A threshold would have flagged exactly that one.

What's left is a question instead of a number: **Would this change a
decision next time?** That belongs in the context file, not in the tool.
The other half of the question — "is this already known?" — is answered
by the duplicate hint in `remember`.

## Limitations

- **`grep` beats it at compounds** (57/60 vs. 31/60). That's not a defect,
  it's the flip side of ranking: substring search only hits that number
  by returning *everything*. A trigram table was built and discarded
  again — it only reaches 60/60 at 200 hits and a 29.6 KB return, is
  worse than the dictionary approach at 10 hits, and triples the index.
- **Language mixing** — not solvable in the tool, but solvable by the
  caller. Term search never finds an English-written memo via a German
  question. That needs meaning instead of word overlap, and FTS5 doesn't
  have that. The rule therefore lives in the context file instead of the
  code: **if the German phrasing turns up nothing, ask the same question
  with English terms — and vice versa.** In both directions, the gap is
  mirror-symmetric.

  This isn't a stopgap for a missing vector store, it's the last stage of
  the search cascade `recall` already runs internally (word sequence →
  exact → OR → stem/word part) — it just sits where a language model that
  can translate already happens to be. Rebuilding it would mean
  replicating, inside the tool, what the caller can already do. The gain
  over embeddings isn't just the saved index: afterward, the history
  shows **which** terms were tried. A vector search only shows that
  something matched, never why — and that removes exactly the
  traceability the rest of the project worked hard to earn.
- **Has to be invoked.** An always-loaded context file sits there
  passively; this tool doesn't. A pointer in the context file ("you reach
  your memory via `recall`") is therefore more effective than any
  improvement to the search itself.
- ~~`remember` loads the split dictionary from the index on every call; at
  ~900 entries that's around 30 ms. Grows with the dataset.~~ **Fixed on
  2026-09-15**: `zerlege` now only asks for substrings of the word being
  split, so only those get fetched (`kandidaten` says which). Measured at
  1315 entries: 18.5 -> 0.04 ms, and flat instead of linear: at
  200/800/3200 entries, 0.46/0.45/0.45 ms, where the old path needed
  0.20/0.72/2.77 ms. `remember` overall: 23.3 -> 3.8 ms.
- **The preview exposes what the full text used to hide:** fragments from
  the paragraph-by-paragraph import ("easily revisable.", "- no server
  component."). As a title line they're obviously worthless; in full
  text they looked substantial. That's not a new bug, just one made
  visible. Cleared out on 2026-09-14: 32 pieces hidden via `vergessen()`,
  of the single-line entries under 150 characters, 40 -> 8 remained. Each
  was checked individually — where it's a heading, the body sits next to
  it as its own entry; where it's a sentence fragment, the head sits with
  the predecessor; so nothing gets lost. A length threshold alone
  couldn't have decided this: the densest entries are also among the
  short ones.
- **The chronicle probe undercounts.** It only counts using the first
  search stage (all terms), not stem and word part. Better to under-report
  than raise a false alarm — whoever wants the exact number uses
  `art="alle"`.

## Files

| | |
|---|---|
| `memory_server.py` | MCP server, eight tools, search cascade, schema, migrations |
| `memory.db.vor-stand5` | snapshot from before the schema rebuild — the way back |
| `nachziehen.py` | recomputes `stems`/`teile` and refreshes the tag directory |
| `faktencheck.py` | opt-in second opinion via any OpenAI-compatible model (off unless configured) |
| `pruefstand_fc.py` | measures the fact check against gold labels from the dataset |
| `pruefpaare_gebaut.json` | the hand-built and hand-found contradiction pairs |
| `morphologie.py` | stemmer and compound splitter |
| `import_memos.py` | import a file-based memory *(retired, see above; still writes to `mem`)* |
| `test_memory.py` | regression net, one case per pitfall (no pytest) |
| `requirements.txt` | just `mcp` |
| `memory.db` | the database (not included in this repository — contents are private) |

`migration_art.py`, `migration_marken.py`, and `migration_zeitstempel.py`
are internal one-off scripts tied to this user's specific historical
data; they already ran against this dataset and are not included in this
repository.

`messung/` keeps the four measurement **reports** — the scripts that
produced them and their raw data are not included, because they only run
against the author's own dataset and the raw data is a verbatim
transcript of real working sessions.

## License

MIT — see [LICENSE](LICENSE).

The numbers throughout this README were measured on one person's real
dataset of roughly 1,300 entries. They are honest about that: where a
measurement didn't hold up on a larger set, it says so. Treat them as
evidence from one installation, not as benchmarks.
