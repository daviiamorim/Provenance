"""Print findings and assessments stored for the last run."""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()

from db.connection import get_connection
from db.repos import assessments as assessment_repo
from db.repos import findings as finding_repo

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"

conn = get_connection()
findings = finding_repo.list_by_run(conn, RUN_ID)
assessments = assessment_repo.list_by_run(conn, RUN_ID)
conn.close()

print(f"=== {len(findings)} Findings ===")
for f in findings:
    print(f"  [{f.id}] {f.severity.value.upper():4s}  {f.type}  {list(f.scope.refs)}")
    print(f"       {f.statement}")

print(f"\n=== {len(assessments)} Assessments ===")
for a in assessments:
    print(
        f"  [{a.id}] {a.severity.value.upper():4s}  goal={a.goal}  verdict={a.verdict}"
    )
