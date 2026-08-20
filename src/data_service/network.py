"""Network helpers for AKShare / Eastmoney requests.

Some environments inject a broken system proxy. AKShare uses ``requests``,
which honors that proxy by default and then fails against Eastmoney hosts.
We disable trust_env / proxies once at process start.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import requests

_PATCHED = False
T = TypeVar("T")


def patch_requests_no_proxy() -> None:
    """Disable env/system proxy usage for all ``requests.Session`` calls."""
    global _PATCHED
    if _PATCHED:
        return

    original_request = requests.sessions.Session.request

    def _request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        self.trust_env = False
        kwargs.setdefault("proxies", {"http": None, "https": None})
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = 60
        return original_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _request  # type: ignore[method-assign]
    _PATCHED = True


def with_retry(
    func: Callable[[], T],
    *,
    retries: int = 3,
    delay_sec: float = 1.5,
    exceptions: tuple = (Exception,),
) -> T:
    """Run ``func`` with simple retries. Last exception is re-raised."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return func()
        except exceptions as exc:  # noqa: PERF203
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay_sec * (attempt + 1))
    assert last_exc is not None
    raise last_exc
