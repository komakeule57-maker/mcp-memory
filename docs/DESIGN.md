# Design

Why the thing is built the way it is: the two filing axes, the morphology,
the database schema, and what was deliberately left out.

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

(This is the tool's actual output, which stays German — see [A Note on Language](../README.md#a-note-on-language).)

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
[What the Import Broke](IMPORT.md#what-the-import-broke).

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

