"""Assemble a presentation snapshot from existing Evidence / Research / Debate / FA artifacts.

Does not call LLMs. Does not modify Agent core. Does not invent facts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from debate.schemas import DebateResult
from evidence.pack import EvidencePack
from final_analyst.judgment_frame import extract_judgment_frame
from final_analyst.schemas import FinalAnalystOutput
from research.schemas import FundamentalResearch, MarketResearch

try:
    from report_format import build_report
except ImportError:  # pragma: no cover
    from web.report_format import build_report  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

STAGE_LABELS = [
    ("evidence", "Evidence", "收集可引用事实"),
    ("fundamental", "Fundamental Research", "压缩基本面命题"),
    ("market", "Market Research", "市场与估值命题"),
    ("bull_bear", "Bull / Bear", "同一证据上的对立解释"),
    ("challenge", "Challenge", "质询对方解释"),
    ("rebuttal", "Rebuttal", "回应质询"),
    ("final_analyst", "Final Analyst", "给出条件化判断"),
    ("report", "Research Brief", "汇总给研究工作台"),
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_studies() -> list[dict[str, Any]]:
    studies: list[dict[str, Any]] = []
    for pack_path in sorted(EXAMPLES.glob("*_evidence_pack.json")):
        symbol = pack_path.name.replace("_evidence_pack.json", "")
        fa_path = EXAMPLES / f"{symbol}_final_analyst.json"
        if not fa_path.exists():
            continue
        name = _stock_name_from_pack(pack_path)
        studies.append(
            {
                "symbol": symbol,
                "name": name,
                "has_debate": (EXAMPLES / f"{symbol}_debate.json").exists(),
                "has_research": (EXAMPLES / f"{symbol}_fundamental_research.json").exists(),
                "source": "artifacts",
            }
        )
    return studies


def _stock_name_from_pack(pack_path: Path) -> str:
    try:
        data = _load_json(pack_path)
        for e in data.get("evidence") or []:
            if e.get("subtype") == "stock_name":
                val = (e.get("value") or {}).get("value")
                if val:
                    return str(val)
                claim = e.get("claim") or ""
                if "股票名称为" in claim:
                    return claim.split("股票名称为", 1)[-1].strip()
    except Exception:
        pass
    return pack_path.name.replace("_evidence_pack.json", "")


def resolve_symbol(query: str) -> str | None:
    q = (query or "").strip().upper().replace("SH", "").replace("SZ", "").replace(".", "")
    q_cn = (query or "").strip()
    for s in list_studies():
        if s["symbol"].upper() == q or s["symbol"] == q_cn:
            return s["symbol"]
        if q_cn and q_cn in s["name"]:
            return s["symbol"]
        if q and q in s["name"].upper():
            return s["symbol"]
    digits = "".join(c for c in q if c.isdigit())
    if len(digits) == 6:
        for s in list_studies():
            if s["symbol"] == digits:
                return s["symbol"]
    return None


def _finding_brief(f: Any) -> dict[str, Any]:
    return {
        "finding_id": getattr(f, "finding_id", None),
        "research_question": getattr(f, "research_question", None),
        "claim": f.claim,
        "interpretation": f.interpretation or "",
        "evidence_ids": list(f.evidence_ids or []),
        "numbers_preserved": list(getattr(f, "numbers_preserved", None) or []),
        "finding_kind": getattr(f, "finding_kind", None),
        "layer": "INPUT",
    }


def _stmt_brief(s: Any, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "kind": s.kind,
        "text": s.text,
        "canonical_finding_ids": list(s.canonical_finding_ids or []),
        "evidence_ids": list(s.evidence_ids or []),
        "debate_refs": list(s.debate_refs or []),
        "numbers_used": list(s.numbers_used or []),
        "assessment_strength": s.assessment_strength,
        "inference_status": s.inference_status,
        "layer": "FACT" if s.kind == "FACT" else "INFERENCE",
    }


_PROFILE_SUBTYPES = (
    "stock_name",
    "industry",
    "listing_date",
    "total_market_cap",
    "total_shares",
    "float_shares",
)


def _company_profile(pack: EvidencePack) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for e in pack.evidence:
        if e.subtype not in _PROFILE_SUBTYPES or e.subtype in found:
            continue
        val = (e.value or {}).get("value")
        found[e.subtype] = {
            "subtype": e.subtype,
            "claim": e.claim,
            "value": val,
            "unit": (e.value or {}).get("unit"),
            "evidence_id": e.evidence_id,
        }
    return [found[k] for k in _PROFILE_SUBTYPES if k in found]


def assemble_snapshot(symbol: str) -> dict[str, Any]:
    pack_path = EXAMPLES / f"{symbol}_evidence_pack.json"
    fa_path = EXAMPLES / f"{symbol}_final_analyst.json"
    if not pack_path.exists() or not fa_path.exists():
        raise FileNotFoundError(f"missing artifacts for {symbol}")

    pack = EvidencePack.load_json(pack_path)
    fa = FinalAnalystOutput.model_validate(_load_json(fa_path))
    fund = None
    market = None
    debate = None
    fund_path = EXAMPLES / f"{symbol}_fundamental_research.json"
    mkt_path = EXAMPLES / f"{symbol}_market_research.json"
    debate_path = EXAMPLES / f"{symbol}_debate.json"
    if fund_path.exists():
        fund = FundamentalResearch.model_validate(_load_json(fund_path))
    if mkt_path.exists():
        market = MarketResearch.model_validate(_load_json(mkt_path))
    if debate_path.exists():
        debate = DebateResult.model_validate(_load_json(debate_path))

    frame = extract_judgment_frame(fa)
    usage: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"research": [], "debate": [], "final_analyst": []})

    def mark(eid: str, bucket: str, ref: str) -> None:
        if not eid:
            return
        lst = usage[eid][bucket]
        if ref not in lst:
            lst.append(ref)

    if fund:
        for f in fund.canonical_findings:
            for eid in f.evidence_ids:
                mark(eid, "research", f"fundamental:{f.finding_id}")
    if market:
        for f in market.canonical_findings:
            for eid in f.evidence_ids:
                mark(eid, "research", f"market:{f.finding_id}")
    if debate:
        for c in list(debate.bull.claims) + list(debate.bear.claims):
            for eid in c.evidence_ids:
                mark(eid, "debate", c.claim_id)
        for ch in debate.challenges:
            for eid in ch.evidence_ids:
                mark(eid, "debate", ch.challenge_id)
        for rb in debate.rebuttals:
            for eid in rb.evidence_ids:
                mark(eid, "debate", rb.rebuttal_id)
    for eid in fa.evidence_ids:
        mark(eid, "final_analyst", "fa.evidence_ids")
    for eid in fa.executive_assessment.evidence_ids:
        mark(eid, "final_analyst", "executive_assessment")
    for i, d in enumerate(fa.key_drivers):
        for eid in d.evidence_ids:
            mark(eid, "final_analyst", f"key_driver[{i}]")

    cited = set(usage.keys())
    evidence_rows = []
    for e in pack.evidence:
        used = usage.get(e.evidence_id, {"research": [], "debate": [], "final_analyst": []})
        supports: list[str] = []
        if used["final_analyst"]:
            supports.append("Final Analyst 判断")
        if used["debate"]:
            supports.append("Debate 主张/质询")
        if used["research"]:
            supports.append("Research 命题")
        evidence_rows.append(
            {
                "evidence_id": e.evidence_id,
                "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
                "subtype": e.subtype,
                "claim": e.claim,
                "value": e.value,
                "source": e.source.model_dump(mode="json"),
                "time": e.time.model_dump(mode="json"),
                "freshness": e.freshness.model_dump(mode="json"),
                "reliability": e.reliability.value if hasattr(e.reliability, "value") else str(e.reliability),
                "used_by": used,
                "supports": supports,
                "cited": e.evidence_id in cited,
            }
        )
    evidence_rows.sort(key=lambda r: (not r["cited"], r["evidence_type"], r["subtype"]))

    counts = {"FACT": 0, "DERIVED": 0, "EVENT": 0, "EXPECTATION": 0}
    for e in pack.evidence:
        k = e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type)
        counts[k] = counts.get(k, 0) + 1

    tensions = []
    for t in fa.core_tensions:
        tensions.append(
            {
                "tension_id": t.tension_id,
                "research_question": t.research_question,
                "bull_position": t.debate_resolution.bull_position,
                "bear_position": t.debate_resolution.bear_position,
                "resolution": t.debate_resolution.resolution,
                "resolution_reason": t.debate_resolution.resolution_reason,
                "assessment_strength": t.debate_resolution.assessment_strength,
                "support_strength": t.debate_resolution.support_strength,
                "decisive_evidence_ids": list(t.debate_resolution.decisive_evidence_ids or []),
                "current_assessment": _stmt_brief(t.current_assessment, "tension_assessment"),
                "unresolved_challenges": list(t.debate_resolution.unresolved_challenges or []),
                "accepted_rebuttals": list(t.debate_resolution.accepted_rebuttals or []),
                "partially_accepted_rebuttals": list(t.debate_resolution.partially_accepted_rebuttals or []),
                "layer": "INFERENCE",
            }
        )

    debate_view = None
    if debate:
        claim_by_id = {c.claim_id: c for c in debate.bull.claims + debate.bear.claims}
        chains = []
        for ch in debate.challenges:
            rbs = [r for r in debate.rebuttals if r.target_challenge_id == ch.challenge_id]
            target = claim_by_id.get(ch.target_claim_id)
            chains.append(
                {
                    "challenge_id": ch.challenge_id,
                    "challenger": ch.challenger,
                    "challenge_type": ch.challenge_type,
                    "argument": ch.argument,
                    "evidence_ids": list(ch.evidence_ids or []),
                    "target_claim_id": ch.target_claim_id,
                    "target_claim": target.claim if target else "",
                    "target_stance": target.stance if target else None,
                    "layer": "INFERENCE",
                    "rebuttals": [
                        {
                            "rebuttal_id": r.rebuttal_id,
                            "author": r.author,
                            "response_type": r.response_type,
                            "argument": r.argument,
                            "evidence_ids": list(r.evidence_ids or []),
                            "layer": "INFERENCE",
                        }
                        for r in rbs
                    ],
                }
            )
        debate_view = {
            "bull": {
                "thesis": debate.bull.thesis,
                "claims": [
                    {
                        "claim_id": c.claim_id,
                        "claim": c.claim,
                        "reasoning": c.reasoning,
                        "evidence_ids": list(c.evidence_ids or []),
                        "canonical_finding_ids": list(c.canonical_finding_ids or []),
                        "layer": "INFERENCE",
                    }
                    for c in debate.bull.claims
                ],
                "key_risks": list(debate.bull.key_risks or []),
                "uncertainties": list(debate.bull.uncertainties or []),
            },
            "bear": {
                "thesis": debate.bear.thesis,
                "claims": [
                    {
                        "claim_id": c.claim_id,
                        "claim": c.claim,
                        "reasoning": c.reasoning,
                        "evidence_ids": list(c.evidence_ids or []),
                        "canonical_finding_ids": list(c.canonical_finding_ids or []),
                        "layer": "INFERENCE",
                    }
                    for c in debate.bear.claims
                ],
                "key_opportunities": list(debate.bear.key_opportunities or []),
                "uncertainties": list(debate.bear.uncertainties or []),
            },
            "chains": chains,
            "summary": debate.debate_summary.model_dump(mode="json"),
            "rounds": list(debate.execution.rounds_executed) if debate.execution else [],
        }

    trace_path = EXAMPLES / f"{symbol}_pipeline_trace.json"
    gate = None
    if trace_path.exists():
        trace = _load_json(trace_path)
        gate = trace.get("final_gate")

    name = _stock_name_from_pack(pack_path)
    profile = _company_profile(pack)
    snap = {
        "symbol": symbol,
        "name": name,
        "as_of": fa.research_as_of_date,
        "analyst_mode": fa.analyst_mode,
        "source": "grounded_artifacts",
        "no_llm_call": True,
        "pipeline_stages": [
            {"id": i, "key": k, "title": t, "note": n} for i, (k, t, n) in enumerate(STAGE_LABELS)
        ],
        "gate": gate,
        "company": {
            "stock_code": symbol,
            "name": name,
            "as_of": fa.research_as_of_date,
            "profile": profile,
        },
        "counts": {
            "evidence": len(pack.evidence),
            "cited_evidence": len(cited),
            "by_type": counts,
            "fundamental_findings": len(fund.canonical_findings) if fund else 0,
            "market_findings": len(market.canonical_findings) if market else 0,
            "bull_claims": len(debate.bull.claims) if debate else 0,
            "bear_claims": len(debate.bear.claims) if debate else 0,
            "challenges": len(debate.challenges) if debate else 0,
            "rebuttals": len(debate.rebuttals) if debate else 0,
        },
        "judgment": frame.model_dump(mode="json"),
        "final_analyst": {
            "executive_assessment": _stmt_brief(fa.executive_assessment, "executive"),
            "core_thesis": _stmt_brief(fa.core_thesis, "thesis"),
            "key_drivers": [_stmt_brief(d, f"driver[{i}]") for i, d in enumerate(fa.key_drivers)],
            "assessment_basis": fa.assessment_basis.model_dump(mode="json"),
            "base_case": {
                "label": fa.base_case.label,
                "thesis": _stmt_brief(fa.base_case.thesis, "base"),
                "explanation_shift_variable": fa.base_case.explanation_shift_variable,
            },
            "bull_case": {
                "label": fa.bull_case.label,
                "thesis": _stmt_brief(fa.bull_case.thesis, "bull_case"),
                "explanation_shift_variable": fa.bull_case.explanation_shift_variable,
            },
            "bear_case": {
                "label": fa.bear_case.label,
                "thesis": _stmt_brief(fa.bear_case.thesis, "bear_case"),
                "explanation_shift_variable": fa.bear_case.explanation_shift_variable,
            },
            "uncertainty": [_stmt_brief(u, "uncertainty") for u in fa.uncertainty],
            "research_gaps": [_stmt_brief(g, "gap") for g in fa.research_gaps],
            "what_would_change_my_view": [v.model_dump(mode="json") for v in fa.what_would_change_my_view],
            "tensions": tensions,
            "evidence_trace": [link.model_dump(mode="json") for link in fa.evidence_trace],
            "why_this_judgment": fa.assessment_basis.model_dump(mode="json"),
            "meta": fa.meta.model_dump(mode="json"),
            "constraints": [
                "判断受 Evidence grounding 约束：不得创造数字或 evidence",
                "Debate resolution / support / pressure 是 INPUT contract，FA 不得改写",
                "JudgmentFrame 由结构提取，而非自由生成",
                "Production Gate 校验：无交易建议、无 information_loss、无 unsupported fact",
            ],
        },
        "research": {
            "fundamental_summary": fund.summary if fund else "",
            "market_summary": market.summary if market else "",
            "fundamental_as_of": fund.research_as_of_date if fund else None,
            "market_as_of": market.research_as_of_date if market else None,
            "fundamental_findings": [_finding_brief(f) for f in (fund.canonical_findings if fund else [])],
            "market_findings": [_finding_brief(f) for f in (market.canonical_findings if market else [])],
            "fundamental_tensions": [_finding_brief(f) for f in (fund.research_tensions if fund else [])],
            "market_tensions": [_finding_brief(f) for f in (market.research_tensions if market else [])],
        },
        "debate": debate_view,
        "evidence": evidence_rows,
    }
    snap["report"] = build_report(snap)
    return snap
