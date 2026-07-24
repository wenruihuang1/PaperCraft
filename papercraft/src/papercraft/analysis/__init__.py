"""Paper logic analyzers consuming DocumentIR 1.0."""

from papercraft.analysis.base import PaperAnalysisError, PaperAnalyzer
from papercraft.analysis.heuristic_analyzer import HeuristicPaperAnalyzer

__all__ = ["PaperAnalysisError", "PaperAnalyzer", "HeuristicPaperAnalyzer"]

