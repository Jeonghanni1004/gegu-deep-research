"""Restore official R8 formal 10x10 from first completed stdout; archive quota run."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ev = ROOT / "examples" / "evaluation"

# Archive quota-exhausted overwrite if present
cur = ev / "stability_10x10_openai_r8.json"
if cur.exists():
    data = json.loads(cur.read_text(encoding="utf-8"))
    if data.get("openai_success") == 32:
        (ev / "stability_10x10_openai_r8_quota_exhaust.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

# Restore from first formal stdout (complete 100-run before concurrent quota collision)
stdout = (ev / "r8_formal_10x10_stdout.txt").read_text(encoding="utf-8")
official = json.loads(stdout)
assert official["total_runs"] == 100
assert official["openai_success"] == 84
cur.write_text(json.dumps(official, ensure_ascii=False, indent=2), encoding="utf-8")
(ev / "stability_10x10_openai.json").write_text(
    json.dumps(official, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Rebuild diagnosis from official attributions
dist: dict[str, int] = {
    "PROVIDER_FAILURE": 0,
    "VALIDATION_FAILURE": 0,
    "EVIDENCE_REPAIR_FAILURE": 0,
    "JSON_PARSE_FAILURE": 0,
    "SCHEMA_SANITIZATION_FAILURE": 0,
}
stages: dict[str, int] = {}
for code, n in (official.get("failure_codes_before_fallback") or {}).items():
    dist[code] = n
for stage, n in (official.get("failure_stages") or {}).items():
    stages[stage] = n

diag = {
    "total_runs": official["total_runs"],
    "openai_success": official["openai_success"],
    "fallback": official["grounded_fallback"],
    "regenerate": official.get("regenerate", 0),
    "retry": official.get("retry", 0),
    "acceptable": official["acceptable"],
    "failure_distribution": dist,
    "failure_stages": stages,
    "runs": official.get("run_attributions") or [],
    "source": "r8_formal_10x10_stdout.txt (first completed formal 10x10)",
    "note": "Concurrent second run hit DeepSeek HTTP 402 and overwrote artifacts; archived as *_quota_exhaust.json",
}
(ev / "round8_failure_diagnosis.json").write_text(
    json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
)

fails = [r for r in diag["runs"] if r.get("fallback")]
print("restored openai_success", official["openai_success"])
print("fallback", len(fails))
print("distribution", dist)
for r in fails:
    print(r.get("failure_code"), "|", (r.get("cause") or "")[:140])
