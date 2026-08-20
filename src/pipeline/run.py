"""Production CLI: python -m pipeline.run --stock 600519 --as-of YYYY-MM-DD --mode openai|grounded"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_analyst.dotenv_load import load_dotenv

load_dotenv(ROOT / ".env")

from final_analyst.pipeline import run_production_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share Production Pipeline (Evidence→Research→Debate→FA)")
    parser.add_argument("--stock", "--symbol", dest="stock", default="600519")
    parser.add_argument("--as-of", dest="as_of", default=None)
    parser.add_argument("--mode", default="grounded", choices=["grounded", "openai"])
    args = parser.parse_args()

    result = asyncio.run(
        run_production_pipeline(
            args.stock,
            mode=args.mode,
            as_of=args.as_of,
            write_trace=True,
            allow_fallback=True,
        )
    )
    payload = {
        "status": result.status,
        "mode": result.mode,
        "stock": result.stock,
        "as_of": result.as_of,
        "failure_code": result.failure_code,
        "trace_path": result.trace_path,
        "gate": result.gate,
        "notes": result.notes[:8],
    }
    # Include compact output summary (full schema available on disk)
    if result.output is not None:
        payload["final_output_summary"] = {
            "analyst_mode": result.output.analyst_mode,
            "primary_resolution": result.output.meta.primary_resolution,
            "assessment_strength": result.output.meta.assessment_strength,
            "executive": result.output.executive_assessment.text[:240],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if result.status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
