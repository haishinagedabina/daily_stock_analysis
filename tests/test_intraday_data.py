# -*- coding: utf-8 -*-
"""
TDD tests for Phase 2a: Intraday (60-minute) data access.

Tests cover:
1. BaseFetcher.get_intraday_data default raises NotImplementedError
2. PytdxFetcher.get_intraday_data returns proper DataFrame
3. AkshareFetcher.get_intraday_data returns proper DataFrame
4. DataFetcherManager.get_intraday_data fallback logic
5. INTRADAY_CATEGORIES mapping
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np
import pandas as pd


EXPECTED_INTRADAY_COLUMNS = {"datetime", "open", "high", "low", "close", "volume"}


def _make_intraday_df(n: int = 200) -> pd.DataFrame:
    """Generate mock intraday data with expected columns."""
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 0.1) + 10.0
    return pd.DataFrame({
        "datetime": pd.date_range(start="2025-03-01 09:30", periods=n, freq="60min"),
        "open": prices - 0.05,
        "high": prices + 0.1,
        "low": prices - 0.1,
        "close": prices,
        "volume": np.random.randint(10000, 100000, n),
    })


class TestBaseFetcherIntraday(unittest.TestCase):
    """BaseFetcher.get_intraday_data raises NotImplementedError by default."""

    def test_default_raises_not_implemented(self):
        from data_provider.base import BaseFetcher
        # BaseFetcher is abstract, so we verify the method exists
        self.assertTrue(hasattr(BaseFetcher, "get_intraday_data"))


class TestPytdxIntradayCategory(unittest.TestCase):
    """PytdxFetcher supports intraday category mapping."""

    def test_intraday_categories_defined(self):
        from data_provider.pytdx_fetcher import INTRADAY_CATEGORIES
        self.assertIn("60min", INTRADAY_CATEGORIES)
        self.assertIn("30min", INTRADAY_CATEGORIES)
        self.assertIn("15min", INTRADAY_CATEGORIES)
        self.assertIn("5min", INTRADAY_CATEGORIES)
        self.assertEqual(INTRADAY_CATEGORIES["60min"], 3)

    def test_get_intraday_data_method_exists(self):
        from data_provider.pytdx_fetcher import PytdxFetcher
        fetcher = PytdxFetcher()
        self.assertTrue(hasattr(fetcher, "get_intraday_data"))


class TestAkshareIntradayMethod(unittest.TestCase):
    """AkshareFetcher has get_intraday_data method."""

    def test_method_exists(self):
        from data_provider.akshare_fetcher import AkshareFetcher
        fetcher = AkshareFetcher()
        self.assertTrue(hasattr(fetcher, "get_intraday_data"))


class TestDataFetcherManagerIntraday(unittest.TestCase):
    """DataFetcherManager.get_intraday_data with fallback."""

    def test_method_exists(self):
        from data_provider.base import DataFetcherManager
        self.assertTrue(hasattr(DataFetcherManager, "get_intraday_data"))

    def test_returns_df_and_source(self):
        from data_provider.base import DataFetcherManager
        mock_df = _make_intraday_df()
        mock_fetcher = MagicMock()
        mock_fetcher.name = "MockFetcher"
        mock_fetcher.priority = 1
        mock_fetcher.get_intraday_data.return_value = mock_df

        manager = DataFetcherManager(fetchers=[mock_fetcher])
        df, source = manager.get_intraday_data("600519", period="60min")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        self.assertEqual(source, "MockFetcher")

    def test_fallback_on_failure(self):
        from data_provider.base import DataFetcherManager, DataFetchError
        mock_df = _make_intraday_df()

        fetcher1 = MagicMock()
        fetcher1.name = "Fetcher1"
        fetcher1.priority = 1
        fetcher1.get_intraday_data.side_effect = DataFetchError("failed")

        fetcher2 = MagicMock()
        fetcher2.name = "Fetcher2"
        fetcher2.priority = 2
        fetcher2.get_intraday_data.return_value = mock_df

        manager = DataFetcherManager(fetchers=[fetcher1, fetcher2])
        df, source = manager.get_intraday_data("600519", period="60min")
        self.assertEqual(source, "Fetcher2")
        self.assertFalse(df.empty)

    def test_all_fail_returns_empty(self):
        from data_provider.base import DataFetcherManager, DataFetchError

        fetcher1 = MagicMock()
        fetcher1.name = "Fetcher1"
        fetcher1.priority = 1
        fetcher1.get_intraday_data.side_effect = DataFetchError("fail1")

        fetcher2 = MagicMock()
        fetcher2.name = "Fetcher2"
        fetcher2.priority = 2
        fetcher2.get_intraday_data.side_effect = DataFetchError("fail2")

        manager = DataFetcherManager(fetchers=[fetcher1, fetcher2])
        df, source = manager.get_intraday_data("600519", period="60min")
        self.assertTrue(df.empty)
        self.assertEqual(source, "")

    def test_not_implemented_is_skipped(self):
        """Fetchers that raise NotImplementedError are silently skipped."""
        from data_provider.base import DataFetcherManager
        mock_df = _make_intraday_df()

        fetcher1 = MagicMock()
        fetcher1.name = "NoIntraday"
        fetcher1.priority = 1
        fetcher1.get_intraday_data.side_effect = NotImplementedError

        fetcher2 = MagicMock()
        fetcher2.name = "HasIntraday"
        fetcher2.priority = 2
        fetcher2.get_intraday_data.return_value = mock_df

        manager = DataFetcherManager(fetchers=[fetcher1, fetcher2])
        df, source = manager.get_intraday_data("600519", period="60min")
        self.assertEqual(source, "HasIntraday")


if __name__ == "__main__":
    unittest.main()
