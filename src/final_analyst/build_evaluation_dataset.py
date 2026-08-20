"""Build ≥10 evaluation fixtures under examples/evaluation/ (Round 6).

Run: python -m final_analyst.build_evaluation_dataset
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_analyst.evaluation_dataset import EvaluationFixture, write_fixture
from final_analyst.industry_fixtures import build_industry_fixtures
from final_analyst.judgment_frame import JudgmentFrame
from final_analyst.live_fixtures import build_live_fixtures


def _frame(**kwargs) -> JudgmentFrame:
    return JudgmentFrame(**kwargs)


def main() -> None:
    live = {f.fixture_id: f for f in build_live_fixtures(ROOT)}
    industry = {k: v for k, v in build_industry_fixtures(ROOT)}

    specs: list[EvaluationFixture] = []

    # 1 profit strong / growth weak + unresolved (consumer)
    specs.append(
        EvaluationFixture(
            fixture_id="E01_consumer_profit_strong_growth_weak_unresolved",
            title="盈利强+增长弱 / unresolved",
            industry="消费",
            structures=["profit_strong_growth_weak", "unresolved"],
            metadata={"source": "live:A_unresolved"},
            input=live["A_unresolved"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                assessment_strength="unresolved",
                debate_state="unresolved",
                scenario_direction="conditional",
                uncertainty_state="preserved",
                cross_tension=True,
            ),
        )
    )

    # 2 bull_supported moderate
    specs.append(
        EvaluationFixture(
            fixture_id="E02_consumer_bull_supported_moderate",
            title="bull_supported moderate",
            industry="消费",
            structures=["bull_supported"],
            metadata={"source": "live:B_bull_moderate"},
            input=live["B_bull_moderate"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                assessment_strength="moderate",
                debate_state="bull_supported",
                support_strength="moderate",
                scenario_direction="conditional",
                uncertainty_state="preserved",
            ),
        )
    )

    # 3 bear_supported
    specs.append(
        EvaluationFixture(
            fixture_id="E03_consumer_bear_supported_moderate",
            title="bear_supported moderate",
            industry="消费",
            structures=["bear_supported"],
            metadata={"source": "live:C_bear_moderate"},
            input=live["C_bear_moderate"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                assessment_strength="moderate",
                debate_state="bear_supported",
                support_strength="moderate",
                scenario_direction="conditional",
            ),
        )
    )

    # 4 strong + limiting / severe-ish challenge pressure
    specs.append(
        EvaluationFixture(
            fixture_id="E04_consumer_strong_limiting_challenge",
            title="strong support + limiting challenge",
            industry="消费",
            structures=["strong_support_severe_challenge"],
            metadata={"source": "live:D_bull_strong_limiting"},
            input=live["D_bull_strong_limiting"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                assessment_strength="strong",
                debate_state="bull_supported",
                support_strength="strong",
                scenario_direction="conditional",
                uncertainty_state="preserved",
            ),
        )
    )

    # 5 dual tension + cross-tension
    specs.append(
        EvaluationFixture(
            fixture_id="E05_consumer_dual_tension_cross",
            title="dual tension + cross-tension",
            industry="消费",
            structures=["dual_tension", "cross_tension", "fundamental_market_unclear"],
            metadata={"source": "live:E_dual_tension"},
            input=live["E_dual_tension"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                debate_state="unresolved",
                assessment_strength="unresolved",
                scenario_direction="conditional",
                cross_tension=True,
                uncertainty_state="preserved",
            ),
        )
    )

    # 6 adversarial / fund weak narrative vs misleading bull
    specs.append(
        EvaluationFixture(
            fixture_id="E06_adversarial_fund_pressure",
            title="基本面压力 + 误导性 bull metadata",
            industry="消费",
            structures=["fundamental_weak_market_mixed", "adversarial"],
            metadata={"source": "live:F_adversarial_debate"},
            input=live["F_adversarial_debate"].inp.model_copy(update={"mode": "grounded"}),
            expected_frame=_frame(
                primary_axis="growth_vs_profitability",
                debate_state="bull_supported",
                assessment_strength="strong",
                pressure_level="severe",
                scenario_direction="conditional",
                uncertainty_state="preserved",
            ),
        )
    )

    # 7 manufacturing volume vs margin bull
    specs.append(
        EvaluationFixture(
            fixture_id="E07_mfg_volume_vs_margin_bull",
            title="制造：量增利不增 / bull",
            industry="制造",
            structures=["volume_vs_margin", "bull_supported", "growth_strong_profit_weak"],
            metadata={"source": "industry:mfg_bull_moderate"},
            input=industry["mfg_bull_moderate"],
            expected_frame=_frame(
                primary_axis="volume_vs_margin",
                debate_state="bull_supported",
                assessment_strength="moderate",
                support_strength="moderate",
                scenario_direction="conditional",
            ),
        )
    )

    # 8 semiconductor util vs asp bear
    specs.append(
        EvaluationFixture(
            fixture_id="E08_semi_util_vs_asp_bear",
            title="半导体：利用率 vs ASP / bear",
            industry="半导体",
            structures=["utilization_vs_asp", "bear_supported", "fundamental_weak_market_mixed"],
            metadata={"source": "industry:semi_bear_moderate"},
            input=industry["semi_bear_moderate"],
            expected_frame=_frame(
                primary_axis="utilization_vs_asp",
                debate_state="bear_supported",
                assessment_strength="moderate",
                support_strength="moderate",
                scenario_direction="conditional",
            ),
        )
    )

    # 9 same bull_supported strong mild vs severe (non-mechanical pair — mild)
    specs.append(
        EvaluationFixture(
            fixture_id="E09_mfg_bull_strong_mild_pressure",
            title="制造 bull_supported strong + mild/elevated pressure",
            industry="制造",
            structures=["bull_supported", "mild_pressure", "non_mechanical"],
            metadata={"source": "industry:mfg_bull_strong_mild"},
            input=industry["mfg_bull_strong_mild"],
            expected_frame=_frame(
                primary_axis="volume_vs_margin",
                debate_state="bull_supported",
                assessment_strength="strong",
                support_strength="strong",
                scenario_direction="conditional",
            ),
        )
    )

    # 10 severe pressure caps
    specs.append(
        EvaluationFixture(
            fixture_id="E10_semi_bull_strong_severe_pressure",
            title="半导体 bull_supported strong + severe pressure",
            industry="半导体",
            structures=["bull_supported", "severe_pressure", "non_mechanical"],
            metadata={"source": "industry:semi_bull_strong_severe"},
            input=industry["semi_bull_strong_severe"],
            expected_frame=_frame(
                primary_axis="utilization_vs_asp",
                debate_state="bull_supported",
                assessment_strength="moderate",  # capped expectation band
                support_strength="strong",
                pressure_level="severe",
                scenario_direction="conditional",
                uncertainty_state="preserved",
            ),
        )
    )

    # 11–14 lightweight industry variants from consumer base with retargeted metadata labels
    # Bank / Pharma / NewEnergy / Tech — reuse consumer unresolved structure with stock relabel via industry builder pattern
    # Use live A with different expected secondary labels stored in metadata only (same analytical structure)
    for fid, industry_name, structures in [
        ("E11_bank_style_unresolved", "银行", ["unresolved", "fundamental_market_unclear"]),
        ("E12_pharma_style_unresolved", "医药", ["unresolved", "profit_strong_growth_weak"]),
        ("E13_newenergy_style_bull", "新能源", ["bull_supported"]),
        ("E14_tech_style_bear", "科技", ["bear_supported"]),
        ("E15_cyclical_style_dual", "周期", ["dual_tension", "cross_tension"]),
    ]:
        if "bull" in fid:
            src = live["B_bull_moderate"].inp.model_copy(update={"mode": "grounded"})
            exp = _frame(
                primary_axis="growth_vs_profitability",
                debate_state="bull_supported",
                assessment_strength="moderate",
                scenario_direction="conditional",
            )
        elif "bear" in fid:
            src = live["C_bear_moderate"].inp.model_copy(update={"mode": "grounded"})
            exp = _frame(
                primary_axis="growth_vs_profitability",
                debate_state="bear_supported",
                assessment_strength="moderate",
                scenario_direction="conditional",
            )
        elif "dual" in fid:
            src = live["E_dual_tension"].inp.model_copy(update={"mode": "grounded"})
            exp = _frame(
                primary_axis="growth_vs_profitability",
                debate_state="unresolved",
                assessment_strength="unresolved",
                scenario_direction="conditional",
                cross_tension=True,
                uncertainty_state="preserved",
            )
        else:
            src = live["A_unresolved"].inp.model_copy(update={"mode": "grounded"})
            exp = _frame(
                primary_axis="growth_vs_profitability",
                debate_state="unresolved",
                assessment_strength="unresolved",
                scenario_direction="conditional",
                uncertainty_state="preserved",
            )
        specs.append(
            EvaluationFixture(
                fixture_id=fid,
                title=f"{industry_name} structural analogue",
                industry=industry_name,
                structures=structures,
                metadata={"analogue": True, "note": "structure-first coverage; Research surface from 600519 family"},
                input=src,
                expected_frame=exp,
            )
        )

    out_paths = []
    for s in specs:
        out_paths.append(str(write_fixture(s, ROOT)))

    manifest = {
        "n": len(specs),
        "fixture_ids": [s.fixture_id for s in specs],
        "industries": sorted({s.industry for s in specs}),
        "structures": sorted({x for s in specs for x in s.structures}),
    }
    man_path = ROOT / "examples" / "evaluation" / "manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
