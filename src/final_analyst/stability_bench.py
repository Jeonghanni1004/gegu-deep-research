"""Live / grounded stability benchmark (Round 6–10).

Env:
  FA_BENCH_FIXTURES=10
  FA_BENCH_RUNS=10
  FA_LIVE=1
  FA_DIAG_OUT=round10_failure_diagnosis.json
  FA_QUOTA_FUSE=3          # consecutive PROVIDER_QUOTA_FAILURE → abort remaining
  FA_QUOTA_FUSE_MAX=8      # total quota failures → abort
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evidence.pack import EvidencePack

from final_analyst.evaluation_dataset import load_evaluation_dataset
from final_analyst.failures import (
    FailureRecord,
    classify_exception,
    classify_from_notes,
    primary_failure,
)
from final_analyst.judgment_frame import (
    compare_judgment_frame,
    extract_judgment_frame,
    frames_structurally_equal,
    judgment_signature,
)
from final_analyst.llm import GroundedFALLMClient, OpenAIFALLMClient
from final_analyst.live_runner import live_api_available, require_live
from final_analyst.production_gate import run_production_gate


@dataclass
class StabilityStats:
    total_runs: int = 0
    openai_success: int = 0
    grounded_fallback: int = 0
    grounded_direct: int = 0
    repair: int = 0
    regenerate: int = 0
    retry: int = 0
    reject: int = 0
    provider_failure: int = 0
    provider_quota_failure: int = 0
    validation_failure: int = 0
    evidence_repair_failure: int = 0
    json_parse_failure: int = 0
    schema_sanitization_failure: int = 0
    information_loss: int = 0
    unsupported_external_fact: int = 0
    contract_violation: int = 0
    judgment_drift: int = 0
    debate_state_drift: int = 0
    primary_axis_drift: int = 0
    assessment_drift: int = 0
    acceptable: int = 0
    aborted_quota: bool = False
    incomplete: bool = False
    abort_reason: str = ""
    failure_codes_before_fallback: dict[str, int] = field(default_factory=dict)
    failure_stages: dict[str, int] = field(default_factory=dict)
    run_attributions: list[dict[str, Any]] = field(default_factory=list)
    fixture_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["openai_success_rate"] = (self.openai_success / self.total_runs) if self.total_runs else 0.0
        d["acceptable_rate"] = (self.acceptable / self.total_runs) if self.total_runs else 0.0
        d["fallback_rate"] = (self.grounded_fallback / self.total_runs) if self.total_runs else 0.0
        d["formal_adjudicable"] = (not self.incomplete) and (not self.aborted_quota) and self.total_runs > 0
        return d


def _note_flag(notes: list[str], key: str) -> bool:
    prefix = f"{key}="
    for n in notes:
        if n.startswith(prefix):
            return n.split("=", 1)[-1].strip().lower() in {"1", "true", "yes"}
    return False


def _note_int(notes: list[str], *keys: str, default: int = 1) -> int:
    for key in keys:
        prefix = f"{key}="
        for n in notes:
            if n.startswith(prefix):
                try:
                    return int(n.split("=", 1)[-1].strip())
                except ValueError:
                    continue
    return default


def _attribution_from_notes(notes: list[str], *, fallback: bool) -> FailureRecord:
    return classify_from_notes(
        notes,
        default_action="fallback" if fallback else "none",
        attempt=1,
    )


def _bump_code(stats: StabilityStats, code: str) -> None:
    stats.failure_codes_before_fallback[code] = stats.failure_codes_before_fallback.get(code, 0) + 1
    if code == "PROVIDER_FAILURE":
        stats.provider_failure += 1
    elif code == "PROVIDER_QUOTA_FAILURE":
        stats.provider_failure += 1
        stats.provider_quota_failure += 1
    elif code == "VALIDATION_FAILURE":
        stats.validation_failure += 1
    elif code == "EVIDENCE_REPAIR_FAILURE":
        stats.evidence_repair_failure += 1
    elif code == "JSON_PARSE_FAILURE":
        stats.json_parse_failure += 1
    elif code == "SCHEMA_SANITIZATION_FAILURE":
        stats.schema_sanitization_failure += 1


def write_failure_diagnosis(stats: StabilityStats, root: Path) -> Path:
    dist = {
        "PROVIDER_QUOTA_FAILURE": stats.failure_codes_before_fallback.get("PROVIDER_QUOTA_FAILURE", 0),
        "PROVIDER_FAILURE": stats.failure_codes_before_fallback.get("PROVIDER_FAILURE", 0),
        "VALIDATION_FAILURE": stats.failure_codes_before_fallback.get("VALIDATION_FAILURE", 0),
        "EVIDENCE_REPAIR_FAILURE": stats.failure_codes_before_fallback.get("EVIDENCE_REPAIR_FAILURE", 0),
        "JSON_PARSE_FAILURE": stats.failure_codes_before_fallback.get("JSON_PARSE_FAILURE", 0),
        "SCHEMA_SANITIZATION_FAILURE": stats.failure_codes_before_fallback.get("SCHEMA_SANITIZATION_FAILURE", 0),
    }
    for k, v in stats.failure_codes_before_fallback.items():
        dist.setdefault(k, v)

    payload = {
        "total_runs": stats.total_runs,
        "openai_success": stats.openai_success,
        "fallback": stats.grounded_fallback,
        "regenerate": stats.regenerate,
        "retry": stats.retry,
        "acceptable": stats.acceptable,
        "aborted_quota": stats.aborted_quota,
        "incomplete": stats.incomplete,
        "abort_reason": stats.abort_reason,
        "formal_adjudicable": (not stats.incomplete) and (not stats.aborted_quota),
        "failure_distribution": dist,
        "failure_stages": dict(stats.failure_stages),
        "runs": list(stats.run_attributions),
    }
    name = os.getenv("FA_DIAG_OUT") or "round8_failure_diagnosis.json"
    out_path = root / "examples" / "evaluation" / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def write_round8_failure_diagnosis(stats: StabilityStats, root: Path) -> Path:
    return write_failure_diagnosis(stats, root)


async def run_stability_benchmark(
    *,
    root: Path | None = None,
    mode: str = "openai",
    n_fixtures: int | None = None,
    n_runs: int | None = None,
    pack: EvidencePack | None = None,
) -> StabilityStats:
    root = root or Path(__file__).resolve().parents[2]
    n_fixtures = n_fixtures or int(os.getenv("FA_BENCH_FIXTURES") or "10")
    n_runs = n_runs or int(os.getenv("FA_BENCH_RUNS") or "10")
    fuse_consecutive = int(os.getenv("FA_QUOTA_FUSE") or "3")
    fuse_max = int(os.getenv("FA_QUOTA_FUSE_MAX") or "8")
    fixtures = load_evaluation_dataset(root)[:n_fixtures]
    stats = StabilityStats()
    use_openai = mode == "openai" and live_api_available() and require_live()
    openai_client = OpenAIFALLMClient(pack_for_validation=pack, fallback_to_grounded=True) if use_openai else None
    grounded_client = GroundedFALLMClient(pack_for_validation=pack)
    consecutive_quota = 0
    abort = False

    for fix in fixtures:
        if abort:
            break
        sigs: list[str] = []
        frames = []
        debate_states: list[str] = []
        axes: list[str] = []
        strengths: list[str] = []
        for i in range(n_runs):
            if abort:
                break
            stats.total_runs += 1
            inp = fix.input.model_copy(update={"mode": "openai" if use_openai else "grounded"})
            run_rec: dict[str, Any] = {
                "fixture": fix.fixture_id,
                "run": i + 1,
                "openai_success": False,
                "fallback": False,
                "stage": None,
                "failure_code": None,
                "cause": None,
                "action": None,
                "attempt": 1,
                "retry_used": False,
                "regenerate_used": False,
            }
            try:
                if use_openai and openai_client is not None:
                    out = await openai_client.generate(inp)
                else:
                    out = await grounded_client.generate(inp.model_copy(update={"mode": "grounded"}))
            except Exception as e:
                stats.reject += 1
                fr = classify_exception(e)
                _bump_code(stats, fr.code)
                stats.failure_stages[fr.stage] = stats.failure_stages.get(fr.stage, 0) + 1
                run_rec.update(
                    {
                        "fallback": False,
                        "stage": fr.stage,
                        "failure_code": fr.code,
                        "cause": fr.cause or fr.message,
                        "action": "reject",
                        "attempt": fr.attempt,
                    }
                )
                stats.run_attributions.append(run_rec)
                if fr.code == "PROVIDER_QUOTA_FAILURE":
                    consecutive_quota += 1
                    if consecutive_quota >= fuse_consecutive or stats.provider_quota_failure >= fuse_max:
                        abort = True
                        stats.aborted_quota = True
                        stats.incomplete = True
                        stats.abort_reason = (
                            f"quota_fuse: consecutive={consecutive_quota} "
                            f"total_quota={stats.provider_quota_failure} "
                            f"(limits {fuse_consecutive}/{fuse_max})"
                        )
                else:
                    consecutive_quota = 0
                continue

            notes = list(out.meta.notes or [])
            regenerate_used = _note_flag(notes, "regenerate_used")
            retry_used = _note_flag(notes, "retry_used")
            attempt = _note_int(notes, "attempt", "openai_attempt", default=1)
            run_rec["regenerate_used"] = regenerate_used
            run_rec["retry_used"] = retry_used
            run_rec["attempt"] = attempt
            if regenerate_used:
                stats.regenerate += 1
            if retry_used:
                stats.retry += 1

            if out.analyst_mode == "openai":
                stats.openai_success += 1
                run_rec["openai_success"] = True
                run_rec["action"] = "none"
                consecutive_quota = 0
            elif any("fallback" in n.lower() for n in notes):
                stats.grounded_fallback += 1
                fr = _attribution_from_notes(notes, fallback=True)
                _bump_code(stats, fr.code)
                stats.failure_stages[fr.stage] = stats.failure_stages.get(fr.stage, 0) + 1
                run_rec.update(
                    {
                        "openai_success": False,
                        "fallback": True,
                        "stage": fr.stage,
                        "failure_code": fr.code,
                        "cause": fr.cause or fr.message,
                        "action": fr.action or "fallback",
                        "attempt": fr.attempt or attempt,
                        "retry_used": fr.retry_used or retry_used,
                    }
                )
                if fr.code == "PROVIDER_QUOTA_FAILURE":
                    consecutive_quota += 1
                    if consecutive_quota >= fuse_consecutive or stats.provider_quota_failure >= fuse_max:
                        abort = True
                        stats.aborted_quota = True
                        stats.incomplete = True
                        stats.abort_reason = (
                            f"quota_fuse: consecutive={consecutive_quota} "
                            f"total_quota={stats.provider_quota_failure} "
                            f"(limits {fuse_consecutive}/{fuse_max})"
                        )
                else:
                    consecutive_quota = 0
            else:
                stats.grounded_direct += 1
                run_rec["action"] = "none"
                consecutive_quota = 0

            if any("evidence_repair_action=REPAIR" in n for n in notes):
                stats.repair += 1
            if any("information_loss=true" in n for n in notes):
                stats.information_loss += 1

            gate = run_production_gate(out, inp, pack=pack, is_fallback=out.analyst_mode != "openai")
            if gate.status == "FAIL":
                stats.reject += 1
                pf = primary_failure(gate.failures)
                if pf and pf.code == "UNSUPPORTED_EXTERNAL_FACT":
                    stats.unsupported_external_fact += 1
                if pf and pf.code == "CONTRACT_VIOLATION":
                    stats.contract_violation += 1
                if pf and pf.code == "INFORMATION_LOSS":
                    stats.information_loss += 1
                if pf and pf.code == "VALIDATION_FAILURE":
                    stats.validation_failure += 1
            else:
                actual = extract_judgment_frame(out, inp)
                cmp = compare_judgment_frame(actual, fix.expected_frame)
                if cmp.acceptable and gate.status in {"PASS", "FALLBACK_PASS"}:
                    stats.acceptable += 1
                frames.append(actual)
                sigs.append(judgment_signature(actual))
                debate_states.append(actual.debate_state)
                axes.append(actual.primary_axis)
                strengths.append(actual.assessment_strength)

            stats.run_attributions.append(run_rec)

        unique = set(sigs)
        if len(unique) > 2:
            stats.judgment_drift += 1
        if len(set(debate_states)) > 1:
            stats.debate_state_drift += 1
        if len(set(axes)) > 1:
            stats.primary_axis_drift += 1
        if len(set(strengths)) > 2:
            stats.assessment_drift += 1

        pairwise_ok = True
        for a, b in zip(frames, frames[1:]):
            if not frames_structurally_equal(a, b):
                if a.debate_state != b.debate_state or a.uncertainty_state == "erased" or b.uncertainty_state == "erased":
                    pairwise_ok = False
                    break
        if not pairwise_ok:
            stats.judgment_drift += 1

        stats.fixture_results.append(
            {
                "fixture_id": fix.fixture_id,
                "signatures": list(unique),
                "n_unique_signatures": len(unique),
                "debate_states": sorted(set(debate_states)),
                "primary_axes": sorted(set(axes)),
                "assessment_strengths": sorted(set(strengths)),
            }
        )

    out_path = root / "examples" / "evaluation" / "stability_stats.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    write_failure_diagnosis(stats, root)
    return stats


def main() -> None:
    from final_analyst.dotenv_load import load_dotenv

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    stats = asyncio.run(run_stability_benchmark())
    print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
