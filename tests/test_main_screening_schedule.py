import argparse
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

for optional_module in ("json_repair",):
    if optional_module not in sys.modules:
        sys.modules[optional_module] = mock.MagicMock()

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

import main as main_module


class MainScreeningScheduleTestCase(unittest.TestCase):
    @staticmethod
    def _build_config(**overrides):
        config = SimpleNamespace(
            log_dir="./logs",
            validate=lambda: [],
            webui_enabled=False,
            schedule_enabled=False,
            schedule_time="18:00",
            schedule_run_immediately=True,
            run_immediately=False,
        )
        for key, value in overrides.items():
            setattr(config, key, value)
        return config

    @staticmethod
    def _build_args(**overrides):
        base = dict(
            debug=False,
            stocks=None,
            webui=False,
            webui_only=False,
            serve=False,
            serve_only=False,
            host="0.0.0.0",
            port=8000,
            backtest=False,
            market_review=False,
            schedule=False,
            no_run_immediately=False,
            screening=False,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_main_runs_screening_once_when_screening_flag_enabled(self) -> None:
        args = self._build_args(screening=True)
        config = self._build_config(schedule_enabled=True)

        with patch.object(main_module, "setup_logging"), patch.object(
            main_module, "parse_arguments", return_value=args
        ), patch.object(
            main_module, "get_config", return_value=config
        ), patch.object(main_module, "run_screening_workflow", return_value={"status": "completed"}) as mock_run:
            exit_code = main_module.main()

        self.assertEqual(exit_code, 0)
        mock_run.assert_called_once_with(config=config, args=args)

    def test_run_screening_workflow_raises_when_screening_failed(self) -> None:
        args = self._build_args(screening=True)
        config = self._build_config()

        fake_service = mock.MagicMock()
        fake_service.run_once.return_value = {
            "run_id": "run-failed",
            "status": "failed",
            "error_summary": "同步失败",
        }

        with patch("src.services.screening_schedule_service.ScreeningScheduleService", return_value=fake_service):
            with self.assertRaisesRegex(RuntimeError, "同步失败"):
                main_module.run_screening_workflow(config=config, args=args)

    def test_run_screening_workflow_raises_when_existing_run_is_still_running(self) -> None:
        args = self._build_args(screening=True)
        config = self._build_config()

        fake_service = mock.MagicMock()
        fake_service.run_once.return_value = {
            "run_id": "run-existing",
            "status": "screening",
        }

        with patch("src.services.screening_schedule_service.ScreeningScheduleService", return_value=fake_service):
            with self.assertRaisesRegex(RuntimeError, "当前状态: screening"):
                main_module.run_screening_workflow(config=config, args=args)

    def test_main_schedules_screening_workflow_when_schedule_mode_enabled(self) -> None:
        args = self._build_args(screening=True, schedule=True)
        config = self._build_config()

        with patch.object(main_module, "setup_logging"), patch.object(
            main_module, "parse_arguments", return_value=args
        ), patch.object(
            main_module, "get_config", return_value=config
        ), patch.object(main_module, "run_screening_workflow", return_value={"status": "completed"}) as mock_run, patch(
            "src.scheduler.run_with_schedule", side_effect=lambda task, schedule_time, run_immediately: task()
        ) as mock_schedule:
            exit_code = main_module.main()

        self.assertEqual(exit_code, 0)
        mock_schedule.assert_called_once_with(
            task=mock.ANY,
            schedule_time="18:00",
            run_immediately=False,
        )
        self.assertEqual(mock_run.call_count, 2)

    def test_main_returns_non_zero_when_immediate_scheduled_screening_fails(self) -> None:
        args = self._build_args(screening=True, schedule=True)
        config = self._build_config()

        with patch.object(main_module, "setup_logging"), patch.object(
            main_module, "parse_arguments", return_value=args
        ), patch.object(
            main_module, "get_config", return_value=config
        ), patch.object(main_module, "run_screening_workflow", side_effect=RuntimeError("同步失败")), patch(
            "src.scheduler.run_with_schedule"
        ) as mock_schedule:
            exit_code = main_module.main()

        self.assertEqual(exit_code, 1)
        mock_schedule.assert_not_called()

    def test_main_returns_non_zero_when_screening_workflow_fails(self) -> None:
        args = self._build_args(screening=True)
        config = self._build_config()

        with patch.object(main_module, "setup_logging"), patch.object(
            main_module, "parse_arguments", return_value=args
        ), patch.object(
            main_module, "get_config", return_value=config
        ), patch.object(main_module, "run_screening_workflow", side_effect=RuntimeError("同步失败")):
            exit_code = main_module.main()

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
