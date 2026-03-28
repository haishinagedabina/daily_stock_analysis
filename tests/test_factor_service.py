import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from src.config import Config
from src.services.factor_service import FactorService
from src.services.theme_context_ingest_service import ExternalTheme, OpenClawThemeContext
from src.storage import DatabaseManager


class FactorServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_factor_service.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = FactorService(self.db, lookback_days=40, breakout_lookback_days=20)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_build_factor_snapshot_uses_prior_window_for_breakout_and_volume_ratio(self) -> None:
        start_date = date(2026, 2, 20)
        rows = []
        for idx in range(21):
            trade_date = start_date + timedelta(days=idx)
            close = 10.0 + idx * 0.1
            high = close + 0.2
            volume = 1000 + idx * 10
            amount = volume * close
            rows.append(
                {
                    "date": trade_date,
                    "open": close - 0.1,
                    "high": high,
                    "low": close - 0.2,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                    "pct_chg": 1.0,
                }
            )

        rows[-1]["close"] = 15.0
        rows[-1]["high"] = 15.3
        rows[-1]["volume"] = 5000
        rows[-1]["amount"] = 75_000

        df = pd.DataFrame(rows)
        self.db.save_daily_data(df, "600519", data_source="test")

        universe_df = pd.DataFrame(
            [{"code": "600519", "name": "贵州茅台", "is_st": False, "list_date": date(2020, 1, 1)}]
        )
        snapshot_df = self.service.build_factor_snapshot(universe_df=universe_df, trade_date=rows[-1]["date"])

        self.assertEqual(len(snapshot_df), 1)
        row = snapshot_df.iloc[0]
        self.assertGreater(row["breakout_ratio"], 1.0)
        self.assertGreater(row["volume_ratio"], 3.0)
        self.assertEqual(row["days_since_listed"], (rows[-1]["date"] - date(2020, 1, 1)).days)

    def test_get_latest_trade_date_returns_latest_available_date(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "date": date(2026, 3, 10),
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.8,
                    "close": 10.1,
                    "volume": 1000,
                    "amount": 10_100,
                    "pct_chg": 1.0,
                },
                {
                    "date": date(2026, 3, 11),
                    "open": 10.2,
                    "high": 10.4,
                    "low": 10.0,
                    "close": 10.3,
                    "volume": 1100,
                    "amount": 11_330,
                    "pct_chg": 1.2,
                },
            ]
        )
        self.db.save_daily_data(df, "000001", data_source="test")

        universe_df = pd.DataFrame([{"code": "000001", "name": "平安银行", "is_st": False, "list_date": None}])
        latest_date = self.service.get_latest_trade_date(universe_df)

        self.assertEqual(latest_date, date(2026, 3, 11))

    def test_build_factor_snapshot_can_persist_snapshots(self) -> None:
        start_date = date(2026, 3, 1)
        rows = []
        for idx in range(21):
            trade_date = start_date + timedelta(days=idx)
            close = 20.0 + idx * 0.2
            rows.append(
                {
                    "date": trade_date,
                    "open": close - 0.1,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 1000 + idx * 50,
                    "amount": (1000 + idx * 50) * close,
                    "pct_chg": 1.0,
                }
            )

        df = pd.DataFrame(rows)
        self.db.save_daily_data(df, "300750", data_source="test")
        universe_df = pd.DataFrame(
            [{"code": "300750", "name": "宁德时代", "is_st": False, "list_date": date(2018, 6, 11)}]
        )

        snapshot_df = self.service.build_factor_snapshot(
            universe_df=universe_df,
            trade_date=rows[-1]["date"],
            persist=True,
        )

        self.assertEqual(len(snapshot_df), 1)
        stored = self.db.list_factor_snapshots(trade_date=rows[-1]["date"])
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["code"], "300750")
        self.assertIn("trend_score", stored[0])

    @patch("src.services.factor_service.get_config")
    def test_factor_service_uses_config_lookbacks_by_default(self, get_config_mock) -> None:
        get_config_mock.return_value.screening_factor_lookback_days = 120
        get_config_mock.return_value.screening_breakout_lookback_days = 30
        get_config_mock.return_value.screening_min_list_days = 180

        service = FactorService(self.db)

        self.assertEqual(service.lookback_days, 120)
        self.assertEqual(service.breakout_lookback_days, 30)
        self.assertEqual(service.min_list_days, 180)

    def test_build_risk_flags_uses_configurable_min_list_days(self) -> None:
        service = FactorService(self.db, min_list_days=180)

        risk_flags = service._build_risk_flags(
            is_st=False,
            days_since_listed=150,
            volume_ratio=1.5,
            breakout_ratio=1.0,
        )

        self.assertIn("new_listing", risk_flags)

    @patch("src.services.hot_theme_factor_enricher.HotThemeFactorEnricher.enrich_snapshot")
    def test_build_factor_snapshot_passes_resolved_boards_to_theme_enricher(self, enrich_snapshot_mock) -> None:
        start_date = date(2026, 3, 1)
        rows = []
        for idx in range(21):
            trade_date = start_date + timedelta(days=idx)
            close = 20.0 + idx * 0.2
            rows.append(
                {
                    "date": trade_date,
                    "open": close - 0.1,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 1000 + idx * 50,
                    "amount": (1000 + idx * 50) * close,
                    "pct_chg": 1.0,
                }
            )

        df = pd.DataFrame(rows)
        self.db.save_daily_data(df, "300750", data_source="test")
        universe_df = pd.DataFrame(
            [{"code": "300750", "name": "寒武纪", "is_st": False, "list_date": date(2018, 6, 11)}]
        )
        theme_context = OpenClawThemeContext(
            source="openclaw",
            trade_date="2026-03-21",
            market="cn",
            themes=[
                ExternalTheme(
                    name="AI芯片",
                    heat_score=90.0,
                    confidence=0.9,
                    catalyst_summary="政策催化",
                    keywords=["AI", "芯片", "算力"],
                    evidence=[],
                )
            ],
            accepted_at="2026-03-21T15:00:00",
        )

        class _FakeFetcherManager:
            def get_belong_boards(self, stock_code: str):
                return [{"name": "AI芯片"}, {"name": "算力"}]

        service = FactorService(
            self.db,
            lookback_days=40,
            breakout_lookback_days=20,
            theme_context=theme_context,
            fetcher_manager=_FakeFetcherManager(),
        )
        enrich_snapshot_mock.side_effect = lambda snapshot, theme_context, boards: {
            **snapshot,
            "theme_boards": boards,
            "is_hot_theme_stock": True,
        }

        snapshot_df = service.build_factor_snapshot(
            universe_df=universe_df,
            trade_date=rows[-1]["date"],
        )

        self.assertEqual(len(snapshot_df), 1)
        self.assertEqual(enrich_snapshot_mock.call_args.kwargs["boards"], ["AI芯片", "算力"])
        self.assertEqual(snapshot_df.iloc[0]["theme_boards"], ["AI芯片", "算力"])


if __name__ == "__main__":
    unittest.main()
