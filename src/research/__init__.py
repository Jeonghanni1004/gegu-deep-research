"""Research agents package (Agent Layer)."""

from research.fundamental_agent import FundamentalAgent
from research.market_agent import MarketAgent
from research.parallel import run_parallel_research, save_research_outputs
from research.retriever import EvidenceRetriever
from research.schemas import FundamentalResearch, MarketResearch, ParallelResearchResult

__all__ = [
    "EvidenceRetriever",
    "FundamentalAgent",
    "MarketAgent",
    "FundamentalResearch",
    "MarketResearch",
    "ParallelResearchResult",
    "run_parallel_research",
    "save_research_outputs",
]
