from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from src.search_service import get_search_service
from src.services.analysis_service import AnalysisService
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

    def analyze_top_k(
        self,
        candidates: Iterable[Any],
        top_k: int,
        news_top_m: Optional[int] = None,
    ) -> CandidateAnalysisBatchResult:
        candidate_list = list(candidates)
        news_query_ids = self._enrich_news_for_top_m(candidate_list, news_top_m if news_top_m is not None else top_k)

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
