"""Final Analyst Round-9 — transient provider retry + E06 fail-closed safety.

Usage:
  python -m tests.test_final_analyst_round9
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_analyst.evaluation_dataset import load_fixture
from final_analyst.evidence_repair import repair_output_citations
from final_analyst.failures import (
    classify_error_message,
    classify_exception,
    classify_from_notes,
    is_quota_provider_failure,
    is_transient_provider_failure,
)
from final_analyst.llm import OpenAIFALLMClient
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.synthesize import synthesize_final_analyst


def _check(name: str, cond: bool, detail="") -> dict:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"name": name, "pass": bool(cond), "detail": str(detail)[:240]}


def _client() -> OpenAIFALLMClient:
    return OpenAIFALLMClient(api_key="test-key", fallback_to_grounded=True, pack_for_validation=None)


def _ok_api_payload(inp) -> dict:
    out = synthesize_final_analyst(inp.model_copy(update={"mode": "grounded"}))
    data = out.model_dump()
    data["analyst_mode"] = "openai"
    return {
        "choices": [
            {
                "message": {"content": json.dumps(data, ensure_ascii=False)},
                "finish_reason": "stop",
            }
        ]
    }


async def main() -> None:
    results: list[dict] = []
    fix = load_fixture("E06_adversarial_fund_pressure", ROOT)
    inp = fix.input.model_copy(update={"mode": "openai"})

    # --- transient / quota classification ---
    results.append(
        _check(
            "r9_premature_is_transient",
            is_transient_provider_failure(RuntimeError("Response ended prematurely")),
            "premature",
        )
    )
    results.append(
        _check(
            "r9_premature_stage_provider",
            classify_exception(RuntimeError("Response ended prematurely")).stage == "provider"
            and classify_exception(RuntimeError("Response ended prematurely")).code == "PROVIDER_FAILURE",
            "stage",
        )
    )
    results.append(
        _check(
            "r9_402_is_quota",
            is_quota_provider_failure("HTTPError: 402 Client Error: Payment Required"),
            "402",
        )
    )
    results.append(
        _check(
            "r9_402_not_transient",
            not is_transient_provider_failure(
                Exception("HTTPError: 402 Client Error: Payment Required for url: https://api.deepseek.com/x")
            ),
            "no-retry",
        )
    )
    q = classify_error_message("HTTPError: 402 Client Error: Payment Required")
    results.append(_check("r9_402_code_quota", q.code == "PROVIDER_QUOTA_FAILURE", q.code))

    async def _run_with_side_effects(side_effects: list) -> tuple:
        seq = list(side_effects)
        posts = {"n": 0}

        def fake_post(_body):
            posts["n"] += 1
            if not seq:
                raise RuntimeError("exhausted")
            item = seq.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        async def fake_to_thread(fn, body):
            return fake_post(body)

        with patch("asyncio.to_thread", side_effect=fake_to_thread):
            out = await _client().generate(inp)
            return out, posts["n"]

    # premature → retry → success
    out_ok, n_ok = await _run_with_side_effects(
        [
            RuntimeError("Response ended prematurely"),
            _ok_api_payload(inp),
        ]
    )
    results.append(
        _check(
            "r9_premature_retry_success",
            out_ok.analyst_mode == "openai"
            and n_ok == 2
            and any("retry_used=true" in x for x in out_ok.meta.notes)
            and any("provider_retry_recovered=true" in x for x in out_ok.meta.notes)
            and any("provider_retry_first_error=" in x for x in out_ok.meta.notes),
            f"mode={out_ok.analyst_mode} posts={n_ok}",
        )
    )
    results.append(
        _check(
            "r9_retry_success_counts_openai",
            out_ok.analyst_mode == "openai",
            "openai_success path",
        )
    )

    # premature → retry → premature → fallback
    out_fail, n_fail = await _run_with_side_effects(
        [
            RuntimeError("Response ended prematurely"),
            RuntimeError("Response ended prematurely"),
        ]
    )
    fr_fail = classify_from_notes(list(out_fail.meta.notes))
    results.append(
        _check(
            "r9_premature_retry_then_fallback",
            out_fail.analyst_mode == "grounded"
            and n_fail == 2
            and any("retry_used=true" in x for x in out_fail.meta.notes)
            and fr_fail.code == "PROVIDER_FAILURE"
            and out_fail.analyst_mode != "openai",
            f"posts={n_fail} code={fr_fail.code}",
        )
    )

    # 402 → no retry (single post then fallback)
    out_402, n_402 = await _run_with_side_effects(
        [Exception("HTTPError: 402 Client Error: Payment Required for url: https://api.deepseek.com/chat/completions")]
    )
    fr_402 = classify_from_notes(list(out_402.meta.notes))
    results.append(
        _check(
            "r9_402_no_retry_fallback",
            out_402.analyst_mode == "grounded"
            and n_402 == 1
            and any("retry_used=false" in x for x in out_402.meta.notes)
            and fr_402.code == "PROVIDER_QUOTA_FAILURE",
            f"posts={n_402} code={fr_402.code}",
        )
    )

    # --- E06 evidence repair safety (must NOT loosen round) ---
    base = synthesize_final_analyst(inp.model_copy(update={"mode": "grounded"}))

    def _mutate(extra: str) -> FinalAnalystOutput:
        d = base.model_dump()
        d["executive_assessment"]["text"] = d["executive_assessment"]["text"] + extra
        return FinalAnalystOutput.model_validate(d)

    r100 = repair_output_citations(_mutate(" 另见 100%。"), inp, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_e06_100pct_no_source_fail",
            r100.action == "REGENERATE" and "100%" in (r100.unresolved_numbers or []),
            f"action={r100.action} unresolved={r100.unresolved_numbers}",
        )
    )

    r_inv = repair_output_citations(_mutate(" 另见 99.99123%。"), inp, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_invented_pct_fail",
            r_inv.action == "REGENERATE" and any("99.99123" in x for x in (r_inv.unresolved_numbers or [])),
            r_inv.unresolved_numbers,
        )
    )

    r_round = repair_output_citations(_mutate(" 另见 1347.13。"), inp, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_1347_1280_to_1347_13_fail_closed",
            r_round.action == "REGENERATE" and "1347.13" in (r_round.unresolved_numbers or []),
            f"action={r_round.action} unresolved={r_round.unresolved_numbers}",
        )
    )

    r_exact = repair_output_citations(_mutate(" 另见 1347.1280。"), inp, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_1347_1280_exact_pass",
            r_exact.action in {"ACCEPT", "REPAIR"} and not r_exact.unresolved_numbers,
            f"action={r_exact.action}",
        )
    )

    # trailing-zero PASS only when source itself is 1347.13
    fund_findings = list(inp.fundamental.canonical_findings)
    assert fund_findings
    f0 = fund_findings[0]
    f0p = f0.model_copy(update={"numbers_preserved": list(f0.numbers_preserved or []) + ["1347.13"]})
    fund_findings[0] = f0p
    inp_13 = inp.model_copy(
        update={"fundamental": inp.fundamental.model_copy(update={"canonical_findings": fund_findings})}
    )

    base13 = synthesize_final_analyst(inp_13.model_copy(update={"mode": "grounded"}))
    d13 = base13.model_dump()
    d13["executive_assessment"]["text"] = d13["executive_assessment"]["text"] + " 另见 1347.1300。"
    r_trail = repair_output_citations(FinalAnalystOutput.model_validate(d13), inp_13, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_trailing_zero_when_source_1347_13",
            r_trail.action in {"ACCEPT", "REPAIR"} and not r_trail.unresolved_numbers,
            f"action={r_trail.action} unresolved={r_trail.unresolved_numbers}",
        )
    )

    # Without injecting 1347.13 as source, 1347.1300 must still fail
    d_bad = base.model_dump()
    d_bad["executive_assessment"]["text"] = d_bad["executive_assessment"]["text"] + " 另见 1347.1300。"
    r_trail_bad = repair_output_citations(FinalAnalystOutput.model_validate(d_bad), inp, pack=None, allow_scrub=False)
    results.append(
        _check(
            "r9_trailing_zero_without_source_fail",
            r_trail_bad.action == "REGENERATE"
            and any(x.startswith("1347.13") for x in (r_trail_bad.unresolved_numbers or [])),
            r_trail_bad.unresolved_numbers,
        )
    )

    # fabricated remains unsupported (taxonomy)
    fab = classify_error_message(
        "openai FA validation failed: fabricated_evidence_hint: stmt[0] ['derived_derived_x']",
        stage="validation",
    )
    results.append(_check("r9_fabricated_still_unsupported", fab.code == "UNSUPPORTED_EXTERNAL_FACT", fab.code))

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\nRound-9: {passed}/{total} PASS")
    out_path = ROOT / "examples" / "evaluation" / "round9_unit_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
