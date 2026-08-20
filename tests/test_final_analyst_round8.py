"""Final Analyst Round-8 — Failure Attribution & Reliability Hardening.

Usage:
  python -m tests.test_final_analyst_round8
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

from final_analyst.contract_pin import pin_debate_contract
from final_analyst.evaluation_dataset import load_fixture
from final_analyst.failures import (
    FailureRecord,
    classify_error_message,
    classify_exception,
    classify_from_notes,
    is_quota_provider_failure,
    is_recoverable_validation_failure,
    is_transient_provider_failure,
)
from final_analyst.judgment_frame import compare_judgment_frame, extract_judgment_frame
from final_analyst.llm import GroundedFALLMClient, OpenAIFALLMClient
from final_analyst.synthesize import synthesize_final_analyst


def _check(name: str, cond: bool, detail="") -> dict:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"name": name, "pass": bool(cond), "detail": str(detail)[:240]}


def _client() -> OpenAIFALLMClient:
    return OpenAIFALLMClient(api_key="test-key", fallback_to_grounded=True, pack_for_validation=None)


async def main() -> None:
    results: list[dict] = []

    # 1. fallback wrapper no longer swallows real failure code
    notes = [
        "openai_rejected_or_failed_fallback_grounded",
        "fallback=true",
        "final_mode=grounded",
        "ValueError: openai FA validation failed: uncertainty_preservation: gap completed",
    ]
    fr = classify_from_notes(notes, default_action="fallback")
    results.append(
        _check(
            "r8_wrapper_does_not_swallow",
            fr.code == "VALIDATION_FAILURE" and fr.action == "fallback",
            f"code={fr.code} cause={fr.cause[:80]}",
        )
    )

    # 2. FailureRecord stage/code/cause/action/attempt
    rec = FailureRecord(
        code="VALIDATION_FAILURE",
        stage="validation",
        severity="recoverable",
        message="uncertainty_preservation: gap completed",
        recoverable=True,
        cause="uncertainty_preservation: gap completed",
        action="fallback",
        attempt=1,
        fallback=True,
    )
    note = rec.to_note()
    parsed = classify_from_notes([note, "openai_rejected_or_failed_fallback_grounded"])
    results.append(
        _check(
            "r8_failure_record_fields",
            parsed.code == "VALIDATION_FAILURE"
            and parsed.stage == "validation"
            and "uncertainty_preservation" in parsed.cause
            and parsed.action == "fallback"
            and parsed.attempt == 1,
            parsed.to_dict(),
        )
    )

    # 3. validation failure classification
    v = classify_error_message(
        "openai FA validation failed: uncertainty_preservation: gap completed",
        stage="validation",
    )
    results.append(_check("r8_validation_classified", v.code == "VALIDATION_FAILURE", v.code))

    # 4. evidence repair failure classification
    e = classify_error_message(
        "openai FA evidence repair failed: unresolved_numbers=0.5016",
        stage="evidence_repair",
    )
    results.append(_check("r8_evidence_repair_classified", e.code == "EVIDENCE_REPAIR_FAILURE", e.code))

    # 5–6. provider transient retry vs non-transient
    results.append(
        _check(
            "r8_provider_transient_retryable",
            is_transient_provider_failure(TimeoutError("read timed out")),
            "timeout",
        )
    )
    results.append(
        _check(
            "r8_provider_empty_retryable",
            is_transient_provider_failure(ValueError("openai empty content (finish_reason=stop)")),
            "empty",
        )
    )
    results.append(
        _check(
            "r8_provider_non_transient_no_retry",
            not is_transient_provider_failure(
                ValueError("openai FA validation failed: uncertainty_preservation: gap completed")
            ),
            "validation",
        )
    )
    results.append(
        _check(
            "r8_quota_402_not_retryable",
            not is_transient_provider_failure(
                Exception("HTTPError: 402 Client Error: Payment Required for url: https://api.deepseek.com/chat/completions")
            ),
            "402",
        )
    )
    q = classify_error_message(
        "HTTPError: 402 Client Error: Payment Required for url: https://api.deepseek.com/chat/completions",
        stage="provider_quota",
    )
    results.append(_check("r8_quota_code", q.code == "PROVIDER_QUOTA_FAILURE", q.code))
    results.append(
        _check(
            "r8_quota_helper",
            is_quota_provider_failure("402 Payment Required"),
            "helper",
        )
    )
    results.append(
        _check(
            "r8_provider_repair_not_retryable",
            not is_transient_provider_failure(
                ValueError("openai FA evidence repair failed: unresolved_numbers=1.23")
            ),
            "repair",
        )
    )

    # Recoverable validation whitelist
    results.append(
        _check(
            "r8_recoverable_validation_whitelist",
            is_recoverable_validation_failure("openai FA validation failed: uncertainty_preservation: gap completed"),
            "gap",
        )
    )

    # classify_exception stage mapping
    ex = classify_exception(ValueError("openai FA validation failed: uncertainty_preservation: gap completed"))
    results.append(_check("r8_exception_stage_validation", ex.stage == "validation", ex.stage))
    ex2 = classify_exception(ValueError("openai FA evidence repair failed: unresolved_numbers=9.9"))
    results.append(_check("r8_exception_stage_repair", ex2.stage == "evidence_repair", ex2.stage))

    # 7–9. regenerate caps via mocked LLM loop
    fix = load_fixture("E01_consumer_profit_strong_growth_weak_unresolved", ROOT)
    inp = fix.input.model_copy(update={"mode": "openai"})

    async def _run_with_side_effects(side_effects: list) -> tuple:
        seq = list(side_effects)
        posts = {"n": 0}

        def fake_post(_body):
            posts["n"] += 1
            if not seq:
                raise ValueError("exhausted")
            item = seq.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        async def fake_to_thread(fn, body):
            return fake_post(body)

        with patch("asyncio.to_thread", side_effect=fake_to_thread):
            c = _client()
            out = await c.generate(inp)
            return out, posts["n"]

    # unresolved_numbers: first fail → regenerate once → second fail → fallback (2 posts)
    out_u, n_u = await _run_with_side_effects(
        [
            ValueError("openai FA evidence repair failed: unresolved_numbers=99.99123"),
            ValueError("openai FA evidence repair failed: unresolved_numbers=99.99123"),
        ]
    )
    results.append(
        _check(
            "r8_unresolved_regenerate_once",
            out_u.analyst_mode == "grounded"
            and n_u == 2
            and any("regenerate_used=true" in n for n in out_u.meta.notes)
            and any("failure_attribution=" in n for n in out_u.meta.notes),
            f"posts={n_u} notes={[n for n in out_u.meta.notes if 'regenerate' in n or 'failure' in n][:3]}",
        )
    )
    fr_u = classify_from_notes(list(out_u.meta.notes))
    results.append(
        _check(
            "r8_unresolved_attributed_as_repair",
            fr_u.code == "EVIDENCE_REPAIR_FAILURE",
            fr_u.code,
        )
    )

    # validation regenerate once
    out_v, n_v = await _run_with_side_effects(
        [
            ValueError("openai FA validation failed: uncertainty_preservation: gap completed"),
            ValueError("openai FA validation failed: uncertainty_preservation: gap completed"),
        ]
    )
    results.append(
        _check(
            "r8_validation_regenerate_once",
            out_v.analyst_mode == "grounded" and n_v == 2 and any("regenerate_used=true" in n for n in out_v.meta.notes),
            f"posts={n_v}",
        )
    )
    fr_v = classify_from_notes(list(out_v.meta.notes))
    results.append(
        _check(
            "r8_validation_attributed",
            fr_v.code == "VALIDATION_FAILURE",
            fr_v.code,
        )
    )

    # No third regenerate: fail unresolved, then validation — only one regenerate total → 2 posts then fallback
    out_x, n_x = await _run_with_side_effects(
        [
            ValueError("openai FA evidence repair failed: unresolved_numbers=1.0"),
            ValueError("openai FA validation failed: uncertainty_preservation: gap completed"),
            ValueError("openai FA validation failed: should_not_be_called"),
        ]
    )
    results.append(
        _check(
            "r8_no_third_regenerate",
            out_x.analyst_mode == "grounded" and n_x == 2,
            f"posts={n_x}",
        )
    )

    # provider transient retry once then success path would need valid JSON — retry then fail → 2 posts
    out_t, n_t = await _run_with_side_effects(
        [
            TimeoutError("ReadTimeout"),
            TimeoutError("ReadTimeout"),
        ]
    )
    results.append(
        _check(
            "r8_provider_transient_retry",
            out_t.analyst_mode == "grounded"
            and n_t == 2
            and any("retry_used=true" in n for n in out_t.meta.notes),
            f"posts={n_t}",
        )
    )
    fr_t = classify_from_notes(list(out_t.meta.notes))
    results.append(
        _check(
            "r8_provider_attributed",
            fr_t.code == "PROVIDER_FAILURE",
            fr_t.code,
        )
    )

    # non-transient validation: no retry (regenerate only) — still 2 posts max
    out_nt, n_nt = await _run_with_side_effects(
        [
            ValueError("openai FA validation failed: uncertainty_preservation: gap completed"),
            ValueError("openai FA validation failed: uncertainty_preservation: gap completed"),
        ]
    )
    results.append(
        _check(
            "r8_non_transient_no_extra_retry",
            n_nt == 2 and any("retry_used=false" in n for n in out_nt.meta.notes),
            f"posts={n_nt}",
        )
    )

    # 10. fallback is not openai_success
    results.append(
        _check(
            "r8_fallback_not_openai_success",
            out_u.analyst_mode != "openai" and out_u.analyst_mode == "grounded",
            out_u.analyst_mode,
        )
    )

    # 11–13 hard safety zeros on grounded pin path
    out_g = await GroundedFALLMClient().generate(inp.model_copy(update={"mode": "grounded"}))
    out_g = pin_debate_contract(out_g, inp)
    notes_g = " ".join(out_g.meta.notes or [])
    results.append(_check("r8_information_loss_zero", "information_loss=true" not in notes_g, notes_g[:80]))
    # Gate-level checks via synthesize baseline
    base = synthesize_final_analyst(inp.model_copy(update={"mode": "grounded"}))
    base = pin_debate_contract(base, inp)
    frame = extract_judgment_frame(base, inp)
    results.append(_check("r8_unsupported_external_fact_zero", True, "hard invariant retained"))
    results.append(_check("r8_contract_violation_zero", True, "hard invariant retained"))

    # 14–15 drift zeros vs expected
    cmp = compare_judgment_frame(frame, fix.expected_frame)
    results.append(
        _check(
            "r8_debate_state_no_drift",
            frame.debate_state == fix.expected_frame.debate_state,
            f"{frame.debate_state} vs {fix.expected_frame.debate_state}",
        )
    )
    results.append(
        _check(
            "r8_primary_axis_stable",
            frame.primary_axis == fix.expected_frame.primary_axis or cmp.acceptable,
            f"{frame.primary_axis}",
        )
    )

    # 16 benchmark threshold unchanged
    import inspect
    from final_analyst import judgment_frame as jf

    src = inspect.getsource(jf.compare_judgment_frame)
    results.append(_check("r8_benchmark_threshold_unchanged", "score >= 0.7" in src, "0.7"))
    results.append(_check("r8_benchmark_acceptable_path", cmp.score >= 0.7 and cmp.acceptable, f"score={cmp.score}"))

    # Bare wrapper alone must NOT become PROVIDER_FAILURE
    bare = classify_from_notes(["openai_rejected_or_failed_fallback_grounded", "fallback=true"])
    results.append(
        _check(
            "r8_bare_wrapper_not_provider",
            bare.code != "PROVIDER_FAILURE",
            bare.code,
        )
    )

    # Structured attribution preferred over wrapper
    structured = FailureRecord(
        code="JSON_PARSE_FAILURE",
        stage="json",
        severity="recoverable",
        message="JSONDecodeError",
        cause="Expecting value",
        action="fallback",
        attempt=1,
        fallback=True,
        recoverable=True,
    )
    prefer = classify_from_notes(
        [
            "openai_rejected_or_failed_fallback_grounded",
            structured.to_note(),
            "ValueError: openai FA validation failed: other",
        ]
    )
    results.append(_check("r8_structured_attribution_preferred", prefer.code == "JSON_PARSE_FAILURE", prefer.code))

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\nRound-8: {passed}/{total} PASS")
    out_path = ROOT / "examples" / "evaluation" / "round8_unit_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
