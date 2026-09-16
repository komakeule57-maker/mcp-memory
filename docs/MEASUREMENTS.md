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

