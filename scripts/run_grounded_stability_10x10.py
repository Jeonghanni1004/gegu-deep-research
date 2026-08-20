"""Write grounded 10×10 baseline artifact."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from final_analyst.dotenv_load import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from final_analyst.stability_bench import run_stability_benchmark


async def main() -> None:
    os.environ.pop("FA_LIVE", None)
    stats = await run_stability_benchmark(
        root=ROOT,
        mode="grounded",
        n_fixtures=int(os.getenv("FA_BENCH_FIXTURES") or "10"),
        n_runs=int(os.getenv("FA_BENCH_RUNS") or "10"),
        pack=None,
    )
    out = stats.to_dict()
    out_path = ROOT / "examples" / "evaluation" / "stability_10x10_grounded.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
