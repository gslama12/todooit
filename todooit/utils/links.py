"""
The links inside a description or a note, and the way out to a browser

Three things that have to be kept together: what todooit *underlines*, what it
*draws*, and what it *opens* are read off the same scan, so a key pressed on
something drawn as a link can never come back saying there was no link there -
and a link drawn short can never point somewhere other than the address that
is written behind it.

This is also where the note's *folding* lives - the one translation between
the text as it is stored and the text as it is drawn - so the other things a
note writes into a line and does not want drawn are folded here too: the marks
(stars, underscores, `==`) either side of an emphasised phrase, and the `#` a heading opens with.
"""

import os
import re
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

from rich.markup import escape

from todooit.utils.files import hand_over

# A link starts at a scheme - or at the "www." that stands in for one - and
# runs to the first character that cannot be part of it. Whitespace ends a
# URL, and so do the quotes and brackets that only ever get wrapped around one
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.IGNORECASE)

# A link written the way markdown writes one: the name for it in brackets, the
# address in parentheses behind them. This is how a long URL lives in a note
# without the note being all URL - the name is what the page shows, and the
# address is still written out in full right next to it, where a save cannot
# lose it and an editor cannot get it wrong.
#
# An empty name is allowed and means "not named yet": a link pasted in and left
# alone is drawn as a shortened form of its own address. Neither half may hold
# the bracket that closes it, which is markdown's own rule, and is what keeps
# two links written on one line from being read as one
MD_LINK_RE = re.compile(r"\[(?P<title>[^\[\]\n]*)\]\((?P<url>[^()\s]+)\)")

# Punctuation that ends the sentence rather than the URL. A link at the end of
# a line is written with a full stop after it far more often than a link is
# written to a path ending in one, so the trailing run is dropped. The "*" is
# in the list because a note can be holding *a link in italics*
TRAILING = ".,;:!?*)]}"

# What a closing bracket in that list is weighed against: a URL carrying a
# balanced pair - the parenthesised tail of a wiki article, say - keeps it
BRACKETS = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True)
class Link:
    """
    One link, and where in the text it was found

    The offsets are in characters and are into the text handed to the scan,
    which is what a cursor position is measured in too. They cover the whole
    of how the link is written, so a markdown one runs from its opening
    bracket to its closing parenthesis - which is what a cursor has to be
    standing on to be standing on the link, and what has to be replaced to
    rewrite it.

    `title` is the name the link is drawn under, and is "" for a link written
    bare: a bare link is its own name until it grows too long to be one.
    """

    start: int
    end: int
    url: str
    title: str = ""


def _trim(url: str) -> str:
    """
    Drop the punctuation that belongs to the sentence, not to the link
    """

    while url and url[-1] in TRAILING:
        opening = BRACKETS.get(url[-1])

        if opening is not None and url.count(opening) >= url.count(url[-1]):
            break

        url = url[:-1]

    return url


def _with_scheme(url: str) -> str:
    """
    A browser needs the scheme even where a reader does not
    """

    return url if "://" in url else f"https://{url}"


def find_links(text: str) -> List[Link]:
    """
    Every link in `text`, in the order they are written

    Both ways of writing one. The named ones are read first and the ground
    they cover is then off limits to the bare scan, so the address inside a
    `[name](url)` is never handed back a second time as a link of its own -
    which would be a second link sitting exactly where the first one is.
    """

    links = []
    named = []

    for match in MD_LINK_RE.finditer(text):
        url = match.group("url")

        # The parentheses alone do not make something a link: `[see](later)`
        # is a pair of brackets, and only an address in them is an address
        if not URL_RE.fullmatch(url):
            continue

        named.append((match.start(), match.end()))

        # A name of nothing but spaces is no name: it would be drawn as a gap
        # on the page with no way of telling what it went to
        title = match.group("title").strip() or link_title(_with_scheme(url))

        links.append(Link(match.start(), match.end(), _with_scheme(url), title))

    for match in URL_RE.finditer(text):
        if any(start <= match.start() < end for start, end in named):
            continue

        found = _trim(match.group())

        # What the trim can leave behind: a bare scheme with the whole of the
        # address trimmed off it is not something to hand a browser
        if found.lower().rstrip("/") in ("http:", "https:", "www"):
            continue

        links.append(
            Link(match.start(), match.start() + len(found), _with_scheme(found))
        )

    links.sort(key=lambda link: link.start)

    return links


def first_link(text: str) -> Optional[Link]:
    """
    The link a row is opened by: the first one written in it
    """

    links = find_links(text)

    return links[0] if links else None


# How wide a link is allowed to be drawn before it is folded down to a name,
# and how wide the name it is folded to may be.
#
# Wide enough that the half of an address that says which one it is - the site
# and the page - still fits; narrow enough that a link sits inside a quote bar
# in a narrow window without the line having to wrap around it, which is what
# takes a link out of the block it was written in
TITLE_MAX = 45


def link_title(url: str) -> str:
    """
    The name a link with none of its own is drawn under: the site it goes to
    and the page it ends at, with the road between them left out

    What is dropped is what a query string is made of - the session ids, the
    tracking, the re-encoded copy of the path - which is most of the length of
    a long URL and none of what tells one apart from another.
    """

    # The scheme says nothing here: what marks this out as a link on the page
    # is that it is drawn as one, underlined and in the accent color
    rest = url.split("://", 1)[-1]
    rest = rest.split("#", 1)[0].split("?", 1)[0]

    host, _, path = rest.partition("/")
    steps = [step for step in path.split("/") if step]

    if not steps:
        drawn = host
    elif len(steps) == 1:
        drawn = f"{host}/{steps[0]}"
    else:
        drawn = f"{host}/…/{steps[-1]}"

    if len(drawn) > TITLE_MAX:
        drawn = drawn[: TITLE_MAX - 1] + "…"

    return drawn


# An emphasised phrase in a note, by markdown's own rule: a run of one to three
# stars or underscores either side, with something between them and neither
# side touching a space, so that `a * b * c` stays arithmetic and `* item`
# stays a bullet. Stars may sit inside a word; underscores may not, so a
# `snake_case_name` stays as written. How many marks the run has says what the
# phrase is: one italic, two bold, three both. `==` either side highlights a
# phrase (not every markdown reads it); like underscores it can't sit inside a
# word, so `a==b and c==d` stays a comparison.
EMPH_PAIR_RE = re.compile(
    r"(?<!\*)(?P<stars>\*{1,3})(?![\s*])(?P<starred>.+?)(?<![\s*])(?P=stars)(?!\*)"
    r"|(?<![\w])(?P<unders>_{1,3})(?![\s_])(?P<underlined>.+?)(?<![\s_])(?P=unders)(?![\w])"
    r"|(?<![\w=])(?P<equals>==)(?![\s=])(?P<marked>.+?)(?<![\s=])(?P=equals)(?![\w=])"
)

# The groups above holding a pair's opening run of marks, one per kind of mark
EMPH_MARKS = ("stars", "unders", "equals")

# A heading: the marks only, which is what comes off the page. Any level, since
# a note has the one heading style.
HEADING_RE = re.compile(r"#{1,6} ")


def emph_pairs(text: str) -> List[Tuple[int, int, int, int]]:
    """
    Where each emphasised phrase's marks are written, in the line as it is
    *stored*: (opening start, opening end, closing start, closing end). A mark
    inside a link belongs to the link, so the links are masked out first. The
    opening run says what the phrase is (see `EMPH_PAIR_RE`).
    """

    masked = text

    for link in find_links(text):
        # Neither a mark, a space nor a word character, so it neither opens,
        # closes nor blocks a pair beside it
        filler = "\x00" * (link.end - link.start)
        masked = masked[: link.start] + filler + masked[link.end :]

    pairs = []

    for match in EMPH_PAIR_RE.finditer(masked):
        marks = next(name for name in EMPH_MARKS if match.group(name))
        opens, words = match.span(marks)
        pairs.append((opens, words, match.end() - (words - opens), match.end()))

    return pairs


@dataclass(frozen=True)
class Folded:
    """
    One line as the page shows it, and everything needed to get back

    `text` is what is drawn, `links` are the links in it and `emph` the
    emphasised phrases, both at the columns they are drawn at.

    Three column maps, all of them from a drawn column to a stored one, and
    all of them the same map on a line with nothing folded out of it:

    - `at[c]` is where drawn column `c` is *written*: where a run picked out
      on the page starts, and the one map that is also read backwards, to say
      where a stored column landed on the page.
    - `opens[c]` is where something *inserted* at drawn column `c` goes in.
      It sits in front of any markup hidden ahead of that column, which is
      what keeps a newline typed at the head of an emphasised phrase outside
      the pair instead of splitting it.
    - `closes[c]` is the column just past where drawn column `c - 1` ends,
      which is where a run picked out on the page stops.

    `written` is each link's span in the stored line, with a flag for whether
    what is drawn for it was made up rather than copied out.
    """

    text: str
    links: Tuple[Link, ...]
    emph: Tuple[Tuple[int, int], ...]
    at: Tuple[int, ...]
    opens: Tuple[int, ...]
    closes: Tuple[int, ...]
    written: Tuple[Tuple[int, int, bool], ...]


@lru_cache(maxsize=512)
def _fold(text: str, raw: bool = False) -> Folded:
    """
    One line folded: what is drawn, the links in it, and the two column maps

    `raw` is a line the cursor or selection stands on: it is drawn exactly as
    written, so no column of it is made up and an edit has nothing to widen.

    What the folding hides is the *markup* of a link and not its name. A link
    written `[the folder](url)` is drawn as `the folder`, and those words are
    the ones in the note - the same characters, at columns that map straight
    through - so a name can be read, retyped and corrected exactly like any
    other words on the line. Only the bracket in front of it and the address
    behind it are taken off the page.

    A link with no name of its own has nothing on the page that is really
    written anywhere: what is drawn is made up out of its address. That one is
    an atom - a single thing the whole of which is either there or not - and
    so is a bare address too long to be left as it stands.

    The maps say, for every column of the drawn line and one past its end,
    which column of the stored line it stands at. They differ only over an
    atom: a range *opening* inside one takes it from the front and a range
    *closing* inside one takes it to the back, which is what makes an edit
    reaching into a link swallow the whole link instead of cutting an address
    in half.

    The marks of an emphasised phrase are folded out on the same pass and are
    the other kind of hidden markup: not an atom standing in for a run, but
    characters worth no column that belong to the words beside them. An opening
    run goes with the phrase it opens, so what is inserted at the head of one
    lands in front of it; a closing run goes with the phrase behind it, so what
    is inserted at its tail lands past it. A heading's marks are hidden the same
    way as an opening run.
    """

    drawn: List[str] = []
    found: List[Link] = []
    emph: List[Tuple[int, int]] = []
    spans: List[Tuple[int, int, bool]] = []
    written_at: List[int] = []
    opens: List[int] = []
    closes: List[int] = [0]
    at = 0
    width = 0

    pairs = [] if raw else emph_pairs(text)

    # Each hidden column, and whether a run of marks starts or ends the phrase there
    opening = {
        column: column == start
        for start, end, _, _ in pairs
        for column in range(start, end)
    }
    closing = {
        column: column == start
        for _, _, start, end in pairs
        for column in range(start, end)
    }
    started: List[int] = []

    # How many hidden columns are standing in front of the next drawn column.
    # Held back rather than written straight out: an opening run is only known
    # to be in front of a column once that column arrives, and the run at the
    # very end of a line is in front of the position one past it
    hidden = 0

    heading = None if raw else HEADING_RE.match(text)

    if heading:
        at = hidden = heading.end()

    def verbatim(start: int, end: int) -> None:
        """A run of the line that is drawn exactly as it is written"""

        nonlocal width, hidden

        for index in range(start, end):
            if index in opening:
                if opening[index]:
                    started.append(width)

                hidden += 1
                continue

            if index in closing:
                if closing[index]:
                    emph.append((started.pop(), width))

                continue

            drawn.append(text[index])
            written_at.append(index)
            opens.append(index - hidden)
            closes.append(index + 1)

            hidden = 0
            width += 1

    for link in find_links(text):
        verbatim(at, link.start)

        if raw:
            before = width
            verbatim(link.start, link.end)
            found.append(Link(before, width, link.url, link.title))
            at = link.end
            continue

        written = text[link.start : link.end]
        named = MD_LINK_RE.match(text, link.start) if link.title else None
        name = named.group("title") if named else ""

        if named and name.strip():
            # The markup either side comes off and the name itself stays: one
            # hidden run, then the words, then the other hidden run
            verbatim(named.start("title"), named.end("title"))
            found.append(Link(width - len(name), width, link.url, link.title))
            spans.append((link.start, link.end, False))
        else:
            # Made up out of the address, or the address itself: either way no
            # column in it is a column of anything the note actually holds, so
            # the whole of it stands or falls together
            atom = link.title or (
                link_title(link.url) if len(written) > TITLE_MAX else written
            )

            drawn.append(atom)

            for _ in range(len(atom)):
                written_at.append(link.start)
                opens.append(link.start - hidden)
                closes.append(link.end)

            hidden = 0

            found.append(Link(width, width + len(atom), link.url, link.title))
            spans.append((link.start, link.end, atom != written))
            width += len(atom)

        at = link.end

    verbatim(at, len(text))

    # One past the end of the drawn line is one past the end of the stored
    # one - behind any marks left standing there, which is markup the position
    # is in front of like any other
    written_at.append(len(text))
    opens.append(len(text) - hidden)

    return Folded(
        "".join(drawn),
        tuple(found),
        tuple(emph),
        tuple(written_at),
        tuple(opens),
        tuple(closes),
        tuple(spans),
    )


def fold_links(text: str, raw: bool = False) -> Tuple[str, List[Link]]:
    """
    `text` as the note draws it, and where the links landed in what it drew

    A named link is drawn as its name and a long bare one as a name made out
    of its address; a bare link short enough to read is drawn exactly as it
    was written, since folding one would hide an address and save nothing.

    The offsets on the links handed back are into the *drawn* text - which is
    what the underlining is measured against - while the URLs on them are the
    whole of what was written. Nothing here changes `text`: the folding is
    what the page shows, and what is stored goes on being what was typed.
    """

    folded = _fold(text, raw)

    return folded.text, list(folded.links)


def folded_emph(text: str, raw: bool = False) -> List[Tuple[int, int]]:
    """
    Where the emphasised phrases of `text` land on the page: one (start, end)
    per finished pair, in drawn columns, with the marks themselves nowhere in
    it because they are nowhere on the page. None on a raw line, which has its
    marks on the page and is lit from `emph_pairs` instead.
    """

    return list(_fold(text, raw).emph)


def folded_link_at(text: str, column: int, raw: bool = False) -> Optional[Link]:
    """
    The link standing at `column` of the drawn line, `text` being the line as
    it is stored

    What the `o` key reads: the cursor is somewhere on the page, and what it
    is standing on is whatever is drawn there - a name as readily as an
    address.
    """

    for link in _fold(text, raw).links:
        if link.start <= column < link.end:
            return link

    return None


def stored_range(
    text: str, start: int, end: int, raw: bool = False
) -> Tuple[int, int]:
    """
    A run of the drawn line, as the run of the stored line behind it

    Which of two answers a link wants depends on the run and not on either end
    of it on its own, which is why this is asked for a range rather than a
    column at a time. A run picking out exactly the name a link is drawn under
    means the name: retyping it renames the link and leaves the address alone.
    A run reaching past either edge of that name has the whole link in it -
    markup, address and all - because half a link left behind on the line is
    not something that could be written back out as a note.
    """

    folded = _fold(text, raw)
    last = len(folded.opens) - 1
    start = max(0, min(start, last))
    end = max(start, min(end, last))

    if (start, end) == (0, last):
        # The whole of the page a line takes up is the whole of the line,
        # markup hidden at either edge and all: out there is nothing for a run
        # to stop short of, and a rewrite of the line has to land on all of it
        return 0, len(text)

    if start == end:
        # Nothing picked out: one place, and it has to come back as one column
        # twice over rather than as the two the maps would give it. Standing at
        # the end of a name counts as standing in it, so that a name being
        # typed goes on being typed rather than spilling out past the address
        for link, (_, _, atom) in zip(folded.links, folded.written):
            if not atom and start == link.end:
                return folded.closes[start], folded.closes[start]

        return folded.opens[start], folded.opens[start]

    opening = folded.at[start]
    closing = folded.closes[end]

    for link, (written_start, written_end, atom) in zip(
        folded.links, folded.written
    ):
        if end <= link.start or start >= link.end:
            continue

        # Inside the name and nowhere else: the run is the run it looks like
        if not atom and start >= link.start and end <= link.end:
            continue

        opening = min(opening, written_start)
        closing = max(closing, written_end)

    for (phrase_start, phrase_end), pair in zip(folded.emph, emph_pairs(text)):
        if start <= phrase_start and end >= phrase_end:
            opening = min(opening, pair[0])
            closing = max(closing, pair[3])

    return opening, closing


def drawn_column(text: str, column: int, raw: bool = False) -> int:
    """
    A column of the stored line, as a column of the line as it is drawn

    The way back, for saying where an edit left the cursor. A column inside
    the markup that folding takes off the page comes back as the first column
    past what that markup was hidden behind.
    """

    at = _fold(text, raw).at

    return min(bisect_left(at, column), len(at) - 1)


def raw_column(text: str, column: int) -> int:
    """
    A column of the folded line, as the column of the same character once the
    line is raw. What was made up out of an address has no such character, and
    lands at the front of the link.
    """

    folded = _fold(text)
    column = max(0, min(column, len(folded.at) - 1))
    stored = folded.at[column]

    # A short bare address is an atom to an edit, but its characters are real
    for link, (start, end, _) in zip(folded.links, folded.written):
        drawn = folded.text[link.start : link.end]

        if link.start <= column < link.end and text[start:end] == drawn:
            stored = start + column - link.start

    return drawn_column(text, stored, raw=True)


# How much of a URL is said back when one is opened: enough to tell two links
# on the same row apart, short enough to leave the line it is written on
LABEL_MAX = 50


def link_label(url: str) -> str:
    """
    A URL as a one-line message can carry it: shortened, and with its
    brackets escaped so a query string is not read as markup
    """

    if len(url) > LABEL_MAX:
        url = url[: LABEL_MAX - 1] + "…"

    return escape(url)


def open_url(url: str) -> bool:
    """
    Hand `url` to the desktop's browser; False when nothing would take it

    Which program that is, and in what order they are tried, is
    `todooit.utils.files`: one desktop opens both a page and a file, and there
    is no reason for todooit to know two lists of doors when the desktop has one
    """

    if hand_over(url):
        return True

    # Last resort, and only where there is a screen to open a window on:
    # `webbrowser` falls back to console browsers - lynx, w3m - which it runs
    # in the *foreground*, and that would take the terminal out from under
    # todooit and hang it there. With a display it hands off to a GUI browser
    # in the background instead, which is the only case worth trying
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False

    import webbrowser

    try:
        return webbrowser.open(url)
    except Exception:
        return False
