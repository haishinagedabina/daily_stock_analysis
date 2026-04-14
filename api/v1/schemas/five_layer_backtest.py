# -*- coding: utf-8 -*-
"""Five-layer backtest API schemas.

Request and response models for the run-based five-layer backtest system.
All endpoints use ``backtest_run_id`` as the primary index.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Request models ─────────────────────────────────────────────────────────

class FiveLayerBacktestRunRequest(BaseModel):
    evaluation_mode: str = Field(
        "historical_snapshot",
        description="评估模式: historical_snapshot / rule_replay / parameter_calibration",
    )
    execution_model: str = Field(
        "conservative",
        description="执行模型: conservative / baseline / optimistic",
    )
    trade_date_from: str = Field(..., description="回测起始日期 (YYYY-MM-DD)")
    trade_date_to: str = Field(..., description="回测结束日期 (YYYY-MM-DD)")
    market: str = Field("cn", description="市场: cn / us / hk")
    eval_window_days: int = Field(10, ge=1, le=120, description="评估窗口（交易日数）")
    generate_recommendations: bool = Field(True, description="是否生成建议")


class FiveLayerCalibrationRequest(BaseModel):
    baseline_run_id: str = Field(..., description="基准运行ID")
    candidate_run_id: str = Field(..., description="候选运行ID")
    calibration_name: str = Field(..., description="校准名称")
    baseline_config: Optional[Dict[str, Any]] = Field(None, description="基准配置")
    candidate_config: Optional[Dict[str, Any]] = Field(None, description="候选配置")


# ── Response models ────────────────────────────────────────────────────────

class FiveLayerRunResponse(BaseModel):
    backtest_run_id: str
    evaluation_mode: str
    execution_model: str
    trade_date_from: Optional[str] = None
    trade_date_to: Optional[str] = None
    market: str = "cn"
    status: str = "pending"
    sample_count: int = 0
    completed_count: int = 0
    error_count: int = 0
    data_version: Optional[str] = None
    market_data_version: Optional[str] = None
    theme_mapping_version: Optional[str] = None
    candidate_snapshot_version: Optional[str] = None
    rules_version: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class FiveLayerEvaluationItem(BaseModel):
    id: Optional[int] = None
    backtest_run_id: str
    trade_date: Optional[str] = None
    code: str
    name: Optional[str] = None
    signal_family: str
    evaluator_type: str
    execution_model: Optional[str] = None

    # Snapshot fields
    snapshot_trade_stage: Optional[str] = None
    snapshot_setup_type: Optional[str] = None
    snapshot_entry_maturity: Optional[str] = None
    snapshot_market_regime: Optional[str] = None
    snapshot_theme_position: Optional[str] = None
    snapshot_candidate_pool_level: Optional[str] = None
    snapshot_risk_level: Optional[str] = None

    # Execution
    entry_fill_status: Optional[str] = None
    entry_fill_price: Optional[float] = None
    exit_fill_price: Optional[float] = None
    limit_blocked: Optional[bool] = None
    gap_adjusted: Optional[bool] = None

    # Metrics
    forward_return_1d: Optional[float] = None
    forward_return_3d: Optional[float] = None
    forward_return_5d: Optional[float] = None
    forward_return_10d: Optional[float] = None
    mae: Optional[float] = None
    mfe: Optional[float] = None
    max_drawdown_from_peak: Optional[float] = None
    holding_days: Optional[int] = None
    plan_success: Optional[bool] = None
    signal_quality_score: Optional[float] = None
    risk_avoided_pct: Optional[float] = None
    opportunity_cost_pct: Optional[float] = None
    outcome: Optional[str] = None
    stage_success: Optional[bool] = None
    eval_status: Optional[str] = None


class FiveLayerEvaluationsResponse(BaseModel):
    backtest_run_id: str
    total: int
    page: int
    limit: int
    items: List[FiveLayerEvaluationItem] = Field(default_factory=list)


class FiveLayerGroupSummaryItem(BaseModel):
    group_type: str
    group_key: str
    sample_count: int = 0
    avg_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    win_rate_pct: Optional[float] = None
    avg_mae: Optional[float] = None
    avg_mfe: Optional[float] = None
    avg_drawdown: Optional[float] = None
    top_k_hit_rate: Optional[float] = None
    excess_return_pct: Optional[float] = None
    ranking_consistency: Optional[float] = None
    p25_return_pct: Optional[float] = None
    p75_return_pct: Optional[float] = None
    extreme_sample_ratio: Optional[float] = None
    time_bucket_stability: Optional[float] = None


class FiveLayerSummariesResponse(BaseModel):
    backtest_run_id: str
    items: List[FiveLayerGroupSummaryItem] = Field(default_factory=list)


class FiveLayerCalibrationItem(BaseModel):
    calibration_name: Optional[str] = None
    baseline_config_json: Optional[str] = None
    candidate_config_json: Optional[str] = None
    delta_metrics_json: Optional[str] = None
    decision: Optional[str] = None
    confidence: Optional[float] = None


class FiveLayerCalibrationResponse(BaseModel):
    backtest_run_id: str
    items: List[FiveLayerCalibrationItem] = Field(default_factory=list)


class FiveLayerRecommendationItem(BaseModel):
    recommendation_type: str
    target_scope: Optional[str] = None
    target_key: Optional[str] = None
    current_rule: Optional[str] = None
    suggested_change: Optional[str] = None
    recommendation_level: str
    sample_count: Optional[int] = None
    confidence: Optional[float] = None
    validation_status: Optional[str] = None
    evidence_json: Optional[str] = None


class FiveLayerRecommendationsResponse(BaseModel):
    backtest_run_id: str
    items: List[FiveLayerRecommendationItem] = Field(default_factory=list)


class FiveLayerFullPipelineResponse(BaseModel):
    run: FiveLayerRunResponse
    summaries: List[FiveLayerGroupSummaryItem] = Field(default_factory=list)
    recommendations: List[FiveLayerRecommendationItem] = Field(default_factory=list)
