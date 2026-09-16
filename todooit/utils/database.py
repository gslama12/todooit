from sqlalchemy import Engine, MetaData, inspect, text
from sqlalchemy.orm import Session


# Todos used to carry an "urgency" from 1 (lowest, and the default) up to 4
# (highest). Priority runs the other way around: 1 is the highest and 3 the
# lowest, with 0 meaning "no priority set".
URGENCY_TO_PRIORITY = {1: 0, 2: 3, 3: 2, 4: 1}


def migrate_urgency_to_priority(engine: Engine):
    """
    Rename a legacy `urgency` column to `priority` and flip its values over to
    the new scale. Does nothing once the database has been migrated.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}
    if "urgency" not in columns or "priority" in columns:
        return

    # a single statement, so that remapped values can't collide with the
    # not-yet-remapped ones
    cases = " ".join(
        f"WHEN {urgency} THEN {priority}"
        for urgency, priority in URGENCY_TO_PRIORITY.items()
    )

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE todo RENAME COLUMN urgency TO priority"))
        connection.execute(
            text(f"UPDATE todo SET priority = CASE priority {cases} ELSE 0 END")
        )


def rename_workspace_to_project(engine: Engine):
    """
    Rename a legacy `workspace` table to `project`, along with the
    `parent_workspace_id` columns that point at it.

    Without this `create_all` would find no `project` table, happily create an
    empty one next to the old one, and leave every existing project and its
    todos stranded in a table nothing reads any more.
    """

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "workspace" not in tables or "project" in tables:
        return

    def has_column(table: str, column: str) -> bool:
        return any(col["name"] == column for col in inspector.get_columns(table))

    statements = ["ALTER TABLE workspace RENAME TO project"]

    # Renaming the table is enough for sqlite to repoint the foreign keys that
    # referenced it; the columns holding them still have to be renamed by hand.
    if has_column("workspace", "parent_workspace_id"):
        statements.append(
            "ALTER TABLE project RENAME COLUMN parent_workspace_id TO parent_project_id"
        )

    if "todo" in tables and has_column("todo", "parent_workspace_id"):
        statements.append(
            "ALTER TABLE todo RENAME COLUMN parent_workspace_id TO parent_project_id"
        )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


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


def migrate_effort_to_agent(engine: Engine):
    """
    Trade a todo table's legacy `effort` column for the `agent` flag.

    Effort was an estimate of how big a job is, on a 1-3 scale; the column that
    took its place says something else entirely -- that the task has been
    handed to an AI which is off working on it -- so nothing is carried over
    and every existing row starts out unflagged.

    The old column has to go rather than being left lying there: it was written
    `NOT NULL` with no default of its own, and the model no longer has anything
    to say about it, so a single row added after the upgrade would be rejected
    by a column nothing is filling in any more.
    """

    inspector = inspect(engine)
    if "todo" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("todo")}

    statements = []

    if "agent" not in columns:
        statements.append(
            "ALTER TABLE todo ADD COLUMN agent BOOLEAN NOT NULL DEFAULT 0"
        )

    if "effort" in columns:
        statements.append("ALTER TABLE todo DROP COLUMN effort")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


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
