"""
The links inside a description or a note, and the way out to a browser

Three things that have to be kept together: what dooit *underlines*, what it
*draws*, and what it *opens* are read off the same scan, so a key pressed on
something drawn as a link can never come back saying there was no link there -
and a link drawn short can never point somewhere other than the address that
is written behind it.
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


@dataclass(frozen=True)
class Folded:
    """
    One line as the page shows it, and everything needed to get back

    `text` is what is drawn and `links` are the links in it, at the columns
    they are drawn at. `opens[c]` is the column of the stored line that drawn
    column `c` begins at, and `closes[c]` the column just past where drawn
    column `c - 1` ends; the two differ only over a link that is drawn as
    something not written anywhere. `written` is each link's span in the
    stored line, with a flag for whether what is drawn for it was made up
    rather than copied out.
    """

    text: str
    links: Tuple[Link, ...]
    opens: Tuple[int, ...]
    closes: Tuple[int, ...]
    written: Tuple[Tuple[int, int, bool], ...]


@lru_cache(maxsize=512)
def _fold(text: str) -> Folded:
    """
    One line folded: what is drawn, the links in it, and the two column maps

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

    The two maps say, for every column of the drawn line and one past its end,
    which column of the stored line it stands at. They differ only over an
    atom: a range *opening* inside one takes it from the front and a range
    *closing* inside one takes it to the back, which is what makes an edit
    reaching into a link swallow the whole link instead of cutting an address
    in half.
    """

    drawn: List[str] = []
    found: List[Link] = []
    spans: List[Tuple[int, int, bool]] = []
    opens: List[int] = []
    closes: List[int] = [0]
    at = 0
    width = 0

    def verbatim(start: int, end: int) -> None:
        """A run of the line that is drawn exactly as it is written"""

        nonlocal width

        drawn.append(text[start:end])

        for index in range(start, end):
            opens.append(index)
            closes.append(index + 1)

        width += end - start

    for link in find_links(text):
        verbatim(at, link.start)

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
                opens.append(link.start)
                closes.append(link.end)

            found.append(Link(width, width + len(atom), link.url, link.title))
            spans.append((link.start, link.end, atom != written))
            width += len(atom)

        at = link.end

    verbatim(at, len(text))

    # One past the end of the drawn line is one past the end of the stored one
    opens.append(len(text))

    return Folded(
        "".join(drawn), tuple(found), tuple(opens), tuple(closes), tuple(spans)
    )


def fold_links(text: str) -> Tuple[str, List[Link]]:
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

    folded = _fold(text)

    return folded.text, list(folded.links)


def folded_link_at(text: str, column: int) -> Optional[Link]:
    """
    The link standing at `column` of the drawn line, `text` being the line as
    it is stored

    What the `o` key reads: the cursor is somewhere on the page, and what it
    is standing on is whatever is drawn there - a name as readily as an
    address.
    """

    for link in _fold(text).links:
        if link.start <= column < link.end:
            return link

    return None


def stored_range(text: str, start: int, end: int) -> Tuple[int, int]:
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

    folded = _fold(text)
    last = len(folded.opens) - 1
    start = max(0, min(start, last))
    end = max(start, min(end, last))

    if start == end:
        # Nothing picked out: one place, and it has to come back as one column
        # twice over rather than as the two the maps would give it. Standing at
        # the end of a name counts as standing in it, so that a name being
        # typed goes on being typed rather than spilling out past the address
        for link, (_, _, atom) in zip(folded.links, folded.written):
            if not atom and start == link.end:
                return folded.closes[start], folded.closes[start]

        return folded.opens[start], folded.opens[start]

    opening = folded.opens[start]
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

    return opening, closing


def drawn_column(text: str, column: int) -> int:
    """
    A column of the stored line, as a column of the line as it is drawn

    The way back, for saying where an edit left the cursor. A column inside
    the markup that folding takes off the page comes back as the first column
    past what that markup was hidden behind.
    """

    opens = _fold(text).opens

    return min(bisect_left(opens, column), len(opens) - 1)


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
    is no reason for dooit to know two lists of doors when the desktop has one
    """

    if hand_over(url):
        return True

    # Last resort, and only where there is a screen to open a window on:
    # `webbrowser` falls back to console browsers - lynx, w3m - which it runs
    # in the *foreground*, and that would take the terminal out from under
    # dooit and hang it there. With a display it hands off to a GUI browser
    # in the background instead, which is the only case worth trying
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False

    import webbrowser

    try:
        return webbrowser.open(url)
    except Exception:
        return False
