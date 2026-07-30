"""One-shot script: print row counts for the last run."""

from dotenv import load_dotenv

load_dotenv()

from db.connection import get_connection

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"

conn = get_connection()


def n(query: str, *args: object) -> int:
    cur = conn.execute(query, args)
    row = cur.fetchone()
    return int(row["n"]) if row else 0


print("datasets :", n("SELECT COUNT(*) as n FROM datasets"))
print("runs     :", n("SELECT COUNT(*) as n FROM runs"))
print(
    "measurements:",
    n(
        "SELECT COUNT(*) as n FROM run_membership_measurements WHERE run_id = %s",
        RUN_ID,
    ),
)
print(
    "findings    :",
    n(
        "SELECT COUNT(*) as n FROM run_membership_findings WHERE run_id = %s",
        RUN_ID,
    ),
)
print(
    "assessments :",
    n(
        "SELECT COUNT(*) as n FROM run_membership_assessments WHERE run_id = %s",
        RUN_ID,
    ),
)
print(
    "claims total:",
    n("SELECT COUNT(*) as n FROM claims WHERE run_id = %s", RUN_ID),
)
print(
    "claims passed:",
    n(
        "SELECT COUNT(*) as n FROM claims WHERE run_id = %s"
        " AND validation->>'status' = 'passed'",
        RUN_ID,
    ),
)
conn.close()
