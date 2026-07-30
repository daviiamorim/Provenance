"""Quick smoke test: call GET /datasets and GET /runs/{id}/report via TestClient."""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient

from api.main import app

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"

client = TestClient(app, raise_server_exceptions=False)

r = client.get("/datasets")
print(f"GET /datasets → {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  {len(data)} dataset(s) retornados")
    for d in data:
        print(f"  id={d['id']}  manifest={d['manifest']}")
else:
    print(f"  ERRO: {r.text[:300]}")

print()
r2 = client.get(f"/runs/{RUN_ID}/report")
print(f"GET /runs/{RUN_ID}/report → {r2.status_code}")
if r2.status_code == 200:
    rep = r2.json()
    print(f"  dataset_name: {rep['dataset_name']}")
    print(f"  counts: {rep['counts']}")
    print(f"  sections: {len(rep['sections'])}")
    for s in rep["sections"]:
        print(f"    [{s['goal']}] {len(s['claims'])} claim(s)")
        for c in s["claims"]:
            print(f"      [{c['severity'].upper()}] {c['text'][:70]}...")
            print(f"             supports: {c['supports']}")
else:
    print(f"  ERRO: {r2.text[:300]}")
