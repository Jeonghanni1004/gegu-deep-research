"""Final Analyst pipeline entrypoint — Production Integration (Round 6).

Keeps Round-1–5 FA logic; adds as_of fail-closed, stage gates, production gate, trace.
EvidencePack is citation-only for FA (never primary analytical input).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from debate.debate_engine import run_debate
from debate.schemas import DebateResult
from evidence.pack import EvidencePack
from research.fundamental_agent import FundamentalAgent
from research.llm import create_llm_client
from research.market_agent import MarketAgent
from research.schemas import FundamentalResearch, MarketResearch

from final_analyst.agent import FinalAnalystAgent
from final_analyst.contract import FinalAnalystInput, build_final_analyst_input
from final_analyst.evidence_repair import repair_output_citations
from final_analyst.failures import FailureRecord, classify_error_message, classify_from_notes, primary_failure
from final_analyst.llm import GroundedFALLMClient
from final_analyst.production_gate import ProductionGateResult, run_production_gate
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.validators import validate_final_analyst

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


@dataclass
class PipelineResult:
    status: str  # PASS | FALLBACK_PASS | FAIL
    mode: str
    stock: str
    as_of: str
    output: FinalAnalystOutput | None = None
    failure_code: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    gate: dict[str, Any] = field(default_factory=dict)
    trace_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "stock": self.stock,
            "as_of": self.as_of,
            "failure_code": self.failure_code,
            "failures": self.failures,
            "gate": self.gate,
            "trace_path": self.trace_path,
            "notes": self.notes,
            "analyst_mode": self.output.analyst_mode if self.output else None,
            "output": self.output.model_dump(mode="json") if self.output else None,
        }


def save_final_analyst(out: FinalAnalystOutput, *, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or EXAMPLES
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{out.stock_code}_final_analyst.json"
    path.write_text(json.dumps(out.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_trace(stock: str, trace: dict[str, Any], *, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or EXAMPLES
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stock}_pipeline_trace.json"
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _check_as_of(
    *,
    requested: str | None,
    fund: FundamentalResearch,
    market: MarketResearch,
) -> tuple[bool, str | None, FailureRecord | None]:
    fund_as = fund.research_as_of_date
    mkt_as = market.research_as_of_date
    if fund_as != mkt_as:
        rec = classify_error_message(
            f"AS_OF_MISMATCH: fundamental={fund_as} market={mkt_as}",
            stage="research",
        )
        return False, fund_as, rec
    if requested and requested != fund_as:
        rec = classify_error_message(
            f"AS_OF_MISMATCH: requested={requested} research={fund_as}",
            stage="research",
        )
        return False, fund_as, rec
    return True, fund_as, None


async def run_final_analyst_pipeline(
    symbol: str,
    *,
    mode: str = "grounded",
    as_of: str | None = None,
    write_trace: bool = True,
    allow_fallback: bool = True,
) -> FinalAnalystOutput:
    """Backward-compatible entry: returns FinalAnalystOutput or raises on hard fail."""
    result = await run_production_pipeline(
        symbol,
        mode=mode,
        as_of=as_of,
        write_trace=write_trace,
        allow_fallback=allow_fallback,
    )
    if result.output is None or result.status == "FAIL":
        code = result.failure_code or "PRODUCTION_GATE_REJECT"
        raise ValueError(f"pipeline FA failed [{code}]: {result.notes[:3]}")
    return result.output


async def run_production_pipeline(
    symbol: str,
    *,
    mode: str = "grounded",
    as_of: str | None = None,
    write_trace: bool = True,
    allow_fallback: bool = True,
) -> PipelineResult:
    """Full production pipeline with gates, repair, fallback, and trace."""
    stages: list[dict[str, Any]] = []
    failures: list[FailureRecord] = []
    notes: list[str] = []
    requested_as_of = as_of
    research_as_of: str | None = None
    debate_as_of: str | None = None
    pack: EvidencePack | None = None
    out: FinalAnalystOutput | None = None
    fa_inp: FinalAnalystInput | None = None
    gate: ProductionGateResult | None = None
    repair_action = "none"
    fallback_used = False

    def _stage(name: str, status: str, **extra: Any) -> None:
        stages.append({"stage": name, "status": status, "ts": _ts(), **extra})

    try:
        pack_path = EXAMPLES / f"{symbol}_evidence_pack.json"
        if not pack_path.exists():
            failures.append(
                classify_error_message(f"CONTRACT_VIOLATION: missing evidence pack {pack_path.name}", stage="evidence")
            )
            _stage("evidence", "FAIL")
            raise RuntimeError("missing_pack")
        pack = EvidencePack.load_json(pack_path)
        _stage("evidence", "OK", pack_path=str(pack_path))

        fund_path = EXAMPLES / f"{symbol}_fundamental_research.json"
        mkt_path = EXAMPLES / f"{symbol}_market_research.json"
        debate_path = EXAMPLES / f"{symbol}_debate.json"

        research_llm = create_llm_client(mode="grounded", pack_for_validation=pack)
        if fund_path.exists() and mkt_path.exists():
            fundamental = FundamentalResearch.model_validate(json.loads(fund_path.read_text(encoding="utf-8")))
            market = MarketResearch.model_validate(json.loads(mkt_path.read_text(encoding="utf-8")))
            notes.append("research_loaded_from_artifacts")
        else:
            fund_agent = FundamentalAgent(llm=research_llm)
            mkt_agent = MarketAgent(llm=research_llm)
            fundamental = await fund_agent.research(pack, as_of=as_of)
            market = await mkt_agent.research(pack, as_of=as_of)
            notes.append("research_generated")

        as_ok, research_as_of, as_fail = _check_as_of(requested=requested_as_of, fund=fundamental, market=market)
        if not as_ok and as_fail:
            failures.append(as_fail)
            _stage("research", "FAIL", as_of=research_as_of)
            raise RuntimeError("as_of_mismatch")
        if not list(fundamental.canonical_findings or []):
            failures.append(classify_error_message("INVALID_RESEARCH: empty canonical_findings", stage="research"))
            _stage("research", "FAIL")
            raise RuntimeError("invalid_research")
        _stage("research", "OK", as_of=research_as_of)

        if debate_path.exists():
            debate = DebateResult.model_validate(json.loads(debate_path.read_text(encoding="utf-8")))
            need_refresh = any(not c.canonical_finding_ids for c in debate.bull.claims + debate.bear.claims)
            if need_refresh:
                debate = await run_debate(pack, fundamental, market)
                notes.append("debate_refreshed_missing_canonical_links")
            else:
                notes.append("debate_loaded_from_artifacts")
        else:
            debate = await run_debate(pack, fundamental, market)
            notes.append("debate_generated")

        debate_as_of = research_as_of  # DebateResult has no as_of field; bind to research
        if not debate.bull.claims or not debate.bear.claims:
            failures.append(classify_error_message("INVALID_DEBATE: missing bull/bear claims", stage="debate"))
            _stage("debate", "FAIL")
            raise RuntimeError("invalid_debate")
        _stage("debate", "OK", as_of=debate_as_of)

        fa_inp = build_final_analyst_input(
            fundamental=fundamental,
            market=market,
            debate=debate,
            mode="openai" if mode == "openai" else "grounded",
        )
        _stage("fa_input", "OK")

        agent = FinalAnalystAgent()
        try:
            out = await agent.analyze(
                fundamental=fundamental,
                market=market,
                debate=debate,
                mode=mode,
                pack_for_validation=pack,
                fa_input=fa_inp,
            )
            _stage("fa_generate", "OK", analyst_mode=out.analyst_mode)
            # LLM client may silently fall back to grounded — surface as taxonomy + trace.
            if mode == "openai" and out.analyst_mode == "grounded":
                fallback_used = True
                if "openai_rejected_or_failed_fallback_grounded" not in notes:
                    notes.append("openai_rejected_or_failed_fallback_grounded")
                # Prefer structured failure_attribution / real err over fallback wrapper.
                fr = classify_from_notes(list(out.meta.notes or []), default_action="fallback")
                if fr.code == "UNKNOWN":
                    failures.append(
                        classify_error_message(
                            "PROVIDER_FAILURE: openai path returned grounded without openai analyst_mode",
                            stage="fa_generate",
                        )
                    )
                else:
                    failures.append(fr)
                _stage("fallback", "OK", analyst_mode="grounded", source="llm_client_internal")
        except Exception as e:
            failures.append(classify_error_message(f"{type(e).__name__}: {e}", stage="fa_generate"))
            _stage("fa_generate", "FAIL", error=str(e)[:200])
            if not allow_fallback or mode == "grounded":
                raise
            # fallback path below
            out = None

        # Validate + repair loop
        if out is not None:
            val_errs = validate_final_analyst(out, fa_inp, pack=pack)
            if val_errs:
                repair = repair_output_citations(out, fa_inp, pack=pack, allow_scrub=False)
                repair_action = repair.action
                if repair.output is not None and repair.action in {"ACCEPT", "REPAIR"}:
                    out = repair.output
                    val_errs = validate_final_analyst(out, fa_inp, pack=pack)
                    _stage("evidence_repair", "OK", action=repair.action)
                else:
                    failures.append(
                        classify_error_message(
                            "EVIDENCE_REPAIR_FAILURE: " + ",".join(repair.unresolved_numbers[:4] or val_errs[:2]),
                            stage="evidence_repair",
                        )
                    )
                    _stage("evidence_repair", "FAIL", action=repair.action)
                    if mode == "openai" and allow_fallback:
                        out = None
                    else:
                        raise RuntimeError("repair_failed")

        if out is None and allow_fallback:
            grounded = GroundedFALLMClient(pack_for_validation=pack)
            out = await grounded.generate(fa_inp.model_copy(update={"mode": "grounded"}))
            fallback_used = True
            notes.append("openai_rejected_or_failed_fallback_grounded")
            _stage("fallback", "OK", analyst_mode="grounded")

        gate = run_production_gate(
            out,
            fa_inp,
            pack=pack,
            research_ok=True,
            debate_ok=True,
            as_of_ok=True,
            prior_failures=failures if fallback_used else [],
            is_fallback=fallback_used or (out is not None and mode == "openai" and out.analyst_mode == "grounded"),
            allow_repair=False,  # already attempted
        )
        _stage("production_gate", gate.decision, gate_status=gate.status)

        if gate.decision in {"REPAIR", "REGENERATE", "FALLBACK"} and allow_fallback and not fallback_used and mode == "openai":
            grounded = GroundedFALLMClient(pack_for_validation=pack)
            out = await grounded.generate(fa_inp.model_copy(update={"mode": "grounded"}))
            fallback_used = True
            notes.append(f"gate_{gate.decision}_triggered_fallback")
            gate = run_production_gate(
                out,
                fa_inp,
                pack=pack,
                research_ok=True,
                debate_ok=True,
                as_of_ok=True,
                prior_failures=failures + gate.failures,
                is_fallback=True,
                allow_repair=False,
            )
            _stage("fallback", "OK", after_gate=gate.decision)
            _stage("production_gate", gate.decision, gate_status=gate.status)

        if gate.status == "FAIL" or out is None:
            failures.extend(gate.failures)
            raise RuntimeError("production_gate_reject")

        save_final_analyst(out)
        status = "FALLBACK_PASS" if gate.status == "FALLBACK_PASS" or fallback_used else "PASS"
        result = PipelineResult(
            status=status,
            mode=out.analyst_mode,
            stock=symbol,
            as_of=research_as_of or out.research_as_of_date,
            output=out,
            failure_code=(primary_failure(failures).code if failures and fallback_used else None),
            failures=[f.to_dict() for f in failures],
            gate=gate.to_dict(),
            notes=notes,
        )
    except Exception as e:
        if not failures:
            failures.append(classify_error_message(f"{type(e).__name__}: {e}", stage="production_gate"))
        result = PipelineResult(
            status="FAIL",
            mode=mode,
            stock=symbol,
            as_of=requested_as_of or research_as_of or "",
            output=out,
            failure_code=(primary_failure(failures).code if primary_failure(failures) else "PRODUCTION_GATE_REJECT"),
            failures=[f.to_dict() for f in failures],
            gate=gate.to_dict() if gate else {},
            notes=notes + [str(e)[:200]],
        )

    trace = {
        "stock": symbol,
        "requested_as_of": requested_as_of,
        "research_as_of": research_as_of,
        "debate_as_of": debate_as_of,
        "mode": mode,
        "final_mode": result.mode,
        "status": result.status,
        "failure_code": result.failure_code,
        "repair_action": repair_action,
        "fallback": fallback_used,
        "final_gate": result.gate,
        "stages": stages,
        "notes": notes,
        "timestamp": _ts(),
    }
    if write_trace:
        path = _write_trace(symbol, trace)
        result.trace_path = str(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Final Analyst")
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--mode", default="grounded", choices=["grounded", "openai"])
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    result = asyncio.run(run_production_pipeline(args.symbol, mode=args.mode, as_of=args.as_of))
    print(
        json.dumps(
            {
                "status": result.status,
                "mode": result.mode,
                "stock": result.stock,
                "as_of": result.as_of,
                "failure_code": result.failure_code,
                "trace_path": result.trace_path,
                "analyst_mode": result.output.analyst_mode if result.output else None,
                "research_as_of_date": result.output.research_as_of_date if result.output else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
