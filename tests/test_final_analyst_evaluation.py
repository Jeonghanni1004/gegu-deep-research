"""Final Analyst Round-6 Evaluation / Benchmark / Drift tests.

Usage:
  python -m tests.test_final_analyst_evaluation
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_analyst.dotenv_load import load_dotenv

load_dotenv(ROOT / ".env")

from evidence.pack import EvidencePack
from final_analyst.evaluation_dataset import (
    list_fixture_ids,
    load_evaluation_dataset,
    validate_fixture,
)
from final_analyst.failures import classify_error_message
from final_analyst.judgment_frame import (
    compare_judgment_frame,
    extract_judgment_frame,
    frames_structurally_equal,
    judgment_signature,
)
from final_analyst.llm import GroundedFALLMClient
from final_analyst.production_gate import run_production_gate
from final_analyst.stability_bench import run_stability_benchmark
from final_analyst.synthesize import synthesize_final_analyst


def _check(name: str, cond: bool, detail="") -> dict:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"name": name, "pass": bool(cond), "detail": str(detail)[:240]}


async def main() -> None:
    results: list[dict] = []
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")

    # Ensure dataset exists
    if len(list_fixture_ids(ROOT)) < 10:
        from final_analyst.build_evaluation_dataset import main as build_main

        build_main()

    fixtures = load_evaluation_dataset(ROOT)
    results.append(_check("eval_dataset_size_ge_10", len(fixtures) >= 10, len(fixtures)))

    industries = {f.industry for f in fixtures}
    results.append(
        _check(
            "eval_industry_coverage",
            len(industries) >= 6,
            sorted(industries),
        )
    )

    structures = {s for f in fixtures for s in f.structures}
    needed = {"unresolved", "bull_supported", "bear_supported", "cross_tension", "dual_tension"}
    results.append(_check("eval_structure_coverage", needed.issubset(structures), sorted(needed - structures)))

    invalid = []
    for f in fixtures:
        errs = validate_fixture(f)
        if errs:
            invalid.append((f.fixture_id, errs[:2]))
    results.append(_check("eval_fixtures_valid", not invalid, invalid[:3]))

    # JudgmentFrame extraction + benchmark (grounded deterministic)
    client = GroundedFALLMClient(pack_for_validation=None)
    acceptable_n = 0
    total_b = 0
    for f in fixtures:
        total_b += 1
        out = await client.generate(f.input)
        actual = extract_judgment_frame(out, f.input)
        cmp = compare_judgment_frame(actual, f.expected_frame)
        if cmp.acceptable:
            acceptable_n += 1
        results.append(
            _check(
                f"benchmark_{f.fixture_id}",
                cmp.acceptable,
                f"score={cmp.score:.2f} mismatches={cmp.mismatches} actual={judgment_signature(actual)}",
            )
        )
        gate = run_production_gate(out, f.input, pack=None)
        results.append(
            _check(
                f"gate_{f.fixture_id}",
                gate.status in {"PASS", "FALLBACK_PASS"},
                gate.decision,
            )
        )

    rate = acceptable_n / total_b if total_b else 0.0
    results.append(_check("eval_benchmark_acceptable_ge_80", rate >= 0.80, f"{acceptable_n}/{total_b}={rate:.2%}"))

    # Drift: same input × 3 grounded must be identical signature
    fix = fixtures[0]
    frames = []
    for _ in range(3):
        o = synthesize_final_analyst(fix.input)
        frames.append(extract_judgment_frame(o, fix.input))
    results.append(
        _check(
            "eval_grounded_no_drift",
            all(frames_structurally_equal(frames[0], x) for x in frames[1:]),
            [judgment_signature(x) for x in frames],
        )
    )

    # Non-mechanical: E09 vs E10
    by_id = {f.fixture_id: f for f in fixtures}
    if "E09_mfg_bull_strong_mild_pressure" in by_id and "E10_semi_bull_strong_severe_pressure" in by_id:
        o9 = await client.generate(by_id["E09_mfg_bull_strong_mild_pressure"].input)
        o10 = await client.generate(by_id["E10_semi_bull_strong_severe_pressure"].input)
        f9, f10 = extract_judgment_frame(o9, by_id["E09_mfg_bull_strong_mild_pressure"].input), extract_judgment_frame(
            o10, by_id["E10_semi_bull_strong_severe_pressure"].input
        )
        results.append(
            _check(
                "eval_non_mechanical_same_resolution",
                f9.debate_state == f10.debate_state == "bull_supported"
                and judgment_signature(f9) != judgment_signature(f10),
                f"{judgment_signature(f9)} || {judgment_signature(f10)}",
            )
        )

    # Failure taxonomy unit
    r = classify_error_message("INFORMATION_LOSS: scrubbed", stage="evidence_repair")
    results.append(_check("eval_taxonomy_information_loss", r.code == "INFORMATION_LOSS", r.code))

    # Stability aggregation (shrunk, grounded-only for deterministic CI).
    # Live 10×10 openai stability belongs to formal audit via stability_bench.py.
    # Do not attach 600519 EvidencePack — evaluation fixtures span industries.
    os.environ.setdefault("FA_BENCH_FIXTURES", "3")
    os.environ.setdefault("FA_BENCH_RUNS", "2")
    stats = await run_stability_benchmark(root=ROOT, mode="grounded", n_fixtures=3, n_runs=2, pack=None)
    results.append(
        _check(
            "eval_stability_stats_written",
            stats.total_runs == 6 and (ROOT / "examples" / "evaluation" / "stability_stats.json").exists(),
            stats.to_dict(),
        )
    )
    results.append(
        _check(
            "eval_stability_no_information_loss",
            stats.information_loss == 0,
            stats.information_loss,
        )
    )
    results.append(
        _check(
            "eval_stability_no_unsupported_fact",
            stats.unsupported_external_fact == 0,
            stats.unsupported_external_fact,
        )
    )
    results.append(
        _check(
            "eval_stability_acceptable_ge_80",
            stats.to_dict()["acceptable_rate"] >= 0.80,
            stats.to_dict()["acceptable_rate"],
        )
    )
    results.append(
        _check(
            "eval_stability_grounded_no_judgment_drift",
            stats.judgment_drift == 0,
            stats.judgment_drift,
        )
    )

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\n{passed}/{total} PASS")
    print(f"benchmark_acceptable_rate={rate:.2%}")
    board = {
        "passed": passed,
        "total": total,
        "benchmark_acceptable_rate": rate,
        "stability": stats.to_dict(),
        "results": results,
    }
    (ROOT / "examples" / "evaluation" / "evaluation_scoreboard.json").write_text(
        json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
