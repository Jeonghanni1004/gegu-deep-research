"""Build EvidencePack from verified raw JSON files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evidence.normalizer import build_evidence_pack, save_evidence_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build EvidencePack")
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    pack = build_evidence_pack(symbol=args.symbol)
    path = save_evidence_pack(pack, args.output)
    d = pack.to_dict()
    print(f"Saved {path}")
    print(f"stock_code={d['stock_code']} evidence_count={d['evidence_count']}")
    print(f"counts_by_type={d['counts_by_type']}")
    print(f"company_events={len(pack.get_company_events())}")
    print(f"expectations={len(pack.get_expectations())}")
    print(f"fundamental_facts={len(pack.get_fundamental_facts())}")
    print(f"market_facts={len(pack.get_market_facts())}")
    recent = pack.summary_for_recent_facts(days=30)
    print(f"recent_30d_events={len(recent)}")
    for item in recent[:5]:
        print(" -", item["evidence_id"], item["claim"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
