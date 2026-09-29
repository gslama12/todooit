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
        # Counts the commits that have gone through here, so that anything
        # watching for a change can ask whether there has been one without
        # reading the database to find out. The undo history is what it is
        # for: it looks after every key, and most keys write nothing.
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

        # Creates whatever tables are missing, indexes included, straight from
        # the models. A table that already exists is never altered, so the
        # database is expected to match the current schema
        BaseModel.metadata.create_all(bind=self.engine)

        self._db_last_modified = self._get_db_last_modified()

    def _get_db_last_modified(self) -> Optional[float]:
        database = self.engine.url.database
        assert database is not None

        try:
            return os.path.getmtime(database)
        except OSError:
            return None

    def has_changed(self) -> bool:
        current_last_modified = self._get_db_last_modified()
        if current_last_modified and self._db_last_modified != current_last_modified:
            self._db_last_modified = current_last_modified
            manager.session.expire_all()

            # Written by somebody else, but written all the same: anything
            # measuring against the last commit has to know the rows it was
            # holding are not the rows that are there now
            self.revision += 1
            return True
        return False

    def delete(self, obj):
        self.session.delete(obj)
        self.commit()

    def save(self, obj):
        self.session.add(obj)
        self.commit()

    def commit(self):
        self.session.commit()
        self.revision += 1
        self._db_last_modified = self._get_db_last_modified()


manager = Manager()
