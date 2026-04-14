from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from src.search_service import get_search_service
from src.services.analysis_service import AnalysisService
from src.services._debug_session_logger_ea8dae import write_debug_log_ea8dae
from src.services.screening_ai_review_prompt_builder import ScreeningAiReviewPromptBuilder
from src.services.screening_ai_review_service import ScreeningAiReviewService
from src.schemas.trading_types import CandidateDecision
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class CandidateAnalysisBatchResult:
    results: Dict[str, Dict[str, Any]]
    failed_codes: list[str]


class CandidateAnalysisService:
    """对规则候选做少量 AI 二筛。

    Supports two analysis paths:
    - **Standard path**: uses AnalysisService with report_type="simple"
    - **Agent-enhanced path** (when skill_manager is set): passes matched
      strategy context to the analysis, enabling strategy-aware AI reasoning.
    """

    def __init__(
        self,
        analysis_service: Optional[AnalysisService] = None,
        search_service: Optional[Any] = None,
        db_manager: Optional[DatabaseManager] = None,
        skill_manager: Optional[Any] = None,
        screening_ai_review_service: Optional[ScreeningAiReviewService] = None,
    ) -> None:
        self.analysis_service = analysis_service or AnalysisService()
        self.search_service = search_service or get_search_service()
        self.db = db_manager or DatabaseManager.get_instance()
        self._skill_manager = skill_manager
        self._prompt_builder = ScreeningAiReviewPromptBuilder()
        self._screening_ai_review_service = screening_ai_review_service or ScreeningAiReviewService()

    def analyze_top_k(
        self,
        candidates: Iterable[Any],
        top_k: int,
        news_top_m: Optional[int] = None,
        five_layer_contexts: Optional[Dict[str, str]] = None,
    ) -> CandidateAnalysisBatchResult:
        candidate_list = list(candidates)
        news_query_ids = self._enrich_news_for_top_m(candidate_list, news_top_m if news_top_m is not None else top_k)
        ctx_map = five_layer_contexts or {}

        results: Dict[str, Dict[str, Any]] = {}
        failed_codes: list[str] = []
        for candidate in candidate_list[:top_k]:
            normalized_candidate = self._coerce_candidate(candidate)
            code = normalized_candidate.code
            raw_system_context = ctx_map.get(code) or self._prompt_builder.build(normalized_candidate)
            system_context = raw_system_context if isinstance(raw_system_context, str) else str(raw_system_context or "")
            context_source = "five_layer_context" if ctx_map.get(code) else "review_prompt"
            # region agent log
            write_debug_log_ea8dae(
                location="src/services/candidate_analysis_service.py:60",
                message="screening_ai_candidate_request",
                hypothesis_id="H4",
                data={
                    "code": code,
                    "top_k": top_k,
                    "news_top_m": news_top_m,
                    "context_source": context_source,
                    "context_length": len(system_context),
                    "context_preview": system_context[:240],
                    "matched_strategies": self._extract_matched_strategies(normalized_candidate),
                    "rule_trade_stage": getattr(normalized_candidate.trade_stage, "value", normalized_candidate.trade_stage),
                },
                run_id="pre-fix",
            )
            # endregion
            try:
                review = self._screening_ai_review_service.review_candidate(normalized_candidate)
            except Exception as exc:
                logger.warning("AI analysis failed for %s: %s", code, exc)
                failed_codes.append(code)
                continue
            # region agent log
            write_debug_log_ea8dae(
                location="src/services/candidate_analysis_service.py:77",
                message="screening_ai_candidate_response",
                hypothesis_id="H1",
                data={
                    "code": code,
                    "has_result": True,
                    "query_id": review.ai_query_id,
                    "analysis_summary_preview": str(review.reasoning_summary or "")[:200],
                    "operation_advice": review.ai_operation_advice,
                    "result_source": review.result_source,
                    "fallback_reason": review.fallback_reason,
                    "trade_stage": getattr(review.trade_stage, "value", review.trade_stage),
                },
                run_id="pre-fix",
            )
            # endregion
            query_id = review.ai_query_id or f"screening-ai-{uuid.uuid4().hex}"
            entry: Dict[str, Any] = {
                **review.to_payload(),
                "ai_query_id": query_id,
                "ai_summary": review.reasoning_summary,
                "ai_operation_advice": review.ai_operation_advice or getattr(review.trade_stage, "value", review.trade_stage),
                "ai_trade_stage": getattr(review.trade_stage, "value", review.trade_stage),
                "ai_reasoning": review.reasoning_summary,
                "ai_confidence": review.confidence,
                "ai_environment_ok": review.environment_ok,
                "initial_position": review.initial_position,
                "stop_loss_rule": review.stop_loss_rule,
                "take_profit_plan": review.take_profit_plan,
                "invalidation_rule": review.invalidation_rule,
            }

            matched_strategies = self._extract_matched_strategies(normalized_candidate)
            if matched_strategies:
                entry["matched_strategies"] = matched_strategies

            results[code] = entry
        for code, query_id in news_query_ids.items():
            results.setdefault(code, {"ai_query_id": query_id})
        return CandidateAnalysisBatchResult(results=results, failed_codes=failed_codes)

    @staticmethod
    def _extract_matched_strategies(candidate: Any) -> list[str]:
        """Extract matched_strategies from a candidate object or dict."""
        if isinstance(candidate, dict):
            return list(candidate.get("matched_strategies", []))
        return list(getattr(candidate, "matched_strategies", []) or [])

    @staticmethod
    def _coerce_candidate(candidate: Any) -> CandidateDecision:
        if isinstance(candidate, CandidateDecision):
            return candidate
        if isinstance(candidate, dict):
            return CandidateDecision.from_payload(candidate)
        payload = {
            key: getattr(candidate, key)
            for key in (
                "code",
                "name",
                "rank",
                "rule_score",
                "rule_hits",
                "factor_snapshot",
                "matched_strategies",
                "market_regime",
                "risk_level",
                "environment_ok",
                "theme_tag",
                "theme_score",
                "theme_position",
                "leader_score",
                "sector_strength",
                "theme_duration",
                "trade_theme_stage",
                "setup_type",
                "entry_maturity",
                "setup_freshness",
                "strategy_family",
                "setup_hit_reasons",
                "trade_stage",
                "trade_plan",
            )
            if hasattr(candidate, key)
        }
        return CandidateDecision.from_payload(payload)

    def _enrich_news_for_top_m(self, candidates: Iterable[Any], news_top_m: int) -> Dict[str, str]:
        news_query_ids: Dict[str, str] = {}
        if news_top_m <= 0:
            return news_query_ids
        if not getattr(self.search_service, "is_available", False):
            return news_query_ids

        for candidate in list(candidates)[:news_top_m]:
            code = candidate["code"] if isinstance(candidate, dict) else candidate.code
            name = candidate.get("name") if isinstance(candidate, dict) else getattr(candidate, "name", None)
            try:
                response = self.search_service.search_stock_news(
                    stock_code=code,
                    stock_name=name or code,
                    max_results=5,
                )
                if response.success and response.results:
                    query_id = f"screening-news-{uuid.uuid4().hex}"
                    self.db.save_news_intel(
                        code=code,
                        name=name or code,
                        dimension="latest_news",
                        query=response.query,
                        response=response,
                        query_context={"query_source": "screening", "query_id": query_id},
                    )
                    news_query_ids[code] = query_id
            except Exception as exc:
                logger.warning("News enrichment failed for %s: %s", code, exc)
        return news_query_ids
