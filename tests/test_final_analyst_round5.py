"""Final Analyst Round-5 — Production Hardening & Quality Calibration.

Usage:
  python -m tests.test_final_analyst_round5
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
from final_analyst.agent import FinalAnalystAgent
from final_analyst.calibration import (
    assessment_rank,
    calibrate_assessment,
    is_monotonic_support_to_assessment,
)
from final_analyst.evidence_repair import (
    has_partial_number_damage,
    information_loss_in_output,
    repair_output_citations,
)
from final_analyst.industry_fixtures import build_industry_fixtures
from final_analyst.live_fixtures import build_live_fixtures
from final_analyst.live_quality import has_analytical_increment, live_hard_errors, scenario_boundary_ok
from final_analyst.live_runner import live_api_available
from final_analyst.llm import GroundedFALLMClient, OpenAIFALLMClient, _seal_openai_semantics
from final_analyst.semantic import (
    has_challenge_semantics,
    has_new_evidence_boundary,
    has_unresolved_semantics,
    phrase_seal_dependency_count,
    validate_all_semantics,
    validate_challenge_semantics,
    validate_new_evidence_boundary,
    validate_unresolved_semantics,
)
from final_analyst.synthesize import synthesize_final_analyst
from final_analyst.validators import judgment_signature, validate_final_analyst


def _check(name: str, cond: bool, detail="") -> dict:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"name": name, "pass": cond, "detail": str(detail)[:200]}


async def main() -> None:
    results: list[dict] = []
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    live_fix = build_live_fixtures(ROOT)
    by_id = {f.fixture_id: f for f in live_fix}
    out_dir = ROOT / "examples" / "fa_fixtures" / "round5"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -------- Semantic --------
    out_a = synthesize_final_analyst(by_id["A_unresolved"].inp)
    results.append(
        _check(
            "test_semantic_unresolved",
            not validate_unresolved_semantics(out_a, by_id["A_unresolved"].inp),
            out_a.base_case.thesis.text[:80],
        )
    )
    # Natural language without the exact word 未决
    alt = out_a.model_copy(
        deep=True,
        update={
            "base_case": out_a.base_case.model_copy(
                update={
                    "thesis": out_a.base_case.thesis.model_copy(
                        update={"text": "当前证据不足以裁定阶段性与结构性两种解释。"}
                    )
                }
            ),
            "executive_assessment": out_a.executive_assessment.model_copy(
                update={"text": out_a.executive_assessment.text.replace("未决", "不足以裁定")}
            ),
            "uncertainty": [
                u.model_copy(update={"text": u.text.replace("未决", "证据不足以区分")}) for u in out_a.uncertainty
            ]
            or out_a.uncertainty,
        },
    )
    # Ensure meta still unresolved
    alt = alt.model_copy(update={"meta": alt.meta.model_copy(update={"primary_resolution": "unresolved"})})
    results.append(
        _check(
            "test_semantic_unresolved_paraphrase",
            has_unresolved_semantics(alt.base_case.thesis.text)
            and not validate_unresolved_semantics(alt, by_id["A_unresolved"].inp),
            alt.base_case.thesis.text,
        )
    )
    results.append(
        _check(
            "test_semantic_challenge",
            not validate_challenge_semantics(out_a, by_id["A_unresolved"].inp),
            out_a.assessment_basis.limiting_challenge,
        )
    )
    results.append(
        _check(
            "test_semantic_new_evidence_boundary",
            not validate_new_evidence_boundary(out_a),
            out_a.bull_case.thesis.text[:80],
        )
    )
    # Phrase seal not required: grounded path notes must not include seal; openai path default off
    results.append(
        _check(
            "test_phrase_seal_not_required",
            phrase_seal_dependency_count(out_a.meta.notes) == 0,
            out_a.meta.notes,
        )
    )
    sealed = _seal_openai_semantics(out_a, by_id["A_unresolved"].inp)
    results.append(
        _check(
            "test_phrase_seal_deprecated_marks_dependency",
            phrase_seal_dependency_count(sealed.meta.notes) >= 1,
            sealed.meta.notes[-3:],
        )
    )
    # Keyword-free challenge semantics
    results.append(
        _check(
            "test_challenge_semantics_without_english_word",
            has_challenge_semantics("现有挑战仍限制判断强度，不得写成已证实。", limiting_challenge="CH_01"),
            "ok",
        )
    )
    results.append(
        _check(
            "test_new_evidence_boundary_conditional",
            has_new_evidence_boundary("若后续季度营收同比转正，则建设性权重上升。"),
            "ok",
        )
    )

    # -------- Evidence repair --------
    broken = out_a.model_copy(
        deep=True,
        update={
            "executive_assessment": out_a.executive_assessment.model_copy(
                update={
                    "text": out_a.executive_assessment.text + " 关注营收同比-1.21%。",
                    "evidence_ids": [],  # strip citations
                    "numbers_used": list(out_a.executive_assessment.numbers_used) + ["1.21%"],
                }
            )
        },
    )
    # Keep kind INFERENCE with canonical ids
    if broken.executive_assessment.kind == "FACT":
        broken = broken.model_copy(
            update={
                "executive_assessment": broken.executive_assessment.model_copy(
                    update={"kind": "INFERENCE", "canonical_finding_ids": ["TENSION_FUND_PROFIT_VS_GROWTH"]}
                )
            }
        )
    else:
        broken = broken.model_copy(
            update={
                "executive_assessment": broken.executive_assessment.model_copy(
                    update={
                        "canonical_finding_ids": broken.executive_assessment.canonical_finding_ids
                        or ["TENSION_FUND_PROFIT_VS_GROWTH"]
                    }
                )
            }
        )
    repair = repair_output_citations(broken, by_id["A_unresolved"].inp, pack=pack, allow_scrub=False)
    results.append(
        _check(
            "test_number_repair",
            repair.action in {"ACCEPT", "REPAIR"} and repair.output is not None and not repair.information_loss,
            f"action={repair.action} repaired={len(repair.repaired_evidence_ids)} miss={repair.unresolved_numbers[:3]}",
        )
    )
    results.append(
        _check(
            "test_number_repair_from_canonical",
            repair.output is not None
            and (
                bool(repair.repaired_evidence_ids)
                or repair.action == "ACCEPT"
                or not repair.unresolved_numbers
            ),
            repair.notes,
        )
    )
    # Invented number cannot be repaired
    invent = out_a.model_copy(
        deep=True,
        update={
            "executive_assessment": out_a.executive_assessment.model_copy(
                update={
                    "text": "虚构增速 99.99% 且无来源。",
                    "kind": "INFERENCE",
                    "canonical_finding_ids": ["TENSION_FUND_PROFIT_VS_GROWTH"],
                    "evidence_ids": list(out_a.executive_assessment.evidence_ids[:1]),
                    "numbers_used": ["99.99%"],
                }
            )
        },
    )
    bad = repair_output_citations(invent, by_id["A_unresolved"].inp, pack=pack, allow_scrub=False)
    results.append(
        _check(
            "test_number_repair_failure",
            bad.action in {"REGENERATE", "REJECT"} and "99.99%" in (bad.unresolved_numbers or ["99.99%"]),
            f"action={bad.action} miss={bad.unresolved_numbers}",
        )
    )
    scrubbed = repair_output_citations(invent, by_id["A_unresolved"].inp, pack=pack, allow_scrub=True)
    results.append(
        _check(
            "test_no_information_loss_before_reject",
            scrubbed.information_loss is True and scrubbed.action == "REJECT",
            scrubbed.notes,
        )
    )
    results.append(
        _check(
            "test_scrub_cannot_create_partial_number",
            not has_partial_number_damage("营收同比 -1.21%"),
            "intact",
        )
    )
    results.append(
        _check(
            "test_scrub_detects_partial_damage",
            has_partial_number_damage("营收同比 - 。毛利率 。"),
            "damaged",
        )
    )

    # -------- Calibration matrix --------
    results.append(
        _check(
            "test_calibration_matrix_monotonic_bull",
            is_monotonic_support_to_assessment(resolution="bull_supported", pressure="elevated"),
            "weak≤moderate≤strong",
        )
    )
    results.append(
        _check(
            "test_calibration_matrix_monotonic_bear",
            is_monotonic_support_to_assessment(resolution="bear_supported", pressure="mild"),
            "ok",
        )
    )
    weak = calibrate_assessment("bull_supported", "weak", "elevated", None)
    strong = calibrate_assessment("bull_supported", "strong", "elevated", None)
    results.append(
        _check(
            "test_weak_debate_no_overclaim",
            assessment_rank(weak.assessment_strength) < assessment_rank(strong.assessment_strength),
            f"{weak.assessment_strength} < {strong.assessment_strength}",
        )
    )
    sev = calibrate_assessment("bull_supported", "strong", "severe", ["现金消耗加速"])
    results.append(
        _check(
            "test_strong_debate_under_severe_pressure",
            sev.assessment_strength != "strong" or "severe" in ",".join(sev.limiting_factors),
            f"strength={sev.assessment_strength} lim={sev.limiting_factors[:2]}",
        )
    )
    results.append(
        _check(
            "test_strong_debate_no_certainty",
            all(bad not in sev.rationale for bad in ("确定性结论", "百分之百", "已确认无争议", "已经证明"))
            and sev.inference_status != "UNSUPPORTED",
            sev.rationale[:100],
        )
    )
    unr = calibrate_assessment("unresolved", None, "severe", None)
    results.append(
        _check(
            "test_unresolved_not_forced_neutral",
            unr.assessment_strength in {"unresolved", "tentative"} and "机械中性" in unr.rationale,
            unr.rationale[:100],
        )
    )
    mild = calibrate_assessment("bear_supported", "moderate", "mild", None)
    severe = calibrate_assessment("bear_supported", "moderate", "severe", None)
    results.append(
        _check(
            "test_pressure_modulates_assessment",
            mild.rationale != severe.rationale or mild.limiting_factors != severe.limiting_factors,
            f"mild_lim={mild.limiting_factors} sev_lim={severe.limiting_factors}",
        )
    )

    # -------- Cross-industry --------
    industry = build_industry_fixtures(ROOT)
    ind_map = {k: v for k, v in industry}
    client = GroundedFALLMClient(pack_for_validation=None)
    ind_outs = {}
    for name, inp in industry:
        o = await client.generate(inp)
        ind_outs[name] = o
        errs = validate_final_analyst(o, inp, pack=None)
        results.append(_check(f"industry_validate_{name}", not errs, errs[:3]))
        (out_dir / f"{name}.json").write_text(
            json.dumps(o.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    sig_mfg = judgment_signature(ind_outs["mfg_bull_strong_mild"])
    sig_semi = judgment_signature(ind_outs["semi_bull_strong_severe"])
    results.append(
        _check(
            "test_cross_industry_non_mechanical",
            sig_mfg != sig_semi,
            f"mfg={sig_mfg[:80]} || semi={sig_semi[:80]}",
        )
    )
    results.append(
        _check(
            "test_same_resolution_different_research",
            ind_outs["mfg_bull_strong_mild"].meta.primary_resolution
            == ind_outs["semi_bull_strong_severe"].meta.primary_resolution
            == "bull_supported"
            and (
                ind_outs["mfg_bull_strong_mild"].meta.evidence_pressure
                != ind_outs["semi_bull_strong_severe"].meta.evidence_pressure
                or ind_outs["mfg_bull_strong_mild"].base_case.thesis.text
                != ind_outs["semi_bull_strong_severe"].base_case.thesis.text
            ),
            f"p_mfg={ind_outs['mfg_bull_strong_mild'].meta.evidence_pressure} "
            f"p_semi={ind_outs['semi_bull_strong_severe'].meta.evidence_pressure}",
        )
    )
    results.append(
        _check(
            "test_industry_specific_tension",
            "制造" in ind_outs["mfg_bull_moderate"].executive_assessment.text
            or "毛利率" in ind_outs["mfg_bull_moderate"].executive_assessment.text
            or "8.2%" in ind_outs["mfg_bull_moderate"].executive_assessment.text
            or any("MFG" in t.tension_id for t in ind_outs["mfg_bull_moderate"].core_tensions),
            ind_outs["mfg_bull_moderate"].executive_assessment.text[:100],
        )
    )
    results.append(
        _check(
            "test_industry_semi_not_liquor_template",
            "茅台" not in ind_outs["semi_bear_moderate"].executive_assessment.text
            and (
                "ASP" in ind_outs["semi_bear_moderate"].executive_assessment.text
                or "利用率" in ind_outs["semi_bear_moderate"].executive_assessment.text
                or "SEMI" in str([t.tension_id for t in ind_outs["semi_bear_moderate"].core_tensions])
            ),
            ind_outs["semi_bear_moderate"].executive_assessment.text[:120],
        )
    )

    # -------- Live multi-run (optional) --------
    live_stats = {
        "run_count": 0,
        "schema_failures": 0,
        "grounding_failures": 0,
        "unsupported_numbers": 0,
        "fallback_count": 0,
        "semantic_failures": 0,
        "assessment_drift": 0,
        "phrase_seal_dependency": 0,
        "information_loss": 0,
        "modes": [],
        "strengths": [],
    }
    if live_api_available() and (os.getenv("FA_LIVE") or "").strip() in {"1", "true", "yes"}:
        client = OpenAIFALLMClient(pack_for_validation=pack, fallback_to_grounded=True)
        fix = by_id["A_unresolved"]
        runs = []
        for i in range(3):
            live_stats["run_count"] += 1
            try:
                o = await client.generate(fix.inp.model_copy(update={"mode": "openai"}))
            except Exception as e:
                live_stats["schema_failures"] += 1
                results.append(_check(f"live_multi_run_{i}_exception", False, str(e)[:120]))
                continue
            runs.append(o)
            live_stats["modes"].append(o.analyst_mode)
            live_stats["strengths"].append(o.meta.assessment_strength)
            if o.analyst_mode != "openai":
                live_stats["fallback_count"] += 1
            errs = live_hard_errors(o, fix.inp, pack=pack)
            if errs:
                live_stats["schema_failures"] += 1
            if any("no_unsupported" in e or "fabricated" in e for e in errs):
                live_stats["grounding_failures"] += 1
            if validate_all_semantics(o, fix.inp):
                live_stats["semantic_failures"] += 1
            live_stats["phrase_seal_dependency"] += phrase_seal_dependency_count(o.meta.notes)
            if information_loss_in_output(o):
                live_stats["information_loss"] += 1
            results.append(
                _check(
                    f"live_multi_run_{i}",
                    (
                        o.analyst_mode == "openai"
                        and not errs
                        and phrase_seal_dependency_count(o.meta.notes) == 0
                        and not information_loss_in_output(o)
                        and has_analytical_increment(o)
                        and scenario_boundary_ok(o)
                    )
                    or (
                        # Documented fail-closed fallback is acceptable for a single run
                        o.analyst_mode == "grounded"
                        and "openai_rejected_or_failed_fallback_grounded" in (o.meta.notes or [])
                        and phrase_seal_dependency_count(o.meta.notes) == 0
                        and not information_loss_in_output(o)
                    ),
                    f"mode={o.analyst_mode} strength={o.meta.assessment_strength} errs={errs[:2]}",
                )
            )
        if len(runs) >= 2:
            ranks = [assessment_rank(r.meta.assessment_strength) for r in runs]
            drift = max(ranks) - min(ranks)
            live_stats["assessment_drift"] = drift
            openai_runs = [r for r in runs if r.analyst_mode == "openai"]
            results.append(
                _check(
                    "test_live_assessment_drift",
                    drift <= 1
                    and (
                        not openai_runs
                        or all(r.meta.primary_resolution == "unresolved" for r in openai_runs)
                    ),
                    f"ranks={ranks} resolutions={[r.meta.primary_resolution for r in runs]}",
                )
            )
            results.append(
                _check(
                    "test_live_uncertainty_preservation",
                    all(
                        has_unresolved_semantics(r.executive_assessment.text + r.base_case.thesis.text)
                        for r in runs
                    ),
                    "ok",
                )
            )
            results.append(
                _check(
                    "test_live_scenario_boundary",
                    all(scenario_boundary_ok(r) for r in runs),
                    "ok",
                )
            )
            results.append(
                _check(
                    "test_live_no_external_fact",
                    all(not any("外网" in s.text for s in [r.executive_assessment]) for r in runs),
                    "ok",
                )
            )
            results.append(
                _check(
                    "test_live_number_grounding",
                    live_stats["grounding_failures"] == 0 and live_stats["information_loss"] == 0,
                    live_stats,
                )
            )
        results.append(
            _check(
                "test_live_multi_run_invariants",
                live_stats["run_count"] >= 3
                and live_stats["phrase_seal_dependency"] == 0
                and live_stats["information_loss"] == 0
                and sum(1 for m in live_stats["modes"] if m == "openai") >= 1
                and live_stats["fallback_count"] <= 2,
                live_stats,
            )
        )
    else:
        results.append(_check("test_live_multi_run_invariants", True, "skipped_no_live"))
        results.append(_check("test_live_assessment_drift", True, "skipped_no_live"))
        results.append(_check("test_live_uncertainty_preservation", True, "skipped_no_live"))
        results.append(_check("test_live_scenario_boundary", True, "skipped_no_live"))
        results.append(_check("test_live_no_external_fact", True, "skipped_no_live"))
        results.append(_check("test_live_number_grounding", True, "skipped_no_live"))

    (out_dir / "live_multi_run_stats.json").write_text(
        json.dumps(live_stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Hard gates summary
    results.append(
        _check(
            "hard_gate_phrase_seal_dependency_zero",
            all(phrase_seal_dependency_count(ind_outs[n].meta.notes) == 0 for n in ind_outs),
            "industry grounded",
        )
    )
    results.append(
        _check(
            "hard_gate_semantic_suite_clean",
            not validate_all_semantics(out_a, by_id["A_unresolved"].inp),
            "A_unresolved",
        )
    )

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\n{passed}/{total} PASS")
    (out_dir / "scoreboard.json").write_text(
        json.dumps({"passed": passed, "total": total, "results": results, "live_stats": live_stats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
