-- The schema dooit v3.0.0-v3.3.4 creates (upstream commit ba2a7efd), frozen
-- so the migration tests need no dooit install. Generated from those models'
-- `create_all` on SQLite; recurrence is SQLAlchemy's Interval, which SQLite
-- stores as the moment that long after 1970-01-01.

CREATE TABLE workspace (
	id INTEGER NOT NULL,
	order_index INTEGER NOT NULL,
	description VARCHAR NOT NULL,
	is_root BOOLEAN NOT NULL,
	parent_workspace_id INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(parent_workspace_id) REFERENCES workspace (id)
);

CREATE TABLE todo (
	id INTEGER NOT NULL,
	order_index INTEGER NOT NULL,
	description VARCHAR NOT NULL,
	due DATETIME,
	effort INTEGER NOT NULL,
	recurrence DATETIME,
	urgency INTEGER NOT NULL,
	pending BOOLEAN NOT NULL,
	parent_workspace_id INTEGER,
	parent_todo_id INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(parent_workspace_id) REFERENCES workspace (id),
	FOREIGN KEY(parent_todo_id) REFERENCES todo (id)
);
