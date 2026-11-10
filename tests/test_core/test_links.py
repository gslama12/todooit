"""
The links inside a description or a note
"""

from todooit.utils.links import (
    TITLE_MAX,
    drawn_column,
    emph_pairs,
    find_links,
    first_link,
    fold_links,
    folded_emph,
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


# The note's emphasis, folded by the same maps as a link's markup: a phrase
# written between two marks that take no columns on the page
EMPH_MARK = "*"
EMPHASISED = "ab" + EMPH_MARK + "cd" + EMPH_MARK + "ef"


def test_a_mark_is_drawn_as_nothing():
    drawn, _ = fold_links(EMPHASISED)

    assert drawn == "abcdef"
    assert folded_emph(EMPHASISED) == [(2, 4)]
    assert emph_pairs(EMPHASISED) == [(2, 3, 5, 6)]


def test_a_stored_column_comes_back_past_the_mark_it_is_hidden_behind():
    assert [drawn_column(EMPHASISED, column) for column in range(9)] == [
        0,
        1,
        2,
        2,
        3,
        4,
        4,
        5,
        6,
    ]


def test_typing_at_the_head_of_a_phrase_lands_outside_it():
    """
    Which is what keeps an `enter` there from cutting a finished pair in half:
    the place in front of the word is the place in front of its mark
    """

    start, end = stored_range(EMPHASISED, 2, 2)

    assert (start, end) == (2, 2)
    assert EMPHASISED[start] == EMPH_MARK


def test_typing_at_the_tail_of_a_phrase_lands_outside_it_too():
    """Emphasis is extended from inside the words, never from either edge"""

    start, end = stored_range(EMPHASISED, 4, 4)

    assert (start, end) == (6, 6)
    assert EMPHASISED[start - 1] == EMPH_MARK


def test_a_letter_picked_out_of_a_phrase_is_only_the_letter():
    """So that backspacing the first letter leaves the emphasis standing"""

    assert stored_range(EMPHASISED, 2, 3) == (3, 4)
    assert stored_range(EMPHASISED, 3, 4) == (4, 5)


def test_a_phrase_picked_out_whole_carries_its_marks():
    """
    Copying one carries the emphasis, and deleting one leaves no half of a
    pair behind
    """

    start, end = stored_range(EMPHASISED, 2, 4)

    assert EMPHASISED[start:end] == EMPH_MARK + "cd" + EMPH_MARK


def test_the_whole_page_of_a_line_is_the_whole_line():
    """A rewrite of a line has to land on the markup at its edges as well"""

    text = EMPH_MARK + "loud" + EMPH_MARK
    drawn, _ = fold_links(text)

    assert stored_range(text, 0, len(drawn)) == (0, len(text))


def test_a_star_with_no_partner_stays_on_the_page():
    text = "ab" + EMPH_MARK + "cd"

    assert fold_links(text)[0] == text
    assert folded_emph(text) == []
    assert stored_range(text, 2, 2) == (2, 2)


def test_double_stars_fold_like_single_ones():
    text = "ab**cd**ef"

    assert fold_links(text)[0] == "abcdef"
    assert folded_emph(text) == [(2, 4)]
    assert stored_range(text, 2, 4) == (2, 8)


def test_a_raw_line_keeps_its_stars():
    assert fold_links(EMPHASISED, True)[0] == EMPHASISED
    assert folded_emph(EMPHASISED, True) == []


def test_a_star_inside_a_link_pairs_nothing():
    text = "*a [n](https://x.io/b*c) d"

    assert emph_pairs(text) == []


def test_a_heading_mark_is_folded_off_the_page():
    assert fold_links("## Title")[0] == "Title"
    assert fold_links("## Title", True)[0] == "## Title"
    assert drawn_column("## Title", 3) == 0


def test_a_run_over_a_phrase_takes_exactly_its_marks():
    # The marks hidden in front of a phrase aren't all its own
    assert stored_range("# *x* yz", 0, 1) == (2, 5)

    # And its closing stars aren't next to its words when a link's markup is
    text = "x *[n](http://a.b)* y"

    assert stored_range(text, 2, 3) == (2, len("x *[n](http://a.b)*"))
