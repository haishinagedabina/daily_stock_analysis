import os
import tempfile
import unittest
from datetime import date

import pandas as pd

from src.config import Config
from src.services.universe_service import UniverseService
from src.storage import DatabaseManager


class _FakeFetcher:
    def __init__(self, df=None, should_raise: bool = False):
        self._df = df
        self._should_raise = should_raise

    def get_stock_list(self):
        if self._should_raise:
            raise RuntimeError("fetch failed")
        return self._df


class _FakeFetcherManager:
    def __init__(self, fetchers):
        self._fetchers = fetchers


class _InvalidSchemaFetcher:
    def get_stock_list(self):
        return pd.DataFrame([{"ticker": "600519", "title": "贵州茅台"}])


class _InvalidCodeValueFetcher:
    def get_stock_list(self):
        return pd.DataFrame(
            [
                {"code": None, "name": "空代码"},
                {"code": "   ", "name": "空白代码"},
            ]
        )


class UniverseServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_universe_service.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_sync_universe_uses_fallback_fetcher_and_is_idempotent(self) -> None:
        fallback_df = pd.DataFrame(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "market": "主板",
                    "industry": "白酒",
                    "list_date": "2001-08-27",
                },
                {
                    "code": "000001",
                    "name": "*ST平安",
                    "market": "主板",
                    "industry": "银行",
                    "list_date": "1991-04-03",
                },
            ]
        )
        service = UniverseService(
            db_manager=self.db,
            fetcher_manager=_FakeFetcherManager(
                [
                    _FakeFetcher(should_raise=True),
                    _FakeFetcher(df=fallback_df),
                ]
            ),
        )

        result = service.sync_universe()
        self.assertEqual(result["saved_count"], 2)
        self.assertEqual(result["source"], "_FakeFetcher")

        active = service.resolve_universe()
        self.assertEqual([item["code"] for item in active.to_dict("records")], ["600519"])
        self.assertFalse(active.iloc[0]["is_st"])

        second = service.sync_universe()
        self.assertEqual(second["saved_count"], 2)
        active_again = service.resolve_universe()
        self.assertEqual(len(active_again), 1)

    def test_resolve_requested_codes_uses_local_instrument_master_then_fallback_names(self) -> None:
        self.db.upsert_instruments(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "market": "cn",
                    "exchange": "SSE",
                    "listing_status": "active",
                    "is_st": False,
                    "industry": "白酒",
                    "list_date": date(2001, 8, 27),
                }
            ]
        )
        service = UniverseService(db_manager=self.db, fetcher_manager=_FakeFetcherManager([]))

        universe = service.resolve_universe(stock_codes=["600519", "300750"])

        self.assertEqual([item["code"] for item in universe.to_dict("records")], ["600519", "300750"])
        self.assertEqual(universe.iloc[0]["name"], "贵州茅台")
        self.assertEqual(universe.iloc[1]["name"], "300750")

    def test_sync_universe_raises_diagnostic_error_when_all_fetchers_fail(self) -> None:
        service = UniverseService(
            db_manager=self.db,
            fetcher_manager=_FakeFetcherManager(
                [
                    _FakeFetcher(should_raise=True),
                    _FakeFetcher(should_raise=True),
                ]
            ),
        )

        with self.assertRaises(RuntimeError) as context:
            service.sync_universe()

        message = str(context.exception)
        self.assertIn("未能从任何数据源获取股票池主数据", message)
        self.assertIn("_FakeFetcher: fetch failed", message)

    def test_sync_universe_falls_back_when_provider_returns_invalid_schema(self) -> None:
        fallback_df = pd.DataFrame(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "industry": "白酒",
                    "list_date": "2001-08-27",
                }
            ]
        )
        service = UniverseService(
            db_manager=self.db,
            fetcher_manager=_FakeFetcherManager(
                [
                    _InvalidSchemaFetcher(),
                    _FakeFetcher(df=fallback_df),
                ]
            ),
        )

        result = service.sync_universe()

        self.assertEqual(result["saved_count"], 1)
        active = service.resolve_universe()
        self.assertEqual([item["code"] for item in active.to_dict("records")], ["600519"])

    def test_sync_universe_falls_back_when_provider_returns_invalid_code_values(self) -> None:
        fallback_df = pd.DataFrame(
            [
                {
                    "code": "000001",
                    "name": "平安银行",
                    "industry": "银行",
                    "list_date": "1991-04-03",
                }
            ]
        )
        service = UniverseService(
            db_manager=self.db,
            fetcher_manager=_FakeFetcherManager(
                [
                    _InvalidCodeValueFetcher(),
                    _FakeFetcher(df=fallback_df),
                ]
            ),
        )

        result = service.sync_universe()

        self.assertEqual(result["saved_count"], 1)
        active = service.resolve_universe()
        self.assertEqual([item["code"] for item in active.to_dict("records")], ["000001"])


if __name__ == "__main__":
    unittest.main()
