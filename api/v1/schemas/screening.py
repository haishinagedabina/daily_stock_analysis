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
    rerun_failed: bool = Field(False, description="是否在同日同模式失败任务存在时原地补跑")
    resume_from: Optional[Literal["ingesting", "factorizing"]] = Field(None, description="失败任务补跑起始阶段")
    market: Literal["cn"] = Field("cn", description="市场标识，MVP 仅支持 A 股")


class ScreeningNotifyRequest(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="推送候选数量上限")
    with_ai_only: bool = Field(False, description="是否仅推送已进入 AI 二筛的候选")


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
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ScreeningRunListResponse(BaseModel):
    total: int
    items: List[ScreeningRunResponse]


class ScreeningCandidateItem(BaseModel):
    code: str
    name: Optional[str] = None
    rank: int
    rule_score: float
    selected_for_ai: bool
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
