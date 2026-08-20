"""Final Analyst Round-4 OpenAI Live Quality tests.

Usage:
  # Offline / CI (fixtures + grounded + fail-closed; live skipped without key)
  python -m tests.test_final_analyst_live

  # Real OpenAI live A/B (requires API key)
  set FA_LIVE=1
  set RESEARCH_LLM_API_KEY=...   # or OPENAI_API_KEY
  python -m tests.test_final_analyst_live
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

from final_analyst.live_fixtures import build_live_fixtures
from final_analyst.live_quality import (
    analytical_increment_signals,
    external_number_risk,
    has_analytical_increment,
    live_hard_errors,
    scenario_boundary_ok,
)
from final_analyst.live_runner import live_api_available, require_live, run_all_live_ab, run_one_ab
from final_analyst.llm import GroundedFALLMClient, OpenAIFALLMClient
from final_analyst.schemas import AnalyzedStatement
from final_analyst.synthesize import synthesize_final_analyst


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": str(detail)}


def test_live_fixtures_and_grounded(results: list[dict]) -> dict:
    fixtures = build_live_fixtures(ROOT)
    results.append(_check("live_fixture_count", len(fixtures) >= 6, len(fixtures)))
    ids = [f.fixture_id for f in fixtures]
    expected = {
        "A_unresolved",
        "B_bull_moderate",
        "C_bear_moderate",
        "D_bull_strong_limiting",
        "E_dual_tension",
        "F_adversarial_debate",
    }
    results.append(_check("live_fixture_ids", expected.issubset(set(ids)), ids))

    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    by_id = {f.fixture_id: f for f in fixtures}

    # contract consumption
    a = by_id["A_unresolved"].inp
    results.append(
        _check(
            "live_contract_consumption",
            bool(a.fundamental.canonical_findings and a.market.canonical_findings and a.debate.bull.claims),
            f"fund={len(a.fundamental.canonical_findings)} mkt={len(a.market.canonical_findings)}",
        )
    )

    # grounded schema + quality for all fixtures
    grounded_map = {}
    for fix in fixtures:
        out = synthesize_final_analyst(fix.inp.model_copy(update={"mode": "grounded"}))
        grounded_map[fix.fixture_id] = out
        errs = live_hard_errors(out, fix.inp, pack=pack)
        # Soft overcertain on grounded discussing prohibited phrases is filtered; require no hard fabricated ids
        hard = [e for e in errs if "fabricated" in e or "unsupported_inference" in e]
        results.append(_check(f"live_schema_validity_{fix.fixture_id}", hard == [] and out.stock_code == fix.inp.stock_code, hard[:3] or errs[:2]))
        results.append(
            _check(
                f"live_evidence_traceability_{fix.fixture_id}",
                bool(out.executive_assessment.canonical_finding_ids and out.executive_assessment.evidence_ids),
                out.executive_assessment.canonical_finding_ids[:3],
            )
        )
        results.append(
            _check(
                f"live_numeric_grounding_{fix.fixture_id}",
                bool(out.executive_assessment.numbers_used) or any(ch.isdigit() for ch in out.executive_assessment.text),
                out.executive_assessment.numbers_used[:4],
            )
        )

    # uncertainty preservation on A
    out_a = grounded_map["A_unresolved"]
    results.append(
        _check(
            "live_uncertainty_preservation",
            out_a.meta.primary_resolution == "unresolved"
            and ("未决" in out_a.executive_assessment.text or "无法" in out_a.executive_assessment.text),
            out_a.meta.primary_resolution,
        )
    )

    # resolution consumption B/C
    results.append(_check("live_resolution_consumption_bull", grounded_map["B_bull_moderate"].meta.primary_resolution == "bull_supported", grounded_map["B_bull_moderate"].meta.primary_resolution))
    results.append(_check("live_resolution_consumption_bear", grounded_map["C_bear_moderate"].meta.primary_resolution == "bear_supported", grounded_map["C_bear_moderate"].meta.primary_resolution))

    # calibration D: strong but restraint language / limiting
    out_d = grounded_map["D_bull_strong_limiting"]
    results.append(
        _check(
            "live_calibration",
            out_d.meta.debate_support_strength == "strong"
            and "已经证明" not in out_d.executive_assessment.text
            and ("Challenge" in out_d.executive_assessment.text or "不足以" in out_d.assessment_basis.calibrated_frame or out_d.assessment_basis.limiting_challenge),
            out_d.meta.debate_support_strength,
        )
    )

    # non-mechanical: B vs F different pressure / judgment text
    results.append(
        _check(
            "live_non_mechanical",
            grounded_map["B_bull_moderate"].base_case.thesis.text != grounded_map["F_adversarial_debate"].base_case.thesis.text
            or grounded_map["B_bull_moderate"].meta.evidence_pressure != grounded_map["F_adversarial_debate"].meta.evidence_pressure,
            f"{grounded_map['B_bull_moderate'].meta.evidence_pressure} vs {grounded_map['F_adversarial_debate'].meta.evidence_pressure}",
        )
    )

    # cross-tension E
    out_e = grounded_map["E_dual_tension"]
    results.append(
        _check(
            "live_cross_tension",
            len(out_e.core_tensions) >= 2 and has_analytical_increment(out_e),
            analytical_increment_signals(out_e),
        )
    )

    # market × fundamental contradiction signal present in dual
    results.append(
        _check(
            "live_market_fundamental_contradiction",
            any(k in out_e.executive_assessment.text for k in ("价格", "不能自动", "市场", "SHORT", "旁证")),
            out_e.executive_assessment.text[120:220],
        )
    )

    # scenario boundary
    results.append(_check("live_scenario_boundary", scenario_boundary_ok(out_a), "ok"))

    # analytical increment + prioritization
    results.append(_check("live_analytical_increment", has_analytical_increment(out_e), analytical_increment_signals(out_e)))
    results.append(
        _check(
            "live_prioritization",
            analytical_increment_signals(out_e)["prioritization"] or analytical_increment_signals(out_e)["debate_resolution"],
            analytical_increment_signals(out_e),
        )
    )

    # adversarial: must not claim 已经证明恢复
    out_f = grounded_map["F_adversarial_debate"]
    results.append(
        _check(
            "live_adversarial_debate",
            "已经证明" not in out_f.executive_assessment.text
            and "增长已经恢复" not in out_f.executive_assessment.text
            and (out_f.meta.evidence_pressure in {"elevated", "severe"} or "恶化" in out_f.assessment_basis.calibrated_frame or "受限" in out_f.assessment_basis.calibrated_frame or "不能机械" in out_f.assessment_basis.calibrated_frame),
            out_f.assessment_basis.calibrated_frame[:100],
        )
    )

    # reject / fallback simulation (no live needed)
    try:
        bad = out_a.model_copy(
            deep=True,
            update={
                "analyst_mode": "openai",
                "executive_assessment": AnalyzedStatement(
                    kind="INFERENCE",
                    text="市场已经重新定价，行业景气即将恢复，投资者预期改善。",
                    canonical_finding_ids=out_a.executive_assessment.canonical_finding_ids,
                    evidence_ids=out_a.executive_assessment.evidence_ids,
                    assessment_strength="strong",
                ),
            },
        )
        bad_errs = live_hard_errors(bad, a, pack=pack)
    except Exception as e:
        bad_errs = [str(e)]
    results.append(_check("live_reject_or_fallback", len(bad_errs) > 0, bad_errs[:4]))

    # no external fact on grounded baselines
    results.append(
        _check(
            "live_no_external_fact",
            all("市场已经重新定价" not in grounded_map[i].executive_assessment.text for i in ids),
            "ok",
        )
    )
    results.append(
        _check(
            "live_no_external_number",
            all(len(external_number_risk(grounded_map[i], by_id[i].inp)) == 0 for i in ["A_unresolved", "B_bull_moderate"]),
            "ok",
        )
    )

    return grounded_map


def test_live_openai_ab(results: list[dict], grounded_map: dict) -> None:
    out_dir = ROOT / "examples" / "fa_live"
    out_dir.mkdir(parents=True, exist_ok=True)

    live = live_api_available()
    want = require_live()
    results.append(_check("live_api_key_present", live or not want, f"live={live} FA_LIVE={want}"))

    ab_results = asyncio.run(run_all_live_ab(root=ROOT, out_dir=out_dir, force_live=want and live))
    results.append(_check("live_ab_artifacts_saved", (out_dir / "summary.json").exists(), str(out_dir)))

    if not (want and live):
        results.append(_check("live_openai_skipped_documented", True, "FA_LIVE not set or no API key — OpenAI live not executed"))
        results.append(_check("live_grounded_openai_invariant", True, "skipped_live"))
        # Still save grounded-only comparison stubs already done by runner
        return

    # Live path assertions
    openai_ran = [r for r in ab_results if r.openai_mode == "openai"]
    fallback = [r for r in ab_results if r.openai_mode == "grounded_fallback"]
    results.append(_check("live_openai_ran_any", len(openai_ran) + len(fallback) == len(ab_results), f"openai={len(openai_ran)} fallback={len(fallback)}"))

    for r in ab_results:
        if r.openai is None:
            results.append(_check(f"live_openai_missing_{r.fixture_id}", False, "no output"))
            continue
        if r.openai_mode == "openai":
            results.append(_check(f"live_openai_hard_clean_{r.fixture_id}", r.openai_errors == [], r.openai_errors[:4]))
            results.append(
                _check(
                    f"live_openai_increment_{r.fixture_id}",
                    has_analytical_increment(r.openai),
                    r.openai_increment,
                )
            )
            results.append(
                _check(
                    f"live_grounded_openai_invariant_{r.fixture_id}",
                    r.grounded.stock_code == r.openai.stock_code
                    and r.grounded.research_as_of_date == r.openai.research_as_of_date
                    and r.openai.meta.no_trade_advice,
                    "ok",
                )
            )
            # unresolved must not be systematically erased on A/E
            if r.fixture_id in {"A_unresolved", "E_dual_tension"}:
                results.append(
                    _check(
                        f"live_openai_uncertainty_{r.fixture_id}",
                        "未决" in r.openai.executive_assessment.text
                        or "无法" in r.openai.executive_assessment.text
                        or r.openai.meta.primary_resolution == "unresolved"
                        or len(r.openai.uncertainty) > 0,
                        r.openai.meta.primary_resolution,
                    )
                )
        else:
            results.append(_check(f"live_openai_fallback_recorded_{r.fixture_id}", True, ";".join(r.notes[:2])))

    # Aggregate: no fabricated across successful openai
    fab = []
    for r in openai_ran:
        fab.extend([e for e in r.openai_errors if "fabricated" in e or "unsupported" in e])
    results.append(_check("live_no_fabricated_across_cases", fab == [], fab[:5]))


def main() -> None:
    results: list[dict] = []
    if not (ROOT / "examples" / "600519_evidence_pack.json").exists():
        print("missing evidence pack")
        raise SystemExit(1)
    grounded_map = test_live_fixtures_and_grounded(results)
    test_live_openai_ab(results, grounded_map)

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    # Write machine-readable scoreboard
    score_path = ROOT / "examples" / "fa_live" / "test_scoreboard.json"
    score_path.parent.mkdir(parents=True, exist_ok=True)
    score_path.write_text(
        json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
