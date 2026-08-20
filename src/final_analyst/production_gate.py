"""Production Gate — fail-closed accept / repair / regenerate / fallback / reject (Round 6)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from evidence.pack import EvidencePack

from final_analyst.contract import FinalAnalystInput
from final_analyst.evidence_repair import information_loss_in_output
from final_analyst.failures import FailureRecord, classify_error_list, primary_failure
from final_analyst.live_quality import has_analytical_increment, live_hard_errors
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.semantic import phrase_seal_dependency_count, validate_all_semantics
from final_analyst.validators import validate_final_analyst

GateDecision = Literal["ACCEPT", "REPAIR", "REGENERATE", "FALLBACK", "REJECT"]


@dataclass
class ProductionGateResult:
    decision: GateDecision
    status: Literal["PASS", "FALLBACK_PASS", "FAIL"]
    failures: list[FailureRecord] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "status": self.status,
            "failures": [f.to_dict() for f in self.failures],
            "checks": self.checks,
            "notes": self.notes,
            "timestamp": self.timestamp,
            "primary_failure_code": (primary_failure(self.failures).code if primary_failure(self.failures) else None),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_production_gate(
    out: FinalAnalystOutput | None,
    inp: FinalAnalystInput | None,
    *,
    pack: EvidencePack | None = None,
    research_ok: bool = True,
    debate_ok: bool = True,
    as_of_ok: bool = True,
    prior_failures: list[FailureRecord] | None = None,
    is_fallback: bool = False,
    allow_repair: bool = True,
) -> ProductionGateResult:
    """Fail-closed production gate.

    ACCEPT: openai/grounded native pass
    FALLBACK: recommend grounded fallback (caller executes)
    REPAIR / REGENERATE: recoverable citation/validation issues
    REJECT: fatal contract / unsupported fact / information loss
    """
    notes: list[str] = []
    failures = list(prior_failures or [])
    checks: dict[str, bool] = {
        "research_contract": research_ok,
        "debate_contract": debate_ok,
        "as_of_consistent": as_of_ok,
        "fa_present": out is not None and inp is not None,
        "schema_valid": False,
        "semantic_valid": False,
        "evidence_grounding": False,
        "no_unsupported_fact": False,
        "no_information_loss": False,
        "no_trade_advice": False,
        "analytical_increment": False,
        "phrase_seal_free": False,
    }

    if not research_ok:
        failures.extend(classify_error_list(["INVALID_RESEARCH: research contract failed"], stage="research"))
    if not debate_ok:
        failures.extend(classify_error_list(["INVALID_DEBATE: debate contract failed"], stage="debate"))
    if not as_of_ok:
        failures.extend(classify_error_list(["AS_OF_MISMATCH: research/debate/request as_of inconsistent"], stage="research"))

    if out is None or inp is None:
        failures.extend(classify_error_list(["INVALID_FA: missing FA output or input"], stage="fa_generate"))
        return ProductionGateResult(
            decision="REJECT",
            status="FAIL",
            failures=failures,
            checks=checks,
            notes=notes + ["missing_output"],
            timestamp=_now(),
        )

    # Schema / semantic / grounding via existing validators
    val_errs = validate_final_analyst(out, inp, pack=pack)
    live_errs = live_hard_errors(out, inp, pack=pack) if pack is not None else list(val_errs)
    sem_errs = validate_all_semantics(out, inp)
    all_errs = list(dict.fromkeys(list(val_errs) + list(live_errs) + list(sem_errs)))
    failures.extend(classify_error_list(all_errs, stage="production_gate"))

    checks["schema_valid"] = not any(
        e.startswith(("evidence_traceability", "canonical_traceability", "assessment_strength", "debate_consumption"))
        for e in all_errs
    ) and out.meta.no_trade_advice
    checks["semantic_valid"] = not sem_errs
    checks["evidence_grounding"] = not any("no_unsupported_inference" in e for e in all_errs)
    checks["no_unsupported_fact"] = not any(
        x in e for e in all_errs for x in ("unsupported_inference", "fabricated_", "fa_finding_namespace")
    )
    checks["no_information_loss"] = not information_loss_in_output(out) and not any(
        "information_loss" in e for e in all_errs
    )
    checks["no_trade_advice"] = bool(out.meta.no_trade_advice)
    checks["analytical_increment"] = has_analytical_increment(out)
    checks["phrase_seal_free"] = phrase_seal_dependency_count(out.meta.notes) == 0

    fatal = [
        f
        for f in failures
        if f.code
        in {
            "UNSUPPORTED_EXTERNAL_FACT",
            "INFORMATION_LOSS",
            "CONTRACT_VIOLATION",
            "AS_OF_MISMATCH",
            "INVALID_RESEARCH",
            "INVALID_DEBATE",
        }
    ]

    if fatal or not checks["no_unsupported_fact"] or not checks["no_information_loss"] or not checks["as_of_consistent"]:
        return ProductionGateResult(
            decision="REJECT",
            status="FAIL",
            failures=failures,
            checks=checks,
            notes=notes + ["fatal_gate"],
            timestamp=_now(),
        )

    if not checks["phrase_seal_free"]:
        return ProductionGateResult(
            decision="REJECT",
            status="FAIL",
            failures=failures + classify_error_list(["phrase_seal_dependency"], stage="production_gate"),
            checks=checks,
            notes=notes + ["phrase_seal_forbidden"],
            timestamp=_now(),
        )

    if all_errs:
        # Recoverable validation → repair / regenerate / fallback
        grounding_issues = any("no_unsupported_inference" in e or "evidence" in e.lower() for e in all_errs)
        if allow_repair and grounding_issues:
            return ProductionGateResult(
                decision="REPAIR",
                status="FAIL",
                failures=failures,
                checks=checks,
                notes=notes + ["suggest_repair"],
                timestamp=_now(),
            )
        if out.analyst_mode == "openai" and not is_fallback:
            return ProductionGateResult(
                decision="FALLBACK",
                status="FAIL",
                failures=failures,
                checks=checks,
                notes=notes + ["suggest_grounded_fallback"],
                timestamp=_now(),
            )
        return ProductionGateResult(
            decision="REJECT",
            status="FAIL",
            failures=failures,
            checks=checks,
            notes=notes + ["unrecoverable_validation"],
            timestamp=_now(),
        )

    if not checks["analytical_increment"]:
        # Soft: still accept grounded if otherwise clean; openai ask regenerate once
        if out.analyst_mode == "openai" and not is_fallback:
            return ProductionGateResult(
                decision="REGENERATE",
                status="FAIL",
                failures=failures + classify_error_list(["analytical_increment_v2: missing"], stage="production_gate"),
                checks=checks,
                notes=notes + ["low_increment"],
                timestamp=_now(),
            )

    if is_fallback or (out.analyst_mode == "grounded" and prior_failures):
        return ProductionGateResult(
            decision="ACCEPT",
            status="FALLBACK_PASS",
            failures=prior_failures or [],
            checks=checks,
            notes=notes + ["fallback_accept"],
            timestamp=_now(),
        )

    return ProductionGateResult(
        decision="ACCEPT",
        status="PASS",
        failures=[],
        checks=checks,
        notes=notes + ["accept"],
        timestamp=_now(),
    )


def gate_result_summary(gate: ProductionGateResult) -> dict[str, Any]:
    return asdict(gate) if False else gate.to_dict()  # prefer to_dict
