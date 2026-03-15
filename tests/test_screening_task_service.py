import os
import tempfile
import logging
from datetime import date
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd
import pytest

from src.config import Config
from src.services.candidate_analysis_service import CandidateAnalysisBatchResult
from src.services.screening_task_service import ScreeningTaskService
from src.services.universe_service import LocalUniverseNotReadyError
from src.storage import DatabaseManager


class _IntegrationUniverseService:
    def resolve_universe(self, stock_codes=None):
        raise LocalUniverseNotReadyError("本地 instrument_master 为空")

    def sync_universe(self, market="cn"):
        raise RuntimeError("sync failed")


class _SuccessUniverseService:
    def resolve_universe(self, stock_codes=None):
        return pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])


def test_screening_task_service_executes_full_pipeline_and_limits_ai_top_k():
    db = MagicMock()
    db.create_screening_run.return_value = "run-001"
    db.get_screening_run.return_value = {
        "run_id": "run-001",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 2,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "000001", "name": "平安银行"},
        ]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [
            {
                "code": "600519",
                "name": "贵州茅台",
                "close": 1500.0,
                "ma5": 1492.0,
                "ma10": 1485.0,
                "ma20": 1470.0,
                "ma60": 1420.0,
                "volume_ratio": 1.5,
                "avg_amount": 150_000_000,
                "breakout_ratio": 1.01,
                "pct_chg": 2.5,
                "is_st": False,
                "days_since_listed": 8000,
            },
            {
                "code": "000001",
                "name": "平安银行",
                "close": 12.0,
                "ma5": 11.9,
                "ma10": 11.8,
                "ma20": 11.7,
                "ma60": 11.5,
                "volume_ratio": 1.2,
                "avg_amount": 80_000_000,
                "breakout_ratio": 0.99,
                "pct_chg": 1.0,
                "is_st": False,
                "days_since_listed": 5000,
            },
        ]
    )

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "rank": 1,
            "rule_score": 91.0,
            "rule_hits": ["trend_aligned", "volume_expanding"],
            "factor_snapshot": {"close": 1500.0},
        },
        {
            "code": "000001",
            "name": "平安银行",
            "rank": 2,
            "rule_score": 80.0,
            "rule_hits": ["trend_aligned"],
            "factor_snapshot": {"close": 12.0},
        },
    ]
    screener_service.evaluate.return_value.rejected = []

    candidate_analysis_service = MagicMock()
    candidate_analysis_service.analyze_top_k.return_value = {
        "600519": {
            "ai_query_id": "q-600519",
            "ai_summary": "保持上升趋势。",
            "ai_operation_advice": "关注",
        }
    }
    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 2,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=candidate_analysis_service,
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=1,
    )

    assert result["run_id"] == "run-001"
    assert result["status"] == "completed"

    statuses = [call.kwargs["status"] for call in db.update_screening_run_status.call_args_list]
    assert statuses == [
        "resolving_universe",
        "ingesting",
        "factorizing",
        "screening",
        "ai_enriching",
        "completed",
    ]
    completed_call = db.update_screening_run_status.call_args_list[-1]
    assert completed_call.kwargs["trade_date"] == date(2026, 3, 13)
    db.save_screening_candidates.assert_called_once()
    saved_candidates = db.save_screening_candidates.call_args.kwargs["candidates"]
    assert saved_candidates[0]["selected_for_ai"] is True
    assert saved_candidates[0]["ai_query_id"] == "q-600519"
    assert saved_candidates[1]["selected_for_ai"] is False
    candidate_analysis_service.analyze_top_k.assert_called_once()
    market_data_sync_service.sync_trade_date.assert_called_once()


def test_screening_task_service_completes_with_ai_degraded_when_ai_analysis_fails():
    db = MagicMock()
    db.create_screening_run.return_value = "run-ai-degraded"
    db.get_screening_run.return_value = {
        "run_id": "run-ai-degraded",
        "mode": "balanced",
        "status": "completed_with_ai_degraded",
        "candidate_count": 1,
        "error_summary": "ai timeout",
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台", "close": 1500.0}]
    )

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "rank": 1,
            "rule_score": 91.0,
            "rule_hits": ["trend_aligned"],
            "factor_snapshot": {"close": 1500.0},
        }
    ]
    screener_service.evaluate.return_value.rejected = []

    candidate_analysis_service = MagicMock()
    candidate_analysis_service.analyze_top_k.side_effect = RuntimeError("ai timeout")

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=candidate_analysis_service,
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        candidate_limit=10,
        ai_top_k=1,
    )

    assert result["status"] == "completed_with_ai_degraded"
    completed_call = db.update_screening_run_status.call_args_list[-1]
    assert completed_call.kwargs["status"] == "completed_with_ai_degraded"
    assert completed_call.kwargs["error_summary"] == "ai timeout"
    saved_candidates = db.save_screening_candidates.call_args.kwargs["candidates"]
    assert saved_candidates[0]["ai_summary"] is None


def test_screening_task_service_completes_with_ai_degraded_when_partial_ai_failures_exist():
    db = MagicMock()
    db.create_screening_run.return_value = "run-ai-partial"
    db.get_screening_run.return_value = {
        "run_id": "run-ai-partial",
        "mode": "balanced",
        "status": "completed_with_ai_degraded",
        "candidate_count": 2,
        "error_summary": "AI degraded for: 000001",
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = [
        {"code": "600519", "name": "贵州茅台", "rank": 1, "rule_score": 91.0, "rule_hits": [], "factor_snapshot": {}},
        {"code": "000001", "name": "平安银行", "rank": 2, "rule_score": 81.0, "rule_hits": [], "factor_snapshot": {}},
    ]
    screener_service.evaluate.return_value.rejected = []

    candidate_analysis_service = MagicMock()
    candidate_analysis_service.analyze_top_k.return_value = CandidateAnalysisBatchResult(
        results={
            "600519": {
                "ai_query_id": "query-600519",
                "ai_summary": "趋势延续。",
                "ai_operation_advice": "关注",
            }
        },
        failed_codes=["000001"],
    )

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 2,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=candidate_analysis_service,
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(trade_date=date(2026, 3, 13), candidate_limit=10, ai_top_k=2)

    assert result["status"] == "completed_with_ai_degraded"
    completed_call = db.update_screening_run_status.call_args_list[-1]
    assert completed_call.kwargs["status"] == "completed_with_ai_degraded"
    assert "000001" in completed_call.kwargs["error_summary"]


def test_screening_task_service_logs_stage_durations_and_health_report(caplog):
    db = MagicMock()
    db.create_screening_run.return_value = "run-observe"
    db.get_screening_run.return_value = {
        "run_id": "run-observe",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 1,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = [
        {"code": "600519", "name": "贵州茅台", "rank": 1, "rule_score": 91.0, "rule_hits": [], "factor_snapshot": {}}
    ]
    screener_service.evaluate.return_value.rejected = [{"code": "000001"}]

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
        "health_report": {
            "summary": "ok",
            "success_rate": 1.0,
            "missing_count": 0,
            "error_count": 0,
        },
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    with caplog.at_level(logging.INFO, logger="src.services.screening_task_service"):
        service.execute_run(trade_date=date(2026, 3, 13), candidate_limit=10, ai_top_k=0)

    assert "screening_run_id=run-observe" in caplog.text
    assert "stage=ingesting" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "health_summary=ok" in caplog.text
    assert "selected_count=1" in caplog.text
    assert "rejected_count=1" in caplog.text
    assert "event=run_completed" in caplog.text


def test_screening_task_service_logs_failed_stage_with_run_id(caplog):
    db = MagicMock()
    db.create_screening_run.return_value = "run-log-failed"
    db.get_screening_run.return_value = {
        "run_id": "run-log-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.side_effect = LocalUniverseNotReadyError("本地 instrument_master 为空")
    universe_service.sync_universe.side_effect = RuntimeError("sync failed")

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    with caplog.at_level(logging.ERROR, logger="src.services.screening_task_service"):
        result = service.execute_run(
            trade_date=date(2026, 3, 13),
            stock_codes=None,
            candidate_limit=30,
            ai_top_k=0,
        )

    assert result["status"] == "failed"
    assert "screening_run_id=run-log-failed" in caplog.text
    assert "stage=syncing_universe" in caplog.text
    assert "error=sync%20failed" in caplog.text


def test_screening_task_service_logs_health_report_before_partial_sync_failure(caplog):
    db = MagicMock()
    db.create_screening_run.return_value = "run-health-failed"
    db.get_screening_run.return_value = {
        "run_id": "run-health-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [{"code": "000001", "reason": "empty_data"}],
        "health_report": {
            "summary": "partial failure",
            "success_rate": 0.5,
            "missing_count": 1,
            "error_count": 1,
        },
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    with caplog.at_level(logging.INFO, logger="src.services.screening_task_service"):
        result = service.execute_run(
            trade_date=date(2026, 3, 13),
            stock_codes=None,
            candidate_limit=30,
            ai_top_k=0,
        )

    assert result["status"] == "failed"
    assert "screening_run_id=run-health-failed" in caplog.text
    assert "health_summary=partial%20failure" in caplog.text
    assert "health_success_rate=0.5" in caplog.text


def test_screening_task_service_reuses_existing_completed_run_for_same_scope():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-duplicate",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 2,
        "config_snapshot": {"stock_codes": ["000001", "600519"]},
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=["600519", "000001"],
        candidate_limit=30,
        ai_top_k=5,
    )

    assert result["run_id"] == "run-duplicate"
    db.create_screening_run.assert_not_called()


def test_screening_task_service_syncs_universe_when_local_master_missing():
    db = MagicMock()
    db.create_screening_run.return_value = "run-002"
    db.get_screening_run.return_value = {"run_id": "run-002", "mode": "balanced", "status": "completed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.side_effect = [
        LocalUniverseNotReadyError("本地 instrument_master 为空，请先执行 universe 同步"),
        pd.DataFrame([{"code": "600519", "name": "贵州茅台"}]),
    ]
    universe_service.sync_universe.return_value = {"saved_count": 1, "source": "StubFetcher", "market": "cn"}

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台", "close": 1500.0, "rule_score": 0}]
    )

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = []
    screener_service.evaluate.return_value.rejected = []

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    db.create_screening_run.assert_called_once()
    statuses = [call.kwargs["status"] for call in db.update_screening_run_status.call_args_list]
    assert statuses[:4] == [
        "resolving_universe",
        "syncing_universe",
        "ingesting",
        "factorizing",
    ]
    universe_service.sync_universe.assert_called_once_with(market="cn")


def test_screening_task_service_marks_run_failed_when_universe_sync_fails():
    db = MagicMock()
    db.create_screening_run.return_value = "run-003"
    db.get_screening_run.return_value = {"run_id": "run-003", "mode": "balanced", "status": "failed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.side_effect = LocalUniverseNotReadyError("本地 instrument_master 为空")
    universe_service.sync_universe.side_effect = RuntimeError("sync failed")

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    statuses = [call.kwargs["status"] for call in db.update_screening_run_status.call_args_list]
    assert statuses == ["resolving_universe", "syncing_universe", "failed"]
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert failed_call.kwargs["error_summary"] == "sync failed"


@patch("src.services.screening_task_service.get_config")
def test_screening_task_service_uses_config_defaults_when_limits_omitted(get_config_mock):
    get_config_mock.return_value.screening_default_mode = "balanced"
    get_config_mock.return_value.screening_candidate_limit = 1
    get_config_mock.return_value.screening_ai_top_k = 1
    get_config_mock.return_value.screening_min_list_days = 120
    get_config_mock.return_value.screening_min_volume_ratio = 1.2
    get_config_mock.return_value.screening_min_avg_amount = 50_000_000
    get_config_mock.return_value.screening_breakout_lookback_days = 20
    get_config_mock.return_value.screening_factor_lookback_days = 80

    db = MagicMock()
    db.create_screening_run.return_value = "run-004"
    db.get_screening_run.return_value = {"run_id": "run-004", "mode": "balanced", "status": "completed", "candidate_count": 1}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "000001", "name": "平安银行"},
        ]
    )

    factor_service = MagicMock()
    factor_service.lookback_days = 80
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台", "close": 1500.0, "rule_score": 0}]
    )

    screener_service = MagicMock()
    screener_service.min_list_days = 120
    screener_service.min_volume_ratio = 1.2
    screener_service.min_avg_amount = 50_000_000
    screener_service.breakout_lookback_days = 20
    screener_service.evaluate.return_value.selected = [
        {"code": "600519", "name": "贵州茅台", "rank": 1, "rule_score": 91.0, "rule_hits": [], "factor_snapshot": {}},
        {"code": "000001", "name": "平安银行", "rank": 2, "rule_score": 80.0, "rule_hits": [], "factor_snapshot": {}},
    ]
    screener_service.evaluate.return_value.rejected = []

    candidate_analysis_service = MagicMock()
    candidate_analysis_service.analyze_top_k.return_value = {}

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 2,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=candidate_analysis_service,
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=None,
        ai_top_k=None,
    )

    create_call = db.create_screening_run.call_args
    assert create_call.kwargs["config_snapshot"]["mode"] == "balanced"
    assert create_call.kwargs["config_snapshot"]["candidate_limit"] == 1
    assert create_call.kwargs["config_snapshot"]["ai_top_k"] == 1
    assert create_call.kwargs["config_snapshot"]["screening_min_list_days"] == 120
    assert create_call.kwargs["config_snapshot"]["screening_min_volume_ratio"] == 1.2
    assert create_call.kwargs["config_snapshot"]["screening_min_avg_amount"] == 50_000_000
    assert (
        create_call.kwargs["config_snapshot"]["screening_breakout_lookback_days"]
        == 20
    )
    assert create_call.kwargs["config_snapshot"]["screening_factor_lookback_days"] == 80
    candidate_analysis_service.analyze_top_k.assert_called_once()
    assert candidate_analysis_service.analyze_top_k.call_args.kwargs["top_k"] == 1
    saved_candidates = db.save_screening_candidates.call_args.kwargs["candidates"]
    assert len(saved_candidates) == 1
    assert factor_service.build_factor_snapshot.call_args.kwargs["persist"] is False


def test_screening_task_service_reruns_failed_run_from_factorizing_stage():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
        "config_snapshot": {"stock_codes": [], "next_resume_stage": "factorizing"},
    }
    db.get_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 1,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = [
        {"code": "600519", "name": "贵州茅台", "rank": 1, "rule_score": 91.0, "rule_hits": [], "factor_snapshot": {}},
    ]
    screener_service.evaluate.return_value.rejected = []

    candidate_analysis_service = MagicMock()
    candidate_analysis_service.analyze_top_k.return_value = {}

    market_data_sync_service = MagicMock()

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=candidate_analysis_service,
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        rerun_failed=True,
        resume_from="factorizing",
    )

    assert result["run_id"] == "run-failed"
    reset_call = db.reset_screening_run_for_rerun.call_args
    assert reset_call.kwargs["run_id"] == "run-failed"
    assert reset_call.kwargs["config_snapshot"]["next_resume_stage"] == "factorizing"
    db.create_screening_run.assert_not_called()
    market_data_sync_service.sync_trade_date.assert_not_called()
    factor_service.build_factor_snapshot.assert_called_once()
    statuses = [call.kwargs["status"] for call in db.update_screening_run_status.call_args_list]
    assert statuses == ["factorizing", "screening", "ai_enriching", "completed"]


def test_screening_task_service_deduplicates_without_explicit_trade_date_by_requested_date():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-latest-trading-day",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 3,
        "config_snapshot": {
            "requested_trade_date": "2026-03-15",
            "stock_codes": [],
            "candidate_limit": 30,
            "ai_top_k": 5,
            "screening_min_list_days": 120,
            "screening_min_volume_ratio": 1.2,
            "screening_min_avg_amount": 50_000_000,
            "screening_breakout_lookback_days": 20,
            "screening_factor_lookback_days": 80,
            "mode": "balanced",
        },
        "trade_date": "2026-03-13",
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    with patch("src.services.screening_task_service.date") as date_mock:
        date_mock.today.return_value = date(2026, 3, 15)
        result = service.execute_run(trade_date=None)

    assert result["run_id"] == "run-latest-trading-day"
    db.create_screening_run.assert_not_called()


def test_screening_task_service_treats_different_effective_config_as_new_run():
    db = MagicMock()
    db.find_latest_screening_run.return_value = None
    db.create_screening_run.return_value = "run-config-new"
    db.get_screening_run.return_value = {
        "run_id": "run-config-new",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = []
    screener_service.evaluate.return_value.rejected = []

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
        "health_report": {
            "expected_count": 1,
            "available_count": 1,
            "missing_count": 0,
            "error_count": 0,
            "missing_codes": [],
            "success_rate": 1.0,
            "summary": "ok",
        },
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        candidate_limit=20,
        ai_top_k=1,
    )

    create_call = db.create_screening_run.call_args
    assert create_call.kwargs["config_snapshot"]["candidate_limit"] == 20
    assert create_call.kwargs["config_snapshot"]["ai_top_k"] == 1


def test_screening_task_service_rejects_factorizing_rerun_when_previous_sync_not_complete():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
        "config_snapshot": {
            "stock_codes": [],
            "next_resume_stage": "ingesting",
        },
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    with pytest.raises(ValueError, match="factorizing"):
        service.execute_run(
            trade_date=date(2026, 3, 13),
            rerun_failed=True,
            resume_from="factorizing",
        )


def test_screening_task_service_refreshes_snapshot_when_failed_run_is_rerun():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
        "config_snapshot": {
            "stock_codes": [],
            "candidate_limit": 30,
            "ai_top_k": 5,
            "next_resume_stage": "factorizing",
        },
    }
    db.get_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = []
    screener_service.evaluate.return_value.rejected = []

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        rerun_failed=True,
        resume_from="factorizing",
        candidate_limit=10,
        ai_top_k=1,
    )

    reset_call = db.reset_screening_run_for_rerun.call_args
    assert reset_call.kwargs["run_id"] == "run-failed"
    assert reset_call.kwargs["ai_top_k"] == 1
    assert reset_call.kwargs["config_snapshot"]["candidate_limit"] == 10


def test_screening_task_service_returns_existing_run_when_rerun_claim_is_lost():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
        "config_snapshot": {
            "stock_codes": [],
            "next_resume_stage": "factorizing",
        },
    }
    db.reset_screening_run_for_rerun.return_value = False
    db.get_screening_run.return_value = {
        "run_id": "run-failed",
        "mode": "balanced",
        "status": "pending",
        "candidate_count": 0,
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        rerun_failed=True,
        resume_from="factorizing",
    )

    assert result["run_id"] == "run-failed"
    assert result["status"] == "pending"


def test_screening_task_service_returns_existing_run_when_failed_rerun_already_claimed():
    db = MagicMock()
    db.find_latest_screening_run.return_value = {
        "run_id": "run-claimed",
        "mode": "balanced",
        "status": "pending",
        "candidate_count": 0,
        "config_snapshot": {
            "stock_codes": [],
            "next_resume_stage": "factorizing",
        },
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        rerun_failed=True,
        resume_from="factorizing",
    )

    assert result["run_id"] == "run-claimed"
    assert result["status"] == "pending"


@patch("src.services.screening_task_service.get_config")
@patch("src.services.screening_task_service.FactorService")
@patch("src.services.screening_task_service.ScreenerService")
def test_screening_task_service_builds_mode_specific_services(
    screener_cls,
    factor_cls,
    get_config_mock,
):
    get_config_mock.return_value.screening_default_mode = "balanced"
    get_config_mock.return_value.screening_candidate_limit = 30
    get_config_mock.return_value.screening_ai_top_k = 5
    get_config_mock.return_value.screening_min_list_days = 120
    get_config_mock.return_value.screening_min_volume_ratio = 1.2
    get_config_mock.return_value.screening_min_avg_amount = 50_000_000
    get_config_mock.return_value.screening_breakout_lookback_days = 20
    get_config_mock.return_value.screening_factor_lookback_days = 80

    db = MagicMock()
    db.create_screening_run.return_value = "run-004a"
    db.get_screening_run.return_value = {"run_id": "run-004a", "mode": "aggressive", "status": "completed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_instance = MagicMock()
    screener_instance.min_list_days = 60
    screener_instance.min_volume_ratio = 1.0
    screener_instance.min_avg_amount = 20_000_000
    screener_instance.breakout_lookback_days = 30
    screener_instance.evaluate.return_value.selected = []
    screener_instance.evaluate.return_value.rejected = []
    screener_cls.return_value = screener_instance

    factor_instance = MagicMock()
    factor_instance.lookback_days = 100
    factor_instance.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_instance.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    factor_cls.return_value = factor_instance

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=None,
        screener_service=None,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        mode="aggressive",
        candidate_limit=None,
        ai_top_k=None,
    )

    screener_cls.assert_called_once_with(
        min_list_days=60,
        min_volume_ratio=1.0,
        min_avg_amount=20_000_000,
        breakout_lookback_days=15,
    )
    factor_cls.assert_called_once_with(
        db,
        lookback_days=60,
        breakout_lookback_days=15,
        min_list_days=60,
    )
    assert factor_instance.build_factor_snapshot.call_args.kwargs["persist"] is False


@patch("src.services.screening_task_service.get_config")
def test_screening_task_service_rejects_non_balanced_mode_with_custom_services(get_config_mock):
    get_config_mock.return_value.screening_default_mode = "balanced"
    get_config_mock.return_value.screening_candidate_limit = 30
    get_config_mock.return_value.screening_ai_top_k = 5
    get_config_mock.return_value.screening_min_list_days = 120
    get_config_mock.return_value.screening_min_volume_ratio = 1.2
    get_config_mock.return_value.screening_min_avg_amount = 50_000_000
    get_config_mock.return_value.screening_breakout_lookback_days = 20
    get_config_mock.return_value.screening_factor_lookback_days = 80

    service = ScreeningTaskService(
        db_manager=MagicMock(),
        universe_service=MagicMock(),
        factor_service=MagicMock(),
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=MagicMock(),
    )

    with pytest.raises(ValueError, match="balanced"):
        service.execute_run(mode="aggressive")


@patch("src.services.screening_task_service.get_config")
@patch("src.services.screening_task_service.FactorService")
@patch("src.services.screening_task_service.ScreenerService")
def test_screening_task_service_disables_shared_snapshot_persistence_for_custom_stock_scope(
    screener_cls,
    factor_cls,
    get_config_mock,
):
    get_config_mock.return_value.screening_default_mode = "balanced"
    get_config_mock.return_value.screening_candidate_limit = 30
    get_config_mock.return_value.screening_ai_top_k = 5
    get_config_mock.return_value.screening_min_list_days = 120
    get_config_mock.return_value.screening_min_volume_ratio = 1.2
    get_config_mock.return_value.screening_min_avg_amount = 50_000_000
    get_config_mock.return_value.screening_breakout_lookback_days = 20
    get_config_mock.return_value.screening_factor_lookback_days = 80

    db = MagicMock()
    db.create_screening_run.return_value = "run-004b"
    db.get_screening_run.return_value = {"run_id": "run-004b", "mode": "balanced", "status": "completed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_instance = MagicMock()
    screener_instance.evaluate.return_value.selected = []
    screener_instance.evaluate.return_value.rejected = []
    screener_cls.return_value = screener_instance

    factor_instance = MagicMock()
    factor_instance.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_instance.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    factor_cls.return_value = factor_instance

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=None,
        screener_service=None,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=["600519"],
        mode=None,
        candidate_limit=None,
        ai_top_k=None,
    )

    assert factor_instance.build_factor_snapshot.call_args.kwargs["persist"] is False


@patch("src.services.screening_task_service.get_config")
@patch("src.services.screening_task_service.FactorService")
@patch("src.services.screening_task_service.ScreenerService")
def test_screening_task_service_persists_shared_snapshot_only_for_default_balanced_full_market(
    screener_cls,
    factor_cls,
    get_config_mock,
):
    get_config_mock.return_value.screening_default_mode = "balanced"
    get_config_mock.return_value.screening_candidate_limit = 30
    get_config_mock.return_value.screening_ai_top_k = 5
    get_config_mock.return_value.screening_min_list_days = 120
    get_config_mock.return_value.screening_min_volume_ratio = 1.2
    get_config_mock.return_value.screening_min_avg_amount = 50_000_000
    get_config_mock.return_value.screening_breakout_lookback_days = 20
    get_config_mock.return_value.screening_factor_lookback_days = 80

    db = MagicMock()
    db.create_screening_run.return_value = "run-004c"
    db.get_screening_run.return_value = {"run_id": "run-004c", "mode": "balanced", "status": "completed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    screener_instance = MagicMock()
    screener_instance.evaluate.return_value.selected = []
    screener_instance.evaluate.return_value.rejected = []
    screener_cls.return_value = screener_instance

    factor_instance = MagicMock()
    factor_instance.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_instance.build_factor_snapshot.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    factor_cls.return_value = factor_instance

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 1,
        "skipped": 0,
        "errors": [],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=None,
        screener_service=None,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        mode=None,
        candidate_limit=None,
        ai_top_k=None,
    )

    assert factor_instance.build_factor_snapshot.call_args.kwargs["persist"] is True


def test_screening_task_service_fails_when_status_persistence_is_rejected():
    db = MagicMock()
    db.create_screening_run.return_value = "run-005"
    db.get_screening_run.return_value = {"run_id": "run-005", "mode": "balanced", "status": "failed", "candidate_count": 0}

    def _update_status(**kwargs):
        return kwargs["status"] != "ingesting"

    db.update_screening_run_status.side_effect = _update_status

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    market_data_sync_service.sync_trade_date.assert_not_called()
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "状态更新失败" in failed_call.kwargs["error_summary"]


def test_screening_task_service_fails_when_market_sync_has_partial_errors():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006"
    db.get_screening_run.return_value = {"run_id": "run-006", "mode": "balanced", "status": "failed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [{"code": "000001", "reason": "empty_data"}],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    statuses = [call.kwargs["status"] for call in db.update_screening_run_status.call_args_list]
    assert statuses == ["resolving_universe", "ingesting", "failed"]
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "000001" in failed_call.kwargs["error_summary"]


def test_screening_task_service_uses_error_detail_in_sync_failure_summary():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006-detail"
    db.get_screening_run.return_value = {"run_id": "run-006-detail", "mode": "balanced", "status": "failed", "candidate_count": 0}

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [
            {
                "code": "000001",
                "reason": "empty_data",
                "detail": "所有数据源获取 000001 失败: provider timeout chain",
            }
        ],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "provider timeout chain" in failed_call.kwargs["error_summary"]


def test_screening_task_service_ignores_delisted_sync_errors_and_continues():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006b"
    db.get_screening_run.return_value = {
        "run_id": "run-006b",
        "mode": "balanced",
        "status": "completed",
        "candidate_count": 1,
        "error_summary": "已忽略退市股票同步失败: 000002",
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台", "listing_status": "active"},
            {"code": "000002", "name": "万科A退", "listing_status": "active"},
        ]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
    factor_service.build_factor_snapshot.return_value = pd.DataFrame(
        [{"code": "600519", "name": "贵州茅台", "close": 1500.0}]
    )

    screener_service = MagicMock()
    screener_service.evaluate.return_value.selected = []
    screener_service.evaluate.return_value.rejected = []

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [{"code": "000002", "reason": "empty_data"}],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=screener_service,
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "completed"
    factor_universe = factor_service.build_factor_snapshot.call_args.kwargs["universe_df"]
    assert factor_universe["code"].tolist() == ["600519"]
    completed_call = db.update_screening_run_status.call_args_list[-1]
    assert completed_call.kwargs["status"] == "completed"
    assert completed_call.kwargs["error_summary"] == "已忽略退市股票同步失败: 000002"


def test_screening_task_service_does_not_ignore_non_delisted_inactive_status_sync_errors():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006c"
    db.get_screening_run.return_value = {
        "run_id": "run-006c",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台", "listing_status": "active"},
            {"code": "000001", "name": "平安银行", "listing_status": "suspended"},
        ]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [{"code": "000001", "reason": "empty_data"}],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    factor_service.build_factor_snapshot.assert_not_called()
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "000001" in failed_call.kwargs["error_summary"]


def test_screening_task_service_fails_when_ignorable_and_blocking_sync_errors_coexist():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006d"
    db.get_screening_run.return_value = {
        "run_id": "run-006d",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台", "listing_status": "active"},
            {"code": "000002", "name": "万科A退", "listing_status": "active"},
            {"code": "000001", "name": "平安银行", "listing_status": "active"},
        ]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 3,
        "synced": 1,
        "skipped": 0,
        "errors": [
            {"code": "000002", "reason": "empty_data"},
            {"code": "000001", "reason": "save_failed"},
        ],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    factor_service.build_factor_snapshot.assert_not_called()
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "000001" in failed_call.kwargs["error_summary"]
    assert "save_failed" in failed_call.kwargs["error_summary"]


def test_screening_task_service_does_not_ignore_regular_name_containing_tui_character():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006e"
    db.get_screening_run.return_value = {
        "run_id": "run-006e",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [
            {"code": "600519", "name": "贵州茅台", "listing_status": "active"},
            {"code": "000003", "name": "进退科技", "listing_status": "active"},
        ]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 2,
        "synced": 1,
        "skipped": 0,
        "errors": [{"code": "000003", "reason": "empty_data"}],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    factor_service.build_factor_snapshot.assert_not_called()
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "000003" in failed_call.kwargs["error_summary"]


def test_screening_task_service_reports_filtered_empty_universe_after_ignoring_delisted_errors():
    db = MagicMock()
    db.create_screening_run.return_value = "run-006f"
    db.get_screening_run.return_value = {
        "run_id": "run-006f",
        "mode": "balanced",
        "status": "failed",
        "candidate_count": 0,
    }

    universe_service = MagicMock()
    universe_service.resolve_universe.return_value = pd.DataFrame(
        [{"code": "000002", "name": "万科A退", "listing_status": "active"}]
    )

    factor_service = MagicMock()
    factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)

    market_data_sync_service = MagicMock()
    market_data_sync_service.sync_trade_date.return_value = {
        "trade_date": "2026-03-13",
        "total": 1,
        "synced": 0,
        "skipped": 0,
        "errors": [
            {
                "code": "000002",
                "reason": "empty_data",
                "detail": "所有数据源获取 000002 失败: no data from providers",
            }
        ],
    }

    service = ScreeningTaskService(
        db_manager=db,
        universe_service=universe_service,
        factor_service=factor_service,
        screener_service=MagicMock(),
        candidate_analysis_service=MagicMock(),
        market_data_sync_service=market_data_sync_service,
    )

    result = service.execute_run(
        trade_date=date(2026, 3, 13),
        stock_codes=None,
        candidate_limit=30,
        ai_top_k=0,
    )

    assert result["status"] == "failed"
    factor_service.build_factor_snapshot.assert_not_called()
    failed_call = db.update_screening_run_status.call_args_list[-1]
    assert "剔除退市且无数据股票后" in failed_call.kwargs["error_summary"]


def test_screening_task_service_persists_failed_run_to_real_database():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "screening_task_failed.db")
        os.environ["DATABASE_PATH"] = db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()

        try:
            db = DatabaseManager.get_instance()
            service = ScreeningTaskService(
                db_manager=db,
                universe_service=_IntegrationUniverseService(),
                factor_service=MagicMock(),
                screener_service=MagicMock(),
                candidate_analysis_service=MagicMock(),
                market_data_sync_service=MagicMock(),
            )

            result = service.execute_run(
                trade_date=date(2026, 3, 13),
                stock_codes=None,
                candidate_limit=30,
                ai_top_k=0,
            )

            persisted = db.get_screening_run(result["run_id"])
            assert result["status"] == "failed"
            assert persisted is not None
            assert persisted["status"] == "failed"
            assert persisted["error_summary"] == "sync failed"
            assert persisted["completed_at"] is not None
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            os.environ.pop("DATABASE_PATH", None)


def test_screening_task_service_persists_effective_trade_date_on_failed_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "screening_task_failed_trade_date.db")
        os.environ["DATABASE_PATH"] = db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()

        try:
            db = DatabaseManager.get_instance()
            factor_service = MagicMock()
            factor_service.get_latest_trade_date.return_value = date(2026, 3, 12)
            factor_service.build_factor_snapshot.side_effect = ValueError("factor build failed")

            market_data_sync_service = MagicMock()
            market_data_sync_service.sync_trade_date.return_value = {
                "trade_date": "2026-03-12",
                "total": 1,
                "synced": 1,
                "skipped": 0,
                "errors": [],
            }

            service = ScreeningTaskService(
                db_manager=db,
                universe_service=_SuccessUniverseService(),
                factor_service=factor_service,
                screener_service=MagicMock(),
                candidate_analysis_service=MagicMock(),
                market_data_sync_service=market_data_sync_service,
            )

            result = service.execute_run(
                trade_date=None,
                stock_codes=None,
                candidate_limit=30,
                ai_top_k=0,
            )

            persisted = db.get_screening_run(result["run_id"])
            assert result["status"] == "failed"
            assert persisted is not None
            assert persisted["trade_date"] == "2026-03-12"
            assert persisted["error_summary"] == "factor build failed"
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            os.environ.pop("DATABASE_PATH", None)


def test_screening_task_service_updates_trade_date_in_real_database():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "screening_task_success.db")
        os.environ["DATABASE_PATH"] = db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()

        try:
            db = DatabaseManager.get_instance()
            factor_service = MagicMock()
            factor_service.get_latest_trade_date.return_value = date(2026, 3, 13)
            factor_service.build_factor_snapshot.return_value = pd.DataFrame(
                [{"code": "600519", "name": "贵州茅台", "close": 1500.0, "rule_score": 0}]
            )

            screener_service = MagicMock()
            screener_service.evaluate.return_value.selected = []
            screener_service.evaluate.return_value.rejected = []

            market_data_sync_service = MagicMock()
            market_data_sync_service.sync_trade_date.return_value = {
                "trade_date": "2026-03-13",
                "total": 1,
                "synced": 1,
                "skipped": 0,
                "errors": [],
            }

            service = ScreeningTaskService(
                db_manager=db,
                universe_service=_SuccessUniverseService(),
                factor_service=factor_service,
                screener_service=screener_service,
                candidate_analysis_service=MagicMock(),
                market_data_sync_service=market_data_sync_service,
            )

            result = service.execute_run(
                trade_date=None,
                stock_codes=None,
                candidate_limit=30,
                ai_top_k=0,
            )

            persisted = db.get_screening_run(result["run_id"])
            assert result["status"] == "completed"
            assert persisted is not None
            assert persisted["trade_date"] == "2026-03-13"
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            os.environ.pop("DATABASE_PATH", None)
