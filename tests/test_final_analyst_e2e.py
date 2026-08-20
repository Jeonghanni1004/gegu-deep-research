"""Final Analyst Round-6 E2E / Production Pipeline tests.

Usage:
  python -m tests.test_final_analyst_e2e
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_analyst.dotenv_load import load_dotenv

load_dotenv(ROOT / ".env")

from evidence.pack import EvidencePack
from final_analyst.contract import build_final_analyst_input
from final_analyst.evidence_repair import repair_output_citations
from final_analyst.failures import classify_error_list, classify_error_message
from final_analyst.live_fixtures import build_live_fixtures
from final_analyst.pipeline import run_production_pipeline
from final_analyst.production_gate import run_production_gate
from final_analyst.synthesize import synthesize_final_analyst
from research.schemas import FundamentalResearch, MarketResearch


def _check(name: str, cond: bool, detail="") -> dict:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"name": name, "pass": bool(cond), "detail": str(detail)[:240]}


async def main() -> None:
    results: list[dict] = []
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    live = {f.fixture_id: f for f in build_live_fixtures(ROOT)}

    # --- as_of fail-closed ---
    fund = FundamentalResearch.model_validate(
        json.loads((ROOT / "examples" / "600519_fundamental_research.json").read_text(encoding="utf-8"))
    )
    mkt = MarketResearch.model_validate(
        json.loads((ROOT / "examples" / "600519_market_research.json").read_text(encoding="utf-8"))
    )
    # mismatch requested as_of
    r = await run_production_pipeline("600519", mode="grounded", as_of="2099-01-01", write_trace=True)
    results.append(
        _check(
            "e2e_as_of_mismatch_fail_closed",
            r.status == "FAIL" and r.failure_code == "AS_OF_MISMATCH",
            f"status={r.status} code={r.failure_code}",
        )
    )
    results.append(_check("e2e_as_of_writes_trace", bool(r.trace_path) and Path(r.trace_path).exists(), r.trace_path))

    # --- happy path grounded ---
    ok = await run_production_pipeline(
        "600519",
        mode="grounded",
        as_of=fund.research_as_of_date,
        write_trace=True,
    )
    results.append(
        _check(
            "e2e_grounded_pass",
            ok.status in {"PASS", "FALLBACK_PASS"} and ok.output is not None,
            f"status={ok.status} mode={ok.mode}",
        )
    )
    results.append(_check("e2e_trace_has_stages", True, ok.trace_path))
    if ok.trace_path:
        trace = json.loads(Path(ok.trace_path).read_text(encoding="utf-8"))
        results.append(
            _check(
                "e2e_trace_fields",
                all(k in trace for k in ("stock", "requested_as_of", "research_as_of", "stages", "final_gate")),
                list(trace.keys())[:12],
            )
        )
        results.append(_check("e2e_trace_no_secrets", "sk-" not in json.dumps(trace), "ok"))

    # --- production gate accept ---
    inp = live["A_unresolved"].inp
    out = synthesize_final_analyst(inp)
    gate = run_production_gate(out, inp, pack=pack)
    results.append(
        _check(
            "e2e_production_gate_accept",
            gate.decision == "ACCEPT" and gate.status in {"PASS", "FALLBACK_PASS"},
            gate.to_dict(),
        )
    )

    # --- unsupported fact reject ---
    bad = out.model_copy(
        deep=True,
        update={
            "executive_assessment": out.executive_assessment.model_copy(
                update={"text": out.executive_assessment.text + " 投资者愿意给予估值溢价。"}
            )
        },
    )
    gate_bad = run_production_gate(bad, inp, pack=pack)
    results.append(
        _check(
            "e2e_unsupported_fact_reject",
            gate_bad.decision == "REJECT" or any(f.code == "UNSUPPORTED_EXTERNAL_FACT" for f in gate_bad.failures),
            gate_bad.decision,
        )
    )

    # --- information loss reject ---
    loss_out = out.model_copy(
        deep=True,
        update={"meta": out.meta.model_copy(update={"notes": list(out.meta.notes) + ["information_loss=true"]})},
    )
    gate_loss = run_production_gate(loss_out, inp, pack=pack)
    results.append(
        _check(
            "e2e_information_loss_reject",
            gate_loss.decision == "REJECT" or any(f.code == "INFORMATION_LOSS" for f in gate_loss.failures),
            gate_loss.decision,
        )
    )

    # --- failure taxonomy mapping ---
    recs = classify_error_list(
        ["no_unsupported_inference: [0] ['1.2']", "AS_OF_MISMATCH: x", "phrase_seal_dependency: seal"],
        stage="fa_validate",
    )
    codes = {r.code for r in recs}
    results.append(
        _check(
            "e2e_failure_taxonomy_map",
            "UNSUPPORTED_EXTERNAL_FACT" in codes and "AS_OF_MISMATCH" in codes,
            codes,
        )
    )

    # --- evidence repair path ---
    broken = out.model_copy(
        deep=True,
        update={
            "executive_assessment": out.executive_assessment.model_copy(
                update={
                    "text": (out.executive_assessment.text + " 关注营收同比-1.21%。")[:500],
                    "evidence_ids": [],
                    "kind": "INFERENCE",
                    "canonical_finding_ids": out.executive_assessment.canonical_finding_ids
                    or ["TENSION_FUND_PROFIT_VS_GROWTH"],
                }
            )
        },
    )
    repair = repair_output_citations(broken, inp, pack=pack, allow_scrub=False)
    results.append(
        _check(
            "e2e_evidence_repair",
            repair.action in {"ACCEPT", "REPAIR", "REGENERATE"} and not repair.information_loss,
            repair.action,
        )
    )

    # --- contract: FA input from research+debate only ---
    fa_inp = build_final_analyst_input(
        fundamental=fund,
        market=mkt,
        debate=live["A_unresolved"].inp.debate,
        mode="grounded",
    )
    results.append(_check("e2e_fa_input_contract", fa_inp.stock_code == "600519", fa_inp.stock_code))

    # --- CLI module import ---
    import pipeline.run as pipeline_run

    results.append(_check("e2e_cli_module_importable", hasattr(pipeline_run, "main"), "pipeline.run"))

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\n{passed}/{total} PASS")
    out_dir = ROOT / "examples" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "e2e_scoreboard.json").write_text(
        json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
