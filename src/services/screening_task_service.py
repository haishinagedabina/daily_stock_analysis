from __future__ import annotations

import hashlib
import json
import logging
import time
from urllib.parse import quote
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from src.config import get_config
from src.core.trading_calendar import MARKET_TIMEZONE, is_market_open
from src.core.market_guard import MarketGuard
from src.services.candidate_analysis_service import CandidateAnalysisService
from src.services.candidate_analysis_service import CandidateAnalysisBatchResult
from src.services.candidate_decision_builder import CandidateDecisionBuilder
from src.services.factor_service import FactorService
from src.services.market_data_sync_service import MarketDataSyncService
from src.services.screening_mode_registry import (
    ResolvedScreeningRuntimeConfig,
    resolve_screening_runtime_config,
)
from src.services.screener_service import ScreeningCandidateRecord, ScreenerService
from src.services.universe_service import LocalUniverseNotReadyError, UniverseService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

# 全局超时（秒）：整个 execute_run 的最大允许时长
_EXECUTE_RUN_DEADLINE_SECONDS: int = 30 * 60  # 30 分钟
_CN_MARKET_CLOSE_TIME = dt_time(hour=15, minute=0)

# ── L1 硬开关：市场环境 → 候选上限映射 ───────────────────────────────────────
# stand_aside → 0 候选（总开关关闭）
# defensive  → 原上限减半（至少 2 个）
# balanced / aggressive → 不限制
def _make_regime_candidate_cap() -> dict:
    from src.schemas.trading_types import MarketRegime
    return {
        MarketRegime.STAND_ASIDE: 0,
        MarketRegime.DEFENSIVE: None,   # 占位，运行时按 max(2, limit//2) 计算
        MarketRegime.BALANCED: None,    # 不限制
        MarketRegime.AGGRESSIVE: None,  # 不限制
    }

try:
    _REGIME_CANDIDATE_CAP = _make_regime_candidate_cap()
except Exception:
    _REGIME_CANDIDATE_CAP = {}


def _ai_review_fields(
    protocol: "AiReviewProtocol",
    ai_payload: Dict[str, Any],
    candidate: Any,
) -> Dict[str, Any]:
    """Apply AiReviewProtocol.parse_ai_response and return AI review fields dict."""
    rule_trade_stage = getattr(candidate, "trade_stage", None) or ""
    market_regime = getattr(candidate, "market_regime", None) or ""
    rule_trade_stage = getattr(rule_trade_stage, "value", rule_trade_stage)
    market_regime = getattr(market_regime, "value", market_regime)
    review = protocol.parse_ai_response(
        ai_summary=ai_payload.get("ai_summary"),
        ai_operation_advice=ai_payload.get("ai_operation_advice"),
        rule_trade_stage=rule_trade_stage,
        market_regime=market_regime,
    )
    reasoning = review.ai_reasoning
    if review.risk_flags:
        reasoning = f"{reasoning} | 风险标记: {', '.join(review.risk_flags)}"
    return {
        "ai_trade_stage": review.ai_trade_stage,
        "ai_reasoning": reasoning,
        "ai_confidence": review.ai_confidence,
        "ai_environment_ok": review.ai_environment_ok,
        "ai_theme_alignment": review.ai_theme_alignment,
        "ai_entry_quality": review.ai_entry_quality,
        "stage_conflict": review.stage_conflict,
    }


class ScreeningTradeDateNotReadyError(ValueError):
    def __init__(self, message: str, error_code: str = "screening_trade_time_not_ready") -> None:
        super().__init__(message)
        self.error_code = error_code


class ScreeningTaskService:
    """全市场筛选编排服务。"""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        universe_service: Optional[UniverseService] = None,
        factor_service: Optional[FactorService] = None,
        screener_service: Optional[ScreenerService] = None,
        candidate_analysis_service: Optional[CandidateAnalysisService] = None,
        market_data_sync_service: Optional[MarketDataSyncService] = None,
        skill_manager: Optional[Any] = None,
    ) -> None:
        self.config = get_config()
        self.db = db_manager or DatabaseManager.get_instance()
        self._last_stage_hint = "initializing"
        self._custom_factor_service = factor_service is not None
        self._custom_screener_service = screener_service is not None
        self._skill_manager = skill_manager
        self.universe_service = universe_service or UniverseService()
        self.screener_service = screener_service
        self.factor_service = factor_service
        self._candidate_analysis_service: Optional[CandidateAnalysisService] = candidate_analysis_service
        self._market_data_sync_service: Optional[MarketDataSyncService] = market_data_sync_service
        self._theme_context: Optional[Any] = None

    @property
    def candidate_analysis_service(self) -> CandidateAnalysisService:
        if self._candidate_analysis_service is None:
            self._candidate_analysis_service = CandidateAnalysisService()
        return self._candidate_analysis_service

    @candidate_analysis_service.setter
    def candidate_analysis_service(self, value: CandidateAnalysisService) -> None:
        self._candidate_analysis_service = value

    @property
    def market_data_sync_service(self) -> MarketDataSyncService:
        if self._market_data_sync_service is None:
            self._market_data_sync_service = MarketDataSyncService(self.db)
        return self._market_data_sync_service

    @market_data_sync_service.setter
    def market_data_sync_service(self, value: MarketDataSyncService) -> None:
        self._market_data_sync_service = value

    def execute_run(
        self,
        trade_date: Optional[date] = None,
        stock_codes: Optional[List[str]] = None,
        mode: Optional[str] = None,
        candidate_limit: Optional[int] = None,
        ai_top_k: Optional[int] = None,
        market: str = "cn",
        rerun_failed: bool = False,
        resume_from: Optional[str] = None,
        trigger_type: str = "manual",
        strategy_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        current_stage = "initializing"
        self._last_stage_hint = current_stage
        self._active_strategy_names = strategy_names
        run_started_at = time.perf_counter()
        normalized_stock_codes = self._normalize_stock_codes(stock_codes)
        runtime_config = self.resolve_run_config(mode=mode, candidate_limit=candidate_limit, ai_top_k=ai_top_k)
        if runtime_config.ai_top_k > runtime_config.candidate_limit:
            raise ValueError("ai_top_k 不能大于 candidate_limit")
        if runtime_config.mode != "balanced" and (self._custom_screener_service or self._custom_factor_service):
            raise ValueError("自定义注入的筛选服务不支持非 balanced mode，请改为使用默认服务构建")
        requested_trade_date = trade_date or self._get_market_today(market)
        resolved_trade_date = requested_trade_date
        trade_date_warning: Optional[str] = None
        if trade_date is not None:
            resolved_trade_date, trade_date_warning = self._resolve_screening_trade_date(
                requested_trade_date=requested_trade_date,
                market=market,
            )
        run_snapshot = self._build_run_config_snapshot(
            requested_trade_date=requested_trade_date,
            normalized_stock_codes=normalized_stock_codes,
            runtime_config=runtime_config,
            ingest_failure_threshold=float(getattr(self.config, "screening_ingest_failure_threshold", 0.20)),
            strategy_names=strategy_names,
            theme_context=self._theme_context,
        )
        if trade_date is not None and resolved_trade_date != requested_trade_date:
            run_snapshot["resolved_trade_date"] = resolved_trade_date.isoformat()
        resume_stage = self._normalize_resume_from(resume_from)
        if resume_stage is not None:
            run_snapshot["next_resume_stage"] = resume_stage
        rerunnable_failed_symbols: List[str] = []
        carried_failed_symbols: List[str] = []
        carried_failed_symbol_reasons: Dict[str, str] = {}
        carried_warnings: List[str] = []
        existing_run = self.db.find_latest_screening_run(
            market=market,
            config_snapshot=run_snapshot,
        )
        if not isinstance(existing_run, dict):
            existing_run = None
        recovered_stale_run_id: Optional[str] = None
        if existing_run is not None:
            pre_recover_id = existing_run.get("run_id")
            existing_run = self._recover_stale_run(existing_run)
            if existing_run is None:
                recovered_stale_run_id = pre_recover_id
        if existing_run is not None:
            carried_failed_symbols = self._extract_failed_symbols(existing_run)
            carried_failed_symbol_reasons = self._extract_failed_symbol_reasons(existing_run)
            rerunnable_failed_symbols = self._extract_rerunnable_failed_symbols(existing_run)
            carried_warnings = self._extract_warnings(existing_run)
            rerun_failed_symbols_for_snapshot = (
                carried_failed_symbols if resume_stage == "factorizing" else rerunnable_failed_symbols
            )
            rerun_failed_symbol_reasons_for_snapshot = (
                carried_failed_symbol_reasons
                if resume_stage == "factorizing"
                else {
                    code: reason
                    for code, reason in carried_failed_symbol_reasons.items()
                    if code in set(rerunnable_failed_symbols)
                }
            )
            rerun_warnings_for_snapshot = (
                carried_warnings
                if resume_stage == "factorizing"
                else (
                    [self._build_known_failed_symbol_warning(rerunnable_failed_symbols)]
                    if rerunnable_failed_symbols
                    else []
                )
            )
            if resume_stage is not None and existing_run.get("status") != "failed":
                if rerun_failed:
                    return existing_run
                raise ValueError("resume_from 仅支持失败任务补跑")
            if existing_run.get("status") == "failed" and rerun_failed:
                if rerun_failed_symbols_for_snapshot:
                    run_snapshot["failed_symbols"] = rerun_failed_symbols_for_snapshot
                if rerun_failed_symbol_reasons_for_snapshot:
                    run_snapshot["failed_symbol_reasons"] = rerun_failed_symbol_reasons_for_snapshot
                if rerun_warnings_for_snapshot:
                    run_snapshot["warnings"] = rerun_warnings_for_snapshot
                self._validate_resume_stage(existing_run=existing_run, resume_stage=resume_stage)
                if not self.db.reset_screening_run_for_rerun(
                    run_id=existing_run["run_id"],
                    config_snapshot=run_snapshot,
                    ai_top_k=runtime_config.ai_top_k,
                ):
                    claimed_run = self.get_run(existing_run["run_id"])
                    if claimed_run is not None:
                        return claimed_run
                    raise RuntimeError("筛选任务补跑初始化失败")
                run_id = existing_run["run_id"]
            elif existing_run.get("status") == "failed":
                logger.info(
                    f"screening_run event=auto_retry_failed_run "
                    f"run_id={existing_run['run_id']} "
                    f"old_error={existing_run.get('error_summary', '')[:80]}"
                )
                if not self.db.reset_screening_run_for_rerun(
                    run_id=existing_run["run_id"],
                    config_snapshot=run_snapshot,
                    ai_top_k=runtime_config.ai_top_k,
                ):
                    claimed_run = self.get_run(existing_run["run_id"])
                    if claimed_run is not None:
                        return claimed_run
                    raise RuntimeError("筛选任务自动重试初始化失败")
                run_id = existing_run["run_id"]
            elif existing_run.get("status") in {"completed", "completed_with_ai_degraded"}:
                create_result = self.db.create_screening_run(
                    trade_date=resolved_trade_date,
                    market=market,
                    config_snapshot=run_snapshot,
                    ai_top_k=runtime_config.ai_top_k,
                    return_created=True,
                    trigger_type=trigger_type,
                )
                if isinstance(create_result, tuple):
                    run_id, _created = create_result
                else:
                    run_id = create_result
            else:
                return existing_run
        elif recovered_stale_run_id is not None:
            if not self.db.reset_screening_run_for_rerun(
                run_id=recovered_stale_run_id,
                config_snapshot=run_snapshot,
                ai_top_k=runtime_config.ai_top_k,
            ):
                raise RuntimeError(
                    f"幽灵任务 {recovered_stale_run_id} 回收后重置失败"
                )
            run_id = recovered_stale_run_id
            logger.info(
                f"screening_run event=stale_run_reused run_id={run_id}"
            )
        else:
            if resume_stage is not None:
                raise ValueError("resume_from 仅支持失败任务补跑")
            create_result = self.db.create_screening_run(
                trade_date=resolved_trade_date,
                market=market,
                config_snapshot=run_snapshot,
                ai_top_k=runtime_config.ai_top_k,
                run_id=self._build_idempotent_run_id(market=market, config_snapshot=run_snapshot),
                return_created=True,
                trigger_type=trigger_type,
            )
            if isinstance(create_result, tuple):
                run_id, created = create_result
            else:
                run_id, created = create_result, True
            if not created:
                existing = self.get_run(run_id)
                if existing is not None:
                    return existing
        self._log_run_event(
            "run_started",
            screening_run_id=run_id,
            stage=current_stage,
            mode=runtime_config.mode,
            market=market,
            candidate_limit=runtime_config.candidate_limit,
            ai_top_k=runtime_config.ai_top_k,
        )
        runtime_screener_service = self._build_runtime_screener_service(
            runtime_config, strategy_names=self._active_strategy_names
        )
        logger.info(f"screening_run event=screener_built active_strategies={self._active_strategy_names}")
        runtime_factor_service = self._build_runtime_factor_service(runtime_config)
        effective_trade_date: Optional[date] = trade_date
        if resume_stage == "factorizing":
            ingest_warnings = list(carried_warnings)
            failed_symbols = list(carried_failed_symbols)
            failed_symbol_reasons = dict(carried_failed_symbol_reasons)
        else:
            ingest_warnings = [trade_date_warning] if trade_date_warning else []
            failed_symbols = list(rerunnable_failed_symbols)
            failed_symbol_reasons = {
                code: reason
                for code, reason in carried_failed_symbol_reasons.items()
                if code in set(rerunnable_failed_symbols)
            }
        sync_warning_summary: Optional[str] = self._join_warning_messages(ingest_warnings)

        try:
            # 全局 deadline：防止任意阶段无限阻塞
            deadline = time.perf_counter() + _EXECUTE_RUN_DEADLINE_SECONDS

            # ── L1 硬开关：大盘 MA100 + 环境判定 → 决定候选上限 ──
            guard_result = None
            market_env = None
            regime_candidate_cap: Optional[int] = None
            decision_context = None
            selected: List[ScreeningCandidateRecord] = []
            if self.config.screening_market_guard_enabled:
                guard = MarketGuard(
                    fetcher_manager=self.market_data_sync_service.fetcher_manager,
                    index_code=self.config.screening_market_guard_index,
                )
                guard_result = guard.check()
                if not guard_result.is_safe:
                    market_guard_msg = (
                        f"⚠️ 大盘情绪低迷，不建议操作 — "
                        f"上证指数 {guard_result.index_price:.2f} "
                        f"低于 MA100 ({guard_result.index_ma100:.2f})，"
                        f"跌幅 {abs(guard_result.index_price - guard_result.index_ma100) / guard_result.index_ma100 * 100:.1f}%"
                    )
                    ingest_warnings.insert(0, market_guard_msg)
                    sync_warning_summary = self._join_warning_messages(ingest_warnings)
                    logger.warning(
                        "screening_run event=market_guard_unsafe %s",
                        guard_result.message,
                    )

                # L1 前置环境评估：根据 regime 决定候选上限
                try:
                    from src.services.market_environment_engine import MarketEnvironmentEngine
                    from src.schemas.trading_types import MarketRegime

                    env_engine = MarketEnvironmentEngine()
                    index_bars = guard.get_index_bars()
                    market_stats = None
                    try:
                        market_stats = self.market_data_sync_service.fetcher_manager.get_market_stats()
                    except Exception:
                        pass
                    market_env = env_engine.assess(guard_result, index_bars, market_stats)
                    regime_candidate_cap = _REGIME_CANDIDATE_CAP.get(
                        market_env.regime,
                    )
                    # defensive → 减半 (至少 2)
                    if regime_candidate_cap is None and market_env.regime.value == "defensive":
                        regime_candidate_cap = max(2, runtime_config.candidate_limit // 2)
                    # stand_aside → 0（已在字典中配置）
                    logger.info(
                        "screening_run event=l1_regime_gate regime=%s cap=%s original_limit=%d",
                        market_env.regime.value, regime_candidate_cap, runtime_config.candidate_limit,
                    )
                except Exception as exc:
                    logger.warning("L1 regime gate failed (degraded, no cap): %s", exc)
            if market_env is None:
                from src.schemas.trading_types import MarketEnvironment, MarketRegime, RiskLevel

                market_env = MarketEnvironment(
                    regime=MarketRegime.BALANCED,
                    risk_level=RiskLevel.MEDIUM,
                    is_safe=True,
                    message="L1 guard disabled or degraded; default to balanced regime",
                )

            current_stage = "resolving_universe"
            self._last_stage_hint = current_stage
            stage_started_at = time.perf_counter()
            universe_df = self._resolve_or_sync_universe(
                run_id=run_id,
                stock_codes=stock_codes,
                market=market,
                update_status=resume_stage != "factorizing",
            )
            if universe_df.empty:
                raise ValueError("股票池为空，无法执行筛选任务")
            resolved_universe_size = len(universe_df.index)
            # 立即写入 universe_size，而非等到最终完成才写入
            # resume_from=factorizing 时跳过，避免多余的 resolving_universe 状态
            if resume_stage != "factorizing":
                self._must_update_status(
                    run_id=run_id,
                    status="resolving_universe",
                    universe_size=resolved_universe_size,
                )
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                universe_size=resolved_universe_size,
            )

            effective_trade_date = (
                resolved_trade_date
                if trade_date is not None
                else runtime_factor_service.get_latest_trade_date(universe_df=universe_df)
            )
            if effective_trade_date is None:
                raise ValueError("未找到可用的本地交易日数据，请先同步日线数据")

            resume_filtered_symbols = carried_failed_symbols if resume_stage == "factorizing" else rerunnable_failed_symbols
            if resume_filtered_symbols:
                universe_df = self._filter_universe_by_codes(
                    universe_df=universe_df,
                    excluded_codes=resume_filtered_symbols,
                )
                ingest_warnings = self._merge_warning_lists(
                    ingest_warnings,
                    [self._build_known_failed_symbol_warning(resume_filtered_symbols)],
                )
                sync_warning_summary = self._join_warning_messages(ingest_warnings)
                if universe_df.empty:
                    raise ValueError("剔除已确认无数据股票后，股票池为空，无法继续筛选")
            if resume_stage != "factorizing":
                self._check_deadline(deadline, "ingesting")
                current_stage = "ingesting"
                self._last_stage_hint = current_stage
                stage_started_at = time.perf_counter()
                self._must_update_status(run_id=run_id, status="ingesting")
                sync_target_total = len(universe_df.index)

                def _sync_heartbeat(synced: int, total: int) -> None:
                    self.db.touch_screening_run_heartbeat(run_id)
                    self._check_deadline(deadline, "ingesting")

                sync_stock_codes = self._resolve_sync_stock_codes(
                    requested_trade_date=requested_trade_date,
                    effective_trade_date=effective_trade_date,
                    stock_codes=stock_codes,
                    rerun_failed=rerun_failed,
                    resume_stage=resume_stage,
                    universe_df=universe_df,
                )
                sync_result = self.market_data_sync_service.sync_trade_date(
                    trade_date=effective_trade_date,
                    stock_codes=sync_stock_codes,
                    force=False,
                    progress_callback=_sync_heartbeat,
                )
                self._log_sync_health_report(run_id=run_id, sync_result=sync_result)
                skippable_sync_errors, blocking_sync_errors = self._partition_sync_errors(sync_result.get("errors", []))
                current_failed_symbols = self._normalize_failed_symbol_codes(skippable_sync_errors)
                if current_failed_symbols:
                    ingest_warnings = self._merge_warning_lists(
                        ingest_warnings,
                        [self._build_skippable_sync_warning_summary(skippable_sync_errors)],
                    )
                    failed_symbols = self._merge_failed_symbols(failed_symbols, current_failed_symbols)
                    failed_symbol_reasons.update(self._build_failed_symbol_reasons(skippable_sync_errors))
                    universe_df = self._filter_universe_by_codes(universe_df=universe_df, excluded_codes=current_failed_symbols)
                sync_failure_ratio = self._calculate_sync_failure_ratio(
                    failure_count=len(current_failed_symbols),
                    total_count=sync_target_total,
                )
                sync_warning_summary = self._join_warning_messages(ingest_warnings)
                self._persist_ingest_context(
                    run_id=run_id,
                    failed_symbols=failed_symbols,
                    failed_symbol_reasons=failed_symbol_reasons,
                    warnings=ingest_warnings,
                    sync_failure_ratio=sync_failure_ratio,
                )
                if blocking_sync_errors:
                    raise ValueError(self._build_sync_error_summary(blocking_sync_errors))
                if universe_df.empty:
                    raise ValueError(
                        self._merge_error_summary(
                            sync_warning_summary,
                            "剔除同步失败股票后，股票池为空，无法继续筛选",
                        )
                    )
                if sync_failure_ratio > self._get_sync_failure_threshold():
                    raise ValueError(
                        self._build_sync_failure_ratio_summary(
                            errors=skippable_sync_errors,
                            failure_ratio=sync_failure_ratio,
                            threshold=self._get_sync_failure_threshold(),
                        )
                    )
                if sync_result["synced"] == 0 and sync_result["skipped"] == 0:
                    raise ValueError("目标交易日无可用日线数据，无法继续筛选")
                self._log_stage_completed(
                    screening_run_id=run_id,
                    stage=current_stage,
                    started_at=stage_started_at,
                    synced=sync_result.get("synced", 0),
                    skipped=sync_result.get("skipped", 0),
                    error_count=len(blocking_sync_errors),
                    ignored_error_count=len(current_failed_symbols),
                    sync_failure_ratio=sync_failure_ratio,
                )
                self._update_run_context(run_id, next_resume_stage="factorizing")

            self._check_deadline(deadline, "factorizing")
            current_stage = "factorizing"
            self._last_stage_hint = current_stage
            stage_started_at = time.perf_counter()
            self._must_update_status(run_id=run_id, status="factorizing")
            snapshot_df = runtime_factor_service.build_factor_snapshot(
                universe_df=universe_df,
                trade_date=effective_trade_date,
                persist=self._should_persist_shared_factor_snapshot(
                    runtime_config=runtime_config,
                    stock_codes=stock_codes,
                ),
            )
            if snapshot_df.empty:
                raise ValueError("未生成可用因子快照，无法继续筛选")
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                snapshot_size=len(snapshot_df.index),
            )
            self._update_run_context(run_id, next_resume_stage="screening")

            self._check_deadline(deadline, "screening")
            current_stage = "screening"
            self._last_stage_hint = current_stage
            stage_started_at = time.perf_counter()
            self._must_update_status(run_id=run_id, status="screening")

            # L1 硬开关: stand_aside → 直接输出 0 候选，跳过选股
            effective_limit = runtime_config.candidate_limit
            if regime_candidate_cap is not None:
                effective_limit = min(effective_limit, regime_candidate_cap)
                logger.info(
                    "screening_run event=regime_cap_applied effective_limit=%d regime=%s",
                    effective_limit,
                    market_env.regime.value if market_env else "unknown",
                )

            if effective_limit == 0:
                # stand_aside: 环境总开关关闭，不执行选股
                selected: List[ScreeningCandidateRecord] = []
                logger.info(
                    "screening_run event=stand_aside_skip reason=regime_cap_zero regime=%s",
                    market_env.regime.value if market_env else "stand_aside",
                )
            elif market_env is not None:
                # ═══ 五层前置管线 (Phase 2 D1/D3/D5) ═══
                from src.services.five_layer_pipeline import FiveLayerPipeline

                pipeline = FiveLayerPipeline()
                pipeline_result = pipeline.run(
                    snapshot_df=snapshot_df,
                    trade_date=effective_trade_date,
                    market_env=market_env,
                    guard_result=guard_result,
                    screener_service=runtime_screener_service,
                    candidate_limit=effective_limit,
                    db_manager=self.db,
                    theme_context=self._theme_context,
                    skill_manager=self._skill_manager,
                )
                selected = pipeline_result.candidates
                decision_context = pipeline_result.decision_context
                logger.info(
                    "screening_run event=five_layer_pipeline_done candidates=%d stats=%s",
                    len(selected), pipeline_result.pipeline_stats,
                )
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                selected_count=len(selected),
                rejected_count=0,
                regime_cap=regime_candidate_cap,
            )

            if decision_context is not None:
                try:
                    self._update_run_context(run_id, decision_context=decision_context)
                except Exception as exc:
                    logger.warning("five_layer: failed to persist decision_context: %s", exc)

            selected = CandidateDecisionBuilder.build_initial(selected)

            # Skip AI enriching for extreme_strength_combo strategy
            ai_results: Dict[str, Dict[str, Any]] = {}
            completion_status = "completed"
            completion_error_summary: Optional[str] = sync_warning_summary

            if strategy_names and strategy_names == ["extreme_strength_combo"]:
                # No AI enriching for hot theme screening
                logger.info("Skipping AI enriching for extreme_strength_combo strategy")
            else:
                self._update_run_context(run_id, next_resume_stage="ai_enriching")

                self._check_deadline(deadline, "ai_enriching")
                current_stage = "ai_enriching"
                self._last_stage_hint = current_stage
                stage_started_at = time.perf_counter()
                self._must_update_status(run_id=run_id, status="ai_enriching")
                try:
                    five_layer_contexts = self._build_five_layer_contexts(selected)
                    ai_batch = self.candidate_analysis_service.analyze_top_k(
                        selected,
                        top_k=runtime_config.ai_top_k,
                        news_top_m=self._resolve_news_top_m(
                            selected_count=len(selected),
                            ai_top_k=runtime_config.ai_top_k,
                        ),
                        five_layer_contexts=five_layer_contexts,
                    )
                    ai_results, failed_codes = self._normalize_ai_batch(ai_batch)
                    if failed_codes:
                        completion_status = "completed_with_ai_degraded"
                        completion_error_summary = self._merge_error_summary(
                            sync_warning_summary,
                            f"AI degraded for: {', '.join(failed_codes)}",
                        )
                except Exception as exc:
                    completion_status = "completed_with_ai_degraded"
                    completion_error_summary = self._merge_error_summary(sync_warning_summary, str(exc))

            candidates = self._build_candidate_payloads(
                selected=selected,
                ai_results=ai_results,
                ai_top_k=runtime_config.ai_top_k,
            )
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                candidate_count=len(candidates),
                ai_result_count=len(ai_results),
                completion_status=completion_status,
            )
            self.db.save_screening_candidates(run_id=run_id, candidates=candidates)
            self._must_update_status(
                run_id=run_id,
                status=completion_status,
                trade_date=effective_trade_date,
                universe_size=len(universe_df.index),
                candidate_count=len(candidates),
                error_summary=completion_error_summary,
            )
            result = self.get_run(run_id) or {
                "run_id": run_id,
                "mode": runtime_config.mode,
                "status": completion_status,
                "universe_size": len(universe_df.index),
                "candidate_count": len(candidates),
            }
            self._log_run_event(
                "run_completed",
                screening_run_id=run_id,
                stage="completed",
                status=completion_status,
                duration_ms=self._duration_ms(run_started_at),
                universe_size=len(universe_df.index),
                candidate_count=len(candidates),
            )
            return result
        except Exception as exc:
            self.db.update_screening_run_status(
                run_id=run_id,
                status="failed",
                trade_date=effective_trade_date,
                error_summary=str(exc),
            )
            failed = self.get_run(run_id) or {
                "run_id": run_id,
                "mode": runtime_config.mode,
                "status": "failed",
            }
            failed["error_summary"] = str(exc)
            self._log_run_failed(
                screening_run_id=run_id,
                stage=self._last_stage_hint or current_stage,
                started_at=run_started_at,
                error_summary=str(exc),
            )
            return failed

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._enrich_run_payload(self._read_run_with_recovery(self.db.get_screening_run(run_id)))

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            item
            for item in (
                self._enrich_run_payload(self._read_run_with_recovery(row))
                for row in self.db.list_screening_runs(limit=limit)
            )
            if item
        ]

    def clear_runs(self) -> int:
        """删除所有筛选历史记录，返回删除数量。"""
        return self.db.clear_screening_runs()

    def delete_run(self, run_id: str) -> bool:
        """删除单条筛选任务及其候选结果。"""
        return self.db.delete_screening_run(run_id)

    def list_candidates(self, run_id: str, limit: int = 100, with_ai_only: bool = False) -> List[Dict[str, Any]]:
        return self.db.list_screening_candidates(run_id=run_id, limit=limit, with_ai_only=with_ai_only)

    def get_candidate_detail(self, run_id: str, code: str) -> Optional[Dict[str, Any]]:
        return self.db.get_screening_candidate_detail(run_id=run_id, code=code)

    def resolve_run_config(
        self,
        mode: Optional[str],
        candidate_limit: Optional[int],
        ai_top_k: Optional[int],
    ) -> ResolvedScreeningRuntimeConfig:
        return resolve_screening_runtime_config(
            config=self.config,
            mode=mode,
            candidate_limit=candidate_limit,
            ai_top_k=ai_top_k,
        )

    def _resolve_or_sync_universe(
        self,
        run_id: str,
        stock_codes: Optional[List[str]],
        market: str,
        update_status: bool = True,
    ) -> Any:
        if update_status:
            self._must_update_status(run_id=run_id, status="resolving_universe")
        try:
            return self.universe_service.resolve_universe(stock_codes=stock_codes)
        except LocalUniverseNotReadyError:
            if stock_codes:
                raise
            if update_status:
                self._last_stage_hint = "syncing_universe"
                self._must_update_status(run_id=run_id, status="syncing_universe")
            self.universe_service.sync_universe(market=market)
            return self.universe_service.resolve_universe(stock_codes=stock_codes)

    @staticmethod
    def _build_candidate_payloads(
        selected: List[Any],
        ai_results: Dict[str, Dict[str, Any]],
        ai_top_k: int,
    ) -> List[Dict[str, Any]]:
        from src.services.ai_review_protocol import AiReviewProtocol

        protocol = AiReviewProtocol()
        normalized = [
            candidate if hasattr(candidate, "to_payload") else CandidateDecisionBuilder.build_initial([candidate])[0]
            for candidate in selected
        ]
        decisions = CandidateDecisionBuilder.attach_ai_reviews(normalized, ai_results, ai_top_k)
        payloads: List[Dict[str, Any]] = []
        for candidate in decisions:
            ai_payload = ai_results.get(candidate.code, {})
            if ai_payload:
                review_fields = _ai_review_fields(protocol, ai_payload, candidate)
                candidate.ai_review = CandidateDecisionBuilder._build_ai_review(
                    {
                        **ai_payload,
                        **review_fields,
                    }
                )
                candidate.has_ai_analysis = True
            payloads.append(candidate.to_payload())
        return payloads

    def _apply_five_layer_decision(
        self,
        selected: List[ScreeningCandidateRecord],
        snapshot_df: Any,
        effective_trade_date: date,
        guard_result: Any = None,
        precomputed_market_env: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """L1→L5 五层决策链路：就地修改 selected 中每个 candidate 的五层字段。

        Returns decision_context dict for L1/L2 snapshot, or None on failure.
        """
        from src.core.market_guard import MarketGuardResult
        from src.schemas.trading_types import (
            MarketRegime,
            SetupType,
            ThemePosition,
        )
        from src.services.market_environment_engine import MarketEnvironmentEngine
        from src.services.sector_heat_engine import SectorHeatEngine
        from src.services.theme_aggregation_service import ThemeAggregationService
        from src.services.theme_position_resolver import ThemePositionResolver
        from src.services.theme_mapping_registry import ThemeMappingRegistry
        from src.services.entry_maturity_assessor import EntryMaturityAssessor
        from src.services.candidate_pool_classifier import CandidatePoolClassifier
        from src.services.trade_stage_judge import TradeStageJudge
        from src.services.strategy_dispatcher import StrategyDispatcher
        from src.services.setup_resolver import SetupResolver
        from src.services.trade_plan_builder import TradePlanBuilder

        if not selected:
            return

        # ── L1: 市场环境 ───────────────────────────────────────────────────
        # 优先使用 execute_run() 中已前置计算的 market_env，避免重复请求
        if precomputed_market_env is not None:
            market_env = precomputed_market_env
            if guard_result is None:
                guard_result = MarketGuardResult(is_safe=market_env.is_safe, message=market_env.message)
        else:
            env_engine = MarketEnvironmentEngine()
            if guard_result is None:
                guard_result = MarketGuardResult(is_safe=True, message="guard disabled")

        # 尝试获取指数日线和市场统计（容错：数据不可用时仍可降级运行）
        if precomputed_market_env is None:
            index_bars = None
            market_stats = None
            try:
                guard = MarketGuard(
                    fetcher_manager=self.market_data_sync_service.fetcher_manager,
                    index_code=self.config.screening_market_guard_index,
                )
                index_bars = guard.get_index_bars()
            except Exception as exc:
                logger.warning("five_layer: failed to fetch index bars: %s", exc)
            try:
                market_stats = self.market_data_sync_service.fetcher_manager.get_market_stats()
            except Exception as exc:
                logger.warning("five_layer: failed to fetch market stats: %s", exc)

            market_env = env_engine.assess(guard_result, index_bars, market_stats)
        logger.info("five_layer L1: regime=%s risk=%s", market_env.regime.value, market_env.risk_level.value)

        # ── L2: 板块热度 + 题材聚合 ────────────────────────────────────────
        sector_results = []
        theme_results = []
        try:
            sector_engine = SectorHeatEngine(db_manager=self.db)
            all_sector_results = sector_engine.compute_all_sectors(snapshot_df, effective_trade_date)

            # L2 过滤：仅保留 hot/warm 板块进入题材聚合管道
            sector_results = [
                s for s in all_sector_results
                if s.sector_status in ("hot", "warm")
            ]
            hot_count = sum(1 for s in sector_results if s.sector_status == "hot")
            warm_count = len(sector_results) - hot_count
            logger.info(
                "five_layer L2: %d sectors computed, %d hot + %d warm passed filter (from %d total)",
                len(sector_results), hot_count, warm_count, len(all_sector_results),
            )
        except Exception as exc:
            logger.warning("five_layer L2 SectorHeatEngine failed (degraded): %s", exc)

        try:
            theme_registry = ThemeMappingRegistry()
            if theme_registry.is_empty:
                logger.warning("five_layer: ThemeMappingRegistry loaded 0 mappings; theme tagging degraded")
        except Exception as exc:
            logger.warning("five_layer ThemeMappingRegistry failed (degraded): %s", exc)
            theme_registry = None

        try:
            agg_service = ThemeAggregationService(registry=theme_registry)
            theme_results = agg_service.aggregate(sector_results)
        except Exception as exc:
            logger.warning("five_layer L2 ThemeAggregation failed (degraded): %s", exc)
            theme_registry = None  # 保持 resolver 与 aggregation 状态一致

        # ── 准备 per-stock 数据 ────────────────────────────────────────────
        all_codes = [c.code for c in selected]
        board_map = self.db.batch_get_instrument_board_names(all_codes)

        theme_resolver = ThemePositionResolver(sector_results, theme_results, self._theme_context, registry=theme_registry)
        maturity_assessor = EntryMaturityAssessor()
        pool_classifier = CandidatePoolClassifier()
        stage_judge = TradeStageJudge()

        # ── Phase 2B: 策略调度器 + 买点收敛器 ──────────────────────────────
        dispatcher: Optional[StrategyDispatcher] = None
        setup_resolver: Optional[SetupResolver] = None
        try:
            strategy_rules = self._get_strategy_rules_for_dispatch()
            if strategy_rules:
                dispatcher = StrategyDispatcher(strategy_rules)
                setup_resolver = SetupResolver(strategy_rules)
        except Exception as exc:
            logger.warning("five_layer: failed to build dispatcher/resolver (degraded): %s", exc)

        # ── Phase 3A: 交易计划生成器 ──────────────────────────────────────────
        plan_builder = TradePlanBuilder()

        # ── 逐票裁决 L2→L5 ────────────────────────────────────────────────
        for candidate in selected:
            fs = candidate.factor_snapshot or {}
            stock_boards = board_map.get(candidate.code, [])

            # L2: 题材地位
            theme_decision = theme_resolver.resolve(stock_boards)
            tp = theme_decision.theme_position

            # Phase 2B: 策略调度 + 买点收敛
            if dispatcher is not None and setup_resolver is not None:
                dispatch_result = dispatcher.filter_strategies(
                    candidate.matched_strategies or [], market_env.regime,
                )
                resolution = setup_resolver.resolve(
                    allowed_strategies=dispatch_result.allowed_strategies,
                    strategy_scores=candidate.strategy_scores or {},
                    market_regime=market_env.regime,
                    theme_position=tp,
                )
                st = resolution.setup_type
                candidate.setup_type = st.value if st != SetupType.NONE else None
                candidate.strategy_family = (
                    resolution.strategy_family.value if resolution.strategy_family else None
                )
                candidate.matched_strategies = dispatch_result.allowed_strategies
            else:
                try:
                    st = SetupType(candidate.setup_type) if candidate.setup_type else SetupType.NONE
                except ValueError:
                    st = SetupType.NONE

            # L4: 买点成熟度
            entry_mat = maturity_assessor.assess(st, fs)

            # L3: 候选池分级
            leader_score = float(fs.get("leader_score", 0.0))
            extreme_strength = float(fs.get("extreme_strength_score", 0.0))
            has_entry_core = st != SetupType.NONE
            pool_level = pool_classifier.classify(
                leader_score=leader_score,
                extreme_strength_score=extreme_strength,
                theme_position=tp,
                market_regime=market_env.regime,
            )

            # L5: 交易阶段裁决
            has_stop = bool(fs.get("has_stop_loss", False))
            trade_stage = stage_judge.judge(
                env=market_env,
                setup_type=st,
                entry_maturity=entry_mat,
                pool_level=pool_level,
                theme_position=tp,
                has_stop_loss=has_stop,
            )

            # Phase 3A: 交易计划生成
            trade_plan = plan_builder.build(
                trade_stage=trade_stage,
                setup_type=st,
                entry_maturity=entry_mat,
                risk_level=market_env.risk_level,
                pool_level=pool_level,
                factor_snapshot=fs,
            )

            # 写回 candidate
            candidate.trade_stage = trade_stage.value
            candidate.market_regime = market_env.regime.value
            candidate.entry_maturity = entry_mat.value
            candidate.candidate_pool_level = pool_level.value
            candidate.theme_position = tp.value
            candidate.risk_level = market_env.risk_level.value
            if trade_plan is not None:
                import json as _json
                candidate.trade_plan_json = _json.dumps(
                    {
                        "initial_position": trade_plan.initial_position,
                        "add_rule": trade_plan.add_rule,
                        "stop_loss_rule": trade_plan.stop_loss_rule,
                        "take_profit_plan": trade_plan.take_profit_plan,
                        "invalidation_rule": trade_plan.invalidation_rule,
                        "risk_level": trade_plan.risk_level.value,
                        "holding_expectation": trade_plan.holding_expectation,
                    },
                    ensure_ascii=False,
                )

        logger.info(
            "five_layer: %d candidates processed, regime=%s",
            len(selected), market_env.regime.value,
        )

        # ── 五层决策后重排序：trade_stage 权重 + rule_score 综合排名 ─────────
        _STAGE_WEIGHT: Dict[str, int] = {
            "add_on_strength": 50,
            "probe_entry": 40,
            "focus": 20,
            "watch": 5,
            "stand_aside": 0,
            "reject": -10,
        }
        _POOL_WEIGHT: Dict[str, int] = {
            "leader_pool": 30,
            "focus_list": 15,
            "watchlist": 0,
        }
        for candidate in selected:
            stage_w = _STAGE_WEIGHT.get(candidate.trade_stage or "", 0)
            pool_w = _POOL_WEIGHT.get(candidate.candidate_pool_level or "", 0)
            candidate.rule_score = candidate.rule_score + stage_w + pool_w
        selected.sort(key=lambda c: c.rule_score, reverse=True)
        for i, candidate in enumerate(selected, 1):
            candidate.rank = i
        logger.info(
            "five_layer rerank: top3 = %s",
            [(c.code, c.rule_score, c.trade_stage, c.theme_position) for c in selected[:3]],
        )

        # ── 构建 decision_context 快照（供前端 L1/L2 展示） ──────────────────
        decision_context: Dict[str, Any] = {
            "market_environment": {
                "market_regime": market_env.regime.value,
                "risk_level": market_env.risk_level.value,
                "index_price": getattr(market_env, "index_price", None),
                "index_ma100": getattr(market_env, "index_ma100", None),
                "is_safe": guard_result.is_safe if guard_result else None,
                "message": guard_result.message if guard_result else None,
            },
            "sector_heat_results": [
                {
                    "board_name": s.board_name,
                    "board_type": s.board_type,
                    "sector_hot_score": s.sector_hot_score,
                    "sector_status": s.sector_status,
                    "sector_stage": s.sector_stage,
                    "canonical_theme": theme_registry.resolve_tag(s.board_name) if theme_registry else s.board_name,
                    "stock_count": s.stock_count,
                    "up_count": s.up_count,
                    "limit_up_count": getattr(s, "limit_up_count", 0),
                }
                for s in sector_results
            ],
            "hot_theme_count": sum(1 for s in sector_results if s.sector_status == "hot"),
            "warm_theme_count": sum(1 for s in sector_results if s.sector_status == "warm"),
        }
        return decision_context

    @staticmethod
    def _build_five_layer_contexts(
        selected: "List[ScreeningCandidateRecord]",
    ) -> Dict[str, str]:
        """将每个候选已有的五层决策字段格式化为 system_context 字符串。

        返回 {stock_code: context_str} 映射，供 AI 二筛使用。
        仅对已填充五层字段的候选生成上下文，其余跳过。
        """
        import json as _json

        ctx_map: Dict[str, str] = {}
        for c in selected:
            if not getattr(c, "trade_stage", None):
                continue

            lines = [
                f"- 市场环境(L1): {getattr(c, 'market_regime', 'N/A')}",
                f"- 风险等级: {getattr(c, 'risk_level', 'N/A')}",
                f"- 题材地位(L2): {getattr(c, 'theme_position', 'N/A')}",
                f"- 候选池(L3): {getattr(c, 'candidate_pool_level', 'N/A')}",
                f"- 买点类型(L4): {getattr(c, 'setup_type', 'N/A') or 'none'}",
                f"- 买点成熟度: {getattr(c, 'entry_maturity', 'N/A')}",
                f"- 交易阶段(L5): {c.trade_stage}",
            ]

            trade_plan_json = getattr(c, "trade_plan_json", None)
            if trade_plan_json:
                try:
                    plan = _json.loads(trade_plan_json)
                    if plan.get("stop_loss_rule"):
                        lines.append(f"- 止损规则: {plan['stop_loss_rule']}")
                    if plan.get("initial_position"):
                        lines.append(f"- 建议仓位: {plan['initial_position']}")
                except (ValueError, TypeError):
                    pass

            matched = getattr(c, "matched_strategies", None)
            if matched:
                lines.append(f"- 匹配策略: {', '.join(matched)}")

            ctx_map[c.code] = "\n".join(lines)
        return ctx_map

    def _get_strategy_rules_for_dispatch(self) -> List:
        """Retrieve strategy rules metadata for Phase 2B dispatch/resolve."""
        from src.services.strategy_screening_engine import build_rules_from_skills

        if self._skill_manager is None:
            return []
        skills = self._skill_manager.get_screening_rules()
        if not skills:
            return []
        return build_rules_from_skills(skills)

    def _should_use_five_layer_pipeline(self) -> bool:
        """五层前置管线已成为唯一主路径。"""
        return True

    @staticmethod
    def _check_deadline(deadline: float, stage: str) -> None:
        """检查全局 deadline，超时则抛出 TimeoutError 终止任务。"""
        if time.perf_counter() > deadline:
            raise TimeoutError(
                f"选股任务全局超时（{_EXECUTE_RUN_DEADLINE_SECONDS // 60} 分钟），"
                f"当前阶段: {stage}"
            )

    @staticmethod
    def _normalize_stock_codes(stock_codes: Optional[List[str]]) -> List[str]:
        return sorted(
            {
                str(code).strip().upper()
                for code in (stock_codes or [])
                if str(code).strip()
            }
        )

    # 各阶段的超时阈值（分钟）：ingesting 涉及全市场数据同步，需要更长时间
    _stage_stale_minutes: Dict[str, int] = {
        "ingesting": 60,
        "syncing_universe": 30,
        "resolving_universe": 10,
        "factorizing": 20,
        "screening": 15,
        "ai_enriching": 30,
    }
    _default_stale_minutes: int = 15

    def _recover_stale_run(self, run: Dict[str, Any], max_stale_minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        检测并回收卡死的幽灵任务。

        优先使用 last_activity_at（心跳）判断是否卡死：
        - 如果有心跳且心跳在阈值内 → 任务仍在运行，不回收
        - 如果无心跳 → 回退到 started_at 判断
        - 各阶段有不同的超时阈值（ingesting 最长，因为涉及全市场同步）
        """
        status = run.get("status", "")
        terminal_statuses = {"completed", "completed_with_ai_degraded", "failed", "cancelled"}
        if status in terminal_statuses:
            return run

        from datetime import datetime

        # 确定超时阈值：优先使用外部传入，否则按阶段查表
        effective_stale_minutes = (
            max_stale_minutes
            if max_stale_minutes is not None
            else self._stage_stale_minutes.get(status, self._default_stale_minutes)
        )

        # 优先使用心跳时间，如果没有则回退到 started_at
        reference_time = run.get("last_activity_at") or run.get("started_at")
        if reference_time is None:
            return run

        if isinstance(reference_time, str):
            try:
                reference_time = datetime.fromisoformat(reference_time)
            except (ValueError, TypeError):
                return run

        elapsed_minutes = (datetime.now() - reference_time).total_seconds() / 60
        if elapsed_minutes <= effective_stale_minutes:
            return run

        run_id = run.get("run_id", "unknown")
        time_source = "心跳" if run.get("last_activity_at") else "启动时间"
        logger.warning(
            f"screening_run event=stale_run_detected run_id={run_id} "
            f"status={status} elapsed_minutes={elapsed_minutes:.1f} "
            f"stale_threshold={effective_stale_minutes} time_source={time_source} "
            f"action=marking_as_failed"
        )
        self.db.update_screening_run_status(
            run_id=run_id,
            status="failed",
            error_summary=(
                f"任务超时：状态 '{status}' 自最近{time_source}已过 {elapsed_minutes:.0f} 分钟"
                f"（阈值 {effective_stale_minutes} 分钟），疑似进程崩溃后遗留"
            ),
        )
        return None

    def _read_run_with_recovery(self, run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(run, dict):
            return None
        recovered = self._recover_stale_run(run)
        if recovered is not None:
            return recovered
        run_id = run.get("run_id")
        if not run_id:
            return None
        refreshed = self.db.get_screening_run(run_id)
        return refreshed if isinstance(refreshed, dict) else None

    @staticmethod
    def _normalize_resume_from(resume_from: Optional[str]) -> Optional[str]:
        if resume_from is None:
            return None
        normalized = str(resume_from).strip().lower()
        if normalized not in {"ingesting", "factorizing"}:
            raise ValueError("resume_from 仅支持 ingesting 或 factorizing")
        return normalized

    @staticmethod
    def _build_run_config_snapshot(
        requested_trade_date: date,
        normalized_stock_codes: List[str],
        runtime_config: ResolvedScreeningRuntimeConfig,
        ingest_failure_threshold: float,
        strategy_names: Optional[List[str]] = None,
        theme_context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        snapshot = {
            "requested_trade_date": requested_trade_date.isoformat(),
            "stock_codes": normalized_stock_codes,
            "screening_ingest_failure_threshold": ingest_failure_threshold,
            **runtime_config.to_snapshot(),
        }
        if strategy_names:
            snapshot["strategy_names"] = sorted(strategy_names)
        if theme_context is not None:
            snapshot["theme_context"] = ScreeningTaskService._serialize_theme_context(theme_context)
            snapshot["normalized_themes"] = ScreeningTaskService._build_initial_normalized_themes(theme_context)
        return snapshot

    @staticmethod
    def _serialize_theme_context(theme_context: Any) -> Dict[str, Any]:
        themes = []
        for theme in getattr(theme_context, "themes", []) or []:
            themes.append(
                {
                    "name": getattr(theme, "name", None),
                    "heat_score": getattr(theme, "heat_score", 0.0),
                    "confidence": getattr(theme, "confidence", 0.0),
                    "catalyst_summary": getattr(theme, "catalyst_summary", None),
                    "keywords": list(getattr(theme, "keywords", []) or []),
                    "evidence": list(getattr(theme, "evidence", []) or []),
                }
            )

        return {
            "source": getattr(theme_context, "source", None),
            "trade_date": getattr(theme_context, "trade_date", None),
            "market": getattr(theme_context, "market", None),
            "accepted_at": getattr(theme_context, "accepted_at", None),
            "themes": themes,
        }

    @staticmethod
    def _build_initial_normalized_themes(theme_context: Any) -> List[Dict[str, Any]]:
        """Build initial normalized theme entries using alias-based normalization.

        Board vocabulary is not available at snapshot time, so this provides
        alias-only normalization. Full recall happens later in FactorService.
        """
        from src.services.theme_normalization_service import ThemeNormalizationService
        normalizer = ThemeNormalizationService()
        results = []
        for theme in getattr(theme_context, "themes", []) or []:
            raw_name = getattr(theme, "name", "") or ""
            keywords = list(getattr(theme, "keywords", []) or [])
            result = normalizer.normalize_theme(raw_theme=raw_name, keywords=keywords)
            results.append(result)
        return results

    @staticmethod
    def _validate_resume_stage(existing_run: Dict[str, Any], resume_stage: Optional[str]) -> None:
        if resume_stage != "factorizing":
            return
        next_resume_stage = (existing_run.get("config_snapshot", {}) or {}).get("next_resume_stage")
        if next_resume_stage not in {"factorizing", "screening", "ai_enriching", "completed"}:
            raise ValueError("resume_from=factorizing 仅支持在日线同步成功后补跑")

    def _update_run_context(self, run_id: str, **config_snapshot_updates: Any) -> None:
        updated = self.db.update_screening_run_context(
            run_id=run_id,
            config_snapshot_updates=config_snapshot_updates,
        )
        if not updated:
            raise RuntimeError("筛选任务上下文更新失败")

    @staticmethod
    def _build_idempotent_run_id(market: str, config_snapshot: Dict[str, Any]) -> str:
        identity_payload = {
            "market": market,
            "config_snapshot": config_snapshot,
        }
        digest = hashlib.sha1(
            json.dumps(identity_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return f"run-{digest[:32]}"

    @staticmethod
    def _resolve_news_top_m(selected_count: int, ai_top_k: int) -> int:
        if selected_count <= 0:
            return 0
        return min(selected_count, max(ai_top_k, min(5, selected_count)))

    @staticmethod
    def _normalize_ai_batch(ai_batch: Any) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
        if isinstance(ai_batch, CandidateAnalysisBatchResult):
            return ai_batch.results, ai_batch.failed_codes
        if isinstance(ai_batch, dict):
            return ai_batch, []
        return {}, []

    def _build_runtime_screener_service(
        self,
        runtime_config: ResolvedScreeningRuntimeConfig,
        strategy_names: Optional[List[str]] = None,
    ) -> ScreenerService:
        if self._custom_screener_service:
            return self.screener_service
        return ScreenerService(
            min_list_days=runtime_config.min_list_days,
            min_volume_ratio=runtime_config.min_volume_ratio,
            min_avg_amount=runtime_config.min_avg_amount,
            breakout_lookback_days=runtime_config.breakout_lookback_days,
            skill_manager=self._skill_manager,
            strategy_names=strategy_names,
        )

    def resolve_active_strategies(
        self,
        mode: str = "balanced",
        strategies: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Determine which strategies to use for screening.

        Returns None to indicate 'use all available strategies'.
        """
        if strategies:
            return strategies
        return None

    def _build_runtime_factor_service(
        self,
        runtime_config: ResolvedScreeningRuntimeConfig,
    ) -> FactorService:
        if self._custom_factor_service:
            return self.factor_service
        return FactorService(
            self.db,
            lookback_days=runtime_config.factor_lookback_days,
            breakout_lookback_days=runtime_config.breakout_lookback_days,
            min_list_days=runtime_config.min_list_days,
            theme_context=getattr(self, '_theme_context', None),
        )

    def _should_persist_shared_factor_snapshot(
        self,
        runtime_config: ResolvedScreeningRuntimeConfig,
        stock_codes: Optional[List[str]],
    ) -> bool:
        return (
            runtime_config.mode == "balanced"
            and not stock_codes
            and not self._custom_factor_service
            and not self._custom_screener_service
        )

    @staticmethod
    def _get_market_now(market: str) -> datetime:
        tz_name = MARKET_TIMEZONE.get(market, "Asia/Shanghai")
        return datetime.now(ZoneInfo(tz_name))

    @classmethod
    def _get_market_today(cls, market: str) -> date:
        return cls._get_market_now(market).date()

    @classmethod
    def _resolve_screening_trade_date(
        cls,
        requested_trade_date: date,
        market: str,
        market_now: Optional[datetime] = None,
    ) -> tuple[date, Optional[str]]:
        resolved_trade_date = requested_trade_date
        warning: Optional[str] = None

        if not is_market_open(market, requested_trade_date):
            resolved_trade_date = cls._find_previous_trading_date(requested_trade_date, market)
            warning = (
                f"所选日期 {requested_trade_date.isoformat()} 非交易日，"
                f"已自动切换到最近交易日 {resolved_trade_date.isoformat()}"
            )

        if market == "cn":
            now_in_market = market_now or cls._get_market_now(market)
            if resolved_trade_date == now_in_market.date() and now_in_market.time() < _CN_MARKET_CLOSE_TIME:
                raise ScreeningTradeDateNotReadyError(
                    "当前时间未到 15:00（Asia/Shanghai），今日 A 股日线数据未完全收盘，请选择上一交易日或 15:00 后再试。"
                )

        return resolved_trade_date, warning

    @staticmethod
    def _find_previous_trading_date(anchor_date: date, market: str) -> date:
        candidate = anchor_date - timedelta(days=1)
        for _ in range(366):
            if is_market_open(market, candidate):
                return candidate
            candidate -= timedelta(days=1)
        raise ValueError(f"无法为 {anchor_date.isoformat()} 找到最近交易日")

    @staticmethod
    def _resolve_sync_stock_codes(
        requested_trade_date: date,
        effective_trade_date: date,
        stock_codes: Optional[List[str]],
        rerun_failed: bool,
        resume_stage: Optional[str],
        universe_df: Any,
    ) -> Optional[List[str]]:
        # For a manual full-market run targeting today, let the sync service
        # drive its own full-universe batch sync instead of enumerating symbols.
        if (
            not stock_codes
            and not rerun_failed
            and resume_stage != "factorizing"
            and requested_trade_date == ScreeningTaskService._get_market_today("cn")
            and effective_trade_date == requested_trade_date
        ):
            return None
        if universe_df is None or getattr(universe_df, "empty", True):
            return []
        return universe_df["code"].tolist()

    @staticmethod
    def _build_sync_error_summary(errors: List[Dict[str, Any]]) -> str:
        parts = []
        for item in errors[:10]:
            code = item.get("code", "unknown")
            detail = item.get("detail")
            reason = detail or item.get("reason", "unknown")
            parts.append(f"{code}: {reason}")
        suffix = " ..." if len(errors) > 10 else ""
        return f"目标交易日日线同步存在失败记录: {'; '.join(parts)}{suffix}"

    @staticmethod
    def _build_ignored_sync_error_summary(errors: List[Dict[str, Any]]) -> str:
        codes = [str(item.get("code", "unknown")).strip().upper() for item in errors[:10]]
        suffix = " ..." if len(errors) > 10 else ""
        return f"已忽略退市股票同步失败: {', '.join(codes)}{suffix}"

    @classmethod
    def _partition_sync_errors(cls, errors: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not errors:
            return [], []
        skippable: List[Dict[str, Any]] = []
        blocking: List[Dict[str, Any]] = []
        for item in errors:
            if cls._is_skippable_sync_error(item):
                skippable.append(item)
            else:
                blocking.append(item)
        return skippable, blocking

    @staticmethod
    def _is_skippable_sync_error(error: Dict[str, Any]) -> bool:
        reason = str(error.get("reason", "")).strip().lower()
        return reason in {"empty_data", "no_data", "not_found", "fetch_failed"}

    @staticmethod
    def _is_rerunnable_failed_symbol_reason(reason: str) -> bool:
        return str(reason or "").strip().lower() in {"empty_data", "no_data", "not_found"}

    @staticmethod
    def _normalize_failed_symbol_codes(errors: List[Dict[str, Any]]) -> List[str]:
        return list(
            dict.fromkeys(
                str(item.get("code", "")).strip().upper()
                for item in errors
                if str(item.get("code", "")).strip()
            )
        )

    @staticmethod
    def _merge_failed_symbols(existing: List[str], incoming: List[str]) -> List[str]:
        return list(dict.fromkeys([*existing, *incoming]))

    @staticmethod
    def _merge_warning_lists(existing: List[str], incoming: List[str]) -> List[str]:
        return list(dict.fromkeys([item for item in [*existing, *incoming] if item]))

    @staticmethod
    def _join_warning_messages(warnings: List[str]) -> Optional[str]:
        if not warnings:
            return None
        return "; ".join(warnings)

    @staticmethod
    def _filter_universe_by_codes(universe_df: Any, excluded_codes: List[str]) -> Any:
        if universe_df is None or getattr(universe_df, "empty", True) or not excluded_codes:
            return universe_df
        normalized_codes = {str(code).strip().upper() for code in excluded_codes if str(code).strip()}
        return universe_df[~universe_df["code"].astype(str).str.upper().isin(normalized_codes)].reset_index(drop=True)

    @staticmethod
    def _build_skippable_sync_warning_summary(errors: List[Dict[str, Any]]) -> str:
        codes = ScreeningTaskService._normalize_failed_symbol_codes(errors[:10])
        suffix = " ..." if len(errors) > 10 else ""
        return f"已跳过同步失败股票: {', '.join(codes)}{suffix}"

    @staticmethod
    def _build_known_failed_symbol_warning(codes: List[str]) -> str:
        normalized_codes = [str(code).strip().upper() for code in codes[:10] if str(code).strip()]
        suffix = " ..." if len(codes) > 10 else ""
        return f"补跑跳过已确认无数据股票: {', '.join(normalized_codes)}{suffix}"

    @staticmethod
    def _calculate_sync_failure_ratio(failure_count: int, total_count: int) -> float:
        if total_count <= 0 or failure_count <= 0:
            return 0.0
        return failure_count / total_count

    def _get_sync_failure_threshold(self) -> float:
        return float(getattr(self.config, "screening_ingest_failure_threshold", 0.20))

    @staticmethod
    def _build_sync_failure_ratio_summary(errors: List[Dict[str, Any]], failure_ratio: float, threshold: float) -> str:
        details = []
        for item in errors[:10]:
            code = str(item.get("code", "unknown")).strip().upper() or "unknown"
            reason = item.get("detail") or item.get("reason") or "unknown"
            details.append(f"{code}: {reason}")
        symbol_preview = "; ".join(details) if details else "unknown"
        suffix = " ..." if len(errors) > 10 else ""
        return (
            f"同步失败比例 {failure_ratio:.1%} 超过阈值 {threshold:.1%}: "
            f"{symbol_preview}{suffix}"
        )

    def _persist_ingest_context(
        self,
        run_id: str,
        failed_symbols: List[str],
        failed_symbol_reasons: Dict[str, str],
        warnings: List[str],
        sync_failure_ratio: float,
    ) -> None:
        self._update_run_context(
            run_id,
            failed_symbols=failed_symbols,
            failed_symbol_reasons=failed_symbol_reasons,
            warnings=warnings,
            sync_failure_ratio=round(sync_failure_ratio, 4),
        )

    @staticmethod
    def _extract_failed_symbols(run_payload: Optional[Dict[str, Any]]) -> List[str]:
        snapshot = (run_payload or {}).get("config_snapshot", {}) or {}
        return [
            str(code).strip().upper()
            for code in (snapshot.get("failed_symbols") or [])
            if str(code).strip()
        ]

    @staticmethod
    def _extract_failed_symbol_reasons(run_payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
        snapshot = (run_payload or {}).get("config_snapshot", {}) or {}
        reason_map = snapshot.get("failed_symbol_reasons") or {}
        if not isinstance(reason_map, dict):
            return {}
        return {
            str(code).strip().upper(): str(reason).strip().lower()
            for code, reason in reason_map.items()
            if str(code).strip() and str(reason).strip()
        }

    @classmethod
    def _extract_rerunnable_failed_symbols(cls, run_payload: Optional[Dict[str, Any]]) -> List[str]:
        reason_map = cls._extract_failed_symbol_reasons(run_payload)
        return [
            code
            for code, reason in reason_map.items()
            if cls._is_rerunnable_failed_symbol_reason(reason)
        ]

    @staticmethod
    def _build_failed_symbol_reasons(errors: List[Dict[str, Any]]) -> Dict[str, str]:
        return {
            str(item.get("code", "")).strip().upper(): str(item.get("reason", "")).strip().lower()
            for item in errors
            if str(item.get("code", "")).strip() and str(item.get("reason", "")).strip()
        }

    @staticmethod
    def _extract_warnings(run_payload: Optional[Dict[str, Any]]) -> List[str]:
        snapshot = (run_payload or {}).get("config_snapshot", {}) or {}
        return [str(item).strip() for item in (snapshot.get("warnings") or []) if str(item).strip()]

    @staticmethod
    def _enrich_run_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None
        snapshot = payload.get("config_snapshot", {}) or {}
        enriched = dict(payload)
        enriched["failed_symbols"] = [
            str(code).strip().upper()
            for code in (snapshot.get("failed_symbols") or [])
            if str(code).strip()
        ]
        enriched["warnings"] = [str(item).strip() for item in (snapshot.get("warnings") or []) if str(item).strip()]
        enriched["sync_failure_ratio"] = float(snapshot.get("sync_failure_ratio") or 0.0)
        enriched["strategy_names"] = snapshot.get("strategy_names")
        # 五层决策上下文快照（L1/L2）
        enriched["decision_context"] = snapshot.get("decision_context")
        return enriched

    @staticmethod
    def _is_ignorable_sync_error(error: Dict[str, Any], instrument: Dict[str, Any]) -> bool:
        if not instrument:
            return False
        reason = str(error.get("reason", "")).strip().lower()
        if reason not in {"empty_data", "no_data", "not_found"}:
            return False
        listing_status = str(instrument.get("listing_status", "")).strip().lower()
        if ScreeningTaskService._is_delisted_listing_status(listing_status):
            return True
        name = str(instrument.get("name", "")).strip().upper()
        return (
            name.endswith("退")
            or "退市" in name
            or "DELISTED" in name
            or "DELIST" in name
        )

    @staticmethod
    def _is_delisted_listing_status(listing_status: str) -> bool:
        if not listing_status:
            return False
        normalized = listing_status.strip().lower()
        if normalized in {"delisted", "terminated", "terminated_listing"}:
            return True
        return "delist" in normalized or "退市" in normalized or "终止上市" in normalized

    @staticmethod
    def _merge_error_summary(primary: Optional[str], secondary: Optional[str]) -> Optional[str]:
        parts = [item for item in [primary, secondary] if item]
        if not parts:
            return None
        return "; ".join(parts)

    def _must_update_status(self, run_id: str, status: str, **kwargs: Any) -> None:
        updated = self.db.update_screening_run_status(run_id=run_id, status=status, **kwargs)
        if not updated:
            raise RuntimeError(f"筛选任务状态更新失败: {status}")

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))

    @staticmethod
    def _format_log_fields(**fields: Any) -> str:
        parts = []
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, str):
                safe_value = value
                if not value.replace("_", "").replace("-", "").replace(":", "").replace(".", "").isalnum():
                    safe_value = quote(value, safe="")
                parts.append(f"{key}={safe_value}")
                continue
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False, default=str)}")
        return " ".join(parts)

    def _log_run_event(self, event: str, **fields: Any) -> None:
        logger.info("screening_run event=%s %s", event, self._format_log_fields(**fields))

    def _log_stage_completed(self, screening_run_id: str, stage: str, started_at: float, **fields: Any) -> None:
        logger.info(
            "screening_run event=stage_completed %s",
            self._format_log_fields(
                screening_run_id=screening_run_id,
                stage=stage,
                duration_ms=self._duration_ms(started_at),
                **fields,
            ),
        )

    def _log_sync_health_report(self, run_id: str, sync_result: Dict[str, Any]) -> None:
        health_report = sync_result.get("health_report") or {}
        if not health_report:
            return
        logger.info(
            "screening_run event=health_report %s",
            self._format_log_fields(
                screening_run_id=run_id,
                stage="ingesting",
                health_summary=health_report.get("summary"),
                health_success_rate=health_report.get("success_rate"),
                missing_count=health_report.get("missing_count"),
                error_count=health_report.get("error_count"),
            ),
        )

    def _log_run_failed(self, screening_run_id: str, stage: str, started_at: float, error_summary: str) -> None:
        logger.error(
            "screening_run event=run_failed %s",
            self._format_log_fields(
                screening_run_id=screening_run_id,
                stage=stage,
                duration_ms=self._duration_ms(started_at),
                error=error_summary,
            ),
        )
