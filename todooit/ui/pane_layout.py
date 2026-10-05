"""
Pane layout: the rows a pane draws, finished

Turns what a pane shows (a project's todos, a fixed project's blocks, the
project tree) into the rows it draws, in order, in one pass: headings, context
rows and model rows, each with its tree guides, whether a line drops from it
into rows below, whether it starts a family, and whether it is banded. The
trees only paint these rows; nothing here knows about Textual.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple, Union

from todooit.api import Project, Todo, TodoGroup, TodoRow, sort_todos
from todooit.api.fixed_projects import PATH_SEPARATOR
from todooit.api.placement import home_of

# File-tree-style guides drawn left of a nested row, all the same width (one
# level of indent)
GUIDE_BRANCH = "├── "
GUIDE_LAST_BRANCH = "╰── "
GUIDE_VERTICAL = "│   "
GUIDE_BLANK = "    "

# GUIDE_VERTICAL without its trailing gap: carries the line down through a
# wrapped row to the column its children turn out of
GUIDE_DROP = GUIDE_VERTICAL[0]

HEADING = "heading"
CONTEXT = "context"
MODEL = "model"

Expanded = Callable[[str], bool]
Children = Callable[[Any], List[Any]]


@dataclass(frozen=True)
class PaneRow:
    """
    One row of a pane

    `uuid` is the model's (blank for a heading): rows hold no model, so a row
    laid out before a delete keeps nothing from the database alive.
    `guides` are what is drawn in front of the row's first line, `below` in
    front of every wrapped line under it. `drops` says a line runs from the
    row into rows drawn under it. A root row starts a family in this pane:
    nothing it hangs off is drawn here.
    """

    id: str
    kind: str = MODEL
    uuid: str = ""
    label: str = ""
    block: int = 0
    guides: str = ""
    below: str = ""
    drops: bool = False
    is_root: bool = True
    shaded: bool = False

    @property
    def is_heading(self) -> bool:
        return self.kind == HEADING

    @property
    def is_context(self) -> bool:
        return self.kind == CONTEXT


def plain_row(uuid: str) -> PaneRow:
    """A row with nothing around it: no guides, nothing under it"""

    return PaneRow(id=uuid, uuid=uuid)


def heading_id(block: int) -> str:
    return f"todooit-todo-group-{block}"


def context_id(block: int, todo: Todo) -> str:
    """
    Keyed by block rather than by todo alone: the same task can be context in
    more than one block (e.g. steps on different days)
    """

    return f"todooit-todo-context-{block}-{todo.id}"


def drawn_children(model: Union[Project, Todo], sort_mode: Optional[str]) -> List[Todo]:
    """
    The todos a pane draws under a project or a row: those living where their
    parent does (see placement), in the pane's order. A completed step stays
    under its open parent; a step binned on its own leaves for the Bin.
    """

    home = model if isinstance(model, Project) else home_of(model)
    todos = [todo for todo in model.todos if home_of(todo) is home]

    return sort_todos(todos, sort_mode)


def project_groups(
    model: Union[Project, Todo], sort_mode: Optional[str]
) -> List[TodoGroup]:
    """
    The blocks a stored project's pane draws: its own todos first (unlabelled),
    then a block per nested sub-project however deep, labelled by its path
    down from here so same-named sub-projects stay apart. Empty blocks are
    dropped.
    """

    groups = [TodoGroup(todos=drawn_children(model, sort_mode))]

    if isinstance(model, Project):
        groups += _sub_project_groups(model, "", sort_mode)

    return [group for group in groups if group.todos]


# Plain recursion rather than closures throughout: a recursive closure is a
# reference cycle, and one holding todos keeps them in the session's identity
# map past their delete, until the garbage collector gets round to it


def _sub_project_groups(
    parent: Project, prefix: str, sort_mode: Optional[str]
) -> List[TodoGroup]:
    groups: List[TodoGroup] = []

    for child in parent.projects:
        label = f"{prefix}{child.description}"
        groups.append(TodoGroup(todos=drawn_children(child, sort_mode), label=label))
        groups += _sub_project_groups(child, f"{label}{PATH_SEPARATOR}", sort_mode)

    return groups


@dataclass
class _Node:
    model: Any
    is_context: bool = False
    under: List["_Node"] = field(default_factory=list)


def _family(model: Any, children: Children, expanded: Expanded) -> _Node:
    """A row with whatever of its own family it is expanded to show"""

    under = children(model) if expanded(model.uuid) else []
    return _Node(model, under=[_family(child, children, expanded) for child in under])


def _picked(rows: List[TodoRow], children: Children, expanded: Expanded) -> List[_Node]:
    """
    A block's rows as nodes. A row that draws its own steps (`under` is None)
    does so as its project would; a row a day block picked steps for draws
    only those, always if it is context, else as far as it's expanded.
    """

    nodes: List[_Node] = []

    for row in rows:
        if row.under is None:
            nodes.append(_family(row.todo, children, expanded))
            continue

        shown = row.is_context or expanded(row.todo.uuid)
        under = _picked(row.under, children, expanded) if shown else []
        nodes.append(_Node(row.todo, row.is_context, under))

    return nodes


def _guides(prefix: str, depth: int, last: bool) -> Tuple[str, str]:
    """(first line, lines below) for a row `depth` levels into its family"""

    if not depth:
        return "", ""

    first = prefix + (GUIDE_LAST_BRANCH if last else GUIDE_BRANCH)
    below = prefix + (GUIDE_BLANK if last else GUIDE_VERTICAL)

    return first, below


def _flatten(nodes: List[_Node], block: int, out: List[PaneRow]) -> None:
    """Appends a block's nodes depth first, each row's guides read off its drawn siblings"""

    _walk(nodes, block, "", 0, out, [0])


def _walk(
    nodes: List[_Node],
    block: int,
    prefix: str,
    depth: int,
    out: List[PaneRow],
    banded: List[int],
) -> None:
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        guides, below = _guides(prefix, depth, last)

        if node.is_context:
            _id, shaded = context_id(block, node.model), False
        else:
            # Counts real rows only, so context rows don't disturb the banding
            _id, shaded = node.model.uuid, bool(banded[0] % 2)
            banded[0] += 1

        out.append(
            PaneRow(
                id=_id,
                kind=CONTEXT if node.is_context else MODEL,
                uuid=node.model.uuid,
                block=block,
                guides=guides,
                below=below,
                drops=bool(node.under),
                is_root=not depth,
                shaded=shaded,
            )
        )

        _walk(node.under, block, below, depth + 1, out, banded)


def todo_rows(
    groups: List[TodoGroup], children: Children, expanded: Expanded
) -> List[PaneRow]:
    """
    A todos pane's rows: each block under its heading (if labelled), its rows
    followed by what's drawn under them. Banding restarts every block.
    """

    rows: List[PaneRow] = []

    for block, group in enumerate(groups):
        if group.label:
            rows.append(
                PaneRow(
                    id=heading_id(block), kind=HEADING, label=group.label, block=block
                )
            )

        _flatten(_picked(group.rows, children, expanded), block, rows)

    return rows


def tree_rows(top: List[Any], children: Children, expanded: Expanded) -> List[PaneRow]:
    """A plain tree's rows (the projects pane): every expanded row followed by its children"""

    rows: List[PaneRow] = []
    _flatten([_family(model, children, expanded) for model in top], 0, rows)

    return rows
