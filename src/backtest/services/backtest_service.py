# -*- coding: utf-8 -*-
"""Five-layer backtest service — orchestration layer.

Pipeline: select_candidates → classify → get_forward_bars →
resolve_execution → evaluate → save_evaluations → update_run.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from src.backtest.aggregators.calibration_output_generator import CalibrationOutputGenerator
from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
from src.backtest.aggregators.system_grader import SystemGrader
from src.backtest.classifiers.signal_classifier import SignalClassifier
from src.backtest.evaluators.entry_evaluator import EntrySignalEvaluator
from src.backtest.evaluators.observation_evaluator import ObservationSignalEvaluator
from src.backtest.execution.execution_model_resolver import ExecutionModelResolver
from src.backtest.models.backtest_models import (
    FiveLayerBacktestCalibrationOutput,
    FiveLayerBacktestEvaluation,
    FiveLayerBacktestGroupSummary,
    FiveLayerBacktestRecommendation,
    FiveLayerBacktestRun,
)
from src.backtest.recommendations.recommendation_engine import RecommendationEngine
from src.backtest.repositories.calibration_repo import CalibrationRepository
from src.backtest.repositories.evaluation_repo import EvaluationRepository
from src.backtest.repositories.recommendation_repo import RecommendationRepository
from src.backtest.repositories.run_repo import RunRepository
from src.backtest.repositories.summary_repo import SummaryRepository
from src.backtest.services.candidate_selector import CandidateSelector
from src.backtest.services.sample_bucket_service import SampleBucketService
from src.backtest.utils.summary_metrics import get_aggregatable_sample_count
from src.repositories.stock_repo import StockRepository
from src.schemas.trading_types import (
    CandidatePoolLevel,
    EntryMaturity,
    MarketEnvironment,
    MarketRegime,
    RiskLevel,
    SetupType,
    ThemePosition,
    TradeStage,
)
from src.services.trade_stage_judge import TradeStageJudge
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

_DEFAULT_EVAL_WINDOW = 10
_ENTRY_SIGNAL_STAGES = frozenset({TradeStage.PROBE_ENTRY.value, TradeStage.ADD_ON_STRENGTH.value})
_LOW123_CONSERVATIVE_REJECTION = "confirmed_missing_breakout_bar_index"


def _dump_json(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def _build_run_sample_baseline(
    raw_candidate_count: int,
    evaluations: List[FiveLayerBacktestEvaluation],
) -> Dict[str, Any]:
    """Build run-level sample baseline without requiring schema changes."""
    entry_count = sum(1 for item in evaluations if item.signal_family == "entry")
    observation_count = sum(1 for item in evaluations if item.signal_family == "observation")
    suppressed_reasons: Dict[str, int] = {}
    aggregatable_count = 0

    for evaluation in evaluations:
        if evaluation.forward_return_5d is not None or evaluation.risk_avoided_pct is not None:
            aggregatable_count += 1
            continue
        if evaluation.signal_family == "observation":
            reason = "missing_risk_avoided_pct"
        elif evaluation.signal_family == "entry":
            reason = "missing_forward_return_5d"
        else:
            reason = "missing_primary_metric"
        suppressed_reasons[reason] = suppressed_reasons.get(reason, 0) + 1

    return {
        "raw_sample_count": raw_candidate_count,
        "evaluated_sample_count": len(evaluations),
        "aggregatable_sample_count": aggregatable_count,
        "entry_sample_count": entry_count,
        "observation_sample_count": observation_count,
        "suppressed_sample_count": len(evaluations) - aggregatable_count,
        "suppressed_reasons": suppressed_reasons,
    }


def _parse_enum_value(enum_cls: type, raw_value: Any):
    if raw_value is None:
        return None
    try:
        return enum_cls(str(raw_value))
    except ValueError:
        return None


def _has_stop_loss_anchor(trade_plan: Any) -> bool:
    if not isinstance(trade_plan, dict):
        return False
    return trade_plan.get("stop_loss") is not None or bool(trade_plan.get("stop_loss_rule"))


class FiveLayerBacktestService:
    """Orchestrates a five-layer backtest run."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()
        self.run_repo = RunRepository(self.db)
        self.eval_repo = EvaluationRepository(self.db)
        self.summary_repo = SummaryRepository(self.db)
        self.calibration_repo = CalibrationRepository(self.db)
        self.recommendation_repo = RecommendationRepository(self.db)
        self.candidate_selector = CandidateSelector(self.db)
        self.stock_repo = StockRepository(self.db)
        self.aggregator = GroupSummaryAggregator(self.eval_repo, self.summary_repo)
        self.recommendation_engine = RecommendationEngine(
            self.summary_repo, self.eval_repo, self.recommendation_repo,
        )
        self.trade_stage_judge = TradeStageJudge()

    def create_run(
        self,
        evaluation_mode: str,
        execution_model: str,
        trade_date_from: date,
        trade_date_to: date,
        market: str = "cn",
        **kwargs,
    ) -> FiveLayerBacktestRun:
        backtest_run_id = f"flbt-{uuid.uuid4().hex[:12]}"
        return self.run_repo.create_run(
            backtest_run_id=backtest_run_id,
            evaluation_mode=evaluation_mode,
            execution_model=execution_model,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            market=market,
            **kwargs,
        )

    def get_run(self, backtest_run_id: str) -> Optional[FiveLayerBacktestRun]:
        return self.run_repo.get_run(backtest_run_id)

    def run_backtest(
        self,
        evaluation_mode: str,
        execution_model: str,
        trade_date_from: date,
        trade_date_to: date,
        market: str = "cn",
        eval_window_days: int = _DEFAULT_EVAL_WINDOW,
        **kwargs,
    ) -> FiveLayerBacktestRun:
        """Full pipeline across a date range: selects all candidates in
        [trade_date_from, trade_date_to], evaluates each, and saves results.
        """
        candidates = self.candidate_selector.select_candidates_by_date_range(
            date_from=trade_date_from,
            date_to=trade_date_to,
            market=market,
        )

        run = self.create_run(
            evaluation_mode=evaluation_mode,
            execution_model=execution_model,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            market=market,
            **kwargs,
        )

        if not candidates:
            self.run_repo.update_run_status(
                run.backtest_run_id,
                status="completed",
                sample_count=0,
                completed_count=0,
                error_count=0,
                completed_at=datetime.now(),
            )
            return self.run_repo.get_run(run.backtest_run_id)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="running",
            sample_count=len(candidates),
            started_at=datetime.now(),
        )

        evaluations, error_count = self._evaluate_candidates(
            run=run,
            candidates=candidates,
            execution_model=execution_model,
            evaluation_mode=evaluation_mode,
            eval_window_days=eval_window_days,
        )

        sample_baseline = _build_run_sample_baseline(len(candidates), evaluations)
        if evaluations:
            self.eval_repo.save_batch(evaluations)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="completed",
            sample_count=len(candidates),
            completed_count=len(evaluations),
            error_count=error_count,
            config_json=_dump_json({"sample_baseline": sample_baseline}),
            completed_at=datetime.now(),
        )

        return self.run_repo.get_run(run.backtest_run_id)

    def run_backtest_pipeline(
        self,
        screening_run_id: str,
        evaluation_mode: str,
        execution_model: str,
        market: str = "cn",
        eval_window_days: int = _DEFAULT_EVAL_WINDOW,
    ) -> FiveLayerBacktestRun:
        """Full pipeline: candidates → classify → execute → evaluate → save."""
        # 1. Select candidates
        candidates = self.candidate_selector.select_candidates(screening_run_id)

        # Derive date range from candidates
        trade_dates = [c["trade_date"] for c in candidates if c.get("trade_date")]
        trade_date_from = min(trade_dates) if trade_dates else date.today()
        trade_date_to = max(trade_dates) if trade_dates else date.today()

        # 2. Create run
        run = self.create_run(
            evaluation_mode=evaluation_mode,
            execution_model=execution_model,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            market=market,
        )

        if not candidates:
            self.run_repo.update_run_status(
                run.backtest_run_id,
                status="completed",
                sample_count=0,
                completed_count=0,
                error_count=0,
                completed_at=datetime.now(),
            )
            return self.run_repo.get_run(run.backtest_run_id)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="running",
            sample_count=len(candidates),
            started_at=datetime.now(),
        )

        evaluations, error_count = self._evaluate_candidates(
            run=run,
            candidates=candidates,
            execution_model=execution_model,
            evaluation_mode=evaluation_mode,
            eval_window_days=eval_window_days,
        )

        sample_baseline = _build_run_sample_baseline(len(candidates), evaluations)
        if evaluations:
            self.eval_repo.save_batch(evaluations)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="completed",
            sample_count=len(candidates),
            completed_count=len(evaluations),
            error_count=error_count,
            config_json=_dump_json({"sample_baseline": sample_baseline}),
            completed_at=datetime.now(),
        )

        return self.run_repo.get_run(run.backtest_run_id)

    def _evaluate_candidates(
        self,
        run: FiveLayerBacktestRun,
        candidates: List[Dict[str, Any]],
        execution_model: str,
        evaluation_mode: str,
        eval_window_days: int,
    ) -> tuple:
        """Process all candidates. Returns (evaluations_list, error_count)."""
        evaluations: List[FiveLayerBacktestEvaluation] = []
        error_count = 0

        for candidate in candidates:
            try:
                evaluation = self._process_candidate(
                    run=run,
                    candidate=candidate,
                    execution_model=execution_model,
                    evaluation_mode=evaluation_mode,
                    eval_window_days=eval_window_days,
                )
                evaluations.append(evaluation)
            except Exception:
                error_count += 1
                logger.exception(
                    "Failed to evaluate candidate %s", candidate.get("code"),
                )

        return evaluations, error_count

    def _process_candidate(
        self,
        run: FiveLayerBacktestRun,
        candidate: Dict[str, Any],
        execution_model: str,
        evaluation_mode: str,
        eval_window_days: int,
    ) -> FiveLayerBacktestEvaluation:
        """Process a single candidate through classify → execute → evaluate."""
        trade_date = candidate["trade_date"]
        code = candidate["code"]
        effective_trade_stage = self._resolve_backtest_trade_stage(candidate)

        # Classify signal
        has_exit_plan = False
        trade_plan = candidate.get("trade_plan")
        if trade_plan and isinstance(trade_plan, dict):
            has_exit_plan = bool(trade_plan.get("exit_signal"))

        classification = SignalClassifier.classify(
            trade_stage=effective_trade_stage,
            ai_trade_stage=candidate.get("ai_trade_stage"),
            ai_confidence=candidate.get("ai_confidence"),
            has_exit_plan=has_exit_plan,
        )

        # Get forward bars
        forward_bars = self.stock_repo.get_forward_bars(
            code=code,
            analysis_date=trade_date,
            eval_window_days=eval_window_days,
        )

        # Build evaluation record
        evaluation = FiveLayerBacktestEvaluation(
            backtest_run_id=run.backtest_run_id,
            screening_run_id=candidate.get("screening_run_id"),
            screening_candidate_id=candidate.get("screening_candidate_id"),
            trade_date=trade_date,
            code=code,
            name=candidate.get("name"),
            evaluation_mode=evaluation_mode,
            signal_family=classification.signal_family,
            signal_type=classification.effective_trade_stage,
            evaluator_type=classification.evaluator_type,
            execution_model=execution_model,
            snapshot_source="screening_candidate",
            eval_status="evaluated",
        )

        # Snapshot fields (historical_snapshot mode)
        evaluation.snapshot_trade_stage = candidate.get("trade_stage")
        evaluation.snapshot_setup_type = candidate.get("setup_type")
        evaluation.snapshot_entry_maturity = candidate.get("entry_maturity")
        evaluation.snapshot_market_regime = candidate.get("market_regime")
        evaluation.snapshot_theme_position = candidate.get("theme_position")
        evaluation.snapshot_candidate_pool_level = candidate.get("candidate_pool_level")
        evaluation.snapshot_risk_level = candidate.get("risk_level")
        evaluation.factor_snapshot_json = _dump_json(candidate.get("factor_snapshot"))
        evaluation.trade_plan_json = _dump_json(candidate.get("trade_plan"))
        evaluation.evidence_json = _dump_json(
            {
                "matched_strategies": candidate.get("matched_strategies", []),
                "rule_hits": candidate.get("rule_hits", []),
                "primary_strategy": candidate.get("primary_strategy"),
                "contributing_strategies": candidate.get("contributing_strategies", []),
                "strategy_scores": candidate.get("strategy_scores", {}),
                "ai_trade_stage": candidate.get("ai_trade_stage"),
                "ai_confidence": candidate.get("ai_confidence"),
            },
        )

        # Replayed fields stay NULL in historical_snapshot mode

        # Execute + evaluate based on signal family
        if classification.signal_family == "entry":
            self._evaluate_entry(evaluation, forward_bars, execution_model, candidate)
        elif classification.signal_family == "observation":
            self._evaluate_observation(evaluation, forward_bars)
        # exit: framework only, no metrics yet

        evaluation.metrics_json = _dump_json(
            self._build_metrics_payload(
                candidate=candidate,
                evaluation=evaluation,
                classification=classification,
            ),
        )

        return evaluation

    def _resolve_backtest_trade_stage(self, candidate: Dict[str, Any]) -> Optional[str]:
        """Recover a usable rule-stage from snapshot fields when persisted stage is overly conservative."""
        persisted_stage = str(candidate.get("trade_stage") or "").lower() or None
        if persisted_stage in _ENTRY_SIGNAL_STAGES:
            return persisted_stage

        factor_snapshot = candidate.get("factor_snapshot")
        if not isinstance(factor_snapshot, dict):
            factor_snapshot = {}

        if factor_snapshot.get("ma100_low123_validation_status") == _LOW123_CONSERVATIVE_REJECTION:
            return persisted_stage

        regime = _parse_enum_value(MarketRegime, candidate.get("market_regime"))
        setup_type = _parse_enum_value(SetupType, candidate.get("setup_type"))
        entry_maturity = _parse_enum_value(EntryMaturity, candidate.get("entry_maturity"))
        pool_level = _parse_enum_value(
            CandidatePoolLevel,
            candidate.get("candidate_pool_level"),
        )
        theme_position = _parse_enum_value(ThemePosition, candidate.get("theme_position"))
        risk_level = _parse_enum_value(RiskLevel, candidate.get("risk_level")) or RiskLevel.MEDIUM

        if None in (regime, setup_type, entry_maturity, pool_level, theme_position):
            return persisted_stage

        derived_stage = self.trade_stage_judge.judge(
            env=MarketEnvironment(regime=regime, risk_level=risk_level),
            setup_type=setup_type,
            entry_maturity=entry_maturity,
            pool_level=pool_level,
            theme_position=theme_position,
            has_stop_loss=_has_stop_loss_anchor(candidate.get("trade_plan")),
        ).value

        if derived_stage in _ENTRY_SIGNAL_STAGES:
            return TradeStage.PROBE_ENTRY.value

        return persisted_stage

    def _evaluate_entry(
        self,
        evaluation: FiveLayerBacktestEvaluation,
        forward_bars: List[Any],
        execution_model: str,
        candidate: Dict[str, Any],
    ) -> None:
        """Fill entry execution + evaluation metrics."""
        trade_plan = candidate.get("trade_plan") or {}
        tp_pct = trade_plan.get("take_profit")
        sl_pct = trade_plan.get("stop_loss")

        exec_result = ExecutionModelResolver.resolve(
            execution_model=execution_model,
            forward_bars=forward_bars,
            take_profit_pct=tp_pct,
            stop_loss_pct=sl_pct,
        )

        evaluation.entry_fill_status = exec_result.fill_status
        evaluation.entry_fill_price = exec_result.fill_price
        evaluation.entry_fill_date = exec_result.fill_date
        evaluation.limit_blocked = exec_result.limit_blocked
        evaluation.gap_adjusted = exec_result.gap_adjusted
        evaluation.ambiguous_intraday_order = exec_result.ambiguous_intraday_order

        if exec_result.exit_fill_price is not None:
            evaluation.exit_fill_price = exec_result.exit_fill_price
            evaluation.exit_fill_date = exec_result.exit_fill_date

        if exec_result.fill_status == "filled" and exec_result.fill_price:
            eval_result = EntrySignalEvaluator.evaluate(
                entry_price=exec_result.fill_price,
                forward_bars=forward_bars,
                take_profit_pct=tp_pct,
                stop_loss_pct=sl_pct,
            )
            evaluation.forward_return_1d = eval_result.forward_return_1d
            evaluation.forward_return_3d = eval_result.forward_return_3d
            evaluation.forward_return_5d = eval_result.forward_return_5d
            evaluation.forward_return_10d = eval_result.forward_return_10d
            evaluation.mae = eval_result.mae
            evaluation.mfe = eval_result.mfe
            evaluation.max_drawdown_from_peak = eval_result.max_drawdown_from_peak
            evaluation.optimal_entry_deviation = eval_result.optimal_entry_deviation
            evaluation.optimal_entry_timing = eval_result.optimal_entry_timing
            evaluation.signal_quality_score = eval_result.signal_quality_score
            evaluation.plan_success = eval_result.plan_success
            evaluation.holding_days = eval_result.holding_days
            evaluation.outcome = eval_result.outcome

    def _evaluate_observation(
        self,
        evaluation: FiveLayerBacktestEvaluation,
        forward_bars: List[Any],
    ) -> None:
        """Fill observation counterfactual metrics."""
        if not forward_bars:
            return

        hypothetical_price = forward_bars[0].open if forward_bars else None
        if hypothetical_price is None or hypothetical_price <= 0:
            return

        eval_result = ObservationSignalEvaluator.evaluate(
            hypothetical_entry_price=hypothetical_price,
            forward_bars=forward_bars,
        )
        evaluation.risk_avoided_pct = eval_result.risk_avoided_pct
        evaluation.opportunity_cost_pct = eval_result.opportunity_cost_pct
        evaluation.stage_success = eval_result.stage_success
        evaluation.holding_days = eval_result.holding_days
        evaluation.outcome = eval_result.outcome

    @staticmethod
    def _build_metrics_payload(
        candidate: Dict[str, Any],
        evaluation: FiveLayerBacktestEvaluation,
        classification: Any,
    ) -> Dict[str, Any]:
        sample_origin = SampleBucketService.resolve_sample_origin(candidate)
        sample_bucket = SampleBucketService.resolve_sample_bucket(
            signal_family=evaluation.signal_family,
            effective_trade_stage=classification.effective_trade_stage,
            entry_maturity=evaluation.snapshot_entry_maturity,
        )
        timing = SampleBucketService.resolve_entry_timing(
            signal_family=evaluation.signal_family,
            entry_fill_status=evaluation.entry_fill_status,
            mae=evaluation.mae,
            mfe=evaluation.mfe,
            forward_return_5d=evaluation.forward_return_5d,
        )
        return {
            "sample_origin": sample_origin,
            "sample_bucket": sample_bucket,
            "effective_trade_stage": classification.effective_trade_stage,
            "ai_overridden": classification.ai_overridden,
            **timing,
        }

    # ── Phase 3: Aggregation & Recommendations ──────────────────────────

    def compute_summaries(
        self,
        backtest_run_id: str,
    ) -> List[FiveLayerBacktestGroupSummary]:
        """Compute all group summaries for a completed run.

        Produces overall, single-dimension, and combo summaries with
        stability metrics and sample threshold checks. Uses snapshot
        fields for historical_snapshot mode grouping.
        """
        summaries = self.aggregator.compute_all_summaries(backtest_run_id)

        # Compute ranking effectiveness and update overall summary
        if summaries:
            ranking = RankingEffectivenessCalculator.compute(summaries)
            overall = next(
                (s for s in summaries if s.group_type == "overall"), None,
            )
            if overall is not None:
                self.summary_repo.upsert_summary(
                    backtest_run_id=backtest_run_id,
                    group_type="overall",
                    group_key="all",
                    sample_count=overall.sample_count,
                    top_k_hit_rate=ranking.top_k_hit_rate,
                    excess_return_pct=ranking.excess_return_pct,
                    ranking_consistency=ranking.ranking_consistency,
                    system_grade=SystemGrader.grade(
                        win_rate_pct=overall.win_rate_pct,
                        profit_factor=overall.profit_factor,
                        time_bucket_stability=overall.time_bucket_stability,
                        sample_count=get_aggregatable_sample_count(overall),
                    ),
                )

        logger.info("Computed %d summaries for run %s", len(summaries), backtest_run_id)
        return summaries

    def get_ranking_effectiveness(self, backtest_run_id: str):
        """Return ranking effectiveness for an existing run."""
        summaries = self.summary_repo.get_by_run(backtest_run_id)
        if not summaries:
            return None
        return RankingEffectivenessCalculator.compute(summaries)

    def generate_recommendations(
        self,
        backtest_run_id: str,
    ) -> List[FiveLayerBacktestRecommendation]:
        """Generate graded recommendations based on summaries.

        ONLY outputs suggestions. NEVER modifies rules/thresholds/parameters.
        Must be called after compute_summaries().
        """
        return self.recommendation_engine.generate_recommendations(backtest_run_id)

    # ── Phase 3: Calibration comparison ────────────────────────────────

    def run_calibration_comparison(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
        calibration_name: str,
        baseline_config: Optional[Dict[str, Any]] = None,
        candidate_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[FiveLayerBacktestCalibrationOutput]:
        """Compare two completed runs and produce a calibration output.

        Both runs must have overall summaries computed (call compute_summaries
        first). Returns a CalibrationOutput with decision and confidence.
        """
        baseline_summaries = self.summary_repo.get_by_run(
            baseline_run_id, group_type="overall",
        )
        candidate_summaries = self.summary_repo.get_by_run(
            candidate_run_id, group_type="overall",
        )

        if not baseline_summaries or not candidate_summaries:
            logger.warning(
                "Cannot compare runs %s / %s — missing overall summaries",
                baseline_run_id, candidate_run_id,
            )
            return None

        output = CalibrationOutputGenerator.generate(
            backtest_run_id=candidate_run_id,
            calibration_name=calibration_name,
            baseline_summary=baseline_summaries[0],
            candidate_summary=candidate_summaries[0],
            baseline_config=baseline_config or {},
            candidate_config=candidate_config or {},
        )
        return self.calibration_repo.save(output)

    # ── Convenience: full pipeline (run + summaries + recommendations) ─

    def run_full_pipeline(
        self,
        evaluation_mode: str,
        execution_model: str,
        trade_date_from: date,
        trade_date_to: date,
        market: str = "cn",
        eval_window_days: int = _DEFAULT_EVAL_WINDOW,
        generate_recommendations: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run backtest → compute summaries → generate recommendations.

        Returns dict with 'run', 'summaries', 'recommendations' keys.
        """
        run = self.run_backtest(
            evaluation_mode=evaluation_mode,
            execution_model=execution_model,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            market=market,
            eval_window_days=eval_window_days,
            **kwargs,
        )

        summaries = self.compute_summaries(run.backtest_run_id)

        recommendations = []
        if generate_recommendations and summaries:
            recommendations = self.generate_recommendations(run.backtest_run_id)

        logger.info(
            "Full pipeline complete: run=%s evals=%d summaries=%d recs=%d",
            run.backtest_run_id,
            run.completed_count or 0,
            len(summaries),
            len(recommendations),
        )

        return {
            "run": run,
            "summaries": summaries,
            "recommendations": recommendations,
        }
