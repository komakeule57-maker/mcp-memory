# Tools

Reference for all eight MCP tools. The fact check behind `pruefe` has its
own page: [FACTCHECK.md](FACTCHECK.md).

## Across `recall`, `frage` and `zeige`: the feedback loop

These three tools share one piece of state. When a search is followed by a
`zeige`, the server stores the pair — the **wording that was searched for**
and the **entry that was then fetched**. Ask the same thing again and those
entries come first, and the header says so: `(+ schon einmal so gesucht)`.

Four things about it are deliberate, and each one was measured before it was
built (`messung/RUECKKOPPLUNG.md`):

- **It fires on word-for-word repeats only.** The key is the sorted set of
  search terms, so word order and case don't matter, but a *similar*
  question inherits nothing. Fuzzy lookup was measured and was worse: it
  pushes sibling questions out of rank 1 while gaining nothing.
- **It records every search→fetch pair**, not just the ones where the search
  visibly failed. That is where the gain comes from — such pairs work
  *against* the decay that comes with a growing dataset, because they grow
  with it.
- **A pair needs a shared content word.** If the fetched entry contains no
  word of at least four letters from the question, it was a change of
  subject, not an answer, and nothing is stored. Without this guard the loop
  collects exactly the poison it cannot tolerate.
- **Boosted hits pass the same filters as any other.** A superseded entry,
  or one excluded by `art=` or `marke=`, stays out.

`RUECKKOPPLUNG = False` in `memory_server.py` is the kill switch; it stops
both firing and collecting. Measured tolerance: the loop survives about 10 %
wrong pairs and is worse than no loop at 25 %, so if `nachfrage` is ever
suspected of being polluted, flip the switch and clean the table rather than
blaming the ranking.

A `zeige` with no search before it stores nothing — whoever already knows
the id was not answering a question.

## `remember(text, tags="", art="", ersetzt="")`

Creates an entry with the current timestamp and returns its **id**.
`tags` are free-form keywords and get searched too — convention: the
project. `art` is the kind of knowledge (see [DESIGN.md](DESIGN.md#two-axes-tag-and-kind)). `ersetzt="12,34"`
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

That is exactly where the **opt-in fact check** comes in (see [FACTCHECK.md](FACTCHECK.md)): if
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

## `verdichten(tags="", art="alle", schwelle=0.5, gruppen=5)`

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


## `vergessen(ids, grund="")`

Marks entries as outdated. **Nothing is ever deleted** — they only
disappear from the default view and remain findable with
`mit_veraltet=True`, along with a note of why and what replaced them.

## `recall(query, limit=8, art="", marke="", voll=False, mit_veraltet=False)`

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
exist: [What the Import Broke](IMPORT.md#what-the-import-broke).

**A chain takes one of the eight slots, not several.** If more than one
piece of the same memo matches, only the best-ranked one is listed; the
others are not missing but folded in, and the span in the note is the
complete information. The freed slots are refilled from the next hits
down, so the list stays at `limit` instead of getting shorter. Before
this, 8.5 % of real questions had slots taken by sibling pieces, in one
case four of eight ([MEASUREMENTS.md](MEASUREMENTS.md#one-slot-per-chain)).

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
as much on this dataset (see [MEASUREMENTS.md](MEASUREMENTS.md#preview-vs-full-text)); the existing filters are therefore
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

## `frage(frage, marke="", art="", limit=8)`

The same search as `recall` — same cascade, same filters, the query is
handed over unchanged. What differs is the **shape of the answer**, and
that is the whole tool.

It resolves chain notes on its own. A hit that is one piece of a memo cut
apart during import (`recall`'s "[Stueck 2 von 4]" note) is expanded to
the **whole chain** and returned as one merged citation instead of a
fragment starting mid-sentence — the caller doesn't have to notice the
note and fetch the rest with `zeige`. Two hits from the same chain count
as one citation, not two — the same folding `recall` does, which `frage`
inherits from the shared cascade. (Until 2026-09-25 it had its own,
without refilling, and so regularly returned fewer than `limit` hits.)

**It is not the cheaper path.** Measured over 275 real questions,
counting every round a question needs: `frage` costs **+10 % characters in
total, +18 % in the median**, for 1.93 rounds instead of 2.00 — and no
class of question was found where it wins, not even questions whose answer
sits in a cut-apart chain (1.13×). The full-text head costs 1,312
characters every time and saves a `zeige` of 3,892 only with probability
p, so it pays off from p > 34 %. Use it when **one** entry answers the
question and is likely to be rank 1 — mostly word-for-word repeats, where
the feedback loop lifts it there. Otherwise `recall` + `zeige`.

Pass `marke=` whenever the project is known: without it the full-text
head comes from the **wrong project** in 34 % of cases, and the answer is
in the head in 25.8 % instead of 36.4 %. Keep the project name in the
question too — dropping it because `marke=` already says it costs 15 %.
Two limits: cross-cutting tags (shell pitfalls, ways of working) are hurt
by the restriction, and sibling projects are not separated, because
crossover entries carry both tags.

```
frage("Warum nutzt SnAI lieber LoRA als ein volles Finetune?")
```

returns the top hit in full text — tagged with its id (or id range for a
resolved chain), kind, date and tags, the same shape as `zeige`'s output
— followed by the remaining hits as preview lines.

A German stop word list used to sit in front of the cascade, trimming a
question down to its content words. It was measured twice — against the
117 real questions that carry a gold answer, and against the 47 real
reformulation chains — and moved **zero** cases either time, because real
queries here are keyword chains ("Aethel Core API Key Umgebungsvariable"),
not sentences: `recall` trained its callers that way. It was removed on
2026-09-21 as dead weight. Before putting anything like it back, measure
whether question-shaped queries are actually being asked.

Only the **top hit** comes back in full text; the rest are `recall`'s
preview lines, with the id to fetch them by. That split is measured, not
guessed. Against the 117 real questions that carry a gold answer, all
paths over the same cases, counting **both** costs per question — the
`frage` output, plus the follow-up `zeige` wherever the answer wasn't in
the full-text part already:

| full-text hits | hit rate | characters | rounds |
|---|---|---|---|
| 0 (= the old two-step path) | 91/117 | 603,188 (+1 %) | 234 |
| **1 (as built)** | **91/117** | **549,045 (−8 %)** | **189** |
| 2 | 91/117 | 637,812 (+7 %) | 175 |
| 3 | 91/117 | 719,193 (+21 %) | 165 |
| 8 (everything in full) | 91/117 | 1,177,856 (+98 %) | 143 |

Baseline (`recall(8)` + a targeted `zeige`): 595,962 characters, 234
rounds.

**The hit rate does not depend on this at all** — every hit is shown
either way, just some as a preview. The choice is purely characters
against round trips, and one full-text hit is the only value that beats
the baseline on *both*. Going to two costs 16 % more characters — a real
difference — to save 7 % of round trips, which under
[MESSKRITERIUM.md](../messung/MESSKRITERIUM.md)'s "anything under 10 %
counts as nothing" is not one. Each further full text buys less and costs
more: 6,340 characters per round saved going from 1 to 2, and 25,527
going from 6 to 8. The first one is worth it because the top hit already
*is* the answer in 45 of 117 cases; the second hits far more rarely for
the same price.

The baseline is *flattered*, too: `zeige(gold)` fetches exactly the ids
that answered in production, granting the two-step path perfect
foresight. And when re-measuring, the second round's characters have to
be counted — leaving them out made two full texts look like −31 % instead
of +7 %.

**Corrected on 2026-09-25:** the comparison against the baseline above
does not hold. A re-measurement over 275 questions found the counting
error behind a similar result: a question was booked as answered in one
round as soon as *one* of the entries it needed stood in the full-text
head, even when it needed four. Counted correctly, one full-text hit is
+10 % characters against the two-step path, not −8 % (see above). What
the table still shows is the *shape* — each further full text costs more
than it saves; the shapes were not re-measured against each other.

The hit rate is the same as `recall`'s, because it *is* `recall`'s
search: 91/117 on the questions with a gold answer, 30/47 on the
reformulation chains, identical on both before and after the stop word
list was removed.

**What it deliberately does not do: write an answer.** Synthesizing one
from several citations is a harder job than the single-word judgment
`pruefe` asks of a language model, over a much smaller context window —
and that judgment already needed its own measurement before it could be
trusted (see [MEASUREMENTS.md](MEASUREMENTS.md)). `frage` leaves the
synthesis to whichever model is calling it, the same stance `recall`
already takes for retrying a query in another language: the caller has a
language model, the tool doesn't need one of its own.

## `themen(marke="", limit=40)`

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

## `zeige(ids)`

Counterpart to the preview: `zeige("376,481")` returns exactly those
entries in full text. Outdated ones explicitly included — whoever asks
for the id means that one too. This output also carries the chain note:
it names the neighboring ids, and that's exactly when you want them —
when you're already looking at the full text.

## `einordnen(ids, art)`

Sets the kind of knowledge for existing entries and reports how many are
still without a kind. Meant for doing in passing: whatever `recall`
surfaces anyway gets its kind assigned along the way.
`einordnen(ids, "gemischt")` undoes the classification.

