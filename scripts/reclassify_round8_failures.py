"""Offline reclassify Round-8 formal 84% failures; never overwrite with quota-exhaust run."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from final_analyst.failures import classify_error_message, is_quota_provider_failure

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "examples" / "evaluation"
OFFICIAL = EV / "stability_10x10_openai_r8.json"
QUOTA_BAN = EV / "stability_10x10_openai_r8_quota_exhaust.json"


def refine_code(cause: str | None, code: str | None) -> tuple[str, str]:
    text = cause or ""
    if is_quota_provider_failure(text) or "402" in text or "Payment Required" in text:
        return "PROVIDER_QUOTA_FAILURE", "provider_quota"
    fr = classify_error_message(text or "UNKNOWN")
    if fr.code == "UNKNOWN" and "ended prematurely" in text.lower():
        return "PROVIDER_FAILURE", "provider"
    # Prefer cause-based classification over locked artifact code when cause is rich.
    if text.strip():
        return fr.code, fr.stage
    return str(code or fr.code), str(fr.stage)


def main() -> None:
    data = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    assert data["total_runs"] == 100 and data["openai_success"] == 84, (
        f"official artifact must be 84/100, got {data.get('openai_success')}/{data.get('total_runs')}"
    )
    if QUOTA_BAN.exists():
        ban = json.loads(QUOTA_BAN.read_text(encoding="utf-8"))
        assert ban.get("openai_success") == 32, "quota exhaust archive unexpected"

    fails = []
    for r in data.get("run_attributions") or []:
        if not r.get("fallback") and r.get("openai_success"):
            continue
        if not (r.get("fallback") or not r.get("openai_success")):
            continue
        if not r.get("fallback"):
            continue
        code, stage = refine_code(r.get("cause"), r.get("failure_code"))
        item = {
            "fixture": r.get("fixture"),
            "run": r.get("run"),
            "failure_code": code,
            "stage": stage,
            "cause": r.get("cause"),
            "action": r.get("action") or "fallback",
            "attempt": r.get("attempt"),
            "retry_used": bool(r.get("retry_used")),
            "regenerate_used": bool(r.get("regenerate_used")),
            "fallback": True,
            "openai_success": False,
        }
        fails.append(item)

    dist = Counter(f["failure_code"] for f in fails)
    stages = Counter(f["stage"] for f in fails)
    buckets = {
        "provider_quota_402": sum(1 for f in fails if f["failure_code"] == "PROVIDER_QUOTA_FAILURE"),
        "provider_other": sum(1 for f in fails if f["failure_code"] == "PROVIDER_FAILURE"),
        "validation_or_unsupported": sum(
            1 for f in fails if f["failure_code"] in {"VALIDATION_FAILURE", "UNSUPPORTED_EXTERNAL_FACT"}
        ),
        "evidence_repair": sum(1 for f in fails if f["failure_code"] == "EVIDENCE_REPAIR_FAILURE"),
        "json": sum(1 for f in fails if f["failure_code"] == "JSON_PARSE_FAILURE"),
        "schema": sum(1 for f in fails if f["failure_code"] == "SCHEMA_SANITIZATION_FAILURE"),
        "other": sum(
            1
            for f in fails
            if f["failure_code"]
            not in {
                "PROVIDER_QUOTA_FAILURE",
                "PROVIDER_FAILURE",
                "VALIDATION_FAILURE",
                "UNSUPPORTED_EXTERNAL_FACT",
                "EVIDENCE_REPAIR_FAILURE",
                "JSON_PARSE_FAILURE",
                "SCHEMA_SANITIZATION_FAILURE",
            }
        ),
    }

    # Software-path rate excluding quota (narrative only; does NOT redefine openai_success)
    non_quota = data["total_runs"] - buckets["provider_quota_402"]
    software_success = data["openai_success"]  # successes unchanged
    narrative_rate = (software_success / non_quota) if non_quota else 0.0

    diagnosis = {
        "locked_official": {
            "artifact": str(OFFICIAL.as_posix()),
            "total_runs": data["total_runs"],
            "openai_success": data["openai_success"],
            "openai_success_rate": data["openai_success"] / data["total_runs"],
            "acceptable": data["acceptable"],
            "grounded_fallback": data["grounded_fallback"],
            "regenerate": data.get("regenerate", 0),
            "retry": data.get("retry", 0),
            "repair": data.get("repair", 0),
            "information_loss": data.get("information_loss", 0),
            "unsupported_external_fact": data.get("unsupported_external_fact", 0),
            "contract_violation": data.get("contract_violation", 0),
            "debate_state_drift": data.get("debate_state_drift", 0),
            "primary_axis_drift": data.get("primary_axis_drift", 0),
            "quota_exhaust_32pct_void": True,
            "quota_exhaust_artifact": str(QUOTA_BAN.as_posix()) if QUOTA_BAN.exists() else None,
        },
        "total_runs": data["total_runs"],
        "openai_success": data["openai_success"],
        "fallback": len(fails),
        "regenerate": data.get("regenerate", 0),
        "retry": data.get("retry", 0),
        "repair": data.get("repair", 0),
        "acceptable": data["acceptable"],
        "failure_distribution": {
            "PROVIDER_QUOTA_FAILURE": dist.get("PROVIDER_QUOTA_FAILURE", 0),
            "PROVIDER_FAILURE": dist.get("PROVIDER_FAILURE", 0),
            "VALIDATION_FAILURE": dist.get("VALIDATION_FAILURE", 0),
            "UNSUPPORTED_EXTERNAL_FACT": dist.get("UNSUPPORTED_EXTERNAL_FACT", 0),
            "EVIDENCE_REPAIR_FAILURE": dist.get("EVIDENCE_REPAIR_FAILURE", 0),
            "JSON_PARSE_FAILURE": dist.get("JSON_PARSE_FAILURE", 0),
            "SCHEMA_SANITIZATION_FAILURE": dist.get("SCHEMA_SANITIZATION_FAILURE", 0),
            "UNKNOWN": dist.get("UNKNOWN", 0),
            **{k: v for k, v in dist.items() if k not in {
                "PROVIDER_QUOTA_FAILURE",
                "PROVIDER_FAILURE",
                "VALIDATION_FAILURE",
                "UNSUPPORTED_EXTERNAL_FACT",
                "EVIDENCE_REPAIR_FAILURE",
                "JSON_PARSE_FAILURE",
                "SCHEMA_SANITIZATION_FAILURE",
                "UNKNOWN",
            }},
        },
        "failure_stages": dict(stages),
        "buckets": buckets,
        "narrative_excluding_quota": {
            "note": "Does NOT redefine openai_success; informational only",
            "non_quota_runs": non_quota,
            "openai_success_unchanged": software_success,
            "success_rate_if_quota_excluded": round(narrative_rate, 4),
            "remaining_failures": len(fails) - buckets["provider_quota_402"],
        },
        "failed_runs": fails,
        "runs": data.get("run_attributions") or [],
    }

    out = EV / "round8_failure_diagnosis.json"
    out.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8")
    detail = EV / "round8_failed_runs.json"
    detail.write_text(json.dumps({"n": len(fails), "failed_runs": fails, "buckets": buckets}, ensure_ascii=False, indent=2), encoding="utf-8")

    print("official", data["openai_success"], "/", data["total_runs"])
    print("failures", len(fails))
    print("distribution", diagnosis["failure_distribution"])
    print("buckets", buckets)
    for f in fails:
        print(f"{f['fixture']}#{f['run']}\t{f['failure_code']}\t{f['stage']}\t{(f['cause'] or '')[:100]}")


if __name__ == "__main__":
    main()
