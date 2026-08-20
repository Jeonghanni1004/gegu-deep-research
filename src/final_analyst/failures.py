"""Unified Failure Taxonomy for Final Analyst (Round 6–8).

Round-8: FailureRecord gains cause/action/attempt; classification must not
let fallback wrappers swallow the real failure code.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FailureCode = Literal[
    "CONTRACT_VIOLATION",
    "AS_OF_MISMATCH",
    "INVALID_RESEARCH",
    "INVALID_DEBATE",
    "INVALID_FA",
    "VALIDATION_FAILURE",
    "EVIDENCE_REPAIR_FAILURE",
    "UNSUPPORTED_EXTERNAL_FACT",
    "INFORMATION_LOSS",
    "PROVIDER_FAILURE",
    "PROVIDER_QUOTA_FAILURE",
    "JSON_PARSE_FAILURE",
    "SCHEMA_SANITIZATION_FAILURE",
    "PRODUCTION_GATE_REJECT",
    "UNKNOWN",
]

Stage = Literal[
    "evidence",
    "research",
    "debate",
    "fa_input",
    "fa_generate",
    "fa_validate",
    "provider",
    "provider_quota",
    "json",
    "schema",
    "evidence_repair",
    "validation",
    "regenerate",
    "fallback",
    "production_gate",
    "cli",
]

FailureAction = Literal["repair", "regenerate", "retry", "fallback", "reject", "none"]


@dataclass
class FailureRecord:
    code: FailureCode
    stage: Stage
    severity: Literal["error", "fatal", "recoverable"]
    message: str
    recoverable: bool = False
    details: list[str] = field(default_factory=list)
    # Round-8 attribution fields (optional / backward compatible)
    cause: str = ""
    action: FailureAction = "none"
    attempt: int = 1
    fallback: bool = False
    retry_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        msg = d.get("message") or ""
        for bad in ("sk-", "Bearer ", "api_key", "API_KEY"):
            if bad in msg:
                d["message"] = "[redacted]"
                break
        cause = d.get("cause") or ""
        for bad in ("sk-", "Bearer ", "api_key", "API_KEY"):
            if bad in cause:
                d["cause"] = "[redacted]"
                break
        return d

    def to_note(self) -> str:
        """Compact note line for FA meta.notes (no secrets)."""
        payload = {
            "code": self.code,
            "stage": self.stage,
            "cause": (self.cause or self.message)[:240],
            "action": self.action,
            "attempt": self.attempt,
            "fallback": self.fallback,
            "retry_used": self.retry_used,
            "recoverable": self.recoverable,
        }
        return "failure_attribution=" + json.dumps(payload, ensure_ascii=False)


# Prefix → taxonomy (order matters). Fallback wrappers demoted.
_PREFIX_MAP: list[tuple[str, FailureCode]] = [
    ("as_of", "AS_OF_MISMATCH"),
    ("contract_consumption", "CONTRACT_VIOLATION"),
    ("contract_violation", "CONTRACT_VIOLATION"),
    ("fa_finding_namespace", "CONTRACT_VIOLATION"),
    ("fabricated_canonical", "UNSUPPORTED_EXTERNAL_FACT"),
    ("fabricated_evidence", "UNSUPPORTED_EXTERNAL_FACT"),
    ("unsupported_inference", "UNSUPPORTED_EXTERNAL_FACT"),
    ("no_unsupported_inference", "UNSUPPORTED_EXTERNAL_FACT"),
    ("unsupported_external", "UNSUPPORTED_EXTERNAL_FACT"),
    ("information_loss", "INFORMATION_LOSS"),
    ("number_scrub_information_loss", "INFORMATION_LOSS"),
    ("phrase_seal_dependency", "VALIDATION_FAILURE"),
    ("unresolved_numbers", "EVIDENCE_REPAIR_FAILURE"),
    ("openai FA evidence repair", "EVIDENCE_REPAIR_FAILURE"),
    ("evidence_repair", "EVIDENCE_REPAIR_FAILURE"),
    ("openai FA validation", "VALIDATION_FAILURE"),
    ("uncertainty_preservation", "VALIDATION_FAILURE"),
    ("JSONDecodeError", "JSON_PARSE_FAILURE"),
    ("json.decoder", "JSON_PARSE_FAILURE"),
    ("ValidationError", "SCHEMA_SANITIZATION_FAILURE"),
    ("schema", "SCHEMA_SANITIZATION_FAILURE"),
    ("openai empty", "PROVIDER_FAILURE"),
    ("ended prematurely", "PROVIDER_FAILURE"),
    # Quota / billing before generic HTTPError (sibling of PROVIDER_FAILURE)
    ("Payment Required", "PROVIDER_QUOTA_FAILURE"),
    ("402 Client Error", "PROVIDER_QUOTA_FAILURE"),
    ("quota exhausted", "PROVIDER_QUOTA_FAILURE"),
    ("insufficient_quota", "PROVIDER_QUOTA_FAILURE"),
    ("HTTPError", "PROVIDER_FAILURE"),
    ("Timeout", "PROVIDER_FAILURE"),
    ("ConnectionError", "PROVIDER_FAILURE"),
    ("ReadTimeout", "PROVIDER_FAILURE"),
    ("ConnectTimeout", "PROVIDER_FAILURE"),
    ("semantic_", "VALIDATION_FAILURE"),
    ("debate_consumption", "INVALID_DEBATE"),
    ("calibration_", "VALIDATION_FAILURE"),
    ("scenario_", "VALIDATION_FAILURE"),
    ("mode_boundary", "CONTRACT_VIOLATION"),
    ("trade_advice", "CONTRACT_VIOLATION"),
    ("production_gate", "PRODUCTION_GATE_REJECT"),
    ("PROVIDER_QUOTA_FAILURE", "PROVIDER_QUOTA_FAILURE"),
    ("PROVIDER_FAILURE", "PROVIDER_FAILURE"),
]

_FALLBACK_WRAPPER_MARKERS = (
    "openai_rejected_or_failed_fallback_grounded",
    "fallback=true",
    "final_mode=grounded",
)

RECOVERABLE_VALIDATION_MARKERS = (
    "uncertainty_preservation",
    "gap completed",
    "scenario_boundary",
    "scenario_non_redundancy",
    "semantic_unresolved",
    "semantic_cross_tension",
    "analytical_increment",
    "new_evidence_boundary",
)


def _stage_for_code(code: FailureCode, *, default: Stage = "fa_generate") -> Stage:
    mapping: dict[str, Stage] = {
        "PROVIDER_FAILURE": "provider",
        "PROVIDER_QUOTA_FAILURE": "provider_quota",
        "JSON_PARSE_FAILURE": "json",
        "SCHEMA_SANITIZATION_FAILURE": "schema",
        "EVIDENCE_REPAIR_FAILURE": "evidence_repair",
        "VALIDATION_FAILURE": "validation",
        "PRODUCTION_GATE_REJECT": "production_gate",
        "UNSUPPORTED_EXTERNAL_FACT": "fa_validate",
        "INFORMATION_LOSS": "evidence_repair",
        "CONTRACT_VIOLATION": "fa_validate",
    }
    return mapping.get(code, default)


def is_quota_provider_failure(exc: BaseException | str) -> bool:
    text = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
    low = text.lower()
    return any(
        k in low
        for k in (
            "402",
            "payment required",
            "quota exhausted",
            "insufficient_quota",
            "billing",
            "exceeded your current quota",
        )
    )


def _is_fallback_wrapper(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("openai_attempt=") or t.startswith("model=") or t.startswith("base_url="):
        return True
    if t.startswith("thinking=") or t.startswith("finish_reason=") or t.startswith("evidence_repair_action="):
        return True
    if t.startswith("openai_live_path") or t.startswith("phrase_seal") or t.startswith("sanitizer_action="):
        return True
    if t.startswith("debate_contract_pinned") or t.startswith("normalized_shape="):
        return True
    return any(m in t for m in _FALLBACK_WRAPPER_MARKERS)


def classify_error_message(
    msg: str,
    *,
    stage: Stage | None = None,
    action: FailureAction = "none",
    attempt: int = 1,
    fallback: bool = False,
    retry_used: bool = False,
    cause: str | None = None,
) -> FailureRecord:
    text = (msg or "").strip()
    low = text.lower()
    code: FailureCode = "UNKNOWN"
    for prefix, mapped in _PREFIX_MAP:
        if prefix.lower() in low or text.startswith(prefix):
            code = mapped
            break
    # Demote bare fallback wrapper → UNKNOWN (not PROVIDER)
    if _is_fallback_wrapper(text) and ("openai_rejected" in low or "fallback=true" in low):
        if code in {"PROVIDER_FAILURE", "UNKNOWN"}:
            code = "UNKNOWN"

    resolved_stage = stage or _stage_for_code(code)
    recoverable = code in {
        "VALIDATION_FAILURE",
        "EVIDENCE_REPAIR_FAILURE",
        "PROVIDER_FAILURE",
        "JSON_PARSE_FAILURE",
        "SCHEMA_SANITIZATION_FAILURE",
    }
    severity: Literal["error", "fatal", "recoverable"] = "recoverable" if recoverable else "fatal"
    if code in {"UNSUPPORTED_EXTERNAL_FACT", "INFORMATION_LOSS", "CONTRACT_VIOLATION", "AS_OF_MISMATCH"}:
        severity = "fatal"
        recoverable = False
    cause_text = (cause if cause is not None else text)[:500]
    return FailureRecord(
        code=code,
        stage=resolved_stage,
        severity=severity,
        message=text[:500],
        recoverable=recoverable,
        details=[],
        cause=cause_text,
        action=action,
        attempt=attempt,
        fallback=fallback,
        retry_used=retry_used,
    )


def classify_error_list(errors: list[str], *, stage: Stage = "fa_validate") -> list[FailureRecord]:
    return [classify_error_message(e, stage=stage) for e in errors]


def parse_failure_attribution_note(note: str) -> FailureRecord | None:
    if not note.startswith("failure_attribution="):
        return None
    raw = note[len("failure_attribution=") :]
    try:
        data = json.loads(raw)
    except Exception:
        return None
    code = data.get("code") or "UNKNOWN"
    stage = data.get("stage") or _stage_for_code(code)  # type: ignore[arg-type]
    return FailureRecord(
        code=code,  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        severity="recoverable",
        message=str(data.get("cause") or "")[:500],
        recoverable=bool(data.get("recoverable", True)),
        cause=str(data.get("cause") or "")[:500],
        action=data.get("action") or "none",  # type: ignore[arg-type]
        attempt=int(data.get("attempt") or 1),
        fallback=bool(data.get("fallback")),
        retry_used=bool(data.get("retry_used")),
    )


def classify_from_notes(
    notes: list[str],
    *,
    default_action: FailureAction = "fallback",
    attempt: int = 1,
) -> FailureRecord:
    """Prefer structured attribution / real err_msg over fallback wrappers."""
    for n in notes:
        fr = parse_failure_attribution_note(n)
        if fr is not None:
            if default_action == "fallback":
                fr.action = "fallback"
                fr.fallback = True
            return fr

    candidates: list[str] = []
    for n in notes:
        if _is_fallback_wrapper(n):
            continue
        if n.startswith("failure_attribution="):
            continue
        candidates.append(n)

    ranked = sorted(
        candidates,
        key=lambda s: (
            0
            if any(
                k in s
                for k in (
                    "unresolved_numbers",
                    "validation failed",
                    "ValidationError",
                    "JSONDecodeError",
                    "HTTPError",
                    "Timeout",
                    "uncertainty_preservation",
                    "Error:",
                )
            )
            else 1,
            -len(s),
        ),
    )
    for n in ranked:
        fr = classify_error_message(
            n,
            action=default_action,
            attempt=attempt,
            fallback=default_action == "fallback",
        )
        if fr.code != "UNKNOWN":
            return fr

    return FailureRecord(
        code="UNKNOWN",
        stage="fallback",
        severity="recoverable",
        message="fallback_without_classified_cause",
        recoverable=True,
        cause="fallback_wrapper_only",
        action=default_action,
        attempt=attempt,
        fallback=True,
    )


def classify_exception(exc: BaseException, *, attempt: int = 1) -> FailureRecord:
    """Map a live exception to FailureRecord with correct stage."""
    name = type(exc).__name__
    msg = f"{name}: {exc}"
    low = msg.lower()

    if name in {"JSONDecodeError"} or "JSONDecodeError" in msg:
        return classify_error_message(msg, stage="json", attempt=attempt, cause=str(exc)[:500])
    if name in {"ValidationError"} or "ValidationError" in msg:
        return classify_error_message(msg, stage="schema", attempt=attempt, cause=str(exc)[:500])
    if is_quota_provider_failure(exc) or is_quota_provider_failure(msg):
        return classify_error_message(msg, stage="provider_quota", attempt=attempt, cause=str(exc)[:500])
    if name in {"Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"} or "timeout" in low:
        return classify_error_message(msg, stage="provider", attempt=attempt, cause=str(exc)[:500])
    if name in {"HTTPError"} or "HTTPError" in msg or "status code 5" in low:
        return classify_error_message(msg, stage="provider", attempt=attempt, cause=str(exc)[:500])
    if "openai empty" in low or "ended prematurely" in low:
        return classify_error_message(msg, stage="provider", attempt=attempt, cause=str(exc)[:500])
    if "unresolved_numbers" in low or "evidence repair failed" in low:
        return classify_error_message(msg, stage="evidence_repair", attempt=attempt, cause=str(exc)[:500])
    if "validation failed" in low or "uncertainty_preservation" in low or "fabricated_evidence" in low:
        return classify_error_message(msg, stage="validation", attempt=attempt, cause=str(exc)[:500])
    return classify_error_message(msg, attempt=attempt, cause=str(exc)[:500])


def is_recoverable_validation_failure(msg: str) -> bool:
    low = (msg or "").lower()
    # Fabricated evidence is fail-closed — not recoverable via regenerate.
    if "fabricated_evidence" in low or "unsupported_external" in low:
        return False
    return any(m in low for m in RECOVERABLE_VALIDATION_MARKERS)


def is_transient_provider_failure(exc: BaseException | str) -> bool:
    text = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
    low = text.lower()
    # Quota / auth: never retry.
    if is_quota_provider_failure(text) or any(k in low for k in ("401", "unauthorized", "403", "forbidden")):
        return False
    if "validation failed" in low or "unresolved_numbers" in low or "ValidationError" in text:
        return False
    if any(
        k in low
        for k in (
            "timeout",
            "connection reset",
            "connection aborted",
            "remote disconnected",
            "openai empty",
            "temporarily",
            "ended prematurely",
            "503",
            "502",
            "504",
        )
    ):
        return True
    if "connectionerror" in low or "connecttimeout" in low or "readtimeout" in low:
        return True
    if "HTTPError" in text and re.search(r"\b5\d\d\b", text):
        return True
    return False


def primary_failure(records: list[FailureRecord]) -> FailureRecord | None:
    if not records:
        return None
    fatals = [r for r in records if not r.recoverable]
    return fatals[0] if fatals else records[0]


def aggregate_codes(records: list[FailureRecord]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        out[r.code] = out.get(r.code, 0) + 1
    return out
