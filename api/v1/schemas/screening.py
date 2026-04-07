from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CreateScreeningRunRequest(BaseModel):
    trade_date: Optional[date] = Field(None, description="交易日，默认当天")
    stock_codes: Optional[List[str]] = Field(None, description="可选的自定义股票池")
    mode: Optional[Literal["balanced", "aggressive", "quality"]] = Field(None, description="筛选模式预设，默认读取配置")
    candidate_limit: Optional[int] = Field(None, ge=1, le=200, description="规则候选上限，默认读取配置")
    ai_top_k: Optional[int] = Field(None, ge=0, le=50, description="AI 二筛上限，默认读取配置")
    strategies: Optional[List[str]] = Field(None, description="指定使用的筛选策略名称列表，默认使用全部可用策略")
    rerun_failed: bool = Field(False, description="是否在同日同模式失败任务存在时原地补跑")
    resume_from: Optional[Literal["ingesting", "factorizing"]] = Field(None, description="失败任务补跑起始阶段")
    market: Literal["cn"] = Field("cn", description="市场标识，MVP 仅支持 A 股")


class ScreeningNotifyRequest(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="推送候选数量上限")
    with_ai_only: bool = Field(False, description="是否仅推送已进入 AI 二筛的候选")
    force: bool = Field(False, description="是否强制补发（仅对 failed/skipped 有效，v1 不允许重发 sent）")


# ── 五层决策上下文快照 ─────────────────────────────────────────────────────

class MarketEnvironmentSnapshot(BaseModel):
    """L1 大盘环境快照。"""
    market_regime: Optional[str] = None
    risk_level: Optional[str] = None
    index_name: str = "上证指数"
    index_price: Optional[float] = None
    index_ma100: Optional[float] = None
    is_safe: Optional[bool] = None
    message: Optional[str] = None


class SectorHeatSnapshotItem(BaseModel):
    """L2 单个板块热度快照。"""
    board_name: str
    board_type: str = "concept"
    sector_hot_score: float = 0.0
    sector_status: str = "cold"
    sector_stage: str = "ferment"
    canonical_theme: Optional[str] = None
    stock_count: int = 0
    up_count: int = 0
    limit_up_count: int = 0


class DecisionContextSnapshot(BaseModel):
    """L1/L2 决策上下文，附在 ScreeningRunResponse 中返回。"""
    market_environment: Optional[MarketEnvironmentSnapshot] = None
    sector_heat_results: List[SectorHeatSnapshotItem] = Field(default_factory=list)
    hot_theme_count: int = 0
    warm_theme_count: int = 0


class ScreeningRunResponse(BaseModel):
    run_id: str
    mode: Optional[str] = None
    status: str
    trade_date: Optional[str] = None
    market: Optional[str] = None
    universe_size: int = 0
    candidate_count: int = 0
    ai_top_k: int = 0
    error_summary: Optional[str] = None
    failed_symbols: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    sync_failure_ratio: float = 0.0
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Notification lifecycle fields
    trigger_type: Optional[str] = "manual"
    notification_status: Optional[str] = None
    notification_attempts: int = 0
    notification_sent_at: Optional[str] = None
    notification_error: Optional[str] = None
    # 五层决策上下文
    strategy_names: Optional[List[str]] = None
    decision_context: Optional[DecisionContextSnapshot] = None


class ScreeningRunListResponse(BaseModel):
    total: int
    items: List[ScreeningRunResponse]


class ScreeningCandidateItem(BaseModel):
    code: str
    name: Optional[str] = None
    rank: int
    rule_score: float
    selected_for_ai: bool
    matched_strategies: List[str] = Field(default_factory=list)
    rule_hits: List[str] = Field(default_factory=list)
    factor_snapshot: Dict[str, Any] = Field(default_factory=dict)
    ai_query_id: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_operation_advice: Optional[str] = None
    has_ai_analysis: Optional[bool] = None
    news_count: Optional[int] = None
    news_summary: Optional[str] = None
    recommendation_source: Optional[str] = None
    recommendation_reason: Optional[str] = None
    final_score: Optional[float] = None
    final_rank: Optional[int] = None
    # -- 五层系统新增字段 (Phase 1) --
    trade_stage: Optional[str] = None
    setup_type: Optional[str] = None
    entry_maturity: Optional[str] = None
    risk_level: Optional[str] = None
    market_regime: Optional[str] = None
    theme_position: Optional[str] = None
    candidate_pool_level: Optional[str] = None
    trade_plan: Optional[Dict[str, Any]] = None
    # -- AI Review Protocol (Phase 3B-1) --
    ai_trade_stage: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_confidence: Optional[float] = None


class ScreeningAnalysisHistoryRef(BaseModel):
    id: Optional[int] = None
    query_id: str
    stock_code: str
    stock_name: Optional[str] = None
    report_type: Optional[str] = None
    operation_advice: Optional[str] = None
    trend_prediction: Optional[str] = None
    sentiment_score: Optional[int] = None
    analysis_summary: Optional[str] = None
    created_at: Optional[str] = None


class ScreeningCandidateDetailResponse(ScreeningCandidateItem):
    analysis_history: Optional[ScreeningAnalysisHistoryRef] = None


class ScreeningCandidateListResponse(BaseModel):
    total: int
    items: List[ScreeningCandidateItem]


class ScreeningStrategyInfo(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    has_screening_rules: bool


class ScreeningStrategyListResponse(BaseModel):
    strategies: List[ScreeningStrategyInfo]
