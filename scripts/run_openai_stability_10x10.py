"""Formal openai stability bench (pack=None). PYTHONUNBUFFERED=1 recommended.

Default output: stability_10x10_openai_r10_final.json
Never overwrites locked Round-8 official artifact stability_10x10_openai_r8.json (84/100).
Prefer scripts/run_openai_stability_r10.py for Round-10 formal runs.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from final_analyst.dotenv_load import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from final_analyst.stability_bench import run_stability_benchmark

LOCKED_R8 = "stability_10x10_openai_r8.json"


async def main() -> None:
    os.environ["FA_LIVE"] = "1"
    stats = await run_stability_benchmark(
        root=ROOT,
        mode="openai",
        n_fixtures=int(os.getenv("FA_BENCH_FIXTURES") or "10"),
        n_runs=int(os.getenv("FA_BENCH_RUNS") or "10"),
        pack=None,
    )
    out = stats.to_dict()
    out_name = os.getenv("FA_BENCH_OUT") or "stability_10x10_openai_r10_final.json"
    if out_name == LOCKED_R8:
        raise SystemExit(f"Refusing to overwrite locked Round-8 official artifact ({LOCKED_R8})")
    out_path = ROOT / "examples" / "evaluation" / out_name
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    if out.get("aborted_quota") or out.get("incomplete"):
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
