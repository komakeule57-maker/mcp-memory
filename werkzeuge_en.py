"""English tool surface for MEMORY_LANG=en.

Thin wrappers: English tool and parameter names, English descriptions, the
work is done by the German functions in memory_server.py. Messages come out
in English because memory_server._t() follows the same switch. Kinds are
mapped at the border (pitfall <-> fallstrick); the database is unchanged.

Registered by memory_server._englisch_einrichten() instead of the German tools - a
session sees one set, never both.
"""

import memory_server as ms


def remember(text: str, tags: str = "", kind: str = "", supersedes: str = "") -> str:
    """Stores a text permanently in memory.

    Reports back which existing entries resemble the new one - so
    contradictions get noticed instead of silently sitting side by side.

    Args:
        text: The content to remember.
        tags: Optional keywords, separated by spaces or commas. Convention:
            the project, i.e. WHERE the knowledge belongs.
        kind: WHICH KIND of knowledge - exactly one of: interface (signature,
            file name, command, data format), pitfall (the obvious approach is
            wrong because ...), decision (made this way, with rationale),
            measurement (a number plus its measurement criterion), workflow
            (how to work with this user), history (chronicle - excluded from
            recall's default view).
        supersedes: Ids of outdated entries that this one replaces (e.g.
            "12,34"). They are not deleted, only removed from the default view.
    """
    return ms.remember(text, tags=tags, art=kind, ersetzt=supersedes)


def recall(
    query: str,
    limit: int = 8,
    kind: str = "",
    tag: str = "",
    full: bool = False,
    include_superseded: bool = False,
) -> str:
    """Searches memory via full-text search, best matches first.

    Also finds inflected forms ("configured" -> "configuring", "studies" ->
    "study").

    By default returns a PREVIEW per hit (id, kind, date, title line). Get
    the full text of the interesting ones afterwards with show("376,481") -
    or set full=True right away if the question is narrow enough.

    Args:
        query: Search term(s), FTS5 syntax allowed (e.g. "sqlite AND fts5", "proj*").
        limit: Maximum number of hits (default 8).
        kind: Restrict to kinds of knowledge, e.g. "pitfall,decision".
            Possible: interface, pitfall, decision, measurement, workflow,
            history, unsorted, all. Default: everything except history -
            otherwise the chronicle drowns out every search for a detail.
        tag: Restrict to a project, e.g. "spaceship". Several tags separated
            by comma or space are OR-combined. Sub-tags are included:
            "lighthouse" also matches "lighthouse-project", but
            "mcp-memory-server" does not match "mcp-memory". topics() lists
            which tags exist.
        full: Full text instead of preview (default: no).
        include_superseded: Also show superseded entries (default: no).
    """
    return ms.recall(query, limit=limit, art=kind, marke=tag, voll=full,
                     mit_veraltet=include_superseded)


def show(ids: str, full: bool = False) -> str:
    """Returns the named entries in full text.

    Counterpart to recall's preview: first see which entry is meant, then
    read only that one. Superseded entries are included - whoever asks for
    the id means that one.

    One call returns about 6000 characters, in the order asked. Whatever
    doesn't fit comes back as a title line plus the call that fetches it.

    Args:
        ids: One or more entry ids, e.g. "376,481". Most wanted first.
        full: Everything asked for at once, without the cap (default: no).
    """
    return ms.zeige(ids, voll=full)


def topics(tag: str = "", limit: int = 0, page: int = 1, all: bool = False) -> str:
    """Shows which projects exist - or the title index of one project.

    Counterpart to recall: that searches for words, this browses. Without an
    argument, the tag board (which project, how many entries, split by kind);
    with an argument, that project's title lines, newest first, one page at
    a time. Follow up with recall(query, tag="...") or straight to show("...").

    Args:
        tag: Project, e.g. "spaceship". Empty = tag board.
        limit: Rows per page (default 40 for the board, 30 for the title index).
        page: Page of the title index (default 1 = the newest).
        all: Whole title index at once, grouped by kind.
    """
    return ms.themen(marke=tag, limit=limit, seite=page, alle=all)


def consolidate(tag: str = "", kind: str = "all", threshold: float = 0.5,
                groups: int = 5) -> str:
    """Finds groups of entries that say largely the same thing.

    Does not summarize anything itself - that is a judgment call. The tool
    delivers the groups; the caller writes a new entry and supersedes the old
    ones via remember(..., supersedes="...").

    Args:
        tag: Only consider entries from this project (empty = all). Sub-tags
            are included, as in recall.
        kind: Only consider entries of this kind/these kinds. Default "all".
        threshold: Similarity above which two entries count as the same.
        groups: Maximum number of groups reported.
    """
    return ms.verdichten(marke=tag, art=kind, schwelle=threshold, gruppen=groups)


def check(ids: str) -> str:
    """Has a small language model judge how the named entries relate.

    Counterpart to consolidate: that one finds groups by word overlap, this
    one says whether a CONTRADICTION is behind it, PROGRESS (a newer state),
    or nothing (INDEPENDENT). Not authoritative: measured 67 % correct on 70
    German pairs; the result says where to look, not what is true. Each pair
    is asked in both directions; disagreement is reported as "disputed". At
    most 5 pairs per call.

    Opt-in: needs MEMORY_FC_URL and MEMORY_FC_MODELL (any OpenAI-compatible
    endpoint; MEMORY_FC_SCHLUESSEL if it wants a key). Without them this tool
    does nothing. When set up, up to 200 characters of each note are sent there.

    Args:
        ids: Two or more entry ids, e.g. "249,255".
    """
    return ms.pruefe(ids)


def forget(ids: str, reason: str = "") -> str:
    """Marks entries as superseded, without a replacement.

    They disappear from recall's default view but remain findable with
    include_superseded=True. Nothing is deleted.

    Args:
        ids: One or more entry ids, e.g. "12,34".
        reason: Why - shown later next to the superseded entry.
    """
    return ms.vergessen(ids, grund=reason)


def classify(ids: str, kind: str) -> str:
    """Sets the kind of knowledge for existing entries.

    Meant for doing in passing: whatever recall surfaces anyway gets its kind
    on the way. The backlog does not have to be sorted in one sitting.

    Args:
        ids: One or more entry ids, e.g. "376,481".
        kind: Exactly one of: interface, pitfall, decision, measurement,
            workflow, history. "unsorted" undoes the classification.
    """
    return ms.einordnen(ids, art=kind)


WERKZEUGE = (remember, recall, show, topics, consolidate, check, forget, classify)
