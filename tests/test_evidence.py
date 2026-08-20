"""Evidence Layer tests.

Usage:
  python -m tests.test_evidence --symbol 600519
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence.normalizer import build_evidence_pack, save_evidence_pack
from evidence.schema import EvidenceType, FORBIDDEN_OPINION_FIELDS, assert_no_opinion_fields


def _check(name: str, cond: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(cond), "detail": detail}


def run_tests(symbol: str = "600519") -> list[dict]:
    pack = build_evidence_pack(symbol=symbol)
    save_evidence_pack(pack)
    data = pack.to_dict()
    evidence = pack.evidence
    results = []

    # 1 FACT from AKShare
    facts = pack.get_by_type(EvidenceType.FACT)
    ak_facts = [e for e in facts if "akshare" in e.source.provider.lower() or e.source.provider.startswith("akshare")]
    # providers may be full source strings like akshare.stock_...
    ak_facts = [e for e in facts if "akshare" in e.source.provider.lower() or "eastmoney" not in e.source.provider.lower() and e.subtype in {
        "operating_revenue", "net_profit_parent", "close_price", "industry", "total_assets"
    }]
    has_revenue = any(e.subtype == "operating_revenue" for e in facts)
    has_np = any(e.subtype == "net_profit_parent" for e in facts)
    results.append(_check("akshare_fact_conversion", has_revenue and has_np, f"facts={len(facts)} revenue={has_revenue} np={has_np}"))

    # 2 DERIVED
    derived = pack.get_by_type(EvidenceType.DERIVED)
    need = {"revenue_yoy", "net_profit_yoy", "gross_margin", "roe", "ma20", "rsi_14"}
    got = {e.subtype for e in derived}
    results.append(_check("derived_conversion", need.issubset(got), f"missing={sorted(need-got)}"))

    # 3 Eastmoney announcements
    anns = [e for e in pack.get_by_type(EvidenceType.EVENT) if e.subtype == "announcement"]
    results.append(_check("eastmoney_announcement", len(anns) > 0, f"count={len(anns)}"))

    # 4 shareholder events
    holders = [e for e in pack.get_by_type(EvidenceType.EVENT) if e.subtype == "shareholder_change"]
    results.append(_check("eastmoney_shareholder", len(holders) > 0, f"count={len(holders)} sample={holders[0].claim if holders else None}"))

    # 5 CLS news/events
    cls_events = [e for e in pack.get_by_type(EvidenceType.EVENT) if e.source.provider == "cls"]
    results.append(_check("cls_news_conversion", len(cls_events) > 0, f"count={len(cls_events)}"))

    # 6 THS consensus
    exps = pack.get_expectations()
    eps = [e for e in exps if e.subtype == "eps_consensus"]
    results.append(_check("ths_consensus", len(eps) >= 1, f"count={len(eps)} claims={[e.claim for e in eps[:3]]}"))

    # 7 unique ids
    ids = [e.evidence_id for e in evidence]
    results.append(_check("evidence_id_unique", len(ids) == len(set(ids)), f"total={len(ids)} unique={len(set(ids))}"))

    # 8 source complete
    source_ok = all(e.source.provider and e.source.source_type and e.source.retrieved_at for e in evidence)
    results.append(_check("source_complete", source_ok, "provider/source_type/retrieved_at required"))

    # 9 time fields present appropriately
    time_ok = True
    bad = []
    for e in evidence:
        if e.evidence_type == EvidenceType.EVENT and not e.time.published_at:
            # allow missing only if still has retrieved_at
            if not e.time.retrieved_at:
                time_ok = False
                bad.append(e.evidence_id)
        if e.evidence_type in {EvidenceType.FACT, EvidenceType.DERIVED}:
            if not (e.time.report_date or e.time.data_date or e.time.retrieved_at):
                time_ok = False
                bad.append(e.evidence_id)
    results.append(_check("time_fields", time_ok, f"bad={bad[:5]}"))

    # 10 freshness
    freshness_ok = all(e.freshness and e.freshness.status for e in evidence)
    results.append(_check("freshness", freshness_ok, "all evidence have freshness.status"))

    # 11 no opinion fields
    try:
        assert_no_opinion_fields(data)
        # also ensure none of forbidden keys appear as evidence attributes via dump
        opinion_ok = True
        detail = "clean"
    except ValueError as exc:
        opinion_ok = False
        detail = str(exc)
    # hard check forbidden names not in schema dump keys at top-level evidence items
    for e in data["evidence"]:
        if FORBIDDEN_OPINION_FIELDS & set(e.keys()):
            opinion_ok = False
            detail = "forbidden keys in evidence object"
            break
    results.append(_check("no_opinion_fields", opinion_ok, detail))

    # 12 pack queries
    q_ok = (
        len(pack.get_by_type(EvidenceType.FACT)) > 0
        and len(pack.get_fundamental_facts()) > 0
        and len(pack.get_market_facts()) > 0
        and len(pack.get_expectations()) > 0
        and callable(pack.get_by_subtype)
        and callable(pack.get_by_source)
        and callable(pack.get_recent)
        and callable(pack.get_by_date_range)
        and callable(pack.get_company_events)
    )
    results.append(_check("evidence_pack_queries", q_ok, f"fund={len(pack.get_fundamental_facts())} market={len(pack.get_market_facts())}"))

    # bonus: sina excluded
    sina = [e for e in evidence if "sina" in e.source.provider.lower() or "新浪" in str(e.metadata.get("raw_source_label") or "")]
    results.append(_check("sina_excluded_from_core", len(sina) == 0, f"sina_count={len(sina)}"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="600519")
    args = parser.parse_args()
    results = run_tests(args.symbol)
    failed = 0
    print(json.dumps({"symbol": args.symbol, "results": results}, ensure_ascii=False, indent=2))
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"[{status}] {r['name']} | {r['detail']}")
        if not r["ok"]:
            failed += 1
    print(f"\nfailed={failed}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
