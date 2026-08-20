"""Demo web assemble — no LLM, artifacts only.

Usage:
  set PYTHONPATH=src;python -m tests.test_demo_web
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEB = ROOT / "web"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from assemble import assemble_snapshot, list_studies, resolve_symbol
from final_analyst.judgment_frame import extract_judgment_frame
from final_analyst.schemas import FinalAnalystOutput
import json


def test_list_and_resolve() -> None:
    studies = list_studies()
    assert any(s["symbol"] == "600519" for s in studies), studies
    assert resolve_symbol("600519") == "600519"
    assert resolve_symbol("贵州茅台") == "600519"
    if any(s["symbol"] == "601127" for s in studies):
        assert resolve_symbol("赛力斯") == "601127"
        assert resolve_symbol("601127") == "601127"
    assert resolve_symbol("999999") is None


def test_assemble_600519() -> None:
    snap = assemble_snapshot("600519")
    assert snap["no_llm_call"] is True
    assert snap["symbol"] == "600519"
    assert snap["name"] == "贵州茅台"
    assert snap["counts"]["evidence"] > 0
    assert snap["judgment"]["debate_state"] in {
        "unresolved",
        "bull_supported",
        "bear_supported",
        "partially_resolved",
        "unknown",
    }
    assert snap["final_analyst"]["executive_assessment"]["text"]
    assert snap["debate"] is not None
    assert snap["debate"]["bull"]["claims"]
    assert snap["debate"]["chains"]
    assert any(e["cited"] for e in snap["evidence"])
    assert snap["final_analyst"]["why_this_judgment"]["primary_resolution"]
    assert snap["source"] == "grounded_artifacts"

    report = snap["report"]
    assert report["title"].startswith("贵州茅台")
    assert report["executive"]["one_liner"]
    assert "事实清楚、解释未决" not in report["executive"]["one_liner"]
    assert "TENSION_" not in report["executive"]["one_liner"]
    assert report["executive"]["core_tension"]
    assert report["executive"]["core_view"]
    assert report["research_brief"]["core_judgment"]
    assert report["research_brief"]["bull_case"]
    assert report["research_brief"]["bear_case"]
    assert report["research_brief"]["key_unknown"]
    assert report["research_brief"].get("insight_next_research")
    assert report.get("insights")
    assert report.get("research_signals")
    assert 1 <= len(report["research_signals"]) <= 5
    assert report["research_signals"][0].get("research_question")
    assert report.get("fundamental_picture")
    assert report["key_evidence"][0].get("metric_label")
    assert "分别为" in report["executive"]["core_view"] or "ROE" in report["executive"]["core_view"]
    assert "合理市值" not in report["executive"]["core_view"]
    assert "买入" not in report["executive"]["core_view"]
    assert report["kpi_table"]
    assert any(r["label"] == "ROE" for r in report["kpi_table"])
    assert any(s["kicker"] == "财务分析" for s in report["sections"])
    assert any(s["kicker"] == "风险因素" for s in report["sections"])
    assert report["cover_title"]
    assert "？" not in report["cover_title"]
    assert len(report["key_tensions"]) <= 3
    assert report["key_tensions"][0]["question"]
    assert report["key_tensions"][0]["thesis"]
    assert report["judgment"]["confirmed"]
    assert report["judgment"]["unconfirmed"]
    assert report["judgment"]["strength_band"] in {"strong", "moderate", "weak", "unresolved"}
    assert len(report["view_changers"]) <= 5
    assert 1 <= len(report["key_evidence"]) <= 6
    assert "as_of=" not in "".join(report["executive_summary"])
    slogan_hits = sum(1 for p in report["executive_summary"] if "事实清楚、解释未决" in p)
    assert slogan_hits <= 1
    assert "ROE" in report["findings"][0]["claim"] or "毛利率" in report["findings"][0]["claim"]
    assert snap["judgment"]["debate_state"] == "unresolved"
    raw = FinalAnalystOutput.model_validate(
        json.loads((ROOT / "examples" / "600519_final_analyst.json").read_text(encoding="utf-8"))
    )
    frame_file = extract_judgment_frame(raw)
    assert snap["judgment"]["primary_axis"] == frame_file.primary_axis
    assert snap["judgment"]["debate_state"] == frame_file.debate_state
    assert snap["judgment"]["assessment_strength"] == frame_file.assessment_strength


def test_insight_layer_differs_by_symbol() -> None:
    maotai = assemble_snapshot("600519")["report"]
    assert "利润降幅" in maotai["research_brief"]["core_judgment"] or "高毛利" in maotai["research_brief"]["core_judgment"]
    assert "盈利能力仍强，增长动能承压" not in maotai["research_brief"]["core_judgment"]
    studies = list_studies()
    if any(s["symbol"] == "601127" for s in studies):
        seres = assemble_snapshot("601127")["report"]
        assert maotai["research_brief"]["core_judgment"] != seres["research_brief"]["core_judgment"]
        assert any(
            "扩张" in seres["research_brief"]["core_judgment"]
            or "利润" in seres["research_brief"]["core_judgment"]
            for _ in [0]
        )
        assert seres.get("external_signals")
        assert any(s.get("kind") == "external" for s in seres["research_signals"])


def main() -> int:
    test_list_and_resolve()
    print("PASS list_and_resolve")
    test_assemble_600519()
    print("PASS assemble_600519")
    test_insight_layer_differs_by_symbol()
    print("PASS insight_layer_differs_by_symbol")
    print("ALL DEMO WEB TESTS PASSED (no API calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
