# -*- coding: utf-8 -*-
"""Five-layer backtest service — orchestration layer.

Pipeline: select_candidates → classify → get_forward_bars →
resolve_execution → evaluate → save_evaluations → update_run.
"""
from __future__ import annotations

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
from src.repositories.stock_repo import StockRepository
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

_DEFAULT_EVAL_WINDOW = 10


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

        if evaluations:
            self.eval_repo.save_batch(evaluations)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="completed",
            sample_count=len(candidates),
            completed_count=len(evaluations),
            error_count=error_count,
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

        if evaluations:
            self.eval_repo.save_batch(evaluations)

        self.run_repo.update_run_status(
            run.backtest_run_id,
            status="completed",
            sample_count=len(candidates),
            completed_count=len(evaluations),
            error_count=error_count,
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

        # Classify signal
        has_exit_plan = False
        trade_plan = candidate.get("trade_plan")
        if trade_plan and isinstance(trade_plan, dict):
            has_exit_plan = bool(trade_plan.get("exit_signal"))

        classification = SignalClassifier.classify(
            trade_stage=candidate.get("trade_stage"),
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
            signal_family=classification.signal_family,
            evaluator_type=classification.evaluator_type,
            execution_model=execution_model,
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

        # Replayed fields stay NULL in historical_snapshot mode

        # Execute + evaluate based on signal family
        if classification.signal_family == "entry":
            self._evaluate_entry(evaluation, forward_bars, execution_model, candidate)
        elif classification.signal_family == "observation":
            self._evaluate_observation(evaluation, forward_bars)
        # exit: framework only, no metrics yet

        return evaluation

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
                        sample_count=overall.sample_count or 0,
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
