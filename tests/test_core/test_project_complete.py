"""
Completing the `#project` in a typed line, the way a shell completes a path
"""

from todooit.utils.project_complete import (
    Candidate,
    Token,
    common_prefix,
    completion,
    extended,
    find_token,
    matching,
    minimal_path,
    written,
)

# A small tree with the two things that make completion interesting in it: a
# project that has something inside it, and a name two projects answer to
POOL = [
    Candidate(("work",), has_children=True),
    Candidate(("work", "api")),
    Candidate(("work", "web"), has_children=True),
    Candidate(("work", "web", "deploy")),
    Candidate(("home",), has_children=True),
    Candidate(("home", "api")),
    Candidate(("my house",)),
]


def token(line: str, cursor: int = -1) -> Token:
    found = find_token(line, len(line) if cursor < 0 else cursor)

    assert found is not None
    return found


def names(line: str, cursor: int = -1):
    return ["/".join(c.steps) for c in matching(token(line, cursor), POOL)]


# ----------------------------------------------------------------------
# Finding the token the cursor is in
# ----------------------------------------------------------------------


def test_a_bare_marker_is_a_token_with_nothing_in_it():
    found = token("buy milk #")

    assert found.text == ""
    assert found.partial == ""
    assert found.anchor == ()


def test_the_token_spans_only_what_follows_the_marker():
    found = token("#work")

    assert (found.start, found.end) == (1, 5)
    assert found.text == "work"


def test_a_marker_mid_word_is_not_a_token():
    assert find_token("issue#12", 8) is None


def test_a_cursor_outside_the_token_finds_nothing():
    # The line names a project and then goes on talking about something else
    assert find_token("#work call the dentist", 22) is None


def test_the_token_the_cursor_is_in_is_the_one_being_typed():
    assert token("#work and #home", 3).text == "work"
    assert token("#work and #home", 15).text == "home"


def test_a_quote_nobody_has_closed_yet_is_still_a_token():
    assert token('buy milk #"my ho').text == "my ho"


def test_a_closed_quote_holds_a_name_with_a_space_in_it():
    found = token('#"my house"')

    assert found.text == "my house"
    assert found.partial == "my house"


def test_a_path_splits_into_what_is_named_above_and_what_is_being_typed():
    found = token("#work/ap")

    assert found.anchor == ("work",)
    assert found.partial == "ap"


def test_a_trailing_separator_is_asking_for_what_is_inside():
    found = token("#work/")

    assert found.anchor == ("work",)
    assert found.partial == ""


# ----------------------------------------------------------------------
# Which projects a half typed name could mean
# ----------------------------------------------------------------------


def test_a_bare_marker_offers_everything_shallowest_first():
    assert names("#") == [
        "home",
        "my house",
        "work",
        "home/api",
        "work/api",
        "work/web",
        "work/web/deploy",
    ]


def test_a_name_matches_at_any_depth():
    assert names("#ap") == ["home/api", "work/api"]


def test_matching_ignores_case():
    assert names("#WO") == ["work"]


def test_a_path_matches_bottom_up():
    assert names("#work/ap") == ["work/api"]


def test_a_path_does_not_reach_past_its_own_parent():
    assert names("#home/web") == []


def test_a_trailing_separator_lists_what_is_inside():
    assert names("#work/") == ["work/api", "work/web"]


def test_a_name_nobody_has_matches_nothing():
    assert names("#zzz") == []


def test_a_path_never_matches_a_project_too_shallow_for_it():
    # `work/work` would need a `work` inside a `work`, and there is one only
    # at the top of the tree
    assert names("#work/work") == []


# ----------------------------------------------------------------------
# How far the matches agree
# ----------------------------------------------------------------------


def test_the_agreed_prefix_of_one_name_is_the_whole_of_it():
    assert common_prefix(["work"]) == "work"


def test_names_agree_as_far_as_they_are_the_same():
    assert common_prefix(["deploy", "delete"]) == "de"


def test_names_that_start_differently_agree_on_nothing():
    assert common_prefix(["api", "web"]) == ""


def test_the_agreed_prefix_is_spelled_the_way_a_project_spells_it():
    assert common_prefix(["Work", "worktree"]) == "Work"


def test_nothing_agrees_on_nothing():
    assert common_prefix([]) == ""


# ----------------------------------------------------------------------
# What a chosen project goes into the line as
# ----------------------------------------------------------------------


def test_a_name_nobody_shares_is_enough_on_its_own():
    assert minimal_path(Candidate(("work", "web")), POOL) == ("web",)


def test_a_shared_name_takes_its_parent_along():
    assert minimal_path(Candidate(("work", "api")), POOL) == ("work", "api")


def test_a_completion_is_as_short_as_it_can_be():
    assert completion(token("#we"), Candidate(("work", "web")), POOL) == "web"


def test_a_completion_keeps_the_path_that_was_typed():
    # Someone who has written `work/` has said where they are looking, and
    # the answer is not allowed to throw that away
    assert (
        completion(token("#work/we"), Candidate(("work", "web")), POOL)
        == "work/web"
    )


def test_a_completion_spells_out_enough_to_tell_two_apart():
    assert completion(token("#ap"), Candidate(("home", "api")), POOL) == "home/api"


def test_growing_a_name_leaves_the_path_above_it_alone():
    assert extended(token("#work/a"), "api") == "work/api"


def test_growing_a_bare_name_is_just_the_name():
    assert extended(token("#a"), "api") == "api"


# ----------------------------------------------------------------------
# How it is written into the line
# ----------------------------------------------------------------------


def test_a_plain_name_is_written_as_it_is():
    assert written("work") == "work"


def test_a_finished_project_ends_the_field_with_a_space():
    assert written("work", " ") == "work "


def test_a_project_with_children_is_left_open():
    assert written("work", "/") == "work/"


def test_a_name_with_a_space_is_quoted():
    assert written("my house") == '"my house"'


def test_the_separator_goes_inside_the_quotes():
    # `#"my house"/x` would be read as the project and then a stray word
    assert written("my house", "/") == '"my house/"'


def test_the_space_that_ends_the_field_stays_outside_the_quotes():
    assert written("my house", " ") == '"my house" '


def test_a_quoted_completion_reads_back_as_the_name_it_was():
    from todooit.utils.quick_add import parse_quick_add

    line = "buy a lamp #" + written("my house", " ") + "tomorrow"

    assert parse_quick_add(line).project == "my house"
