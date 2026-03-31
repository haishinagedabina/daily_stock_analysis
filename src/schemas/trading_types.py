"""五层交易系统的核心枚举与数据结构。

Layer architecture:
  L1 Market Environment → L2 Theme/Sector → L3 Strong Stock Pool
  → L4 Setup Identification → L5 Trade Management

Each layer's output constrains downstream layers via hard rules
(e.g., stand_aside caps trade_stage at watch).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class MarketRegime(str, Enum):
    """L1 市场环境状态"""
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    DEFENSIVE = "defensive"
    STAND_ASIDE = "stand_aside"


class ThemePosition(str, Enum):
    """L2 题材地位"""
    MAIN_THEME = "main_theme"
    SECONDARY_THEME = "secondary_theme"
    FADING_THEME = "fading_theme"
    NON_THEME = "non_theme"


class CandidatePoolLevel(str, Enum):
    """L3 候选池分级"""
    LEADER_POOL = "leader_pool"
    FOCUS_LIST = "focus_list"
    WATCHLIST = "watchlist"


class TradeStage(str, Enum):
    """L5 交易阶段——贯穿全系统的核心输出"""
    STAND_ASIDE = "stand_aside"
    WATCH = "watch"
    FOCUS = "focus"
    PROBE_ENTRY = "probe_entry"
    ADD_ON_STRENGTH = "add_on_strength"
    REJECT = "reject"


class SetupType(str, Enum):
    """L4 买点类型"""
    BOTTOM_DIVERGENCE_BREAKOUT = "bottom_divergence_breakout"
    LOW123_BREAKOUT = "low123_breakout"
    TREND_BREAKOUT = "trend_breakout"
    TREND_PULLBACK = "trend_pullback"
    GAP_BREAKOUT = "gap_breakout"
    LIMITUP_STRUCTURE = "limitup_structure_breakout"
    NONE = "none"


class EntryMaturity(str, Enum):
    """买点成熟度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyFamily(str, Enum):
    """三大买点模板家族"""
    REVERSAL = "reversal"
    TREND = "trend"
    MOMENTUM = "momentum"
    AUXILIARY = "auxiliary"


class StrategyRole(str, Enum):
    """策略在系统中的角色"""
    ENTRY_CORE = "entry_core"
    STOCK_POOL = "stock_pool"
    THEME_SCORE = "theme_score"
    CONFIRM = "confirm"
    BONUS_SIGNAL = "bonus_signal"
    OBSERVATION = "observation"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class MarketEnvironment:
    """L1 市场环境层输出"""
    regime: MarketRegime
    risk_level: RiskLevel
    index_price: float = 0.0
    index_ma100: float = 0.0
    is_safe: bool = True
    message: str = ""


@dataclass
class ThemeDecision:
    """L2 题材层输出（单个题材）"""
    theme_tag: str
    theme_score: float = 0.0
    theme_position: ThemePosition = ThemePosition.NON_THEME
    leader_score: float = 0.0
    sector_strength: float = 0.0
    theme_duration: str = "unknown"
    leader_stocks: List[str] = field(default_factory=list)
    front_stocks: List[str] = field(default_factory=list)


@dataclass
class SetupDecision:
    """L4 买点识别层输出"""
    setup_type: SetupType = SetupType.NONE
    entry_maturity: EntryMaturity = EntryMaturity.LOW
    setup_freshness: float = 0.0
    hit_reasons: List[str] = field(default_factory=list)


@dataclass
class TradePlan:
    """L5 交易管理层输出"""
    initial_position: Optional[str] = None
    add_rule: Optional[str] = None
    stop_loss_rule: Optional[str] = None
    take_profit_plan: Optional[str] = None
    invalidation_rule: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    holding_expectation: Optional[str] = None


@dataclass
class CandidateDecision:
    """统一候选股决策结果——贯穿 5 层的最终输出"""
    code: str
    name: str = ""
    # L1
    market_regime: MarketRegime = MarketRegime.BALANCED
    environment_ok: bool = True
    # L2
    theme_tag: str = ""
    theme_position: ThemePosition = ThemePosition.NON_THEME
    leader_score: float = 0.0
    # L3
    candidate_pool_level: CandidatePoolLevel = CandidatePoolLevel.WATCHLIST
    relative_strength_market: float = 0.0
    relative_strength_sector: float = 0.0
    # L4
    setup_type: SetupType = SetupType.NONE
    entry_maturity: EntryMaturity = EntryMaturity.LOW
    setup_freshness: float = 0.0
    matched_strategies: List[str] = field(default_factory=list)
    # L5
    trade_stage: TradeStage = TradeStage.WATCH
    trade_plan: Optional[TradePlan] = None
    # AI 二筛
    ai_trade_stage: Optional[TradeStage] = None
    ai_reasoning: str = ""
    ai_confidence: float = 0.0
    # 评分
    rule_score: float = 0.0
    final_score: float = 0.0
