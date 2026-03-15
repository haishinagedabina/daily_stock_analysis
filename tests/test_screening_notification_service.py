import unittest
from unittest.mock import MagicMock, call

from src.services.screening_notification_service import (
    ScreeningNotificationDeliveryError,
    ScreeningNotificationService,
)


class ScreeningNotificationServiceTestCase(unittest.TestCase):
    def test_build_run_notification_contains_rules_and_ai_sections(self) -> None:
        service = ScreeningNotificationService(
            screening_task_service=MagicMock(),
            notifier=MagicMock(),
        )

        content = service.build_run_notification(
            run={
                "run_id": "run-001",
                "trade_date": "2026-03-13",
                "mode": "balanced",
                "status": "completed_with_ai_degraded",
                "universe_size": 5000,
                "candidate_count": 2,
            },
            candidates=[
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "final_rank": 1,
                    "rule_score": 91.5,
                    "final_score": 96.5,
                    "recommendation_source": "rules_plus_ai",
                    "recommendation_reason": "规则得分 91.5；AI 建议 关注；新闻补充 1 条",
                    "ai_summary": "趋势未破坏。",
                    "news_summary": "贵州茅台新品上市",
                },
                {
                    "code": "000001",
                    "name": "平安银行",
                    "final_rank": 2,
                    "rule_score": 82.0,
                    "final_score": 82.0,
                    "recommendation_source": "rules_only",
                    "recommendation_reason": "规则得分 82.0；按规则结果输出",
                },
            ],
        )

        self.assertIn("全市场筛选推荐名单", content)
        self.assertIn("AI 二筛已降级", content)
        self.assertIn("贵州茅台", content)
        self.assertIn("趋势未破坏", content)
        self.assertIn("平安银行", content)
        self.assertIn("规则输出", content)

    def test_send_run_notification_uses_notification_service_and_saves_report(self) -> None:
        screening_task_service = MagicMock()
        screening_task_service.get_run.return_value = {
            "run_id": "run-001",
            "trade_date": "2026-03-13",
            "mode": "balanced",
            "status": "completed",
            "universe_size": 5000,
            "candidate_count": 1,
        }
        screening_task_service.list_candidates.return_value = [
            {
                "code": "600519",
                "name": "贵州茅台",
                "final_rank": 1,
                "rule_score": 91.5,
                "final_score": 96.5,
                "recommendation_source": "rules_plus_ai",
                "recommendation_reason": "规则得分 91.5；AI 建议 关注",
            }
        ]

        notifier = MagicMock()
        notifier.send.return_value = True
        notifier.save_report_to_file.return_value = "reports/screening_run_001.md"

        service = ScreeningNotificationService(
            screening_task_service=screening_task_service,
            notifier=notifier,
        )

        result = service.send_run_notification(run_id="run-001", limit=5, with_ai_only=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["run_id"], "run-001")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["report_path"], "reports/screening_run_001.md")
        notifier.send.assert_called_once()
        self.assertEqual(notifier.send.call_args.kwargs["email_stock_codes"], ["600519"])
        notifier.save_report_to_file.assert_called_once()

    def test_send_run_notification_raises_when_delivery_fails_after_report_saved(self) -> None:
        screening_task_service = MagicMock()
        screening_task_service.get_run.return_value = {
            "run_id": "run-001",
            "trade_date": "2026-03-13",
            "mode": "balanced",
            "status": "completed",
            "universe_size": 5000,
            "candidate_count": 1,
        }
        screening_task_service.list_candidates.return_value = [
            {
                "code": "600519",
                "name": "贵州茅台",
                "final_rank": 1,
                "rule_score": 91.5,
                "final_score": 96.5,
                "recommendation_source": "rules_plus_ai",
                "recommendation_reason": "规则得分 91.5；AI 建议 关注",
            }
        ]

        notifier = MagicMock()
        notifier.send.return_value = False
        notifier.save_report_to_file.return_value = "reports/screening_run_001.md"

        service = ScreeningNotificationService(
            screening_task_service=screening_task_service,
            notifier=notifier,
        )

        with self.assertRaises(ScreeningNotificationDeliveryError):
            service.send_run_notification(run_id="run-001", limit=5, with_ai_only=False)

        notifier.save_report_to_file.assert_called_once()
        notifier.send.assert_called_once()
        self.assertLess(
            notifier.mock_calls.index(call.save_report_to_file(unittest.mock.ANY, filename="screening_run-001.md")),
            notifier.mock_calls.index(call.send(unittest.mock.ANY, email_stock_codes=["600519"])),
        )


if __name__ == "__main__":
    unittest.main()
