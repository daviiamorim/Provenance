"""Show scope kinds and types of measurements for the run."""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()

from db.connection import get_connection
from db.repos import measurements as measurement_repo

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"

conn = get_connection()
measurements = measurement_repo.list_by_run(conn, RUN_ID)
conn.close()

for m in measurements:
    row_count = m.payload.get("row_count", "-")
    refs = list(m.scope.refs)[:2]
    print(f"  {m.scope.kind.value:8s}  {m.type:35s}  refs={refs}  rc={row_count}")
