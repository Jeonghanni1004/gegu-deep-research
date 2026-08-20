"""Adversarial debate layer tests.

Usage:
  python -m tests.test_debate --symbol 600519
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence.pack import EvidencePack
from evidence.schema import Evidence, EvidenceSource, EvidenceTime, EvidenceType, Freshness, FreshnessStatus, Reliability
from research.schemas import FundamentalResearch, MarketResearch

from debate.bear_agent import BearAgent
from debate.bull_agent import BullAgent
from debate.context import build_shared_context
from debate.debate_engine import run_debate, save_debate_outputs
from debate.evidence_weight import calculate_evidence_weight, freshness_weight, reliability_weight
from debate.schemas import DebateResult


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": detail}


def _load_research(symbol: str):
    examples = ROOT / "examples"
    pack = EvidencePack.load_json(examples / f"{symbol}_evidence_pack.json")
    fundamental = FundamentalResearch.model_validate(
        json.loads((examples / f"{symbol}_fundamental_research.json").read_text(encoding="utf-8"))
    )
    market = MarketResearch.model_validate(
        json.loads((examples / f"{symbol}_market_research.json").read_text(encoding="utf-8"))
    )
    return pack, fundamental, market


def _make_evidence(*, reliability: Reliability, freshness: FreshnessStatus) -> Evidence:
    return Evidence(
        evidence_id="test_ev_1",
        stock_code="600519",
        evidence_type=EvidenceType.FACT,
        subtype="close_price",
        claim="test",
        value={},
        source=EvidenceSource(provider="test", source_type="unit", retrieved_at="2026-01-01"),
        time=EvidenceTime(data_date="2026-01-01"),
        freshness=Freshness(age_hours=1.0, status=freshness),
        reliability=reliability,
    )


def _authored_text(result: DebateResult) -> str:
    parts = [
        result.bull.thesis,
        result.bear.thesis,
        " ".join(result.debate_summary.shared_facts),
        " ".join(result.debate_summary.core_disagreements),
        " ".join(result.debate_summary.unresolved_issues),
    ]
    for c in result.bull.claims + result.bear.claims:
        parts.extend([c.claim, c.reasoning])
    for ch in result.challenges:
        parts.append(ch.argument)
    for rb in result.rebuttals:
        parts.append(rb.argument)
    return "\n".join(parts)


async def _run_async(symbol: str) -> list[dict]:
    results: list[dict] = []
    pack, fundamental, market = _load_research(symbol)
    before = copy.deepcopy([e.model_dump(mode="json") for e in pack.evidence])
    known_ids = {e.evidence_id for e in pack.evidence}

    # Evidence weight unit checks
    w1 = calculate_evidence_weight(_make_evidence(reliability=Reliability.HIGH, freshness=FreshnessStatus.VERY_RECENT))
    w2 = calculate_evidence_weight(_make_evidence(reliability=Reliability.LOW, freshness=FreshnessStatus.STALE))
    results.append(_check("evidence_weight_high_recent", abs(w1 - 1.0) < 1e-9, f"w={w1}"))
    results.append(_check("evidence_weight_low_stale", abs(w2 - 0.24) < 1e-9, f"w={w2} expected=0.24"))
    results.append(_check("reliability_table", reliability_weight("medium") == 0.8, str(reliability_weight("medium"))))
    results.append(_check("freshness_table", freshness_weight("periodic") == 0.8, str(freshness_weight("periodic"))))

    # Identical shared context
    ctx_a = build_shared_context(pack, fundamental, market)
    ctx_b = build_shared_context(pack, fundamental, market)
    results.append(_check("shared_context_identical", ctx_a == ctx_b, "fingerprint equal"))

    bull_agent = BullAgent()
    bear_agent = BearAgent()

    def _block(*a, **k):
        raise RuntimeError("network forbidden in debate")

    with mock.patch("requests.get", side_effect=_block), mock.patch(
        "requests.post", side_effect=_block
    ), mock.patch("requests.request", side_effect=_block):
        # Parallel claims timing smoke: gather returns both
        t0 = time.perf_counter()
        bull, bear = await asyncio.gather(
            bull_agent.research(pack, fundamental, market, shared_context=ctx_a),
            bear_agent.research(pack, fundamental, market, shared_context=ctx_a),
        )
        claim_elapsed = time.perf_counter() - t0

        result = await run_debate(pack, fundamental, market, bull_agent=bull_agent, bear_agent=bear_agent)

    results.append(_check("parallel_claims", bool(bull.claims) and bool(bear.claims), f"elapsed={claim_elapsed:.4f}"))
    results.append(_check("bull_max_3_claims", len(result.bull.claims) <= 3, f"n={len(result.bull.claims)}"))
    results.append(_check("bear_max_3_claims", len(result.bear.claims) <= 3, f"n={len(result.bear.claims)}"))

    bull_ids_ok = all(c.evidence_ids and all(i in known_ids for i in c.evidence_ids) for c in result.bull.claims)
    bear_ids_ok = all(c.evidence_ids and all(i in known_ids for i in c.evidence_ids) for c in result.bear.claims)
    results.append(_check("bull_claims_have_evidence_id", bull_ids_ok, [c.claim_id for c in result.bull.claims]))
    results.append(_check("bear_claims_have_evidence_id", bear_ids_ok, [c.claim_id for c in result.bear.claims]))

    claim_ids = {c.claim_id for c in result.bull.claims + result.bear.claims}
    ch_ok = all(ch.target_claim_id in claim_ids for ch in result.challenges)
    results.append(_check("challenges_target_existing_claims", ch_ok, f"n={len(result.challenges)}"))

    ch_ids = {ch.challenge_id for ch in result.challenges}
    rb_ok = all(rb.target_challenge_id in ch_ids for rb in result.rebuttals)
    results.append(_check("rebuttals_target_existing_challenges", rb_ok, f"n={len(result.rebuttals)}"))

    # cited evidence in challenges/rebuttals must exist
    cited_ok = True
    missing = []
    for obj in list(result.challenges) + list(result.rebuttals):
        for eid in obj.evidence_ids:
            if eid not in known_ids:
                cited_ok = False
                missing.append(eid)
    results.append(_check("challenge_rebuttal_ids_in_pack", cited_ok, f"missing={missing[:5]}"))

    # weights present and match formula
    weight_ok = True
    detail = ""
    by_id = {e.evidence_id: e for e in pack.evidence}
    for w in result.evidence_weights:
        ev = by_id.get(w.evidence_id)
        if not ev:
            weight_ok = False
            detail = f"unknown {w.evidence_id}"
            break
        expected = calculate_evidence_weight(ev)
        if abs(expected - w.weight) > 1e-9:
            weight_ok = False
            detail = f"{w.evidence_id} {w.weight}!={expected}"
            break
    results.append(_check("evidence_weights_correct", weight_ok and len(result.evidence_weights) >= 1, detail or f"n={len(result.evidence_weights)}"))

    after = [e.model_dump(mode="json") for e in pack.evidence]
    results.append(_check("no_new_or_mutated_evidence", before == after, f"{len(before)}->{len(after)}"))

    # max 2 debate rounds after claims: rounds = claims, challenges, rebuttals
    rounds = (result.execution.rounds_executed if result.execution else []) or []
    results.append(
        _check(
            "max_two_debate_rounds",
            rounds == ["claims", "challenges", "rebuttals"] and (result.execution.max_rounds if result.execution else 0) == 2,
            str(rounds),
        )
    )
    results.append(
        _check(
            "parallel_flags",
            bool(result.execution and result.execution.parallel_claims and result.execution.parallel_challenges and result.execution.parallel_rebuttals),
            str(result.execution.model_dump() if result.execution else None),
        )
    )

    results.append(_check("no_internet", True, "requests blocked"))

    # schema validate
    DebateResult.model_validate(result.model_dump(mode="json"))
    results.append(_check("pydantic_schema", True, "DebateResult"))

    # no BUY/SELL / probabilities / scores
    authored = _authored_text(result)
    authored_u = authored.upper()
    banned = ["STRONG BUY", "STRONG SELL", "买入", "卖出", "加仓", "减仓", "目标价"]
    has_ban = any(b in authored or b in authored_u for b in banned)
    dump = result.model_dump(mode="json")
    dump_s = json.dumps(dump, ensure_ascii=False)
    score_ban = any(
        k in dump_s
        for k in (
            '"bull_score"',
            '"bear_score"',
            '"bull_probability"',
            '"bear_probability"',
            '"buy_probability"',
        )
    )
    results.append(_check("no_trade_advice", not has_ban, "authored fields"))
    results.append(_check("no_score_probability", not score_ban, "no bull/bear scores"))

    # Traceability: claim → evidence → source/date
    c0 = result.bull.claims[0]
    e0 = by_id[c0.evidence_ids[0]]
    trace_ok = bool(e0.source.provider) and bool(e0.time.report_date or e0.time.data_date or e0.time.published_at)
    results.append(
        _check(
            "traceability_chain",
            trace_ok,
            f"{c0.claim_id}->{e0.evidence_id}->{e0.source.provider}->{e0.source.url}->{e0.time.report_date or e0.time.data_date}",
        )
    )

    # interpretation conflict exists ideally
    has_interp = any(ch.challenge_type == "interpretation_conflict" for ch in result.challenges)
    results.append(_check("interpretation_conflict_marked", has_interp, [ch.challenge_type for ch in result.challenges]))

    paths = save_debate_outputs(result, out_dir=ROOT / "examples")
    results.append(
        _check(
            "outputs_saved",
            all(p.exists() and p.stat().st_size > 50 for p in paths.values()),
            {k: str(v) for k, v in paths.items()},
        )
    )

    # debate_summary required fields
    results.append(
        _check(
            "debate_summary_present",
            bool(result.debate_summary.shared_facts)
            and bool(result.debate_summary.core_disagreements)
            and bool(result.debate_summary.unresolved_issues),
            result.debate_summary.model_dump(),
        )
    )

    return results


def run_tests(symbol: str = "600519") -> list[dict]:
    return asyncio.run(_run_async(symbol))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="600519")
    args = parser.parse_args()
    results = run_tests(args.symbol)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['name']}: {r['detail']}")
    print(f"\n{passed}/{total} PASS")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
