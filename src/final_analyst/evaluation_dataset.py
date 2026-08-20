"""Evaluation dataset loader (Round 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.judgment_frame import JudgmentFrame

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "examples" / "evaluation"


class EvaluationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    title: str = ""
    industry: str = ""
    structures: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    input: FinalAnalystInput
    expected_frame: JudgmentFrame


def evaluation_dir(root: Path | None = None) -> Path:
    return (root or ROOT) / "examples" / "evaluation"


def list_fixture_ids(root: Path | None = None) -> list[str]:
    d = evaluation_dir(root)
    if not d.exists():
        return []
    skip = {"manifest", "e2e_scoreboard", "evaluation_scoreboard", "stability_stats"}
    return sorted(
        p.stem
        for p in d.glob("*.json")
        if p.stem not in skip and not p.stem.endswith("_scoreboard") and p.stem.startswith("E")
    )

def load_fixture(fixture_id: str, root: Path | None = None) -> EvaluationFixture:
    path = evaluation_dir(root) / f"{fixture_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationFixture.model_validate(data)


def load_evaluation_dataset(root: Path | None = None) -> list[EvaluationFixture]:
    return [load_fixture(fid, root) for fid in list_fixture_ids(root)]


def validate_fixture(fix: EvaluationFixture) -> list[str]:
    errors: list[str] = []
    try:
        FinalAnalystInput.model_validate(fix.input.model_dump())
    except ValidationError as e:
        errors.append(f"invalid_input:{e}")
    try:
        JudgmentFrame.model_validate(fix.expected_frame.model_dump())
    except ValidationError as e:
        errors.append(f"invalid_expected_frame:{e}")

    canon = {c.finding_id for c in all_canonical(fix.input)}
    for cid in fix.input.debate.bull.claims[0].canonical_finding_ids if fix.input.debate.bull.claims else []:
        if cid and cid not in canon:
            # Allow industry rewritten ids present on primary tension
            if not any(cid == c.finding_id for c in all_canonical(fix.input)):
                errors.append(f"debate_canonical_ref_missing:{cid}")

    # No fixture-external promotional / invented investment language.
    # Research disclaimers may contain「不作目标价」— strip known safe phrases first.
    blob = json.dumps(fix.input.model_dump(), ensure_ascii=False)
    for safe in (
        "不作目标价",
        "禁止输出 BUY/SELL/目标价",
        "禁止 BUY/SELL/HOLD、目标价",
        "禁止输出 BUY/SELL/目标价/投资建议",
    ):
        blob = blob.replace(safe, "")
    for bad in ("外网研报", "必涨", "必跌", "目标价", "强烈买入"):
        if bad in blob:
            errors.append(f"fixture_external_fact:{bad}")
    if not fix.fixture_id:
        errors.append("missing_fixture_id")
    return errors


def write_fixture(fix: EvaluationFixture, root: Path | None = None) -> Path:
    d = evaluation_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{fix.fixture_id}.json"
    path.write_text(json.dumps(fix.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
