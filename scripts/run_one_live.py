"""Run a single live fixture for faster debugging."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from final_analyst.dotenv_load import load_dotenv

load_dotenv(ROOT / ".env")

from evidence.pack import EvidencePack
from final_analyst.live_fixtures import build_live_fixtures
from final_analyst.live_runner import run_one_ab


async def main() -> None:
    fid = sys.argv[1] if len(sys.argv) > 1 else "A_unresolved"
    pack = EvidencePack.load_json(ROOT / "examples" / "600519_evidence_pack.json")
    fix = next(f for f in build_live_fixtures(ROOT) if f.fixture_id == fid)
    r = await run_one_ab(fix, pack=pack, force_live=True)
    print("mode=", r.openai_mode)
    print("notes=", r.notes[:4])
    if r.openai and r.openai_mode == "openai":
        print("exec=", r.openai.executive_assessment.text[:300])
        print("resolution=", r.openai.meta.primary_resolution)
    else:
        err = ROOT / "examples" / "fa_live" / "last_openai_error.txt"
        if err.exists():
            print(err.read_text(encoding="utf-8")[:800])


if __name__ == "__main__":
    asyncio.run(main())
