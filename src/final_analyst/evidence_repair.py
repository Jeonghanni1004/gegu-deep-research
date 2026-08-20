"""Evidence repair — prefer citation repair over number scrub.

Priority: repair > regenerate > fallback > scrub(last resort, marks information_loss).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from evidence.pack import EvidencePack
from evidence.schema import Evidence
from research.citation import evidence_support_blob, extract_fact_tokens, tokens_supported

from final_analyst.contract import FinalAnalystInput, all_canonical
from final_analyst.schemas import AnalyzedStatement, FinalAnalystOutput
from final_analyst.validators import _iter_statements

RepairAction = Literal["ACCEPT", "REPAIR", "REGENERATE", "REJECT", "FALLBACK"]


@dataclass
class EvidenceRepairResult:
    action: RepairAction
    output: FinalAnalystOutput | None
    repaired_evidence_ids: list[str] = field(default_factory=list)
    unresolved_numbers: list[str] = field(default_factory=list)
    unresolved_claims: list[str] = field(default_factory=list)
    information_loss: bool = False
    notes: list[str] = field(default_factory=list)


def _norm_token(t: str) -> str:
    return (t or "").strip()


def _token_variants(token: str) -> list[str]:
    t = _norm_token(token)
    out = [t]
    if t.endswith("%"):
        out.append(t[:-1])
    else:
        out.append(t + "%")
    # Truncation variants: 1357.7337 ↔ 1357.73
    m = re.fullmatch(r"(\d+)\.(\d+)%?", t)
    if m:
        whole, frac = m.group(1), m.group(2)
        for n in range(2, min(len(frac), 6) + 1):
            out.append(f"{whole}.{frac[:n]}")
            out.append(f"{whole}.{frac[:n]}%")
    return list(dict.fromkeys(out))


def _build_evidence_index(
    inp: FinalAnalystInput,
    pack: EvidencePack | None,
) -> tuple[dict[str, Evidence], dict[str, list[str]], dict[str, list[str]]]:
    """Return (by_id, token→evidence_ids, canonical_id→evidence_ids)."""
    by_id: dict[str, Evidence] = {}
    if pack is not None:
        by_id = {e.evidence_id: e for e in pack.evidence}

    canon_eids: dict[str, list[str]] = {}
    token_map: dict[str, list[str]] = {}

    def _index_blob(eids: list[str], blob: str) -> None:
        for tok in extract_fact_tokens(blob):
            for v in _token_variants(tok):
                token_map.setdefault(v, [])
                for eid in eids:
                    if eid not in token_map[v]:
                        token_map[v].append(eid)

    for c in all_canonical(inp):
        eids = list(c.evidence_ids or [])
        canon_eids[c.finding_id] = eids
        blob = " ".join([c.claim or "", " ".join(c.numbers_preserved or [])])
        _index_blob(eids, blob)
        for eid in eids:
            ev = by_id.get(eid)
            if ev is not None:
                _index_blob([eid], evidence_support_blob(ev))

    # Debate surface evidence
    for cl in list(inp.debate.bull.claims) + list(inp.debate.bear.claims):
        _index_blob(list(cl.evidence_ids or []), cl.claim or "")
        for eid in cl.evidence_ids or []:
            ev = by_id.get(eid)
            if ev is not None:
                _index_blob([eid], evidence_support_blob(ev))

    if pack is not None:
        for e in pack.evidence:
            _index_blob([e.evidence_id], evidence_support_blob(e))

    return by_id, token_map, canon_eids


def _match_token_eids(token: str, token_map: dict[str, list[str]]) -> list[str]:
    found: list[str] = []
    for v in _token_variants(token):
        for eid in token_map.get(v, []):
            if eid not in found:
                found.append(eid)
    # Prefix soft-match: same whole-number family only (avoid 0.5016 ↔ unrelated)
    if not found:
        bare = token.rstrip("%")
        m_tok = re.fullmatch(r"(\d+)\.(\d+)", bare)
        for key, eids in token_map.items():
            kb = key.rstrip("%")
            if bare == kb:
                soft = True
            elif m_tok and re.fullmatch(r"(\d+)\.(\d+)", kb):
                soft = m_tok.group(1) == kb.split(".")[0] and (
                    bare.startswith(kb) or kb.startswith(bare)
                )
            else:
                soft = False
            if soft:
                for eid in eids:
                    if eid not in found:
                        found.append(eid)
    return found


def _statement_missing_tokens(
    s: AnalyzedStatement,
    by_id: dict[str, Evidence],
    as_of: str,
) -> list[str]:
    tokens = extract_fact_tokens(s.text)
    filtered = [t for t in tokens if not re.fullmatch(r"\d{1,2}", t) and t != as_of]
    if not filtered:
        return []
    cited = [by_id[e] for e in s.evidence_ids if e in by_id]
    if not cited:
        # No pack citations — treat all tokens as needing repair if we have an index
        return filtered
    _, missing = tokens_supported(filtered, cited)
    return missing


def _scrub_unsupported_number_tokens_local(out: FinalAnalystOutput, missing: list[str]) -> FinalAnalystOutput:
    """Last-resort scrub — always marks information_loss in caller notes."""
    if not missing:
        return out
    data = out.model_dump()
    missing_sorted = sorted({m for m in missing if m}, key=len, reverse=True)

    def scrub(text: str) -> str:
        t = text
        for tok in missing_sorted:
            t = re.sub(re.escape(tok) + r"\d*", "", t)
        t = re.sub(r"\s{2,}", " ", t)
        return t.strip(" ，,；;/、")

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "text" in node and isinstance(node["text"], str):
                node["text"] = scrub(node["text"])
            if "numbers_used" in node and isinstance(node["numbers_used"], list):
                node["numbers_used"] = [
                    n
                    for n in node["numbers_used"]
                    if not any(str(n) == m or str(n).startswith(m) or m.startswith(str(n)) for m in missing_sorted)
                ]
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return FinalAnalystOutput.model_validate(walk(data))


def repair_output_citations(
    out: FinalAnalystOutput,
    inp: FinalAnalystInput,
    *,
    pack: EvidencePack | None = None,
    allow_scrub: bool = False,
) -> EvidenceRepairResult:
    """Level 1–2 repair: attach evidence_ids for numbers already in INPUT.

    Does not call LLM. Level 3 regenerate is handled by caller.
    """
    by_id, token_map, canon_eids = _build_evidence_index(inp, pack)
    data = out.model_dump()
    repaired_ids: list[str] = []
    still_missing: list[str] = []

    def repair_stmt(node: dict[str, Any]) -> None:
        text = node.get("text") or ""
        if not isinstance(text, str) or not text.strip():
            return
        eids = list(node.get("evidence_ids") or [])
        cids = list(node.get("canonical_finding_ids") or [])
        # Level 2: expand from canonical
        for cid in cids:
            for eid in canon_eids.get(cid, []):
                if eid not in eids:
                    eids.append(eid)
                    repaired_ids.append(eid)
        tokens = extract_fact_tokens(text)
        filtered = [t for t in tokens if not re.fullmatch(r"\d{1,2}", t) and t != out.research_as_of_date]
        cited = [by_id[e] for e in eids if e in by_id]
        missing: list[str] = []
        if filtered:
            if cited:
                _, missing = tokens_supported(filtered, cited)
            else:
                # Without pack blobs, try token_map only
                missing = []
                for t in filtered:
                    matched = _match_token_eids(t, token_map)
                    if matched:
                        continue
                    # Without pack: only accept exact / variant hits on numbers_preserved (not loose substring)
                    in_canon = False
                    for c in all_canonical(inp):
                        preserved = [str(x) for x in (c.numbers_preserved or [])]
                        variants = set(_token_variants(t))
                        if any(p in variants or any(v == p for v in variants) for p in preserved):
                            in_canon = True
                            for eid in c.evidence_ids or []:
                                if eid not in eids:
                                    eids.append(eid)
                                    repaired_ids.append(eid)
                            break
                        # Exact token appearance in claim (full token, not short truncation)
                        claim = c.claim or ""
                        if t in claim or (t + "%") in claim or (t.endswith("%") and t[:-1] in claim):
                            in_canon = True
                            for eid in c.evidence_ids or []:
                                if eid not in eids:
                                    eids.append(eid)
                                    repaired_ids.append(eid)
                            break
                    if not in_canon:
                        missing.append(t)
        for tok in list(missing):
            matched = _match_token_eids(tok, token_map)
            if matched:
                for eid in matched[:4]:
                    if eid not in eids:
                        eids.append(eid)
                        repaired_ids.append(eid)
                # Re-check this token
                cited2 = [by_id[e] for e in eids if e in by_id]
                if cited2:
                    _, miss2 = tokens_supported([tok], cited2)
                    if not miss2 and tok in missing:
                        missing.remove(tok)
                else:
                    # Matched via input surface without pack object — accept
                    if tok in missing:
                        missing.remove(tok)
        # Also attach numbers_used grounding
        nums = list(node.get("numbers_used") or [])
        for n in nums:
            for eid in _match_token_eids(str(n), token_map)[:2]:
                if eid not in eids:
                    eids.append(eid)
                    repaired_ids.append(eid)
        node["evidence_ids"] = eids[:16]
        for tok in missing:
            if tok not in still_missing:
                still_missing.append(tok)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "text" in node and "evidence_ids" in node:
                repair_stmt(node)
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    data = walk(data)
    repaired = FinalAnalystOutput.model_validate(data)

    # Re-evaluate missing with pack if available
    final_missing: list[str] = []
    if pack is not None:
        for s in _iter_statements(repaired):
            final_missing.extend(_statement_missing_tokens(s, by_id, out.research_as_of_date))
        final_missing = list(dict.fromkeys(final_missing))
    else:
        final_missing = still_missing

    notes = [f"evidence_repair:repaired_ids={len(set(repaired_ids))}"]
    if not final_missing:
        action: RepairAction = "REPAIR" if repaired_ids else "ACCEPT"
        meta_notes = list(repaired.meta.notes) + notes + [f"evidence_repair_action={action}"]
        repaired = repaired.model_copy(
            update={"meta": repaired.meta.model_copy(update={"notes": meta_notes})}
        )
        return EvidenceRepairResult(
            action=action,
            output=repaired,
            repaired_evidence_ids=list(dict.fromkeys(repaired_ids)),
            unresolved_numbers=[],
            information_loss=False,
            notes=notes,
        )

    if allow_scrub:
        # Last-resort scrub — marks information_loss; caller must not treat as production PASS
        scrubbed = _scrub_unsupported_number_tokens_local(repaired, final_missing)
        loss = True
        meta_notes = list(scrubbed.meta.notes) + notes + [
            "evidence_repair_action=REJECT_SCRUB",
            "information_loss=true",
        ]
        scrubbed = scrubbed.model_copy(
            update={"meta": scrubbed.meta.model_copy(update={"notes": meta_notes})}
        )
        return EvidenceRepairResult(
            action="REJECT",
            output=scrubbed,
            repaired_evidence_ids=list(dict.fromkeys(repaired_ids)),
            unresolved_numbers=final_missing,
            information_loss=loss,
            notes=notes + ["scrub_used_information_loss"],
        )

    return EvidenceRepairResult(
        action="REGENERATE",
        output=repaired,
        repaired_evidence_ids=list(dict.fromkeys(repaired_ids)),
        unresolved_numbers=final_missing,
        unresolved_claims=[f"ungrounded:{t}" for t in final_missing[:6]],
        information_loss=False,
        notes=notes + [f"unresolved_numbers={final_missing[:6]}"],
    )


def has_partial_number_damage(text: str) -> bool:
    """Detect scrub artifacts like『营收同比 -』or『毛利率 。』."""
    if re.search(r"(同比|环比|增速|毛利率|ROE|PE|PB)\s*[-—–]\s*(?:[，,。；;\s]|$)", text):
        return True
    if re.search(r"(同比|环比|毛利率|ROE)\s+[，,。]", text):
        return True
    return False


def information_loss_in_output(out: FinalAnalystOutput) -> bool:
    if any("information_loss=true" in n for n in (out.meta.notes or [])):
        return True
    from final_analyst.validators import _iter_statements

    return any(has_partial_number_damage(s.text) for s in _iter_statements(out))
