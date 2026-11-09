"""Pin every test run to a dedicated Postgres database before any app module
reads configuration. Tests truncate tables, so this must never resolve to the
dev or production database: the name has to end in `_test`.

Override with TEST_DATABASE_URL. (Reading the environment here, outside
config.py, is the one sanctioned exception: it runs before Settings exists.)
"""

import os

from psycopg.conninfo import conninfo_to_dict

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://thalace:thalace@localhost:5433/thalace_test")

if not str(conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")).endswith("_test"):
    raise RuntimeError(f"Refusing to run tests against {TEST_DATABASE_URL!r}: the database name must end in '_test'.")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
