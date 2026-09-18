"""
The links inside a description or a note
"""

from todooit.utils.links import (
    TITLE_MAX,
    find_links,
    first_link,
    fold_links,
    link_label,
    link_title,
    stored_range,
)

# The kind of address a note is really up against: the site and the page are
# the whole of what says which link this is, and everything between them is
# a re-encoded copy of the path with a session id wrapped around it
SHAREPOINT = (
    "https://atdfsds.sharepoint.com/sites/INP-TREASURY-SAL/Shared%20Documents"
    "/Forms/AllItems.aspx?d=w6b644727c5a24335bfb4a1ddf1c6e2de&csf=1&web=1"
    "&e=9pE4sh&CID=48733ba2%2Dc02d%2D3001%2D47cc%2Df67908799d9d"
)


def test_a_plain_url_is_found():
    (link,) = find_links("see https://example.com for more")

    assert link.url == "https://example.com"
    assert link.start == 4
    assert link.end == 4 + len("https://example.com")


def test_www_stands_in_for_a_scheme():
    (link,) = find_links("go to www.example.com now")

    # A browser needs the scheme even where a reader does not
    assert link.url == "https://www.example.com"


def test_every_link_in_order():
    links = find_links("https://a.com then https://b.com")
    assert [link.url for link in links] == ["https://a.com", "https://b.com"]


def test_no_links():
    assert find_links("nothing to open here") == []
    assert first_link("nothing") is None


def test_sentence_punctuation_is_not_part_of_the_link():
    (link,) = find_links("read https://example.com/page.")
    assert link.url == "https://example.com/page"

    (link,) = find_links("(see https://example.com/page)")
    assert link.url == "https://example.com/page"


def test_balanced_brackets_stay_in_the_link():
    (link,) = find_links("https://en.wikipedia.org/wiki/Dooit_(app)")
    assert link.url == "https://en.wikipedia.org/wiki/Dooit_(app)"


def test_a_bare_scheme_is_not_a_link():
    assert find_links("https:// is how they start") == []
    assert find_links("www. is not an address") == []


def test_first_link():
    link = first_link("https://a.com and https://b.com")
    assert link is not None
    assert link.url == "https://a.com"


def test_link_label_shortens_and_escapes():
    assert link_label("https://a.com") == "https://a.com"

    long_url = "https://example.com/" + "x" * 100
    label = link_label(long_url)
    assert len(label) == 50
    assert label.endswith("…")

    # Markup-like brackets escaped, so a URL is not read as rich markup
    assert r"\[bold]" in link_label("https://a.com/[bold]x")


def test_a_named_link_is_found_whole():
    """A markdown link is one link, from its bracket to its parenthesis"""

    text = f"see [the folder]({SHAREPOINT}) for it"
    (link,) = find_links(text)

    assert link.url == SHAREPOINT
    assert link.title == "the folder"

    # The span covers the whole of how it is written, so the cursor is on the
    # link anywhere in it and replacing it replaces all of it
    assert text[link.start : link.end] == f"[the folder]({SHAREPOINT})"


def test_the_address_inside_a_named_link_is_not_a_second_link():
    (link,) = find_links("[a](https://a.com/x)")

    assert link.title == "a"


def test_brackets_without_an_address_are_not_a_link():
    assert find_links("[see](later) for that") == []


def test_an_unnamed_link_is_named_after_its_address():
    (link,) = find_links(f"[]({SHAREPOINT})")

    assert link.title == link_title(SHAREPOINT)


def test_link_title_keeps_the_site_and_the_page():
    assert link_title(SHAREPOINT) == "atdfsds.sharepoint.com/…/AllItems.aspx"

    # Nothing to leave out: a site on its own, and a page directly under one
    assert link_title("https://example.com") == "example.com"
    assert link_title("https://example.com/page") == "example.com/page"

    # A page name long enough to be the problem itself is cut like any other
    title = link_title("https://example.com/a/" + "x" * 100)
    assert len(title) == TITLE_MAX
    assert title.endswith("…")


def test_a_long_link_is_drawn_short_and_still_points_home():
    drawn, (link,) = fold_links(f"see {SHAREPOINT} here")

    assert drawn == "see atdfsds.sharepoint.com/…/AllItems.aspx here"

    # The offsets are into what was drawn, which is what gets underlined
    assert drawn[link.start : link.end] == "atdfsds.sharepoint.com/…/AllItems.aspx"

    # And the address behind it is the whole one, which is what gets opened
    assert link.url == SHAREPOINT


def test_a_short_link_is_drawn_as_it_was_written():
    """Folding one would hide an address and save no room at all"""

    text = "see https://example.com here"
    drawn, (link,) = fold_links(text)

    assert drawn == text
    assert drawn[link.start : link.end] == "https://example.com"


def test_a_named_link_is_drawn_as_its_name():
    drawn, (link,) = fold_links(f"see [the folder]({SHAREPOINT}) here")

    assert drawn == "see the folder here"
    assert drawn[link.start : link.end] == "the folder"
    assert link.url == SHAREPOINT


def test_a_named_link_is_drawn_out_of_the_note_itself():
    """
    The fold hides the markup and not the name: the words on the page are the
    same characters, at columns that map straight through, which is what lets
    a name be retyped like any other words
    """

    text = f"see [the folder]({SHAREPOINT}) here"
    drawn, (link,) = fold_links(text)

    assert drawn[link.start : link.end] == "the folder"

    # Every column of the name stands at a column of the note
    for offset in range(link.end - link.start):
        assert stored_range(text, link.start + offset, link.start + offset + 1) == (
            text.index("the folder") + offset,
            text.index("the folder") + offset + 1,
        )


def test_picking_out_a_name_exactly_means_the_name():
    text = f"see [the folder]({SHAREPOINT}) here"
    (link,) = fold_links(text)[1]

    start, end = stored_range(text, link.start, link.end)

    assert text[start:end] == "the folder"


def test_a_run_reaching_past_a_name_takes_the_whole_link():
    """Half a link left on the line is not something a note could hold"""

    text = f"see [the folder]({SHAREPOINT}) here"
    drawn, (link,) = fold_links(text)

    # From the start of the line into the middle of the name
    start, end = stored_range(text, 0, link.start + 3)
    assert text[start:end] == f"see [the folder]({SHAREPOINT})"

    # And the whole drawn line means the whole stored one
    start, end = stored_range(text, 0, len(drawn))
    assert text[start:end] == text


def test_an_unnamed_link_is_all_or_nothing():
    """
    Nothing drawn for it is written anywhere, so no part of it can be edited
    """

    text = f"see []({SHAREPOINT}) here"
    (link,) = fold_links(text)[1]

    start, end = stored_range(text, link.start + 2, link.start + 5)

    assert text[start:end] == f"[]({SHAREPOINT})"


def test_a_place_to_type_comes_back_as_one_column():
    """
    An insertion is one place, not a run: handed back as two it would delete
    whatever the two maps disagreed about
    """

    text = f"see [the folder]({SHAREPOINT}) here"
    drawn, _ = fold_links(text)

    for column in range(len(drawn) + 1):
        start, end = stored_range(text, column, column)

        assert start == end


def test_the_end_of_a_name_is_still_inside_it():
    """So that a name being typed goes on being typed"""

    text = f"see [the]({SHAREPOINT}) here"
    (link,) = fold_links(text)[1]

    start, end = stored_range(text, link.end, link.end)

    assert text[:start].endswith("[the")
    assert start == end


def test_two_links_on_one_line_both_land_where_they_are_drawn():
    drawn, links = fold_links(f"[a](https://a.com/x) then {SHAREPOINT}")

    assert [drawn[link.start : link.end] for link in links] == [
        "a",
        "atdfsds.sharepoint.com/…/AllItems.aspx",
    ]
    assert [link.url for link in links] == ["https://a.com/x", SHAREPOINT]
