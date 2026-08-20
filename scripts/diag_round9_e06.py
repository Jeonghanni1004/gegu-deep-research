"""Round-9 pre-code diagnosis: E06 100% / 1347.13 vs matcher."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from final_analyst.contract import all_canonical
from final_analyst.evaluation_dataset import load_fixture
from final_analyst.evidence_repair import (
    _build_evidence_index,
    _match_token_eids,
    _token_variants,
    repair_output_citations,
)
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.synthesize import synthesize_final_analyst
from research.citation import extract_fact_tokens


def main() -> None:
    fix = load_fixture("E06_adversarial_fund_pressure", ROOT)
    inp = fix.input
    blob = json.dumps(inp.model_dump(), ensure_ascii=False)

    print("=== literal occurrences in INPUT JSON ===")
    for n in ["100%", "100.0%", "1347.13", "1347.1280", "1347.128", "1341.99"]:
        print(f"  {n!r}: count={blob.count(n)}")

    preserved: list[str] = []
    for c in all_canonical(inp):
        preserved.extend(str(x) for x in (c.numbers_preserved or []))
    print("\n=== numbers_preserved with 100 or 1347 ===")
    for p in preserved:
        if "100" in p or "1347" in p:
            print(" ", p)

    # claim snippets containing 100
    print("\n=== claim snippets with '100' ===")
    for c in all_canonical(inp):
        if "100" in (c.claim or ""):
            print(" ", c.finding_id, ":", (c.claim or "")[:160])
    for cl in list(inp.debate.bull.claims) + list(inp.debate.bear.claims):
        if "100" in (cl.claim or ""):
            print("  debate:", (cl.claim or "")[:160])

    by_id, tm, _ = _build_evidence_index(inp, None)
    print("\n=== token_map keys containing 1347 or exact 100% ===")
    for k in sorted(tm):
        if "1347" in k or k in {"100%", "100", "100.0%", "100.0"}:
            print(f"  {k!r} -> {tm[k][:3]} (n={len(tm[k])})")

    print("\n=== _match_token_eids ===")
    for t in ["100%", "100", "1347.13", "1347.1280", "1347.1", "1347", "99.99123%"]:
        print(f"  {t!r} -> {_match_token_eids(t, tm)[:4]}")

    print("\n=== soft-match geometry 1347.13 vs 1347.1280 ===")
    bare, kb = "1347.13", "1347.1280"
    print("  startswith either way:", bare.startswith(kb), kb.startswith(bare))
    print("  variants(1347.1280):", _token_variants("1347.1280"))
    print("  variants(1347.13):", _token_variants("1347.13"))

    # Mutate grounded with problem tokens
    out = synthesize_final_analyst(inp.model_copy(update={"mode": "grounded"}))
    d = out.model_dump()
    d["executive_assessment"]["text"] = d["executive_assessment"]["text"] + " 另见 100% 与 1347.13。"
    mutated = FinalAnalystOutput.model_validate(d)
    print("\n=== extract_fact_tokens from mutated text ===")
    print(extract_fact_tokens(mutated.executive_assessment.text)[-10:])

    r = repair_output_citations(mutated, inp, pack=None, allow_scrub=False)
    print("repair action", r.action, "unresolved", r.unresolved_numbers)

    # Also test 100% alone and 1347.13 alone
    for extra in [" 另见 100%。", " 另见 1347.13。", " 另见 1347.1280。"]:
        d2 = out.model_dump()
        d2["executive_assessment"]["text"] = d2["executive_assessment"]["text"] + extra
        r2 = repair_output_citations(FinalAnalystOutput.model_validate(d2), inp, pack=None, allow_scrub=False)
        print(f"extra={extra!r} -> {r2.action} unresolved={r2.unresolved_numbers}")

    # Ambiguity: how many distinct eids for 1347 family
    eids_1347 = set()
    for k, eids in tm.items():
        if "1347" in k:
            eids_1347.update(eids)
    print("\n=== distinct evidence_ids for 1347* keys ===", len(eids_1347), sorted(eids_1347)[:8])

    # Where does 100 appear as substring false positive risk
    print("\n=== tokens extracted from INPUT that equal 100% or 100 ===")
    all_toks = set()
    for c in all_canonical(inp):
        all_toks.update(extract_fact_tokens((c.claim or "") + " " + " ".join(c.numbers_preserved or [])))
    print("  ", [t for t in sorted(all_toks) if t in {"100", "100%", "100.0", "100.0%"} or t.startswith("100")])


if __name__ == "__main__":
    main()
