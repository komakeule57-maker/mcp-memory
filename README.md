# mcp-memory

A persistent memory for AI assistants that is just a SQLite file.

No vector store, no embeddings, no external service, no API key. Python,
SQLite with FTS5, stdio — the only dependency is the official `mcp` SDK.
Nothing leaves your machine unless you explicitly turn on the optional
fact check.

Built for **German-language notes**: the search understands inflection
("Rangliste" finds "Ranglisten") and compound words ("Katalysator" finds
"Fusionskatalysator").

## Why

An assistant's memory usually fails in one of two ways: it is a pile of
markdown files that has to be read whole to be searched, or it is a
vector database that answers *that* something matched but never *why*.

This one is a ranked full-text index over short entries, with two things
bolted on that turn a note pile into a memory: entries are filed on two
axes — **where** it belongs (project) and **what kind** of knowledge it is
(pitfall, decision, measurement, …) — and when you write something down,
the tool tells you which existing entries it overlaps with, so
contradictions surface instead of quietly piling up.

## Features

- **Ranked search with German morphology** — inflection and compound
  splitting, no dictionary file needed; the dataset itself is the
  dictionary.
- **Two filing axes** — a free-text project tag and a closed, enforced
  vocabulary of knowledge kinds. Chronicle entries are hidden from search
  by default, but the header always says how many were held back.
- **Preview instead of full text** — a hit costs about 1.2 KB, not 4.2 KB.
  The worst case is capped and therefore calculable.
- **Duplicate and contradiction hints** — `remember` reports similar
  existing entries and which numbers changed, so you can supersede
  instead of accumulate.
- **Nothing is ever deleted** — superseded entries drop out of the default
  view and stay findable, with a note on why and by what.
- **Browsing, not just searching** — `themen()` lists projects and a
  project's newest title lines for when you have forgotten the words to
  search for. Capped like everything else: one page, and a line saying how
  to get the rest.
- **Project-bound in use, not in search** — the usual question is asked
  inside one project, with `marke=`. That filter is hard, so when the best
  match lies outside the project, `recall` names it instead of leaving you
  with a plausible-looking list of the wrong entries.
- **Opt-in second opinion** — optionally ask any OpenAI-compatible model
  whether two entries contradict each other or just supersede one another.
- **It learns from its own failures** — when a search is followed by
  fetching an entry, that pair is remembered. Ask the same thing again and
  the entry that answered last time comes first. Word-for-word repeats
  only, and the header says when it fired.

## Requirements

- Python 3.11+
- The `mcp` SDK (`requirements.txt`, that's the whole list)
- SQLite with FTS5 — included in standard CPython builds
- Optional, for the fact check only: any OpenAI-compatible endpoint

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

The database is created on first use as `memory.db` next to the script.

**One rule matters more than any setting: one fact per call, not one
document.** `recall` returns whole entries — store a 180 KB file as a
single entry and you get it back as a single hit, having gained nothing.

### Reading another machine's memory

Each machine keeps its own memory, and each numbers its entries from 1. A
session on machine A can read the memory of machine B over SSH — the server
runs on B, next to its file; the database itself never crosses the network:

```
claude mcp add memory-b -s project -- \
    ssh b /path/to/mcp-memory/.venv/bin/python \
          /path/to/mcp-memory/memory_server.py --gast
```

`--gast` (guest) means three things:

- **Read-only.** The file is opened with `mode=ro`, and only `recall`,
  `zeige` and `themen` are offered. The writing tools are gone, and so are
  `verdichten` and `pruefe`: upkeep belongs to the owner, who can act on it. A guest's searches do
  not feed the owner's search feedback either, and a guest never migrates
  the schema.
- **Every id carries the memory's name:** `b#72`, not `#72`. The name is the
  host name in lower case; `MEMORY_NAME` overrides it.
- **A named id is checked, in both modes.** `zeige("b#72")` asked of any
  memory other than `b` is refused instead of quietly returning that
  memory's own #72. Bare ids (`72`, `#72`) mean the memory being asked.

`-s project` keeps the three extra tool definitions out of sessions that do
not need them. The tools are then called `mcp__memory-b__recall` and so on.

## The Eight Tools

| | |
|---|---|
| `remember(text, tags, art, ersetzt)` | store an entry; reports similar existing ones and what it would supersede |
| `recall(query, limit, art, marke, …)` | ranked full-text search, preview by default; under `marke=` it names a better match outside the project |
| `zeige(ids, voll)` | full text of specific entries, about 6000 characters per call; what doesn't fit is listed with the call that fetches it |
| `themen(marke, limit, seite, alle)` | browse: which projects exist, or one project's title lines, newest first, a page at a time |
| `vergessen(ids, grund)` | mark as outdated — never deletes |
| `einordnen(ids, art)` | assign the knowledge kind of existing entries |
| `verdichten(marke, art, …)` | find groups of entries that say much the same thing |
| `pruefe(ids)` | opt-in: have a language model judge contradiction vs. newer state |

Full reference with parameters and behavior: [docs/TOOLS.md](docs/TOOLS.md).
With `MEMORY_LANG=en` the same tools come with English names and parameters,
see [A Note on Language](#a-note-on-language).

## Some Numbers

Measured on one real dataset of ~1,300 entries — evidence from one
installation, not a benchmark:

- **3.9× cheaper than reading markdown files** for the same three real
  questions (5,846 vs. 22,978 tokens). The gap grows with file size,
  because reading a file is all-or-nothing: one question against a
  188 KB project file costs 94,152 tokens.
- **82.3 % Recall@10** against the public LoCoMo dataset, untuned, first
  run, at 2 ms and 2.7 KB per query.
- **73 % smaller returns** from the preview, with a calculable worst case.
- **−23 % expected characters per question** from the feedback loop, at
  84 % vs. 73 % first-round hit rate, measured over 164 questions from 30
  real sessions in a time-ordered replay — a pair only ever helps *later*
  questions, never itself. 19 questions gained, none lost.
- **53 % → 64 %** hit rate on 47 real reformulation chains from a one-line
  ranking fix — found by measuring where real search sessions had failed,
  not by guessing. On today's dataset the same fix also *costs* 3 of the 117
  questions that already worked, so the net is +2 of 164.

- **93 % of the dataset belongs to a project** (1,777 of 1,907 entries),
  and that is how the tool is used. Search itself does not care: general
  knowledge is found as well as project knowledge (92 % vs. 96 %, a tie
  under the 10 % rule). What the project filter buys is precision for
  short questions — 97 % vs. 85 % found at about three words. What it
  costs is everything outside the project: 40 questions about general
  knowledge, asked under 22 project tags, found **0 of 880**. `recall` now
  names the better match outside the tag in 82 % of those cases, and in
  70 % that line already is the entry sought; on real project questions
  it fires in 7–16 %.
- **−83 % for a project's title index, −34 % for fetching eight full
  texts**, from capping `themen` and `zeige`. On 110 project questions the
  cap cost not one answer.

Where a measurement did not survive a larger sample, it says so:
[docs/MEASUREMENTS.md](docs/MEASUREMENTS.md), and the raw reports in
[`messung/`](messung/). The ranking figure above is the clearest case: it
read **64 % → 77 %** until 2026-09-21. Two things were wrong with it, and
they are wrong in different ways.

The **numbers** were too high because the hit count scanned the output for
any `#id`, which also catches the `[[#1234]]` cross-references *inside*
another hit's title line. That was a counting bug and it was there from the
first run; on the original dataset, counted strictly, the pair is
49 % → 68 %.

The **claim that the fix was free** was true when it was written and is not
true any more. Re-run against the 2026-09-15 snapshot, the fix *gains* 3 of
the 117 questions that already worked; against today's, 29 % more entries
later, it *loses* 3. Net over both sets: +12 of 164 then, +2 of 164 now. More
entries mean more competition for the same eight slots, and this fix spends
part of that budget on morphological variants — so its value shrinks as the
dataset grows. The direction still holds; the margin is thinner than
published, and getting thinner.

## Documentation

| | |
|---|---|
| [docs/TOOLS.md](docs/TOOLS.md) | all eight tools in detail |
| [docs/DESIGN.md](docs/DESIGN.md) | the two axes, the morphology, the database schema, and what was left out on purpose |
| [docs/MEASUREMENTS.md](docs/MEASUREMENTS.md) | what was measured, and the known limitations |
| [docs/FACTCHECK.md](docs/FACTCHECK.md) | the opt-in fact check: setup, what it can and cannot do |
| [docs/IMPORT.md](docs/IMPORT.md) | importing an existing folder of notes, and the damage that did |
| [`messung/`](messung/) | the seven underlying measurement reports (German) |

## A Note on Language

German is the default: tool names, status messages and the kind vocabulary
(`schnittstelle`, `fallstrick`, `entscheidung`, `messwert`, `arbeitsweise`,
`verlauf`, `gemischt`) are German, and the search stems German and splits
German compounds.

**English mode:** start the server with `MEMORY_LANG=en`. Then

- the tools are `remember(text, tags, kind, supersedes)`,
  `recall(query, limit, kind, tag, full, include_superseded)`, `show(ids)`,
  `topics(tag, limit)`, `forget(ids, reason)`, `classify(ids, kind)`,
  `consolidate(tag, kind, threshold, groups)` and `check(ids)`,
- the kinds are `interface`, `pitfall`, `decision`, `measurement`,
  `workflow`, `history`, `unsorted`,
- every message is English,
- the search uses a small English suffix stemmer ("configured" finds
  "configuring") instead of the German one, and does not split compounds.

The database itself does not change: kinds are always stored under their
German names and translated at the border, and German kind names are
accepted in both modes. What does change is the stem index, so the file
records the language it was built in and the server refuses to open it
with the other one. To switch an existing memory, back it up and run
`MEMORY_LANG=en python3 nachziehen.py` once.

Not covered by the switch: the fact-check prompt stays German (it is
calibrated word for word, and adding one sentence once halved its
accuracy; only its verdicts are shown in English), and so do the import
script and the measurement reports. The English stemmer is new and has
**not** been measured on real questions the way the German search has.

## Files

| | |
|---|---|
| `memory_server.py` | MCP server, eight tools, search cascade, schema, migrations |
| `morphologie.py` | stemmer and compound splitter (German; small English stemmer for `MEMORY_LANG=en`) |
| `werkzeuge_en.py` | the English tool surface for `MEMORY_LANG=en` |
| `texte_en.py` | English messages, keyed by the German text |
| `nachziehen.py` | recomputes `stems`/`teile` and refreshes the tag directory |
| `faktencheck.py` | opt-in second opinion via any OpenAI-compatible model (off unless configured) |
| `pruefstand_fc.py` | measures the fact check against gold labels from the dataset |
| `pruefpaare_gebaut.json` | the hand-built and hand-found contradiction pairs |
| `import_memos.py` | import a file-based memory *(one-off; see docs/IMPORT.md)* |
| `test_memory.py` | regression net, one case per pitfall (no pytest) |
| `requirements.txt` | just `mcp` |
| `memory.db` | the database — created on first use, never committed |

`messung/` keeps the seven measurement **reports**. The scripts that
produced them and their raw data are not included: they only run against
the author's own dataset, and the raw data is a verbatim transcript of
real working sessions.

## License

MIT — see [LICENSE](LICENSE).
