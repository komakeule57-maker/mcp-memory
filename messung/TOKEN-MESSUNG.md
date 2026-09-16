# Real tokens: mcp-memory vs. .md files

Measured on 2026-09-16. Closes the gap that [ERGEBNIS.md](ERGEBNIS.md) had to
leave open: there, the metric was **characters**, because two token
calibrations had failed and the token column was computed on the assumption
"3 characters per token". **That assumption was wrong.**

## The measurement method: the session measures itself

This machine has no tokenizer and no API key — but the transcript of the
running session logs `cache_creation_input_tokens` with every request, and
the sum adds up **without gaps**:

    cache_read(n+1) = cache_read(n) + cache_creation(n)

for every measured round without exception. `cache_creation(n+1)` is thus
exactly the number of tokens that entered the context between two requests:
the model's own reply (`output_tokens`, known) plus the tool result plus a
fixed frame. So:

    Token(tool result) = cache_creation(n+1) - output_tokens(n) - frame

**The frame is measured, not estimated.** Two empty rounds (`Bash: true`,
result "(Bash completed with no output)") both gave **exactly 39** — the
value is reproducible and includes the ~8 tokens of this sentence. That makes
the calculation for all other rounds off by at most 8 tokens in the strict
direction, which doesn't matter for results ranging from 500 to 10,000
tokens.

Condition for validity: **exactly one tool call per round**, otherwise the
delta can't be attributed. The measurement rounds were run accordingly.

These are **real tokens from the production Claude model**, no conversion
and no third-party tokenizer.

## The finding that corrects the old measurement

| Text type | Characters/token (measured) |
|---|---:|
| `.md` files, German technical prose (3 files, 3–21 KB) | **1.90 – 2.09** |
| `recall` preview (3 calls) | **1.83 – 1.91** |
| `zeige` full text (3 calls) | **1.95 – 2.07** |

**Not 3.0 but 2.0.** All token figures in ERGEBNIS.md are **50 % too low**
— on both sides equally. The reason is the language: German technical prose
with compounds, umlauts, and code blocks breaks into noticeably more tokens
than English prose, for which the rule of thumb of 3–4 holds.

For the *ratio* A:B the assumption was almost inconsequential, but not
entirely: `recall` has the densest text type in the field at 1.87, the `.md`
files the thinnest at 2.00. In real tokens the server therefore comes out
roughly **7 % worse** than the character measurement showed — below the
pre-set 10 % tie threshold and thus without consequence for the decision.

## Three real questions, both paths, run live

The questions come from `aufrufe.json` (harvested `recall` calls from real
sessions), not from imagination. Path B is `grep -Eril` over the 38 frozen
`.md` files, then reading the best file in full — what an agent without a
tool does. Path A is `recall` → `zeige`. Both paths take **2 rounds**.

| Question | | search | read | **total** |
|---|---|---:|---:|---:|
| "LÖVE Headless Testing Xvfb" | B `.md` (3 KB) | 563 | 1,480 | **2,043** |
| | A Server | 836 | 1,285 | **2,121** |
| "Custom-Git-Host Deploy Workflow Konfiguration" | B `.md` (17 KB) | 727 | 9,202 | **9,929** |
| | A Server | 662 | 744 | **1,406** |
| "DEEP HULL Waffen Chips Ruestung Roster" | B `.md` (21 KB) | 257 | 10,749 | **11,006** |
| | A Server | 909 | 1,410 | **2,319** |
| **Total** | **B** | 1,547 | 21,431 | **22,978** |
| | **A** | 2,407 | 3,439 | **5,846** |

Question 1 is, with a 3.8 % gap, a **tie** under the pre-set 10 % rule, not
a win for the `.md` path — the gap is smaller than the effect of a single
`zeige` id (see below).

**Factor 3.9 across the three questions, median 4.8.** This matches
yesterday's character measurement (3.3–7.6) and is now backed by real
tokens.

## The three things the measurement actually shows

**1. `grep` is cheap, reading is expensive.** The search costs 250 to 900
tokens on both paths — nothing. The entire difference arises during
reading: 21,431 vs. 3,439 tokens. Whoever defends the server against
`grep` is defending it at the wrong spot; the real opponent is `cat`.

**2. For small files it's a tie — and question 1 carries no verdict at
all.** 2,043 vs. 2,121 is a 3.8 % difference; the pre-set rule states "a
difference under 10 % counts as none", so this is a tie, not a win for the
`.md` path.

**The gap is also smaller than the protocol parameter that produces it.**
Of the 1,285 reading tokens on A's side, **642 come from a single entry**,
#1379 (230 / 886 / 1,283 characters for #190 / #191 / #1379). With
`zeige("190,191")` instead of `zeige("190,191,1379")`, A would have landed
at around 1,476 and **won** the question by a factor of 1.4. How many ids
`zeige` fetches is a free choice of the person measuring — at a gap of 78
tokens, that choice decides the outcome, not the data model. Question 1
therefore only shows that both paths land in the **same order of
magnitude** for small files. The token counts themselves don't fluctuate
though: tokenization is deterministic, the same string always yields the
same number.

The reason it gets close at all at 3 KB remains valid: the file is called
`love-headless-visual-testing.md`, the file name already answers the
question, and `grep` returns 14 hits, among which the right one jumps out.
That's exactly what one file per fact is built for. The server's advantage
grows only with file size, because `Read` doesn't read partially: at 21 KB,
a single file carries 10,749 tokens into context, of which three
paragraphs are actually needed. Only questions 2 and 3 are far enough apart
that the choice of ids can no longer flip the sign.

**3. What the server delivers differently in return.** For question 1,
`recall` surfaced the pitfall **#1379 from 2026-09-14** (xdotool
`mousedown --window` doesn't fire under Xvfb) — which appears in **no**
`.md` file, because the archive was frozen on 2026-09-10. Conversely, for
question 3 the server's ranking was mediocre: ranks 1 and 3 belonged to a
different project. Both are known and already quantified in ERGEBNIS.md
(38 % rephrasing rate).

## What the archive as a whole weighs

38 `.md` files, 529,958 characters → **roughly 265,000 real tokens** when
an agent reads through them. Individual chunks within it:

| File | Characters | Tokens |
|---|---:|---:|
| `raumschiff-project.md` | 188,303 | **94,152** |
| `lehrling-rpg-project.md` | 75,520 | 37,760 |
| `atlas-kern-found.md` | 50,515 | 25,258 |
| `MEMORY.md` (maintained index) | 5,513 | 2,756 |

A single question about Raumschiff costs **94,152 tokens** via the `.md`
path, once `grep` points at the project file — nearly half of a 200k
context window for one question. That's the real reason the factor runs
away with project size: not the data model, but the indivisibility of the
file.

## Applying this to the 117-question measurement

With the measured factors (A: 1.92 mixed; B: 2.00), the characters from
ERGEBNIS.md convert to real tokens:

| | Characters (yesterday) | **Tokens (measured)** |
|---|---:|---:|
| A: `recall` → `zeige`, per question | 4,152 | **2,163** |
| A: per *answered* question (with rephrasings) | 5,060 | **2,635** |
| B1: one file per fact, `grep` + `Read` | 17,428 | **8,714** |
| B2: the real 38-file archive | 286,049 | **143,025** |
| B: full index `MEMORY.md` with 1171 lines (fixed cost) | 208,641 | **104,321** |

Not transferable is the line "A: eight tool definitions, 7,313 characters":
that's JSON schema, not German prose, and the factor of 2.0 doesn't apply
to it. This figure stays open rather than being invented with a borrowed
factor.

## Limits of this measurement

- **Three questions, not 117.** Each measurement question costs four rounds
  and permanently carries the full `.md` content into the measurement
  context; more isn't feasible in one session without blowing the context
  window. The three factors (tie / 7.1 / 4.8) are therefore **evidence for
  the order of magnitude** of the 117-question measurement, not a
  replacement for it.
- **How much A reads is a free choice, not a measured quantity.** The
  number of `zeige` ids is set by the person measuring; in question 1, one
  fewer id would have flipped the sign. A result only carries weight where
  the gap is bigger than one entry — for questions 2 and 3 it is, by a wide
  margin. A difference under 10 % counts as none under the measurement
  criterion anyway.
- **The character/token factors are solid**, varying across nine
  measurement points only between 1.83 and 2.09.
- **The 39-token frame** applies to this harness and this model version;
  needs recalibrating for a different tool-result presentation.
- What's measured is the **read path**. This measurement says nothing about
  the write path.
