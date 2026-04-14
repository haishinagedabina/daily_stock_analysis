# -*- coding: utf-8 -*-
"""Backtest-specific enumerations.

These enums are specific to the five-layer backtest subsystem.
For five-layer trading enums (MarketRegime, TradeStage, etc.),
use src.schemas.trading_types.
"""
from enum import Enum


class EvaluationMode(str, Enum):
    """Backtest evaluation mode."""
    HISTORICAL_SNAPSHOT = "historical_snapshot"
    RULE_REPLAY = "rule_replay"
    PARAMETER_CALIBRATION = "parameter_calibration"


class ExecutionModel(str, Enum):
    """Trade execution assumption tier."""
    CONSERVATIVE = "conservative"
    BASELINE = "baseline"
    OPTIMISTIC = "optimistic"


class SignalFamily(str, Enum):
    """High-level signal classification."""
    ENTRY = "entry"
    EXIT = "exit"
    OBSERVATION = "observation"


class FillStatus(str, Enum):
    """Execution fill outcome."""
    FILLED = "filled"
    LIMIT_BLOCKED = "limit_blocked"
    GAP_ADJUSTED = "gap_adjusted"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"


class BacktestRunStatus(str, Enum):
    """Backtest run lifecycle status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationLevel(str, Enum):
    """Recommendation confidence tier."""
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    ACTIONABLE = "actionable"
