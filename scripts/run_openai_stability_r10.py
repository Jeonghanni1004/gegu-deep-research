"""Formal OpenAI/DeepSeek 10×10 for Round-10.

- Writes stability_10x10_openai_r10_final.json (never overwrites R8 locked artifact)
- Single-process; thinking off via FA_THINKING unset/false
- Quota fuse via FA_QUOTA_FUSE / FA_QUOTA_FUSE_MAX (bench aborts → incomplete, not adjudicable)
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

LOCKED = {
    "stability_10x10_openai_r8.json",
    "stability_10x10_openai_r8_quota_exhaust.json",
    "round8_failure_diagnosis_formal84.json",
    "round8_failed_runs_formal84.json",
}


async def main() -> None:
    os.environ["FA_LIVE"] = "1"
    os.environ.setdefault("FA_THINKING", "0")
    os.environ.setdefault("FA_BENCH_FIXTURES", "10")
    os.environ.setdefault("FA_BENCH_RUNS", "10")
    os.environ.setdefault("FA_QUOTA_FUSE", "3")
    os.environ.setdefault("FA_QUOTA_FUSE_MAX", "8")
    os.environ.setdefault("FA_DIAG_OUT", "round10_failure_diagnosis.json")
    out_name = os.getenv("FA_BENCH_OUT") or "stability_10x10_openai_r10_final.json"
    if out_name in LOCKED or out_name == "stability_10x10_openai_r8.json":
        raise SystemExit(f"Refusing to overwrite locked artifact: {out_name}")

    stats = await run_stability_benchmark(
        root=ROOT,
        mode="openai",
        n_fixtures=int(os.environ["FA_BENCH_FIXTURES"]),
        n_runs=int(os.environ["FA_BENCH_RUNS"]),
        pack=None,
    )
    out = stats.to_dict()
    out["round"] = "r10"
    out["locked_r8_success_baseline"] = 84
    out_path = ROOT / "examples" / "evaluation" / out_name
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    if out.get("aborted_quota") or out.get("incomplete"):
        print(
            f"\n[VOID] incomplete formal run: {out.get('abort_reason') or 'incomplete'}; "
            "do not adjudicate Strict GO from this artifact.",
            flush=True,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
