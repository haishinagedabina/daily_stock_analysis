from __future__ import annotations

import hashlib
import json
import logging
import time
from urllib.parse import quote
from datetime import date
from typing import Any, Dict, List, Optional

from src.config import get_config
from src.services.candidate_analysis_service import CandidateAnalysisService
from src.services.candidate_analysis_service import CandidateAnalysisBatchResult
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
        self.candidate_analysis_service = candidate_analysis_service or CandidateAnalysisService()
        self.market_data_sync_service = market_data_sync_service or MarketDataSyncService(self.db)

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
    ) -> Dict[str, Any]:
        current_stage = "initializing"
        self._last_stage_hint = current_stage
        run_started_at = time.perf_counter()
        normalized_stock_codes = self._normalize_stock_codes(stock_codes)
        runtime_config = self.resolve_run_config(mode=mode, candidate_limit=candidate_limit, ai_top_k=ai_top_k)
        if runtime_config.ai_top_k > runtime_config.candidate_limit:
            raise ValueError("ai_top_k 不能大于 candidate_limit")
        if runtime_config.mode != "balanced" and (self._custom_screener_service or self._custom_factor_service):
            raise ValueError("自定义注入的筛选服务不支持非 balanced mode，请改为使用默认服务构建")
        requested_trade_date = trade_date or date.today()
        run_snapshot = self._build_run_config_snapshot(
            requested_trade_date=requested_trade_date,
            normalized_stock_codes=normalized_stock_codes,
            runtime_config=runtime_config,
            ingest_failure_threshold=float(getattr(self.config, "screening_ingest_failure_threshold", 0.02)),
        )
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
            else:
                return existing_run
        else:
            if resume_stage is not None:
                raise ValueError("resume_from 仅支持失败任务补跑")
            create_result = self.db.create_screening_run(
                trade_date=requested_trade_date,
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
        runtime_screener_service = self._build_runtime_screener_service(runtime_config)
        runtime_factor_service = self._build_runtime_factor_service(runtime_config)
        effective_trade_date: Optional[date] = trade_date
        if resume_stage == "factorizing":
            ingest_warnings = list(carried_warnings)
            failed_symbols = list(carried_failed_symbols)
            failed_symbol_reasons = dict(carried_failed_symbol_reasons)
        else:
            ingest_warnings = []
            failed_symbols = list(rerunnable_failed_symbols)
            failed_symbol_reasons = {
                code: reason
                for code, reason in carried_failed_symbol_reasons.items()
                if code in set(rerunnable_failed_symbols)
            }
        sync_warning_summary: Optional[str] = self._join_warning_messages(ingest_warnings)

        try:
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
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                universe_size=len(universe_df.index),
            )

            effective_trade_date = trade_date or runtime_factor_service.get_latest_trade_date(universe_df=universe_df)
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
                current_stage = "ingesting"
                self._last_stage_hint = current_stage
                stage_started_at = time.perf_counter()
                self._must_update_status(run_id=run_id, status="ingesting")
                sync_target_total = len(universe_df.index)
                sync_result = self.market_data_sync_service.sync_trade_date(
                    trade_date=effective_trade_date,
                    stock_codes=universe_df["code"].tolist(),
                    force=False,
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

            current_stage = "screening"
            self._last_stage_hint = current_stage
            stage_started_at = time.perf_counter()
            self._must_update_status(run_id=run_id, status="screening")
            evaluation = runtime_screener_service.evaluate(snapshot_df)
            selected = evaluation.selected[: runtime_config.candidate_limit]
            self._log_stage_completed(
                screening_run_id=run_id,
                stage=current_stage,
                started_at=stage_started_at,
                selected_count=len(selected),
                rejected_count=len(getattr(evaluation, "rejected", []) or []),
            )
            self._update_run_context(run_id, next_resume_stage="ai_enriching")

            current_stage = "ai_enriching"
            self._last_stage_hint = current_stage
            stage_started_at = time.perf_counter()
            self._must_update_status(run_id=run_id, status="ai_enriching")
            ai_results: Dict[str, Dict[str, Any]] = {}
            completion_status = "completed"
            completion_error_summary: Optional[str] = sync_warning_summary
            try:
                ai_batch = self.candidate_analysis_service.analyze_top_k(
                    selected,
                    top_k=runtime_config.ai_top_k,
                    news_top_m=self._resolve_news_top_m(
                        selected_count=len(selected),
                        ai_top_k=runtime_config.ai_top_k,
                    ),
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
        return self._enrich_run_payload(self.db.get_screening_run(run_id))

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [item for item in (self._enrich_run_payload(row) for row in self.db.list_screening_runs(limit=limit)) if item]

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
        selected: List[ScreeningCandidateRecord],
        ai_results: Dict[str, Dict[str, Any]],
        ai_top_k: int,
    ) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        for candidate in selected:
            if isinstance(candidate, dict):
                code = candidate["code"]
                name = candidate.get("name")
                rank = int(candidate.get("rank", 0))
                rule_score = float(candidate.get("rule_score", 0.0))
                rule_hits = candidate.get("rule_hits", [])
                factor_snapshot = candidate.get("factor_snapshot", {})
            else:
                code = candidate.code
                name = candidate.name
                rank = candidate.rank
                rule_score = candidate.rule_score
                rule_hits = candidate.rule_hits
                factor_snapshot = candidate.factor_snapshot

            ai_payload = ai_results.get(code, {})
            payloads.append(
                {
                    "code": code,
                    "name": name,
                    "rank": rank,
                    "rule_score": rule_score,
                    "selected_for_ai": rank <= ai_top_k,
                    "rule_hits": rule_hits,
                    "factor_snapshot": factor_snapshot,
                    "ai_query_id": ai_payload.get("ai_query_id"),
                    "ai_summary": ai_payload.get("ai_summary"),
                    "ai_operation_advice": ai_payload.get("ai_operation_advice"),
                }
            )
        return payloads

    @staticmethod
    def _normalize_stock_codes(stock_codes: Optional[List[str]]) -> List[str]:
        return sorted(
            {
                str(code).strip().upper()
                for code in (stock_codes or [])
                if str(code).strip()
            }
        )

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
    ) -> Dict[str, Any]:
        snapshot = {
            "requested_trade_date": requested_trade_date.isoformat(),
            "stock_codes": normalized_stock_codes,
            "screening_ingest_failure_threshold": ingest_failure_threshold,
            **runtime_config.to_snapshot(),
        }
        return snapshot

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
        return float(getattr(self.config, "screening_ingest_failure_threshold", 0.02))

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
