"""Pin Debate contract onto FA output — resolution is INPUT, not LLM rewrite (Round 7)."""

from __future__ import annotations

from final_analyst.calibration import evidence_pressure, normalize_support_strength
from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.resolution import resolve_debate_for_tension
from final_analyst.schemas import FinalAnalystOutput


def contract_resolution(inp: FinalAnalystInput) -> tuple[str, str | None, str]:
    """Return (resolution, support_strength, evidence_pressure) from INPUT structure."""
    force = (inp.debate.metadata or {}).get("force_resolution")
    force_strength = (inp.debate.metadata or {}).get("force_assessment_strength")
    findings = list(all_canonical(inp))
    pressure = evidence_pressure(findings)

    tensions = [c for c in findings if str(c.finding_id).startswith("TENSION_")]
    primary = tensions[0] if tensions else (findings[0] if findings else None)
    if primary is not None:
        dr = resolve_debate_for_tension(inp, primary)
        res = dr.resolution
        support = dr.support_strength
    else:
        res = "unresolved"
        support = None

    if force in {"unresolved", "bull_supported", "bear_supported", "partially_resolved"}:
        res = force
        support = normalize_support_strength(force_strength, resolution=res)  # type: ignore[arg-type]

    return res, support, pressure


def pin_debate_contract(out: FinalAnalystOutput, inp: FinalAnalystInput) -> FinalAnalystOutput:
    """Overwrite LLM-rewritten resolution fields with deterministic INPUT contract.

    Does not invent facts; does not change Research claims; only pins judgment contract fields.
    """
    res, support, pressure = contract_resolution(inp)
    data = out.model_dump()

    ab = data.get("assessment_basis") or {}
    ab["primary_resolution"] = res
    ab["debate_support_strength"] = support
    ab["evidence_pressure"] = pressure
    data["assessment_basis"] = ab

    meta = data.get("meta") or {}
    meta["primary_resolution"] = res
    meta["debate_support_strength"] = support
    meta["evidence_pressure"] = pressure
    notes = list(meta.get("notes") or [])
    if "debate_contract_pinned" not in notes:
        notes.append("debate_contract_pinned")
    meta["notes"] = notes
    data["meta"] = meta

    for t in data.get("core_tensions") or []:
        if not isinstance(t, dict):
            continue
        dr = t.get("debate_resolution")
        if isinstance(dr, dict):
            dr["resolution"] = res
            if res == "unresolved":
                dr["support_strength"] = None
            elif support is not None:
                dr["support_strength"] = support
            t["debate_resolution"] = dr

    return FinalAnalystOutput.model_validate(data)
