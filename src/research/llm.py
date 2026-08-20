"""LLM adapter for research agents.

Modes:
- grounded / test: deterministic synthesizer (CI default, offline, reproducible)
- openai: OpenAI-compatible Chat Completions with same response schema

Grounded mode is NOT claimed to be autonomous research — it is deterministic synthesis
over weight-selected evidence bundles with number preservation and canonical findings.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from research.citation import validate_research_citations
from research.schemas import FundamentalResearch, MarketResearch
from research.synthesize import synthesize_fundamental, synthesize_market

T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT_COMMON = """你是一名研究分析员。
你只能使用提供的 Evidence。
禁止编造数据、联网、修改 Evidence、输出买卖建议。
优先产出带关键数字的跨证据关系与研究张力；证据不足则 insufficient_evidence。
claim/reasoning/interpretation 中的事实必须全部出现在本 finding 的 evidence_ids。
遵守 research_as_of_date；不得使用该日之后信息。
同一研究命题只生成一次 canonical finding，其他 section 仅引用。
"""


class LLMClient(Protocol):
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T: ...


def _extract_json_blob(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


class GroundedLLMClient:
    """Deterministic offline synthesizer for tests / reproducible research."""

    def __init__(self, *, validate_citations: bool = True, pack_for_validation: Any = None):
        self.validate_citations = validate_citations
        self.pack_for_validation = pack_for_validation

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        try:
            payload = _extract_json_blob(user_prompt)
        except Exception:
            start = user_prompt.find("{")
            end = user_prompt.rfind("}")
            if start < 0 or end < 0:
                raise ValueError("GroundedLLMClient requires JSON user_prompt")
            payload = json.loads(user_prompt[start : end + 1])

        stock_code = str(payload.get("stock_code") or "")
        agent = str(payload.get("agent") or "").lower()
        if response_model is FundamentalResearch or agent == "fundamental":
            result = synthesize_fundamental(stock_code, payload)
        elif response_model is MarketResearch or agent == "market":
            result = synthesize_market(stock_code, payload)
        else:
            raise TypeError(f"Unsupported response_model: {response_model}")

        if self.validate_citations and self.pack_for_validation is not None:
            errors = validate_research_citations(result, self.pack_for_validation)
            if errors:
                raise ValueError("citation validation failed: " + "; ".join(errors[:5]))
        return result  # type: ignore[return-value]


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        pack_for_validation: Any = None,
    ):
        self.api_key = api_key or os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("RESEARCH_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("RESEARCH_LLM_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        self.pack_for_validation = pack_for_validation
        if not self.api_key:
            raise ValueError("OpenAICompatibleLLMClient requires RESEARCH_LLM_API_KEY or OPENAI_API_KEY")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        import asyncio

        import requests

        schema = response_model.model_json_schema()
        body = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt + "\n请严格输出符合 schema 的 JSON。"},
                {
                    "role": "user",
                    "content": user_prompt + "\n\nJSON Schema:\n" + json.dumps(schema, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        }

        def _post() -> dict[str, Any]:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()

        data = await asyncio.to_thread(_post)
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json_blob(content)
        result = response_model.model_validate(parsed)
        if self.pack_for_validation is not None and isinstance(
            result, (FundamentalResearch, MarketResearch)
        ):
            errors = validate_research_citations(result, self.pack_for_validation)
            if errors:
                raise ValueError("citation validation failed: " + "; ".join(errors[:8]))
        return result


def create_llm_client(mode: str | None = None, *, pack_for_validation: Any = None) -> LLMClient:
    mode = (mode or os.getenv("RESEARCH_LLM_MODE") or "grounded").lower()
    if mode in {"grounded", "test"}:
        return GroundedLLMClient(pack_for_validation=pack_for_validation)
    if mode == "openai":
        return OpenAICompatibleLLMClient(pack_for_validation=pack_for_validation)
    if os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAICompatibleLLMClient(pack_for_validation=pack_for_validation)
        except Exception:
            return GroundedLLMClient(pack_for_validation=pack_for_validation)
    return GroundedLLMClient(pack_for_validation=pack_for_validation)
