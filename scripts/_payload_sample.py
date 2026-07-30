"""Show payload of dataset-level and one column-level measurement."""

import json
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
    if m.scope.kind.value == "dataset":
        print(f"dataset-level  {m.type}")
        print(json.dumps(dict(m.payload), indent=2, ensure_ascii=False))
        print()

# Also show one column missing payload
for m in measurements:
    if m.type == "core.quality.missing" and m.scope.kind.value == "column":
        print(f"column missing  {m.scope.refs}")
        print(json.dumps(dict(m.payload), indent=2, ensure_ascii=False))
        break
