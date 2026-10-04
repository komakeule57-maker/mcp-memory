# Measurements

What was measured, against what, and where it did not hold up.

The four underlying reports live in [`../messung/`](../messung/) and are
written in German:

| | |
|---|---|
| [MESSKRITERIUM.md](../messung/MESSKRITERIUM.md) | the criterion, fixed in writing **before** the measurement — so the result could not be argued into shape afterwards |
| [ERGEBNIS.md](../messung/ERGEBNIS.md) | server vs. a folder of markdown files: cost per answered question |
| [TOKEN-MESSUNG.md](../messung/TOKEN-MESSUNG.md) | the same comparison in real tokens, after the "3 characters per token" assumption turned out to be wrong |
| [SCHEMA-BEFUND.md](../messung/SCHEMA-BEFUND.md) | what using an FTS5 index as the store actually cost, and what the rebuild did and did not fix |

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


### The Feedback Loop

Test bench: **164 questions with a known answer**, drawn from 1,013 real
tool calls across 30 sessions. 117 of them worked on the first try in
production (the answer is whatever `zeige` fetched right after); 47 did not
and were rephrased (the answer is what the chain ended up fetching, so it
does not come from the search itself and cannot be circular).

The replay is **time-ordered** — sessions by their first timestamp, calls by
line number — and a pair is stored only *after* the question it comes from
has been scored. A pair can therefore only ever help a later question.

Four mechanisms, the 2×2 of what is stored against how it is looked up,
plus the baseline:

| Arm | Hit rate | Expected chars | Fired | Misfired | Gained | Lost |
|---|---|---|---|---|---|---|
| A: today | 73 % | 3,218 | – | – | – | – |
| B1 narrow / exact | 77 % | 2,895 | 21 | 0 | 8 | 0 |
| B2 narrow / fuzzy | 77 % | 2,934 | 40 | 8 | 8 | 1 |
| B3 broad / fuzzy | 82 % | 2,565 | 100 | 19 | 21 | 5 |
| **B4 broad / exact** | **84 %** | **2,450** | 68 | **0** | 19 | **0** |

"Expected chars" is first-round output plus the probability of failing times
6,592 characters — the measured median cost of a rescue chain. It matters
because 55 % of the total cost of a search sits in the failures, not in the
payload.

Re-run against the **built** server rather than the simulation, replaying
the same stream end to end: 84 %, −23 %, 19 gained, 0 lost — the build
reproduces the bench.

**Poisoning.** With artificially wrong pairs injected at rate p, B4 survives
p = 10 % (−23 %, one loss), is barely ahead at 25 % and behind the baseline
at 50 %. The fuzzy arm breaks at 25 % already. The *real* poison arm — the
five chains the harvester rejects as changes of subject, fed in anyway —
moves nothing on any arm, but with 5 pairs out of 169 it is far too small to
show damage. That is reported as an underpowered measurement, not as an
acquittal of the relevance guard.

**What this cannot show:** whether the loop helps questions that were never
asked. The bench only knows the 265 real queries, and inventing questions is
ruled out — they would be invented by the same system that is being
measured.

### One Slot per Chain

258 entries are pieces of memos the import cut apart (110 chains). When
several pieces of one chain ranked among the eight hits, they said the
same thing and took slots other entries needed. Since 2026-09-25 the
best-ranked piece stays, the rest are folded in, and the cascade fetches
up to twice `limit` candidates to refill the freed slots.

Criterion, fixed beforehand: this is a bug fix, not a ranking lever, so
the measurement had to rule out harm, not justify a gain — anything under
10 % counts as unchanged. 260 real questions with a gold answer, a fresh
copy of the live dataset, `marke=` set, feedback loop off, `limit=8`; the
comparison arm is the same source with the fix disabled at two lines.

| | before | after |
|---|---|---|
| questions with slots taken by sibling pieces | 8.5 % | 0.0 % |
| gold at rank 1 | 39.6 % | 39.6 % |
| gold among the 8 | 81.2 % | 80.0 % |
| characters | — | +0.2 % |
| latency (median of 5 alternating runs) | 1.88 ms | 2.01 ms (+6.8 %) |

No number went up, and that is not an objection — a bug fix does not need
a gain. The −1.4 % among the 8 are an artifact of the measure: in all
three lost questions the gold was a *second* piece of a chain whose first
piece was listed. Counting "gold or a sibling of its chain", it is 81.2 %
either way. A single run's latency swung between +5 and +16 %, hence the
median.

### The Cascade Against Plain OR

Measured 2026-10-04, prompted by a comparison with another memory tool whose
bare FTS5 search, once its queries were rewritten to `OR`, came out level
with this one. The question: do the stages in front of `OR` — word
sequence and all-terms — earn their place?

Criterion, fixed beforehand: under 10 % relative difference is a tie, per
row. Same 260 real questions with a gold answer as above, a fresh copy of
the live dataset (1,903 entries), feedback loop off, `limit=8`. One copy of
the real `memory_server.py` with one switch inside `_kaskade_roh`; index,
tokenizer, filter, tag clause and chain folding are identical in every arm.

| | with `marke=` R@1 | R@8 | without `marke=` R@1 | R@8 |
|---|---|---|---|---|
| cascade as shipped | 35.8 % | 80.8 % | 24.6 % | 66.9 % |
| without stem / word part | 35.8 % | 76.2 % | 24.6 % | 61.5 % |
| `OR` only, ranked by BM25 | 35.4 % | 80.8 % | 27.7 % | 72.3 % |

With `marke=` set — the usual case — plain `OR` is a tie on both measures,
and the two arms differ in one question each way. Without it, `OR` is ahead:
+12.5 % at rank 1, which is over the threshold, +8.0 % among the eight,
which is not; 15 questions only `OR` finds, one only the cascade. The
all-terms stage fills slots with entries that happen to contain every word.

Stem and word part look like they carry 12 to 14 questions (the second row,
one-sided: none are found only without them). But `OR` plus that stage gives
exactly the numbers of `OR` alone — `OR` fills the eight slots itself, and
morphology only ever fills free ones. What it contributes in the shipped
cascade is what all-terms left empty.

A rebuild was then measured as real source against real source: word
sequence first, then `OR`, the all-terms stage removed.

| | R@1 | R@8 |
|---|---|---|
| 260 questions, with `marke=` | 35.8 → 36.2 % | 80.8 → 81.2 % |
| 260 questions, without | 24.6 → 25.0 % | 67.3 → 70.0 % |
| 81 reformulation chains, with `marke=` | 32.1 → 32.1 % | 66.7 → 66.7 % |
| 81 reformulation chains, without | 9.9 → 9.9 % | 54.3 → 56.8 % |

Every row is a tie. The lead of plain `OR` at rank 1 is gone, because the
word sequence that goes first pushes the best `OR` hit down; removing that
precedence would bring back the "Deck 5" failure it was built for. The
rebuild was not adopted: one stage less code is not a result. (The baseline
without `marke=` reads 67.3 here and 66.9 above — the copy was drawn again
with one more entry in it.)

**What this does not show:** that morphology is dispensable. The gold comes
from the cascade's own operation — what was fetched is what it had shown —
so questions in an inflected form that never hit are not on the bench. And
R@8 does not see the case the word-sequence stage exists for. The scripts
are, like the others, not part of this repository.

### Tool Definitions Are Not Always a Fixed Cost

The fixed-cost figures in `messung/` count the tool definitions as paid in
every session before the first question. On 2026-10-04 a fresh Claude Code
session reported 635 tokens for the tools of **all** connected MCP servers
together (190 tools, marked "loaded on-demand"), and 1.4k after `recall`,
`themen` and `zeige` had been used: the client lists names and fetches a
definition when the tool is first needed. The eight definitions, 9,019
characters, are then a cost per tool used, not per session.

In that session the five calls returned 40,569 characters, 26,815 of them
one `themen` title index of a project with 351 entries. A shortened set of
definitions (4,998 characters, every caller-facing rule kept) would have
saved 1,534 characters there, under 4 % of what the results cost. It was
measured and not adopted. Whether a client loads up front or on demand is
the client's choice, so the per-session figures remain right for those that
load everything; the token counts above are the client's own estimate.

### Capping `themen` and `zeige`

2026-10-04, against 1,907 live entries, read-only. The occasion was the
session above: "everything about project P01" (351 entries) returned a
title index of 26,506 characters and then sixteen full texts. `recall`
had been capped at eight previews for weeks; these two returned whatever
was asked for.

Criterion, fixed beforehand: characters returned by the real tool
functions; under 10 % difference is a tie. The one free parameter is
*which* sixteen entries `zeige` fetches — so not one selection but 200
random draws with a fixed seed, plus the sixteen newest.

| call | before | after | |
|---|---|---|---|
| `themen("P01")` | 26,506 | 4,599 | −83 % |
| `zeige`, 16 ids, random, median (range) | 24,595 (17,391–33,617) | 8,106 (5,025–9,083) | −67 % |
| `zeige`, the 16 newest | 18,865 | 8,521 | −55 % |

**Those percentages are the caps themselves, not a finding** — 30 titles
instead of up to 280, 6,000 characters instead of 24,000. The counter-test
is the caller who fetches the rest anyway: all sixteen full texts then cost
30,580 characters over five calls instead of 24,595 in one (+24 %). The
cap only pays if title lines are enough to choose from. So the real
question is whether an answer still arrives in the *first* call.

**Does it?** Gold entries drawn at random per project (22 projects, fixed
seed), one question each, then the usual path with the real functions:
`recall(question, marke=project)` → `zeige(all eight hits in rank order)`
— the worst case for the cap. "Answered" means the gold entry is in the
full-text part of the first `zeige`; the comparison is the same call with
`voll=True`.

| | run 1: keyword questions | run 2: project-work questions |
|---|---|---|
| questions (gold outside the chronicle) | 158 | 110 |
| words per question | 3.2 | 7.6 |
| question words found verbatim in the gold's title line | 60 % | 4 % |
| found by `recall` | 153 (97 %) | 106 (96 %) |
| gold at rank 1 | 135 | 96 |
| in the first `zeige`, uncapped | 153 | 106 |
| in the first `zeige`, capped | 150 | 106 |
| lost to the cap | 3 (ranks 5, 7, 8) | 0 |
| `zeige` over 8 hits, characters | 6,843 → 4,897 (−28 %) | 8,274 → 5,461 (−34 %) |
| `zeige` over the best 3, characters | 3,001 → 2,948 (−2 %) | 3,307 → 3,216 (−3 %) |

Run 1 was too easy — its questions were close to the title lines — and
was repeated as run 2 with questions written from the point of view of
someone who has the problem, not the solution. The result did not move.
The cap is harmless on this path because `recall` puts the entry among
the first three hits almost every time and the first block holds a median
of four full texts.

Replaying the 411 real `zeige` calls from 151 earlier sessions against
today's dataset says the same from the other side: 332 (81 %) pass
uncapped — the median call asks for three ids — and the total shrinks by
16 %.

**What the cap on `themen` costs.** Whether the gold's title line is in
the output at all, old code (from the previous commit, loaded as a second
module) against page 1 of the new:

| projects | gold | old: in the index | old: characters | page 1: in the index | page 1: characters |
|---|---|---|---|---|---|
| the 12 largest (44–351 entries) | 60 | 57 | 10,211 | 18 | 3,999 (−61 %) |
| the 10 smallest (8–31 entries) | 50 | 50 | 1,730 | 50 | 1,952 (+13 %) |

Page 1 is sorted by date and the gold was drawn uniformly over age, so in
a large project it is rarely there. That is not a defect to tune away but
a change of purpose: page 1 answers "what happened lately", and older
knowledge is reached through `recall`. The 13 % that small projects now
cost *more* — each line carries its kind — is a known regression, left
open.

Limits: questions were written by a language model that had seen the
entry; run 2's are longer than real ones (median of 591 real `recall`
queries: 5 words), and more words give a term search more to hold on to.
Five to eight questions per project carry no comparison between projects.
The values 30 and 6,000 are set, not measured. The scripts, questions and
gold sets are not part of this repository.

### A Project Tag Hides Everything Outside It

Same day, same setup. The question was whether the tool is a project
memory or a general one. First the dataset: 1,664 of 1,907 live entries
carry one of the 22 tags of a project with a folder, 113 belong to other
projects, 130 (7 %) are general — the machine, tools, hosting, ways of
working. That last sorting was done by hand over tag prefixes.

Then one dial: the same questions with and without `marke=`. And a third
set, 40 gold entries drawn from the general 130, questions paraphrased as
strictly as in run 2.

| | project, with `marke=` | same questions, without | general knowledge, without |
|---|---|---|---|
| questions | 110 | 110 | 40 |
| found | 106 (96 %) | 103 (94 %) | 37 (92 %) |
| gold at rank 1 | 96 (87 %) | 93 (85 %) | 34 (85 %) |

All three are a tie. **The search does not treat general entries worse
than project entries.** The filter does matter for short questions: with
the 3.2-word questions of run 1, 97 % are found with `marke=` and 85 %
without — twelve points, above the threshold.

The weak point is elsewhere. A session working in a project asks with
that project's tag, and the tag is joined with `AND` to every stage of
the cascade. The 40 general questions, asked once under each of the 22
project tags:

| | without `marke=` | under a project tag |
|---|---|---|
| gold found | 37 of 40 (92 %) | **0 of 880** |
| empty answer — `recall` itself suggests dropping the tag | — | 107 (12 %) |
| project hits, marked as `OR` fallback | — | 729 (83 %) |
| project hits, no mark at all | — | 44 (5 %) |

Zero is by construction, not a sampling result. What the measurement adds
is the second half: in 88 % of the cases the session gets a full list
that looks like an answer.

Three ways of saying so were compared with one switch in the real code.
The hint should appear when the answer lies outside the tag (880 cases)
and stay away when it lies inside (the project questions, asked under
their own tag):

| trigger | appears when it should | names the gold itself | false alarm, long questions (110) | false alarm, short questions (158) |
|---|---|---|---|---|
| plain text on every `OR` fallback | 729 (83 %) | 0 | 102 (93 %) | 52 (33 %) |
| on `OR` fallback, only if the best hit *without* the tag lies outside; that hit is named | 726 (82 %) | 614 (70 %) | 8 (7 %) | 25 (16 %) |
| the same probe on every search with a tag | 770 (88 %) | 653 (74 %) | 9 (8 %) | 30 (19 %) |

The first was the obvious fix and had already been agreed on. It
discriminates nothing: long questions fall back to `OR` almost always, so
the hint appeared on project questions *more* often than where it
belonged. The second is what was built. Together with the empty answers
it covers 833 of the 880 (95 %), and in 70 % the named line already is
the entry sought — a `zeige` instead of a second `recall`. It costs one
more query on that path (14 → 23 ms) and 18 % more characters there; a
project question under its own tag is unchanged (+1 %). The third buys
six points for a second query in every tagged search and was left out.

Limits: the 880 cases are 40 questions times 22 tags, not 880 independent
questions. With shorter real questions the share of unmarked project hits
— the 5 % no trigger reaches — is probably larger. A false alarm here is
one line pointing at another project's entry, not a wrong answer. And how
often a project session actually asks for general knowledge was not
measured at all.

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
- **A project tag hides everything outside it.** `marke=` is a hard
  filter, so a session working in a project does not see general
  knowledge unless it asks without the tag. `recall` now points at the
  better match outside in most such cases, but not in all (95 % of those
  measured), and the caller still has to follow the pointer. The tool is
  project-bound in how it is used, not in what the search can find.
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

