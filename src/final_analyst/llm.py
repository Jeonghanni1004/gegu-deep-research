"""LLM adapter for Final Analyst (grounded default; openai optional)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from evidence.pack import EvidencePack

from final_analyst.dotenv_load import load_dotenv
from final_analyst.contract import FinalAnalystInput
from final_analyst.live_prompt import SYSTEM_PROMPT, build_user_prompt
from final_analyst.live_quality import live_hard_errors
from final_analyst.schemas import FinalAnalystOutput
from final_analyst.synthesize import synthesize_final_analyst
from final_analyst.validators import validate_final_analyst

# Load repo-root .env once (does not override already-set env vars)
load_dotenv()


class FALLMClient(Protocol):
    async def generate(self, inp: FinalAnalystInput) -> FinalAnalystOutput: ...


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _default_statement(
    *,
    kind: str = "INFERENCE",
    text: str,
    cids: list[str] | None = None,
    eids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text[:500],
        "canonical_finding_ids": list(cids or [])[:6],
        "evidence_ids": list(eids or [])[:8],
        "debate_refs": [],
        "numbers_used": [],
        "assessment_strength": "tentative",
        "inference_status": "DERIVED",
    }


def _append_once(text: str, needle: str, clause: str) -> str:
    if needle in text:
        return text
    return (text.rstrip("。；; ") + clause)[:500]


def _seal_openai_semantics(out: FinalAnalystOutput, inp: FinalAnalystInput) -> FinalAnalystOutput:
    """DEPRECATED (Round 5): phrase seal must not gate production quality.

    Kept for emergency compatibility when FA_PHRASE_SEAL=1.
    Production path uses semantic validators instead.
    """
    data = out.model_dump()
    exe = data["executive_assessment"]
    exe["text"] = _append_once(exe["text"], "未决", "；主矛盾仍未决。")
    if "Challenge" not in exe["text"] and "挑战" not in exe["text"]:
        exe["text"] = _append_once(exe["text"], "Challenge", "；开放 Challenge 仍限制强度。")
    if len(data.get("core_tensions") or []) >= 2:
        if "跨 tension" not in exe["text"] and "中间条件" not in exe["text"]:
            exe["text"] = _append_once(exe["text"], "跨 tension", "；跨 tension 上形成中间条件。")

    res = (data.get("meta") or {}).get("primary_resolution") or (
        (data.get("assessment_basis") or {}).get("primary_resolution")
    )
    if res == "unresolved":
        base_t = data["base_case"]["thesis"]
        if not any(k in base_t["text"] for k in ("未决", "无法裁定", "解释未决")):
            base_t["text"] = _append_once(base_t["text"], "解释未决", "（解释未决）。")

    bull_t = data["bull_case"]["thesis"]
    if "解释框架" not in bull_t["text"] and "移向" not in bull_t["text"] and "更强支持" not in bull_t["text"]:
        bull_t["text"] = _append_once(bull_t["text"], "解释框架", "则解释框架移向更强支持。")
    if "新证据" not in bull_t["text"] and "出现" not in bull_t["text"]:
        if bull_t["text"].startswith("若"):
            bull_t["text"] = "若出现可核对新证据且" + bull_t["text"][1:]
        else:
            bull_t["text"] = "若出现可核对新证据，" + bull_t["text"]
        bull_t["text"] = bull_t["text"][:500]

    bear_t = data["bear_case"]["thesis"]
    if "新证据" not in bear_t["text"] and "出现" not in bear_t["text"]:
        if bear_t["text"].startswith("若"):
            bear_t["text"] = "若出现可核对新证据且" + bear_t["text"][1:]
        else:
            bear_t["text"] = "若出现可核对新证据，" + bear_t["text"]
        bear_t["text"] = bear_t["text"][:500]

    unc = data.get("uncertainty") or []
    blob = " ".join(u.get("text", "") for u in unc) + exe["text"]
    if inp.debate.debate_summary.unresolved_issues:
        if "unresolved" not in blob.lower() and "未决" not in blob and "无法" not in blob:
            if unc:
                unc[0]["text"] = _append_once(unc[0]["text"], "未决", "（仍未决）。")
            else:
                unc = [
                    {
                        "kind": "UNCERTAINTY",
                        "text": "Debate unresolved 议题仍未决。",
                        "canonical_finding_ids": [],
                        "evidence_ids": [],
                        "debate_refs": [],
                        "numbers_used": [],
                        "assessment_strength": "unresolved",
                        "inference_status": "CONDITIONAL",
                    }
                ]
            data["uncertainty"] = unc

    ab = data.get("assessment_basis") or {}
    if not ab.get("limiting_challenge") and res != "partially_resolved":
        ab["limiting_challenge"] = "无开放 Challenge"
        data["assessment_basis"] = ab

    meta = data.get("meta") or {}
    meta["notes"] = list(meta.get("notes") or []) + ["openai_phrase_seal"]
    data["meta"] = meta
    return FinalAnalystOutput.model_validate(data)


def _scrub_unsupported_number_tokens(out: FinalAnalystOutput, missing: list[str]) -> FinalAnalystOutput:
    if not missing:
        return out
    data = out.model_dump()
    # Longer tokens first so 1357.7337 is not left as orphan after removing 1357.73
    missing_sorted = sorted({m for m in missing if m}, key=len, reverse=True)

    def scrub(text: str) -> str:
        t = text
        for tok in missing_sorted:
            # Remove token and common nearby punctuation / longer lookalikes starting with tok
            t = re.sub(re.escape(tok) + r"\d*", "", t)
            t = t.replace(f"（{tok}）", "").replace(f"({tok})", "")
        t = re.sub(r"\s{2,}", " ", t)
        t = re.sub(r"[，,]{2,}", "，", t)
        return t.strip(" ，,；;/、")

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "text" in node and isinstance(node["text"], str):
                node["text"] = scrub(node["text"])
            if "numbers_used" in node and isinstance(node["numbers_used"], list):
                cleaned = []
                for n in node["numbers_used"]:
                    ns = str(n)
                    if any(ns == m or ns.startswith(m) or m.startswith(ns) for m in missing_sorted):
                        continue
                    cleaned.append(n)
                node["numbers_used"] = cleaned
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return FinalAnalystOutput.model_validate(walk(data))


def _sanitize_llm_json(obj: Any, actions: list[str] | None = None) -> Any:
    """Normalize common LLM JSON quirks before pydantic validation.

    Round 7: optional actions log (sanitizer_action); never invent facts/evidence.
    """
    acts = actions if actions is not None else []
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, str) and v.strip().lower() in {"null", "none", "undefined"}:
                out[k] = None
                acts.append(f"null_string:{k}")
            else:
                out[k] = _sanitize_llm_json(v, acts)

        for id_key in ("evidence_ids", "canonical_finding_ids", "debate_refs", "numbers_used"):
            if id_key in out and out[id_key] is None:
                out[id_key] = []
                acts.append(f"empty_list:{id_key}")
            elif id_key in out and isinstance(out[id_key], str):
                out[id_key] = [out[id_key]] if out[id_key].strip() else []
                acts.append(f"scalar_to_list:{id_key}")
            elif id_key in out and isinstance(out[id_key], (int, float)):
                out[id_key] = [str(out[id_key])]
                acts.append(f"number_to_list:{id_key}")

        if "direction" in out and isinstance(out["direction"], str):
            d = out["direction"].lower()
            if "unresolved" in d:
                out["direction"] = "unresolved_to_resolved"
            elif "cautious" in d or "bear" in d:
                out["direction"] = "more_cautious"
            elif "constructive" in d or "bull" in d:
                out["direction"] = "more_constructive"

        if "assessment_strength" in out and isinstance(out["assessment_strength"], str):
            a = out["assessment_strength"].lower().strip()
            if a in {"strong", "moderate", "tentative", "unresolved"}:
                out["assessment_strength"] = a
            elif "unresolved" in a:
                out["assessment_strength"] = "unresolved"
            elif "weak" in a:
                out["assessment_strength"] = "tentative"
            else:
                out["assessment_strength"] = "tentative"

        if "support_strength" in out:
            s = out["support_strength"]
            if isinstance(s, str):
                s2 = s.lower().strip()
                out["support_strength"] = s2 if s2 in {"weak", "moderate", "strong"} else None

        dr = out.get("debate_resolution")
        if isinstance(dr, dict) and dr.get("resolution") == "unresolved":
            dr["support_strength"] = None

        if "evidence_pressure" in out and isinstance(out["evidence_pressure"], str):
            ep = out["evidence_pressure"].lower()
            if ep not in {"mild", "elevated", "severe"}:
                out["evidence_pressure"] = "elevated"

        if "kind" in out and isinstance(out["kind"], str):
            knd = out["kind"].upper()
            if knd not in {"FACT", "INFERENCE", "ASSUMPTION", "UNCERTAINTY"}:
                out["kind"] = "INFERENCE"

        if "inference_status" in out and isinstance(out["inference_status"], str):
            st = out["inference_status"].upper()
            if st == "UNSUPPORTED":
                out["inference_status"] = "CONDITIONAL"
            elif st not in {"SUPPORTED", "DERIVED", "CONDITIONAL"}:
                out["inference_status"] = "DERIVED"

        if "analyst_mode" in out:
            out["analyst_mode"] = "openai"

        # Only repair FinalAnalystOutput root-shaped objects
        is_root = (
            "stock_code" in out
            and "executive_assessment" in out
            and "base_case" in out
            and "bull_case" in out
            and "bear_case" in out
        )
        if not is_root:
            return out

        # Misplaced tension fields sometimes appear at FA root — park then drop
        misplaced_ca = out.pop("current_assessment", None)
        misplaced_ctc = out.pop("conditions_to_change", None)

        # Repair core_tensions missing required nested statements
        tensions = out.get("core_tensions")
        if isinstance(tensions, list):
            fixed = []
            for i, t in enumerate(tensions):
                if not isinstance(t, dict):
                    continue
                tid = t.get("tension_id") or "TENSION_UNKNOWN"
                dres = t.get("debate_resolution")
                if isinstance(dres, dict):
                    for bad in ("current_assessment", "fact_anchor", "bull_interpretation", "bear_interpretation"):
                        dres.pop(bad, None)
                    if dres.get("resolution") == "unresolved":
                        dres["support_strength"] = None
                if "fact_anchor" not in t or not isinstance(t.get("fact_anchor"), dict):
                    t["fact_anchor"] = _default_statement(
                        kind="FACT",
                        text=f"事实锚点：{tid}",
                        cids=[tid],
                        eids=list((dres or {}).get("decisive_evidence_ids") or [])[:4],
                    )
                if "bull_interpretation" not in t or not isinstance(t.get("bull_interpretation"), dict):
                    t["bull_interpretation"] = _default_statement(
                        text=f"若 Bull 条件成立，则提高对 {tid} 的建设性权重（条件假设）。",
                        cids=[tid],
                    )
                if "bear_interpretation" not in t or not isinstance(t.get("bear_interpretation"), dict):
                    t["bear_interpretation"] = _default_statement(
                        text=f"若 Bear 条件成立，则提高对 {tid} 的谨慎权重（条件假设）。",
                        cids=[tid],
                    )
                if "current_assessment" not in t or not isinstance(t.get("current_assessment"), dict):
                    if i == 0 and isinstance(misplaced_ca, dict):
                        t["current_assessment"] = misplaced_ca
                    else:
                        res = (dres or {}).get("resolution") or "unresolved"
                        reason = (dres or {}).get("resolution_reason") or "见 Debate resolution"
                        t["current_assessment"] = _default_statement(
                            kind="UNCERTAINTY" if res == "unresolved" else "INFERENCE",
                            text=f"对 {tid} 的当前评估：resolution={res}；{reason}",
                            cids=[tid],
                            eids=list((dres or {}).get("decisive_evidence_ids") or [])[:4],
                        )
                if "challenges" not in t or not isinstance(t.get("challenges"), list):
                    t["challenges"] = []
                if "rebuttals" not in t or not isinstance(t.get("rebuttals"), list):
                    t["rebuttals"] = []
                if "conditions_to_change" not in t or not isinstance(t.get("conditions_to_change"), list):
                    if i == 0 and isinstance(misplaced_ctc, list) and misplaced_ctc:
                        t["conditions_to_change"] = [str(x) for x in misplaced_ctc]
                    else:
                        t["conditions_to_change"] = ["可核对多期增长证据出现后可能改变评估"]
                if "research_question" not in t:
                    t["research_question"] = tid
                # Strip unknown extras on tension
                allowed_t = {
                    "tension_id",
                    "research_question",
                    "fact_anchor",
                    "bull_reference",
                    "bear_reference",
                    "bull_interpretation",
                    "bear_interpretation",
                    "challenges",
                    "rebuttals",
                    "debate_resolution",
                    "current_assessment",
                    "conditions_to_change",
                }
                t = {k: v for k, v in t.items() if k in allowed_t}
                fixed.append(t)
            out["core_tensions"] = fixed[:3]

        for key, default in (
            ("key_drivers", []),
            ("what_would_change_my_view", []),
            ("uncertainty", []),
            ("research_gaps", []),
            ("evidence_trace", []),
            ("canonical_finding_ids", []),
            ("evidence_ids", []),
        ):
            if key not in out or out[key] is None:
                out[key] = default

        # Strip unknown extras from AnalyzedStatement-shaped dicts recursively handled by pydantic;
        # clean statement dicts at known locations
        def _clean_stmt(s: Any) -> Any:
            if not isinstance(s, dict):
                return s
            allowed = {
                "kind",
                "text",
                "canonical_finding_ids",
                "evidence_ids",
                "debate_refs",
                "numbers_used",
                "assessment_strength",
                "inference_status",
            }
            return {k: v for k, v in s.items() if k in allowed}

        for sk in ("executive_assessment", "core_thesis"):
            if sk in out:
                out[sk] = _clean_stmt(out[sk])
        if isinstance(out.get("key_drivers"), list):
            out["key_drivers"] = [_clean_stmt(x) for x in out["key_drivers"]]
        if isinstance(out.get("uncertainty"), list):
            out["uncertainty"] = [_clean_stmt(x) for x in out["uncertainty"]]
        if isinstance(out.get("research_gaps"), list):
            out["research_gaps"] = [_clean_stmt(x) for x in out["research_gaps"]]

        default_labels = {"base_case": "base", "bull_case": "bull", "bear_case": "bear"}
        for case_key in ("base_case", "bull_case", "bear_case"):
            case = out.get(case_key)
            if not isinstance(case, dict):
                continue
            # Common LLM aliases → schema fields
            if "label" not in case:
                alias = case.get("name") or case.get("scenario") or default_labels[case_key]
                case["label"] = str(alias).lower().replace("_case", "").replace("case", "").strip() or default_labels[case_key]
            lbl = str(case.get("label", "")).lower()
            if "bull" in lbl:
                case["label"] = "bull"
            elif "bear" in lbl:
                case["label"] = "bear"
            else:
                case["label"] = "base"
            if "supporting_canonical_ids" not in case and isinstance(case.get("canonical_finding_ids"), list):
                case["supporting_canonical_ids"] = case.pop("canonical_finding_ids")
            if "inconsistent_with" not in case and isinstance(case.get("invalidated_if"), list):
                case["inconsistent_with"] = [str(x) for x in case.pop("invalidated_if")]
            if "explanation_shift_variable" not in case:
                case["explanation_shift_variable"] = str(
                    case.pop("shift_variable", None)
                    or case.pop("key_variable", None)
                    or "可核对证据增量"
                )
            allowed_case = {
                "label",
                "thesis",
                "supporting_canonical_ids",
                "required_assumptions",
                "inconsistent_with",
                "explanation_shift_variable",
            }
            cleaned = {k: v for k, v in case.items() if k in allowed_case}
            if "thesis" not in cleaned or not isinstance(cleaned.get("thesis"), dict):
                cleaned["thesis"] = _default_statement(
                    kind="UNCERTAINTY",
                    text=f"{case_key} 情景：在既有 Debate resolution 边界内成立。",
                )
            else:
                cleaned["thesis"] = _clean_stmt(cleaned["thesis"])
            if not isinstance(cleaned.get("required_assumptions"), list):
                cleaned["required_assumptions"] = []
            else:
                cleaned["required_assumptions"] = [_clean_stmt(x) for x in cleaned["required_assumptions"] if isinstance(x, dict)]
            if not isinstance(cleaned.get("supporting_canonical_ids"), list):
                cleaned["supporting_canonical_ids"] = []
            if not isinstance(cleaned.get("inconsistent_with"), list):
                cleaned["inconsistent_with"] = []
            out[case_key] = cleaned

        if isinstance(out.get("core_tensions"), list):
            for t in out["core_tensions"]:
                if not isinstance(t, dict):
                    continue
                for sk in ("fact_anchor", "bull_interpretation", "bear_interpretation", "current_assessment"):
                    if sk in t:
                        t[sk] = _clean_stmt(t[sk])

        # Final root whitelist (extra=forbid on FinalAnalystOutput)
        allowed_root = {
            "stock_code",
            "research_as_of_date",
            "analyst_mode",
            "executive_assessment",
            "core_thesis",
            "key_drivers",
            "core_tensions",
            "assessment_basis",
            "base_case",
            "bull_case",
            "bear_case",
            "what_would_change_my_view",
            "uncertainty",
            "research_gaps",
            "evidence_trace",
            "canonical_finding_ids",
            "evidence_ids",
            "meta",
        }
        out = {k: v for k, v in out.items() if k in allowed_root}
        if acts:
            meta = out.get("meta") if isinstance(out.get("meta"), dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            notes = list(meta.get("notes") or [])
            notes.append("sanitizer_action=" + ",".join(dict.fromkeys(acts))[:400])
            notes.append(f"normalized_shape=root_keys:{len(out)}")
            meta["notes"] = notes
            meta.setdefault("no_trade_advice", True)
            meta.setdefault("grounded_is_not_autonomous", True)
            out["meta"] = meta
        return out
    if isinstance(obj, list):
        return [_sanitize_llm_json(x, acts) for x in obj]
    return obj


class GroundedFALLMClient:
    """Deterministic offline FA. Not autonomous research."""

    def __init__(self, *, pack_for_validation: EvidencePack | None = None):
        self.pack_for_validation = pack_for_validation

    async def generate(self, inp: FinalAnalystInput) -> FinalAnalystOutput:
        from final_analyst.contract_pin import pin_debate_contract

        payload = inp.model_copy(update={"mode": "grounded"})
        out = synthesize_final_analyst(payload)
        out = pin_debate_contract(out, payload)
        errors = validate_final_analyst(out, payload, pack=self.pack_for_validation)
        if errors:
            raise ValueError("FA validation failed: " + "; ".join(errors[:8]))
        return out


class OpenAIFALLMClient:
    """OpenAI-compatible synthesis under the same FinalAnalystInput/Output schema."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        pack_for_validation: EvidencePack | None = None,
        fallback_to_grounded: bool = True,
    ):
        self.api_key = api_key or os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("RESEARCH_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("RESEARCH_LLM_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        self.pack_for_validation = pack_for_validation
        self.fallback_to_grounded = fallback_to_grounded
        if not self.api_key:
            raise ValueError("OpenAIFALLMClient requires API key")

    async def generate(self, inp: FinalAnalystInput) -> FinalAnalystOutput:
        import asyncio

        import requests

        from final_analyst.calibration import calibrate_assessment
        from final_analyst.contract_pin import pin_debate_contract
        from final_analyst.evidence_repair import repair_output_citations

        thinking = (os.getenv("FA_THINKING") or "").strip().lower() in {"1", "true", "yes", "enabled"}

        def _build_body(extra_user: str | None = None) -> dict[str, Any]:
            user = build_user_prompt(inp)
            if extra_user:
                user = user + "\n\n" + extra_user
            body: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": int(os.getenv("FA_MAX_TOKENS") or "12288"),
            }
            if "deepseek" in self.base_url.lower() or "deepseek" in self.model.lower():
                body["thinking"] = {"type": "enabled" if thinking else "disabled"}
                if thinking:
                    body["reasoning_effort"] = os.getenv("FA_REASONING_EFFORT") or "high"
                else:
                    body["temperature"] = 0.2
            else:
                body["temperature"] = 0.2
            return body

        def _post(body: dict[str, Any]) -> dict[str, Any]:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()

        async def _attempt(
            *,
            feedback_extra: str | None,
            attempt: int,
            regenerate_used: bool,
            retry_used: bool,
        ) -> FinalAnalystOutput:
            data = await asyncio.to_thread(_post, _build_body(feedback_extra))
            msg = data["choices"][0]["message"]
            raw = msg.get("content") or ""
            finish = data["choices"][0].get("finish_reason")
            if not str(raw).strip():
                raise ValueError(f"openai empty content (finish_reason={finish})")
            # stash for outer except
            nonlocal raw_content
            raw_content = raw
            acts: list[str] = []
            parsed = _sanitize_llm_json(_extract_json(raw), acts)
            out = FinalAnalystOutput.model_validate(parsed)
            out = out.model_copy(update={"analyst_mode": "openai"})

            seal_on = (os.getenv("FA_PHRASE_SEAL") or "").strip().lower() in {"1", "true", "yes"}
            if seal_on:
                out = _seal_openai_semantics(out, inp)

            # Pin Debate contract BEFORE calibration (resolution is INPUT)
            out = pin_debate_contract(out, inp)

            repair = repair_output_citations(out, inp, pack=self.pack_for_validation, allow_scrub=False)
            if repair.output is not None:
                out = repair.output
            if repair.action == "REGENERATE" and repair.unresolved_numbers:
                repair2 = repair_output_citations(out, inp, pack=self.pack_for_validation, allow_scrub=False)
                if repair2.output is not None:
                    out = repair2.output
                if repair2.unresolved_numbers:
                    raise ValueError(
                        "openai FA evidence repair failed: unresolved_numbers="
                        + ",".join(repair2.unresolved_numbers[:6])
                    )

            # Re-pin after repair (notes may change)
            out = pin_debate_contract(out, inp)
            res = out.meta.primary_resolution or "unresolved"
            support = out.meta.debate_support_strength
            pressure = out.meta.evidence_pressure or "elevated"
            boundaries = list(inp.fundamental.uncertainty_boundaries or [])[:4]
            boundaries += list(inp.market.uncertainty_boundaries or [])[:2]
            cal = calibrate_assessment(res, support, pressure, boundaries)  # type: ignore[arg-type]
            ab = out.assessment_basis.model_copy(
                update={
                    "primary_resolution": res,
                    "debate_support_strength": cal.support_strength,
                    "evidence_pressure": cal.evidence_pressure,
                    "calibrated_frame": out.assessment_basis.calibrated_frame or cal.rationale[:200],
                }
            )
            meta = out.meta.model_copy(
                update={
                    "primary_resolution": res,
                    "assessment_strength": cal.assessment_strength,
                    "debate_support_strength": cal.support_strength,
                    "evidence_pressure": cal.evidence_pressure,
                }
            )
            out = out.model_copy(update={"assessment_basis": ab, "meta": meta})
            if out.executive_assessment.assessment_strength is None:
                out = out.model_copy(
                    update={
                        "executive_assessment": out.executive_assessment.model_copy(
                            update={"assessment_strength": cal.assessment_strength}
                        )
                    }
                )

            errors = list(dict.fromkeys(live_hard_errors(out, inp, pack=self.pack_for_validation)))
            if errors:
                raise ValueError("openai FA validation failed: " + "; ".join(errors[:8]))
            notes = list(out.meta.notes) + [
                "openai_live_path",
                "phrase_seal_dependency=0",
                f"evidence_repair_action={repair.action}",
                f"openai_attempt={attempt}",
                f"regenerate_used={str(regenerate_used).lower()}",
                f"retry_used={str(retry_used).lower()}",
                f"model={self.model}",
                f"base_url={self.base_url}",
                f"thinking={'enabled' if thinking else 'disabled'}",
                f"finish_reason={finish}",
            ]
            return out.model_copy(update={"meta": out.meta.model_copy(update={"notes": notes})})

        from final_analyst.failures import (
            classify_exception,
            is_quota_provider_failure,
            is_recoverable_validation_failure,
            is_transient_provider_failure,
        )

        raw_content = ""
        last_err: Exception | None = None
        feedback_extra: str | None = None
        regenerate_used = False
        retry_used = False
        llm_calls = 0
        first_provider_error: str | None = None
        # Max path: initial + optional 1 provider retry + optional 1 regenerate (never 3 regenerates).
        while llm_calls < 3:
            llm_calls += 1
            try:
                out = await _attempt(
                    feedback_extra=feedback_extra,
                    attempt=llm_calls,
                    regenerate_used=regenerate_used,
                    retry_used=retry_used,
                )
                if retry_used and first_provider_error:
                    notes = list(out.meta.notes) + [
                        "provider_retry_recovered=true",
                        f"provider_retry_first_error={first_provider_error[:240]}",
                        f"attempt={llm_calls}",
                    ]
                    out = out.model_copy(update={"meta": out.meta.model_copy(update={"notes": notes})})
                return out
            except Exception as e:
                last_err = e
                err_s = str(e)

                # Quota: never retry (explicit guard before transient).
                if is_quota_provider_failure(e) or is_quota_provider_failure(err_s):
                    break

                # Transient provider: at most 1 retry (not a regenerate).
                if (not retry_used) and is_transient_provider_failure(e):
                    retry_used = True
                    first_provider_error = f"{type(e).__name__}: {e}"[:300]
                    feedback_extra = None
                    continue

                # At most 1 regenerate total (unresolved_numbers OR recoverable validation).
                if not regenerate_used:
                    if "unresolved_numbers=" in err_s:
                        nums = [x for x in err_s.split("unresolved_numbers=", 1)[-1].split(",") if x][:8]
                        regenerate_used = True
                        feedback_extra = (
                            "REGENERATE 约束（evidence repair / unresolved_numbers）：\n"
                            f"INVALID NUMBER: {nums}\n"
                            "请仅使用 ALLOWED_NUMBERS 中已有数字的原始形式；不得创建新数字；"
                            "不得改写数字含义；不得删除事实以绕过校验；"
                            "evidence_ids 只能从候选 evidence 中选择；"
                            "不得修改 FIXED_DEBATE_CONTRACT / Debate resolution；"
                            "不得创造 evidence 或外部事实。"
                        )
                        continue
                    if is_recoverable_validation_failure(err_s):
                        regenerate_used = True
                        feedback_extra = (
                            "REGENERATE 约束（recoverable validation failure）：\n"
                            f"VALIDATION ERROR: {err_s[:600]}\n"
                            "必须遵守 INPUT contract 与 FIXED_DEBATE_CONTRACT；"
                            "不得修改 Debate resolution / support / pressure；"
                            "不得创造数字、evidence 或外部事实；"
                            "必须保留 uncertainty / gap（不得 completed 抹平）；"
                            "仅基于当前 INPUT 与已有 evidence 修正表述。"
                        )
                        continue
                break

        err_msg = f"{type(last_err).__name__}: {last_err}" if last_err else "openai FA failed"
        failure_rec = classify_exception(last_err or RuntimeError(err_msg), attempt=llm_calls)
        failure_rec.action = "fallback"
        failure_rec.fallback = True
        failure_rec.retry_used = retry_used
        failure_rec.cause = (failure_rec.cause or err_msg)[:500]
        try:
            from pathlib import Path

            root = Path(__file__).resolve().parents[2] / "examples" / "fa_live"
            root.mkdir(parents=True, exist_ok=True)
            (root / "last_openai_error.txt").write_text(
                f"base_url={self.base_url}\nmodel={self.model}\nerror={err_msg}\n"
                f"code={failure_rec.code}\nstage={failure_rec.stage}\ncause={failure_rec.cause}\n"
                f"attempt={llm_calls}\nretry_used={retry_used}\nregenerate_used={regenerate_used}\n"
                f"first_provider_error={first_provider_error or ''}\n",
                encoding="utf-8",
            )
            if raw_content:
                (root / "last_openai_raw.txt").write_text(raw_content[:50000], encoding="utf-8")
        except Exception:
            pass
        if not self.fallback_to_grounded:
            assert last_err is not None
            raise last_err
        grounded = GroundedFALLMClient(pack_for_validation=self.pack_for_validation)
        out = await grounded.generate(inp)
        # Pin grounded output contract too for stable JudgmentFrame
        out = pin_debate_contract(out, inp)
        notes = list(out.meta.notes) + [
            "openai_rejected_or_failed_fallback_grounded",
            "fallback=true",
            "final_mode=grounded",
            f"openai_attempt={llm_calls}",
            f"attempt={llm_calls}",
            f"regenerate_used={str(regenerate_used).lower()}",
            f"retry_used={str(retry_used).lower()}",
            failure_rec.to_note(),
            err_msg[:500],
        ]
        if first_provider_error:
            notes.append(f"provider_retry_first_error={first_provider_error[:240]}")
        return out.model_copy(update={"meta": out.meta.model_copy(update={"notes": notes})})


def create_fa_llm_client(
    mode: str | None = None,
    *,
    pack_for_validation: EvidencePack | None = None,
) -> FALLMClient:
    mode = (mode or os.getenv("RESEARCH_LLM_MODE") or "grounded").lower()
    if mode in {"grounded", "test"}:
        return GroundedFALLMClient(pack_for_validation=pack_for_validation)
    if mode == "openai":
        try:
            return OpenAIFALLMClient(pack_for_validation=pack_for_validation)
        except Exception:
            return GroundedFALLMClient(pack_for_validation=pack_for_validation)
    return GroundedFALLMClient(pack_for_validation=pack_for_validation)
