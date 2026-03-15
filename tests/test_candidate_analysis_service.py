import unittest
from unittest.mock import MagicMock

from src.search_service import SearchResponse
from src.search_service import SearchResult
from src.services.candidate_analysis_service import CandidateAnalysisBatchResult
from src.services.candidate_analysis_service import CandidateAnalysisService


class CandidateAnalysisServiceTestCase(unittest.TestCase):
    def test_analyze_top_k_searches_news_for_top_m_without_blocking_ai(self) -> None:
        analysis_service = MagicMock()
        analysis_service.analyze_stock.return_value = {
            "report": {
                "meta": {"query_id": "query-600519"},
                "summary": {
                    "analysis_summary": "趋势延续。",
                    "operation_advice": "关注",
                },
            }
        }

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
            analysis_service=analysis_service,
            search_service=search_service,
            db_manager=db,
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
        analysis_service = MagicMock()
        analysis_service.analyze_stock.side_effect = [
            {
                "report": {
                    "meta": {"query_id": "query-600519"},
                    "summary": {
                        "analysis_summary": "趋势延续。",
                        "operation_advice": "关注",
                    },
                }
            },
            RuntimeError("ai timeout"),
        ]

        search_service = MagicMock()
        search_service.is_available = False

        service = CandidateAnalysisService(
            analysis_service=analysis_service,
            search_service=search_service,
            db_manager=MagicMock(),
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
        analysis_service = MagicMock()
        analysis_service.analyze_stock.return_value = {
            "report": {
                "meta": {"query_id": "query-600519"},
                "summary": {
                    "analysis_summary": "趋势延续。",
                    "operation_advice": "关注",
                },
            }
        }

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
            analysis_service=analysis_service,
            search_service=search_service,
            db_manager=db,
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
