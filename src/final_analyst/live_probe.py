"""One-shot OpenAI connectivity check for Final Analyst live mode.

Usage (CMD):
  set RESEARCH_LLM_API_KEY=...
  set RESEARCH_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  set RESEARCH_LLM_MODEL=qwen-plus
  set PYTHONPATH=C:\\Users\\86137\\ashare-deep-research\\src
  python -m final_analyst.live_probe
"""

from final_analyst.dotenv_load import load_dotenv

load_dotenv()

import json
import os
import sys
from pathlib import Path

import requests


def main() -> None:
    key = os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base = (os.getenv("RESEARCH_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("RESEARCH_LLM_MODEL") or "gpt-4o-mini"
    if not key:
        print("FAIL: no API key in env")
        raise SystemExit(1)

    print(f"base_url={base}")
    print(f"model={model}")
    print(f"key_prefix={key[:6]}... len={len(key)}")

    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": '{"ping": true}'},
        ],
        "thinking": {"type": "disabled"},
    }
    # Some providers reject response_format; probe without it first.
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        print(f"status={resp.status_code}")
        text = resp.text[:800]
        print(f"body={text}")
        out = Path(__file__).resolve().parents[2] / "examples" / "fa_live" / "live_probe.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"base_url": base, "model": model, "status": resp.status_code, "body": resp.text[:4000]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if resp.status_code >= 400:
            raise SystemExit(2)
        print("OK: API reachable")
    except requests.RequestException as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        raise SystemExit(3)


if __name__ == "__main__":
    main()
