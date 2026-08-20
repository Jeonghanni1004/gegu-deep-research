import os
from pathlib import Path

print("process RESEARCH_LLM_API_KEY:", "SET" if os.getenv("RESEARCH_LLM_API_KEY") else "MISSING")
print("process OPENAI_API_KEY:", "SET" if os.getenv("OPENAI_API_KEY") else "MISSING")
print("process BASE:", os.getenv("RESEARCH_LLM_BASE_URL"))
print("process MODEL:", os.getenv("RESEARCH_LLM_MODEL"))
print("process FA_LIVE:", os.getenv("FA_LIVE"))
print(".env exists:", (Path(".") / ".env").exists())
