"""RED phase: Tests for notify_run service logic.

These tests verify the idempotent notification workflow:
- can_notify gate checks
- pending run triggers notification
- already-sent run is skipped
- failed run allows retry
- 0 candidates still sends notification
- manual run defaults to skipped
"""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.services.screening_notification_service import (
    ScreeningNotificationService,
    ScreeningRunNotFoundError,
    ScreeningRunNotReadyError,
)


class NotifyRunIdempotencyTestCase(unittest.TestCase):
    """Tests for notify_run() idempotent behavior."""

    def _build_service(
        self,
        run: dict | None = None,
        candidates: list | None = None,
        send_success: bool = True,
    ) -> ScreeningNotificationService:
        task_service = MagicMock()
        task_service.get_run.return_value = run
        task_service.list_candidates.return_value = candidates or []
        notifier = MagicMock()
        notifier.send.return_value = send_success
        notifier.save_report_to_file.return_value = "reports/screening_run-001.md"
        db_manager = MagicMock()
        db_manager.update_notification_status.return_value = True
        service = ScreeningNotificationService(
            screening_task_service=task_service,
            notifier=notifier,
            db_manager=db_manager,
        )
        return service

    def _completed_run(self, **overrides) -> dict:
        base = {
            "run_id": "run-001",
            "trade_date": "2026-03-15",
            "mode": "aggressive",
            "status": "completed",
            "universe_size": 5000,
            "candidate_count": 3,
            "trigger_type": "scheduled",
            "notification_status": "pending",
            "notification_attempts": 0,
            "notification_sent_at": None,
            "notification_error": None,
        }
        base.update(overrides)
        return base

    # -- notify_run: pending -> sent --

    def test_notify_run_sends_for_pending_scheduled_run(self) -> None:
        run = self._completed_run(notification_status="pending")
        service = self._build_service(run=run, candidates=[{"code": "600519", "name": "T", "final_rank": 1, "rule_score": 90, "final_score": 95}])
        result = service.notify_run("run-001")
        self.assertTrue(result["success"])
        self.assertEqual(result["notification_status"], "sent")

    # -- notify_run: already sent, force=False -> skip --

    def test_notify_run_skips_already_sent_without_force(self) -> None:
        run = self._completed_run(notification_status="sent", notification_sent_at="2026-03-15T10:00:00")
        service = self._build_service(run=run)
        result = service.notify_run("run-001", force=False)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "already_sent")

    # -- notify_run: failed -> retry --

    def test_notify_run_retries_failed_run(self) -> None:
        run = self._completed_run(notification_status="failed", notification_attempts=1, notification_error="timeout")
        service = self._build_service(run=run, candidates=[])
        result = service.notify_run("run-001")
        self.assertTrue(result["success"])

    # -- notify_run: skipped + force=True -> send --

    def test_notify_run_force_sends_skipped_run(self) -> None:
        run = self._completed_run(trigger_type="manual", notification_status="skipped")
        service = self._build_service(run=run, candidates=[])
        result = service.notify_run("run-001", force=True)
        self.assertTrue(result["success"])

    # -- notify_run: sent + force=True -> reject (v1 rule) --

    def test_notify_run_rejects_force_resend_of_sent(self) -> None:
        run = self._completed_run(notification_status="sent", notification_sent_at="2026-03-15T10:00:00")
        service = self._build_service(run=run)
        result = service.notify_run("run-001", force=True)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "already_sent")

    # -- notify_run: 0 candidates sends notification --

    def test_notify_run_sends_with_zero_candidates(self) -> None:
        run = self._completed_run(candidate_count=0, notification_status="pending")
        service = self._build_service(run=run, candidates=[])
        result = service.notify_run("run-001")
        self.assertTrue(result["success"])

    # -- notify_run: run not found --

    def test_notify_run_raises_when_run_not_found(self) -> None:
        service = self._build_service(run=None)
        with self.assertRaises(ScreeningRunNotFoundError):
            service.notify_run("run-nonexist")

    # -- notify_run: run not completed --

    def test_notify_run_raises_when_run_not_completed(self) -> None:
        run = self._completed_run(status="screening")
        service = self._build_service(run=run)
        with self.assertRaises(ScreeningRunNotReadyError):
            service.notify_run("run-001")

    # -- notify_run: delivery failure -> mark failed --

    def test_notify_run_marks_failed_on_delivery_error(self) -> None:
        run = self._completed_run(notification_status="pending")
        service = self._build_service(run=run, candidates=[], send_success=False)
        result = service.notify_run("run-001")
        self.assertFalse(result["success"])
        self.assertEqual(result["notification_status"], "failed")


class CanNotifyTestCase(unittest.TestCase):
    """Tests for can_notify() gate logic."""

    def _make_run(self, **overrides) -> dict:
        base = {
            "status": "completed",
            "notification_status": "pending",
        }
        base.update(overrides)
        return base

    def test_can_notify_pending(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(), force=False)
        self.assertTrue(result["allowed"])

    def test_can_notify_failed(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(notification_status="failed"), force=False)
        self.assertTrue(result["allowed"])

    def test_cannot_notify_sent_without_force(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(notification_status="sent"), force=False)
        self.assertFalse(result["allowed"])

    def test_cannot_notify_sent_even_with_force(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(notification_status="sent"), force=True)
        self.assertFalse(result["allowed"])

    def test_can_notify_skipped_with_force(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(notification_status="skipped"), force=True)
        self.assertTrue(result["allowed"])

    def test_cannot_notify_skipped_without_force(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(notification_status="skipped"), force=False)
        self.assertFalse(result["allowed"])

    def test_cannot_notify_non_completed_run(self) -> None:
        result = ScreeningNotificationService.can_notify(self._make_run(status="screening"), force=False)
        self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
