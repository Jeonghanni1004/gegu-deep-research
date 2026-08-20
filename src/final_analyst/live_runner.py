"""OpenAI Live A/B runner for Final Analyst."""

from final_analyst.dotenv_load import load_dotenv

load_dotenv()

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence.pack import EvidencePack

from final_analyst.contract import FinalAnalystInput
from final_analyst.live_fixtures import LiveFixture, build_live_fixtures
from final_analyst.live_quality import (
    analytical_increment_signals,
    external_number_risk,
    has_analytical_increment,
    live_hard_errors,
    scenario_boundary_ok,
    structural_invariants,
)
from final_analyst.llm import GroundedFALLMClient, OpenAIFALLMClient
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.synthesize import synthesize_final_analyst


@dataclass
class LiveABResult:
    fixture_id: str
    title: str
    intent: str
    live_available: bool
    openai_mode: str  # openai | grounded_fallback | skipped
    grounded: FinalAnalystOutput
    openai: FinalAnalystOutput | None
    grounded_errors: list[str]
    openai_errors: list[str]
    openai_increment: dict[str, bool]
    notes: list[str]


def live_api_available() -> bool:
    return bool(os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def require_live() -> bool:
    return os.getenv("FA_LIVE", "").strip() in {"1", "true", "TRUE", "yes", "YES"}


async def run_one_ab(
    fix: LiveFixture,
    *,
    pack: EvidencePack | None,
    force_live: bool = False,
) -> LiveABResult:
    grounded_inp = fix.inp.model_copy(update={"mode": "grounded"})
    grounded = synthesize_final_analyst(grounded_inp)
    g_errs = live_hard_errors(grounded, grounded_inp, pack=pack)

    notes: list[str] = []
    openai_out: FinalAnalystOutput | None = None
    o_errs: list[str] = []
    mode = "skipped"
    live = live_api_available()

    if (force_live or require_live()) and live:
        client = OpenAIFALLMClient(
            pack_for_validation=pack,
            fallback_to_grounded=True,
            timeout=180.0,
        )
        try:
            openai_out = await client.generate(fix.inp.model_copy(update={"mode": "openai"}))
            # Detect silent fallback: grounded mode returned
            if openai_out.analyst_mode == "grounded":
                mode = "grounded_fallback"
                notes.append("OpenAI path returned grounded (fallback after reject/error)")
                notes.extend([n for n in openai_out.meta.notes if "fallback" in n or "Error" in n or "HTTP" in n or "validation" in n][:3])
            else:
                mode = "openai"
            o_errs = live_hard_errors(openai_out, fix.inp, pack=pack)
            if mode == "openai" and o_errs:
                # Should have been rejected by client — if somehow present, mark
                notes.append("openai_errors_present_after_client: " + "; ".join(o_errs[:4]))
        except Exception as e:
            mode = "grounded_fallback"
            notes.append(f"openai_exception: {type(e).__name__}: {e}")
            openai_out = grounded.model_copy(update={"analyst_mode": "grounded"})
            o_errs = [str(e)]
    else:
        notes.append(
            "Live OpenAI skipped: set FA_LIVE=1 and RESEARCH_LLM_API_KEY or OPENAI_API_KEY to run"
        )
        openai_out = None

    incr = analytical_increment_signals(openai_out) if openai_out and mode == "openai" else {}
    return LiveABResult(
        fixture_id=fix.fixture_id,
        title=fix.title,
        intent=fix.intent,
        live_available=live,
        openai_mode=mode,
        grounded=grounded,
        openai=openai_out,
        grounded_errors=g_errs,
        openai_errors=o_errs,
        openai_increment=incr,
        notes=notes,
    )


def result_summary(r: LiveABResult) -> dict[str, Any]:
    return {
        "fixture_id": r.fixture_id,
        "title": r.title,
        "openai_mode": r.openai_mode,
        "grounded_errors": r.grounded_errors,
        "openai_errors": r.openai_errors,
        "notes": r.notes,
    }


async def run_all_live_ab(
    *,
    root: Path | None = None,
    out_dir: Path | None = None,
    force_live: bool = False,
) -> list[LiveABResult]:
    root = root or Path(__file__).resolve().parents[2]
    out_dir = out_dir or (root / "examples" / "fa_live")
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = EvidencePack.load_json(root / "examples" / "600519_evidence_pack.json")
    fixtures = build_live_fixtures(root)
    results: list[LiveABResult] = []

    for fix in fixtures:
        r = await run_one_ab(fix, pack=pack, force_live=force_live)
        results.append(r)
        payload = {
            "fixture_id": r.fixture_id,
            "title": r.title,
            "intent": r.intent,
            "live_available": r.live_available,
            "openai_mode": r.openai_mode,
            "notes": r.notes,
            "grounded_errors": r.grounded_errors,
            "openai_errors": r.openai_errors,
            "openai_increment": r.openai_increment,
            "grounded_has_increment": has_analytical_increment(r.grounded),
            "openai_has_increment": bool(r.openai)
            and r.openai_mode == "openai"
            and has_analytical_increment(r.openai),
            "scenario_ok_grounded": scenario_boundary_ok(r.grounded),
            "scenario_ok_openai": bool(r.openai) and scenario_boundary_ok(r.openai),
            "invariants": structural_invariants(r.grounded, r.openai) if r.openai else ["openai_missing"],
            "external_numbers_openai": external_number_risk(r.openai, fix.inp) if r.openai else [],
            "grounded_exec": r.grounded.executive_assessment.text,
            "openai_exec": r.openai.executive_assessment.text if r.openai else None,
            "grounded": r.grounded.model_dump(mode="json"),
            "openai": r.openai.model_dump(mode="json") if r.openai else None,
        }
        (out_dir / f"{r.fixture_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = {
        "n_fixtures": len(results),
        "live_requested": force_live or require_live(),
        "live_available": live_api_available(),
        "modes": {r.fixture_id: r.openai_mode for r in results},
        "openai_error_counts": {r.fixture_id: len(r.openai_errors) for r in results},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> None:
    force = os.getenv("FA_LIVE", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    results = asyncio.run(run_all_live_ab(force_live=force))
    for r in results:
        print(f"[{r.openai_mode}] {r.fixture_id}: g_err={len(r.grounded_errors)} o_err={len(r.openai_errors)} notes={r.notes[:1]}")


if __name__ == "__main__":
    main()
