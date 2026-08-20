"""Summarize round8 failure diagnosis."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "examples/evaluation/round8_failure_diagnosis.json").read_text(encoding="utf-8"))
fails = [r for r in d["runs"] if r.get("fallback")]
print("n_fail", len(fails))
print("success", d["openai_success"], "regen", d["regenerate"], "retry", d["retry"])
print("distribution", d["failure_distribution"])
print("stages", d["failure_stages"])
c = Counter()
for r in fails:
    cause = (r.get("cause") or "")[:160]
    c[(r.get("failure_code"), cause)] += 1
for (code, cause), n in c.most_common():
    print(f"{n}\t{code}\t{cause}")
