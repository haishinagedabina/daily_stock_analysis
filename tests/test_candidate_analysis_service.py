import unittest
from unittest.mock import MagicMock

from src.search_service import SearchResponse
from src.search_service import SearchResult
from src.services.candidate_analysis_service import CandidateAnalysisBatchResult
from src.services.candidate_analysis_service import CandidateAnalysisService


def _mock_review(query_id: str = "query-600519") -> MagicMock:
    review = MagicMock()
    review.to_payload.return_value = {
        "result_source": "rules_plus_ai",
        "fallback_reason": None,
    }
    review.reasoning_summary = "趋势延续。"
    review.ai_operation_advice = "focus"
    review.ai_query_id = query_id
    review.result_source = "rules_plus_ai"
    review.fallback_reason = None
    review.trade_stage = "focus"
    review.confidence = 0.75
    review.environment_ok = True
    review.initial_position = "1/4"
    review.stop_loss_rule = "跌破MA20离场"
    review.take_profit_plan = "沿5日线止盈"
    review.invalidation_rule = "放量长阴失效"
    return review


class CandidateAnalysisServiceTestCase(unittest.TestCase):
    def test_analyze_top_k_searches_news_for_top_m_without_blocking_ai(self) -> None:
        screening_ai_review_service = MagicMock()
        screening_ai_review_service.review_candidate.return_value = _mock_review()

        search_service = MagicMock()
        search_service.is_available = True
        search_service.search_stock_news.side_effect = [
            SearchResponse(
                query="贵州茅台 600519 股票 最新消息",
                provider="stub",
                success=True,
                results=[
                    SearchResult(
                        title="贵州茅台发布新品",
                        snippet="新品反馈积极。",
                        url="https://example.com/1",
                        source="stub",
                    )
                ],
            ),
            RuntimeError("news failed"),
        ]

        db = MagicMock()
        service = CandidateAnalysisService(
            search_service=search_service,
            db_manager=db,
            screening_ai_review_service=screening_ai_review_service,
        )

        batch = service.analyze_top_k(
            candidates=[
                {"code": "600519", "name": "贵州茅台", "rank": 1},
                {"code": "000001", "name": "平安银行", "rank": 2},
            ],
            top_k=1,
            news_top_m=2,
        )

        self.assertIsInstance(batch, CandidateAnalysisBatchResult)
        self.assertIn("600519", batch.results)
        self.assertEqual(batch.results["600519"]["ai_query_id"], "query-600519")
        self.assertEqual(search_service.search_stock_news.call_count, 2)
        db.save_news_intel.assert_called_once()

    def test_analyze_top_k_reports_failed_codes_when_single_ai_call_fails(self) -> None:
        screening_ai_review_service = MagicMock()
        screening_ai_review_service.review_candidate.side_effect = [
            _mock_review(),
            RuntimeError("ai timeout"),
        ]

        search_service = MagicMock()
        search_service.is_available = False

        service = CandidateAnalysisService(
            search_service=search_service,
            db_manager=MagicMock(),
            screening_ai_review_service=screening_ai_review_service,
        )

        batch = service.analyze_top_k(
            candidates=[
                {"code": "600519", "name": "贵州茅台", "rank": 1},
                {"code": "000001", "name": "平安银行", "rank": 2},
            ],
            top_k=2,
        )

        self.assertEqual(batch.failed_codes, ["000001"])

    def test_analyze_top_k_binds_news_only_candidate_to_stable_query_id(self) -> None:
        screening_ai_review_service = MagicMock()
        screening_ai_review_service.review_candidate.return_value = _mock_review()

        search_service = MagicMock()
        search_service.is_available = True
        search_service.search_stock_news.side_effect = [
            SearchResponse(
                query="贵州茅台 600519 股票 最新消息",
                provider="stub",
                success=True,
                results=[
                    SearchResult(
                        title="贵州茅台发布新品",
                        snippet="新品反馈积极。",
                        url="https://example.com/1",
                        source="stub",
                    )
                ],
            ),
            SearchResponse(
                query="平安银行 000001 股票 最新消息",
                provider="stub",
                success=True,
                results=[
                    SearchResult(
                        title="平安银行业绩预告",
                        snippet="盈利改善。",
                        url="https://example.com/2",
                        source="stub",
                    )
                ],
            ),
        ]

        db = MagicMock()
        service = CandidateAnalysisService(
            search_service=search_service,
            db_manager=db,
            screening_ai_review_service=screening_ai_review_service,
        )

        batch = service.analyze_top_k(
            candidates=[
                {"code": "600519", "name": "贵州茅台", "rank": 1},
                {"code": "000001", "name": "平安银行", "rank": 2},
            ],
            top_k=1,
            news_top_m=2,
        )

        self.assertIn("000001", batch.results)
        self.assertTrue(str(batch.results["000001"]["ai_query_id"]).startswith("screening-news-"))


if __name__ == "__main__":
    unittest.main()
