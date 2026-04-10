from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from src.search_service import get_search_service
from src.services.analysis_service import AnalysisService
from src.services.ai_review_protocol import AiReviewProtocol
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
    ) -> None:
        self.analysis_service = analysis_service or AnalysisService()
        self.search_service = search_service or get_search_service()
        self.db = db_manager or DatabaseManager.get_instance()
        self._skill_manager = skill_manager
        self._ai_review_protocol = AiReviewProtocol()

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
            code = candidate["code"] if isinstance(candidate, dict) else candidate.code
            try:
                result = self.analysis_service.analyze_stock(
                    stock_code=code,
                    report_type="simple",
                    force_refresh=False,
                    send_notification=False,
                    system_context=ctx_map.get(code) or self._build_review_prompt(candidate),
                )
            except Exception as exc:
                logger.warning("AI analysis failed for %s: %s", code, exc)
                failed_codes.append(code)
                continue
            if not result:
                failed_codes.append(code)
                continue

            report = result.get("report", {})
            summary = report.get("summary", {}) if isinstance(report, dict) else {}
            entry: Dict[str, Any] = {
                "ai_query_id": report.get("meta", {}).get("query_id") or news_query_ids.get(code),
                "ai_summary": summary.get("analysis_summary"),
                "ai_operation_advice": summary.get("operation_advice"),
            }

            matched_strategies = self._extract_matched_strategies(candidate)
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

    def _build_review_prompt(self, candidate: Any) -> str:
        if isinstance(candidate, dict):
            trade_plan = candidate.get("trade_plan")
            return self._ai_review_protocol.build_review_prompt(
                code=str(candidate.get("code", "")),
                name=str(candidate.get("name", "") or ""),
                rule_trade_stage=str(candidate.get("trade_stage", "") or ""),
                setup_type=str(candidate.get("setup_type", "") or ""),
                market_regime=str(candidate.get("market_regime", "") or ""),
                theme_position=str(candidate.get("theme_position", "") or ""),
                entry_maturity=str(candidate.get("entry_maturity", "") or ""),
                trade_plan=trade_plan if isinstance(trade_plan, dict) else None,
                factor_snapshot=dict(candidate.get("factor_snapshot", {}) or {}),
            )
        trade_plan = getattr(candidate, "trade_plan", None)
        trade_plan_payload = trade_plan.to_payload() if hasattr(trade_plan, "to_payload") else None
        if trade_plan_payload is None and trade_plan is not None:
            trade_plan_payload = {
                "initial_position": getattr(trade_plan, "initial_position", None),
                "add_rule": getattr(trade_plan, "add_rule", None),
                "stop_loss_rule": getattr(trade_plan, "stop_loss_rule", None),
                "take_profit_plan": getattr(trade_plan, "take_profit_plan", None),
                "invalidation_rule": getattr(trade_plan, "invalidation_rule", None),
                "holding_expectation": getattr(trade_plan, "holding_expectation", None),
                "execution_note": getattr(trade_plan, "execution_note", None),
            }
        return self._ai_review_protocol.build_review_prompt(
            code=str(getattr(candidate, "code", "")),
            name=str(getattr(candidate, "name", "") or ""),
            rule_trade_stage=str(getattr(getattr(candidate, "trade_stage", ""), "value", getattr(candidate, "trade_stage", "")) or ""),
            setup_type=str(getattr(getattr(candidate, "setup_type", ""), "value", getattr(candidate, "setup_type", "")) or ""),
            market_regime=str(getattr(getattr(candidate, "market_regime", ""), "value", getattr(candidate, "market_regime", "")) or ""),
            theme_position=str(getattr(getattr(candidate, "theme_position", ""), "value", getattr(candidate, "theme_position", "")) or ""),
            entry_maturity=str(getattr(getattr(candidate, "entry_maturity", ""), "value", getattr(candidate, "entry_maturity", "")) or ""),
            trade_plan=trade_plan_payload,
            factor_snapshot=dict(getattr(candidate, "factor_snapshot", {}) or {}),
        )

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
