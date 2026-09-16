# Importing a File-Based Memory

The one-off import of an existing folder of `.md` notes, the damage it did,
and the repairs that followed.


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

## What the Import Broke

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


## Classifying the Legacy Backlog by Kind (historical note)

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

## Correcting Legacy Timestamps (historical note)

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

