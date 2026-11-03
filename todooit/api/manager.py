import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from todooit.paths import database_file


class Manager:
    """
    Class for managing sqlalchemy sessions
    """

    def __init__(self) -> None:
        # Commit counter, so undo history can cheaply detect "nothing written"
        self.revision = 0

    def connect(self, path: Optional[str] = None):
        """
        Connect to database using a file path

        Args:
            path: Path to SQLite database file. Can include ~ for home directory.
        """

        from todooit.api import BaseModel

        path = str(path or database_file())
        path = os.path.expanduser(path)

        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        connection_string = f"sqlite:///{path}"

        self.engine = create_engine(connection_string)
        self.session = Session(self.engine)

        # Creates missing tables only; existing tables are never migrated
        BaseModel.metadata.create_all(bind=self.engine)
        self._drop_retired_columns()
        self._add_new_columns()

    # Columns the model no longer has. Left in place they would break every
    # insert, since they were created NOT NULL with only a Python-side default.
    RETIRED_COLUMNS = (("todo", "agent"),)

    def _drop_retired_columns(self) -> None:
        with self.engine.begin() as connection:
            for table, column in self.RETIRED_COLUMNS:
                present = connection.exec_driver_sql(
                    f"SELECT 1 FROM pragma_table_info('{table}') WHERE name = ?",
                    (column,),
                ).first()

                if present:
                    connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")

    # Columns added to tables that may already exist: `create_all` leaves an
    # existing table alone, so a database from before them gets them here.
    # (table, column, definition)
    ADDED_COLUMNS = (
        ("project", "expanded", "BOOLEAN NOT NULL DEFAULT 1"),
        ("todo", "expanded", "BOOLEAN NOT NULL DEFAULT 1"),
    )

    def _add_new_columns(self) -> None:
        with self.engine.begin() as connection:
            for table, column, definition in self.ADDED_COLUMNS:
                present = connection.exec_driver_sql(
                    f"SELECT 1 FROM pragma_table_info('{table}') WHERE name = ?",
                    (column,),
                ).first()

                if not present:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )

    def delete(self, obj):
        self.session.delete(obj)
        self.commit()

    def save(self, obj):
        self.session.add(obj)
        self.commit()

    def commit(self):
        self.session.commit()
        self.revision += 1


manager = Manager()
