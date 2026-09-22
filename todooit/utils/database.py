from sqlalchemy import Engine, MetaData, inspect, text
from sqlalchemy.orm import Session


def add_scheduled_column(engine: Engine):
    """
    Add the `scheduled` column to a todo table written before it existed.

    `create_all` only ever creates whole tables that are missing, so a database
    from an older version keeps its todo table exactly as it was.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}
    if "scheduled" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE todo ADD COLUMN scheduled DATETIME"))


def add_note_column(engine: Engine):
    """
    Add the `note` column to a todo table written before it existed.

    Same story as `add_scheduled_column`: `create_all` never touches a table it
    already found, so the column has to be bolted on by hand.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}
    if "note" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE todo ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        )


def add_attachments_column(engine: Engine):
    """
    Add the `attachments` column to the tables written before it existed.

    Same story as `add_scheduled_column`, twice over: both the todos and the
    pinned note carry files now, and `create_all` never touches a table it
    already found. What the column holds is one path per line, so a database
    from before there were any grows an empty one - which is what "nothing
    attached" is written as.
    """

    inspector = inspect(engine)

    for table in ("todo", "pinnednote"):
        if table not in inspector.get_table_names():
            continue

        columns = {column["name"] for column in inspector.get_columns(table)}
        if "attachments" in columns:
            continue

        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN attachments TEXT NOT NULL DEFAULT ''"
                )
            )


def add_completed_at_column(engine: Engine):
    """
    Add the `completed_at` column to a todo table written before it existed.

    Same story as `add_scheduled_column`. Todos completed before there was
    anywhere to write the date keep an empty one: the Completed project sorts
    them below everything that carries a real date.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}
    if "completed_at" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE todo ADD COLUMN completed_at DATETIME"))


def add_bin_columns(engine: Engine):
    """
    Add the columns the Bin is kept in to a todo table written before it
    existed.

    Same story as `add_scheduled_column`. Nothing that was already in the
    database was ever thrown away, so every existing row starts out with an
    empty bin date and no path of its own to remember.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}

    statements = []

    if "binned_at" not in columns:
        statements.append("ALTER TABLE todo ADD COLUMN binned_at DATETIME")

    if "origin_path" not in columns:
        statements.append(
            "ALTER TABLE todo ADD COLUMN origin_path TEXT NOT NULL DEFAULT ''"
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def add_agent_column(engine: Engine):
    """
    Add the `agent` flag to a todo table written before it existed.

    Same story as `add_scheduled_column`. The flag says the task has been
    handed to an AI which is off working on it, so every row that was already
    in the database starts out unflagged.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}
    if "agent" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE todo ADD COLUMN agent BOOLEAN NOT NULL DEFAULT 0")
        )


def add_project_color_column(engine: Engine):
    """
    Add the `color` column to a project table written before it existed.

    Same story as `add_scheduled_column`: `create_all` never touches a table it
    already found. Every project that was already in the database starts out
    with no color, which is what an empty column means.
    """

    inspector = inspect(engine)
    if "project" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project")}
    if "color" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE project ADD COLUMN color INTEGER"))


# Walks the project tree from its top level down, handing each project the
# color of the one it is filed in. The anchor row of the recursion is a top
# level project -- one whose parent is the root, or, defensively, one with no
# parent at all -- and that is the only place a color is read from rather than
# passed on. The root itself is kept out of the walk entirely: left in, it
# would reach the top level projects a second time and hand them the color it
# has never had, and each of them would then be in the walk twice over.
SYNC_PROJECT_COLORS = """
WITH RECURSIVE tree(id, color) AS (
    SELECT child.id, child.color
    FROM project AS child
    LEFT JOIN project AS parent ON parent.id = child.parent_project_id
    WHERE child.is_root = 0
      AND (child.parent_project_id IS NULL OR parent.is_root = 1)

    UNION ALL

    SELECT child.id, tree.color
    FROM project AS child
    JOIN tree ON tree.id = child.parent_project_id
)
UPDATE project
SET color = (SELECT color FROM tree WHERE tree.id = project.id)
WHERE color IS NOT (SELECT color FROM tree WHERE tree.id = project.id)
"""


def sync_project_colors(engine: Engine):
    """
    Bring every sub project into line with the color of the project it is in.

    A color labels a whole tree, and the model keeps it that way from here on.
    A database written before that was the rule can still hold a sub project
    painted a color of its own, so the rule is applied to what is already
    there once on the way in. Idempotent: a tree that already agrees with
    itself is left untouched.
    """

    inspector = inspect(engine)
    if "project" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project")}
    if "color" not in columns:
        return

    with engine.begin() as connection:
        connection.execute(text(SYNC_PROJECT_COLORS))


def delete_all_data(session: Session):
    meta = MetaData()
    meta.reflect(bind=session.get_bind())
    for table in reversed(meta.sorted_tables):
        session.execute(table.delete())
    session.commit()


# The columns the panes are looked up by. Everything here is either a foreign
# key a relationship is walked through, or a column one of the fixed projects
# filters on -- the two shapes that turn a pane into a run of full table scans
# once the database has some history in it.
#
# The two date columns the logs are read by are deliberately absent.
# `completed_at` and `binned_at` are sorted in Python, not in SQL, so an index
# on either buys nothing on its own; the Bin gets a partial one only because
# `binned_tasks` asks for `IS NOT NULL`, which is the whole of that index.
INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_todo_parent_todo_id ON todo (parent_todo_id)",
    "CREATE INDEX IF NOT EXISTS ix_todo_parent_project_id ON todo (parent_project_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_project_parent_project_id "
        "ON project (parent_project_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_todo_pending_scheduled ON todo (pending, scheduled)",
    (
        "CREATE INDEX IF NOT EXISTS ix_todo_binned_at ON todo (binned_at) "
        "WHERE binned_at IS NOT NULL"
    ),
)


def add_indexes(engine: Engine):
    """
    Index the columns the panes are looked up by

    Unlike every migration above it, this one runs *after* `create_all` rather
    than before it. `create_all` skips a table it already found -- indexes and
    all -- so a database written before these existed never gets the ones
    declared on the models, and a database written from scratch has no tables
    to index until `create_all` has made them. Running here is the one moment
    both are true.

    The names match what the models declare, so the two ways in converge on
    one set of indexes rather than each laying down its own.
    """

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if not {"todo", "project"} <= tables:  # pragma: no cover
        return

    with engine.begin() as connection:
        for statement in INDEXES:
            connection.execute(text(statement))
