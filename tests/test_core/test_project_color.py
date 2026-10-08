"""
A color labels a whole project tree

The slot is held by the project at the top of the tree and handed down from
there, so a sub project is never drawn in a color of its own -- whether it was
there when the color was picked, made afterwards, or built back out of a
binned todo's path.
"""

from tests.test_core.core_base import *  # noqa


def test_coloring_a_project_colors_every_project_under_it(create_project):
    top = create_project("work")
    child = top.add_project()
    grandchild = child.add_project()

    top.set_color(4)

    assert top.color == 4
    assert child.color == 4
    assert grandchild.color == 4


def test_clearing_a_color_clears_the_whole_tree(create_project):
    top = create_project("work")
    child = top.add_project()
    grandchild = child.add_project()

    top.set_color(4)
    top.set_color(None)

    assert [p.color for p in (top, child, grandchild)] == [None, None, None]


def test_coloring_a_sub_project_colors_the_tree_it_is_in(create_project):
    """
    The row the color is typed over is only the way into the tree: what gets
    painted is the project at the top of it and everything filed under that
    """

    top = create_project("work")
    child = top.add_project()
    sibling = top.add_project()
    grandchild = child.add_project()

    grandchild.set_color(7)

    assert top.color == 7
    assert child.color == 7
    assert sibling.color == 7
    assert grandchild.color == 7


def test_a_sub_project_made_later_is_born_in_the_color(create_project):
    top = create_project("work")
    top.set_color(2)

    child = top.add_project()
    grandchild = child.add_project()

    assert child.color == 2
    assert grandchild.color == 2


def test_a_sub_project_cannot_be_given_a_color_of_its_own(create_project):
    """
    Writing to the column directly is still not a way around the rule: the
    next save puts the sub project back in its parent's slot
    """

    top = create_project("work")
    top.set_color(1)

    child = top.add_project()
    child.color = 8
    child.save()

    assert child.color == 1


def test_a_top_level_project_keeps_its_own_color(create_project):
    """
    Top level projects all answer to the root, which is in no palette slot,
    so they are colored one at a time and not as one family
    """

    work = create_project("work")
    personal = create_project("personal")

    work.set_color(3)

    assert work.color == 3
    assert personal.color is None


def test_a_sibling_of_a_sub_project_takes_the_shared_color(create_project):
    top = create_project("work")
    top.set_color(5)

    child = top.add_project()
    sibling = child.add_sibling()

    assert sibling.color == 5


def test_a_sibling_of_a_top_level_project_starts_uncolored(create_project):
    work = create_project("work")
    work.set_color(5)

    other = work.add_sibling()

    assert other.color is None


def test_descendants_walks_every_level(create_project):
    top = create_project("work")
    child = top.add_project()
    grandchild = child.add_project()
    sibling = top.add_project()

    assert set(top.descendants) == {child, grandchild, sibling}
    assert top.descendants[0] is child
    assert top.descendants[1] is grandchild


def test_color_root_is_the_top_of_the_tree(create_project):
    top = create_project("work")
    child = top.add_project()
    grandchild = child.add_project()

    assert top.color_root is top
    assert child.color_root is top
    assert grandchild.color_root is top


def test_an_indented_tree_takes_its_new_parents_color(create_project):
    work = create_project("work")
    work.set_color(2)
    home = create_project("home")
    home.set_color(5)
    room = home.add_project()

    outcome = home.indent()

    assert [p.color for p in (home, room)] == [2, 2]
    # Its own color gave way, which is worth a word in the bar
    assert outcome
    assert "recolored" in outcome.summary()


def test_indenting_into_the_same_color_says_nothing(create_project):
    work = create_project("work")
    home = create_project("home")

    assert not home.indent()


def test_an_unindented_project_keeps_its_color(create_project):
    work = create_project("work")
    work.set_color(3)
    sub = work.add_project()
    sub_sub = sub.add_project()

    assert not sub.unindent()
    assert [p.color for p in (work, sub, sub_sub)] == [3, 3, 3]
