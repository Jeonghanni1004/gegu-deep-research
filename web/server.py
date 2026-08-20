"""Deep Research Demo web server.

Read-only over frozen grounded artifacts. Default path does NOT call LLMs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEB = Path(__file__).resolve().parent
STATIC = WEB / "static"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from assemble import assemble_snapshot, list_studies, resolve_symbol

app = FastAPI(
    title="A-Share Deep Research Demo",
    description="Single-stock research workspace over frozen Final Analyst artifacts. No LLM by default.",
    version="0.1.0",
)


class StartRequest(BaseModel):
    query: str = Field(..., min_length=1, description="股票代码或名称，如 600519 / 贵州茅台")
    mode: str = Field(default="replay", description="replay=只读 artifacts；live 未开放以免消耗 API")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_enabled": False, "mode": "replay"}


@app.get("/api/studies")
def studies() -> dict:
    return {"studies": list_studies()}


@app.post("/api/research/start")
def start_research(body: StartRequest) -> dict:
    if body.mode not in {"replay", "grounded"}:
        raise HTTPException(
            status_code=400,
            detail="Demo 仅支持 mode=replay（读取已有 grounded artifacts，不调用 LLM）。",
        )
    symbol = resolve_symbol(body.query)
    if not symbol:
        raise HTTPException(
            status_code=404,
            detail=(
                f"未找到完整研究产物：{body.query!r}。"
                "当前 Demo 仅开放已有 artifacts 的股票（示例：600519 / 贵州茅台）。"
            ),
        )
    try:
        snapshot = assemble_snapshot(symbol)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface schema/load errors to UI
        raise HTTPException(status_code=500, detail=f"assemble failed: {exc}") from exc
    return {
        "job_id": f"replay-{symbol}",
        "status": "ready",
        "mode": "replay",
        "no_llm_call": True,
        "snapshot": snapshot,
    }


@app.get("/api/research/{symbol}")
def get_research(symbol: str) -> dict:
    resolved = resolve_symbol(symbol) or symbol
    try:
        snapshot = assemble_snapshot(resolved)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ready", "mode": "replay", "no_llm_call": True, "snapshot": snapshot}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
