"""Shared HTTP helpers for market-source PoC (does not touch data_service)."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
EXAMPLES.mkdir(parents=True, exist_ok=True)

_SESSION = requests.Session()
_SESSION.trust_env = False
_SESSION.headers.update({"User-Agent": UA})
_SESSION.proxies = {"http": None, "https": None}

_EM_LAST = 0.0
_EM_MIN_INTERVAL = 1.0


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 20,
    eastmoney: bool = False,
) -> requests.Response:
    global _EM_LAST
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    if eastmoney:
        wait = _EM_MIN_INTERVAL - (time.time() - _EM_LAST)
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        resp = _SESSION.get(
            url,
            params=params,
            headers=hdrs,
            timeout=timeout,
            proxies={"http": None, "https": None},
        )
        return resp
    finally:
        if eastmoney:
            _EM_LAST = time.time()


def save_json(name: str, payload: Any) -> Path:
    path = EXAMPLES / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def attempt(name: str, fn) -> dict[str, Any]:
    started = time.time()
    try:
        data = fn()
        return {
            "name": name,
            "ok": True,
            "elapsed_sec": round(time.time() - started, 2),
            "data": data,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "ok": False,
            "elapsed_sec": round(time.time() - started, 2),
            "data": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
