"""Aggregate data service: raw + derived layers (AI layer reserved)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .derived.indicators import compute_all_indicators
from .network import patch_requests_no_proxy
from .raw.company_info import get_company_info
from .raw.financials import get_financials
from .raw.main_business import get_main_business
from .raw.market_history import get_market_history
from .raw.market_snapshot import get_market_snapshot
from .utils import meta, normalize_symbol, now_utc_iso


class DataService:
    """Stable data acquisition facade for the Deep Research MVP."""

    def __init__(self, symbol: str = "600519"):
        self.symbol = normalize_symbol(symbol)

    def fetch_raw(self) -> dict[str, Any]:
        patch_requests_no_proxy()
        company = get_company_info(self.symbol)
        main_business = get_main_business(self.symbol)
        financials = get_financials(self.symbol)
        market_history = get_market_history(self.symbol, years=3)
        market_snapshot = get_market_snapshot(self.symbol)
        return {
            "company_info": company,
            "main_business": main_business,
            "financials": financials,
            "market_history": market_history,
            "market_snapshot": market_snapshot,
        }

    def fetch_bundle(self) -> dict[str, Any]:
        """Return layered payload: raw / derived / ai_analysis(placeholder)."""
        raw = self.fetch_raw()
        derived = compute_all_indicators(
            financials=raw["financials"],
            market_history=raw["market_history"],
        )
        todos = self._collect_todos(raw, derived)
        return {
            "schema_version": "1.0.0",
            "stock_code": self.symbol,
            "retrieved_at": now_utc_iso(),
            "layers": {
                "raw": raw,
                "derived": derived,
                "ai_analysis": {
                    "status": "not_implemented",
                    "note": "Reserved for stage-2 AI agent. Do not mix into raw/derived.",
                    "items": [],
                },
            },
            "todos": todos,
            "_meta": meta(source="data_service.fetch_bundle"),
        }

    @staticmethod
    def _collect_todos(raw: dict[str, Any], derived: dict[str, Any]) -> list[dict[str, Any]]:
        todos: list[dict[str, Any]] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if "todos" in node and isinstance(node["todos"], list):
                    todos.extend(node["todos"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(raw)
        walk(derived)
        return todos


def fetch_stock_bundle(symbol: str = "600519") -> dict[str, Any]:
    return DataService(symbol).fetch_bundle()


def save_bundle(symbol: str = "600519", output_path: str | Path | None = None) -> Path:
    bundle = fetch_stock_bundle(symbol)
    path = Path(output_path) if output_path else Path("examples") / f"{normalize_symbol(symbol)}_bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Market history can be large; keep full data but ensure JSON-serializable
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
