"""Independent module tests for the data service layer.

Usage:
  python -m tests.run_module_tests
  python -m tests.run_module_tests company
  python -m tests.run_module_tests history
  python -m tests.run_module_tests all --symbol 600519
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

from data_service.derived.indicators import test_indicators  # noqa: E402
from data_service.raw.company_info import test_company_info  # noqa: E402
from data_service.raw.financials import test_financials  # noqa: E402
from data_service.raw.main_business import test_main_business  # noqa: E402
from data_service.raw.market_history import test_market_history  # noqa: E402
from data_service.raw.market_snapshot import test_market_snapshot  # noqa: E402
from data_service.service import fetch_stock_bundle, save_bundle  # noqa: E402


TESTS = {
    "company": test_company_info,
    "business": test_main_business,
    "financials": test_financials,
    "history": test_market_history,
    "snapshot": test_market_snapshot,
    "indicators": test_indicators,
}


def _print(title: str, payload: dict) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run A-share data module tests")
    parser.add_argument(
        "module",
        nargs="?",
        default="all",
        choices=[*TESTS.keys(), "all", "bundle"],
        help="module name, all, or bundle",
    )
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--save", action="store_true", help="save full bundle JSON under examples/")
    args = parser.parse_args()

    symbol = args.symbol
    failed = 0

    if args.module in {"all", "bundle"} or args.save:
        if args.module == "bundle" or args.save:
            path = save_bundle(symbol)
            print(f"Saved bundle -> {path}")
            if args.module == "bundle":
                bundle = json.loads(path.read_text(encoding="utf-8"))
                summary = {
                    "stock_code": bundle["stock_code"],
                    "retrieved_at": bundle["retrieved_at"],
                    "raw_keys": list(bundle["layers"]["raw"].keys()),
                    "history_bars": len(bundle["layers"]["raw"]["market_history"].get("items") or []),
                    "income_periods": len(
                        bundle["layers"]["raw"]["financials"]["income_statement"].get("items") or []
                    ),
                    "derived_fundamentals": bundle["layers"]["derived"]["fundamentals"].get("latest"),
                    "derived_technicals": bundle["layers"]["derived"]["technicals"].get("latest"),
                    "todos": bundle.get("todos"),
                }
                _print("bundle_summary", summary)
                return 0

    targets = list(TESTS.keys()) if args.module == "all" else [args.module]
    for name in targets:
        fn = TESTS[name]
        try:
            result = fn(symbol)
            ok = bool(result.get("ok"))
            if not ok:
                failed += 1
            _print(name, result)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            _print(name, {"ok": False, "error": str(exc)})

    print(f"\nDone. failed={failed}/{len(targets)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
