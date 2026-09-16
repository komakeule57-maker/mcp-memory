# The Fact Check

Everything about `pruefe` and `faktencheck.py`: what it is for, how to point
it at a model, what it measurably can and cannot do, and how to re-measure it.

## `pruefe(ids)` — opt-in, needs a language model

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
are a fixed vocabulary shared with `faktencheck.py`'s prompt — see
[A Note on Language](../README.md#a-note-on-language) on why they aren't
translated.)

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

### Two Defects, Found 2026-09-15 During Retesting

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

