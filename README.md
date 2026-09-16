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
- **Browsing, not just searching** — `themen()` lists projects and title
  lines for when you have forgotten the words to search for.
- **Opt-in second opinion** — optionally ask any OpenAI-compatible model
  whether two entries contradict each other or just supersede one another.

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

## The Eight Tools

| | |
|---|---|
| `remember(text, tags, art, ersetzt)` | store an entry; reports similar existing ones and what it would supersede |
| `recall(query, limit, art, marke, …)` | ranked full-text search, preview by default |
| `zeige(ids)` | full text of specific entries |
| `themen(marke, limit)` | browse: which projects exist, or one project's title lines |
| `vergessen(ids, grund)` | mark as outdated — never deletes |
| `einordnen(ids, art)` | assign the knowledge kind of existing entries |
| `verdichten(marke, art, …)` | find groups of entries that say much the same thing |
| `pruefe(ids)` | opt-in: have a language model judge contradiction vs. newer state |

Full reference with parameters and behavior: [docs/TOOLS.md](docs/TOOLS.md).

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
- **64 % → 77 %** hit rate from a one-line ranking fix — found by measuring
  where real search sessions had failed, not by guessing.

Where a measurement did not survive a larger sample, it says so:
[docs/MEASUREMENTS.md](docs/MEASUREMENTS.md), and the raw reports in
[`messung/`](messung/).

## Documentation

| | |
|---|---|
| [docs/TOOLS.md](docs/TOOLS.md) | all eight tools in detail |
| [docs/DESIGN.md](docs/DESIGN.md) | the two axes, the morphology, the database schema, and what was left out on purpose |
| [docs/MEASUREMENTS.md](docs/MEASUREMENTS.md) | what was measured, and the known limitations |
| [docs/FACTCHECK.md](docs/FACTCHECK.md) | the opt-in fact check: setup, what it can and cannot do |
| [docs/IMPORT.md](docs/IMPORT.md) | importing an existing folder of notes, and the damage that did |
| [`messung/`](messung/) | the four underlying measurement reports (German) |

## A Note on Language

This documentation is in English, the tool is not. Every string the server
prints or returns stays German: status messages, the kind vocabulary
(`schnittstelle`, `fallstrick`, `entscheidung`, `messwert`, `arbeitsweise`,
`verlauf`, `gemischt`) and the fact-check verdicts
(`WIDERSPRUCH`/contradiction, `FORTSCHRITT`/progress,
`UNABHAENGIG`/independent, `uneinig`/disputed).

That is not an oversight. Those words are a fixed vocabulary that several
scripts compare against by exact string, and the fact-check prompt is
calibrated word for word — adding one sentence to it once halved the
accuracy. Example blocks in these docs therefore show real, unmodified
output, glossed in English where it first appears.

## Files

| | |
|---|---|
| `memory_server.py` | MCP server, eight tools, search cascade, schema, migrations |
| `morphologie.py` | stemmer and compound splitter |
| `nachziehen.py` | recomputes `stems`/`teile` and refreshes the tag directory |
| `faktencheck.py` | opt-in second opinion via any OpenAI-compatible model (off unless configured) |
| `pruefstand_fc.py` | measures the fact check against gold labels from the dataset |
| `pruefpaare_gebaut.json` | the hand-built and hand-found contradiction pairs |
| `import_memos.py` | import a file-based memory *(one-off; see docs/IMPORT.md)* |
| `test_memory.py` | regression net, one case per pitfall (no pytest) |
| `requirements.txt` | just `mcp` |
| `memory.db` | the database — created on first use, never committed |

`messung/` keeps the four measurement **reports**. The scripts that
produced them and their raw data are not included: they only run against
the author's own dataset, and the raw data is a verbatim transcript of
real working sessions.

## License

MIT — see [LICENSE](LICENSE).
