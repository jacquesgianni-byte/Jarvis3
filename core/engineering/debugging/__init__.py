# Genesis-017 Sprints 001-006 — Engineering Debugging (COMPLETE)
from core.engineering.debugging.debugger import EngineeringDebugger
from core.engineering.debugging.models import DebugReport, FailureEvidence, FailureType
from core.engineering.debugging.classifier import FailureClassifier
from core.engineering.debugging.extractor import EvidenceExtractor, StackFrame
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory
from core.engineering.debugging.analyzer import RootCauseAnalyzer
from core.engineering.debugging.correlation import CorrelationRecord, CorrelationType
from core.engineering.debugging.engine import FailureCorrelationEngine, FailureRecord
from core.engineering.debugging.recommendation import (
    Recommendation, RecommendationCategory, RecommendationPriority
)
from core.engineering.debugging.rec_engine import RecommendationEngine
from core.engineering.debugging.repair import (
    RepairPlan, RepairStep, RepairRisk, RepairEffort
)
from core.engineering.debugging.planner import RepairPlanner

__all__ = [
    "EngineeringDebugger",
    "DebugReport", "FailureEvidence", "FailureType",
    "FailureClassifier",
    "EvidenceExtractor", "StackFrame",
    "RootCause", "RootCauseCategory",
    "RootCauseAnalyzer",
    "CorrelationRecord", "CorrelationType",
    "FailureCorrelationEngine", "FailureRecord",
    "Recommendation", "RecommendationCategory", "RecommendationPriority",
    "RecommendationEngine",
    "RepairPlan", "RepairStep", "RepairRisk", "RepairEffort",
    "RepairPlanner",
]