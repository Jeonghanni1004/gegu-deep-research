"""Adversarial Research Layer: Bull / Bear / Debate."""

from debate.bear_agent import BearAgent
from debate.bull_agent import BullAgent
from debate.debate_engine import run_debate, save_debate_outputs
from debate.evidence_weight import calculate_evidence_weight
from debate.schemas import BearResearch, BullResearch, Challenge, DebateResult, Rebuttal, ResearchClaim

__all__ = [
    "BullAgent",
    "BearAgent",
    "ResearchClaim",
    "BullResearch",
    "BearResearch",
    "Challenge",
    "Rebuttal",
    "DebateResult",
    "calculate_evidence_weight",
    "run_debate",
    "save_debate_outputs",
]
