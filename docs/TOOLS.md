# Tools

Reference for all eight MCP tools. The fact check behind `pruefe` has its
own page: [FACTCHECK.md](FACTCHECK.md).

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

