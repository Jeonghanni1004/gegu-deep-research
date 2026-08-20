import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from final_analyst.dotenv_load import load_dotenv

p = load_dotenv(ROOT / ".env")
print("loaded", p)
print("FA_LIVE=", repr(os.getenv("FA_LIVE")))
print("KEY_SET=", bool(os.getenv("RESEARCH_LLM_API_KEY")))
print("BASE=", os.getenv("RESEARCH_LLM_BASE_URL"))
print("MODEL=", os.getenv("RESEARCH_LLM_MODEL"))

from final_analyst.live_runner import live_api_available, require_live

print("require_live", require_live())
print("live_api_available", live_api_available())
