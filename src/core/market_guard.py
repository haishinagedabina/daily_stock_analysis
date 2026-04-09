# -*- coding: utf-8 -*-
"""
Market-level MA100 risk control.

Checks whether the broad market index (default: Shanghai Composite sh000001) is
above its 100-day moving average.  When the index is below MA100, individual
stock signals should be treated with extra caution.

Design: MarketGuard is the L1 hard gate of the five-layer system.  When the
market regime is ``stand_aside``, the pipeline MUST output zero candidates.
When ``defensive``, candidate output is capped (see screening_task_service).
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_INDEX_CODE = "sh000001"
MIN_DATA_ROWS = 100


@dataclass
class MarketGuardResult:
    """Result of the market-level MA100 safety check."""
    is_safe: bool = False
    index_code: str = ""
    index_price: float = 0.0
    index_ma100: float = 0.0
    message: str = ""


class MarketGuard:
    """Assess market-level risk using index MA100."""

    def __init__(self, fetcher_manager, index_code: str = DEFAULT_INDEX_CODE):
        self._fetcher = fetcher_manager
        self._index_code = index_code

    def _fetch_index_data(self) -> tuple[pd.DataFrame, str]:
        """Fetch index history, using a dedicated path for the Shanghai Composite."""
        if self._index_code == DEFAULT_INDEX_CODE:
            import akshare as ak

            df = ak.stock_zh_index_daily(symbol=DEFAULT_INDEX_CODE)
            return df, "AkshareIndexDaily"

        return self._fetcher.get_daily_data(self._index_code, days=200)

    def get_index_bars(self) -> pd.DataFrame | None:
        """获取指数日线数据（公开接口，供 MarketEnvironmentEngine 等外部使用）。"""
        try:
            df, _ = self._fetch_index_data()
            return df
        except Exception as e:
            logger.warning("MarketGuard.get_index_bars failed: %s", e)
            return None

    def check(self) -> MarketGuardResult:
        try:
            df, _source = self._fetch_index_data()
        except Exception as e:
            logger.warning("MarketGuard: failed to fetch index data: %s", e)
            return MarketGuardResult(
                is_safe=True,
                index_code=self._index_code,
                message=f"Error fetching index data, defaulting to safe: {e}",
            )

        if df is None or df.empty:
            return MarketGuardResult(
                is_safe=True,
                index_code=self._index_code,
                message="Empty index data, defaulting to safe",
            )

        if len(df) < MIN_DATA_ROWS:
            return MarketGuardResult(
                is_safe=True,
                index_code=self._index_code,
                message=f"Insufficient data ({len(df)} rows < {MIN_DATA_ROWS}), defaulting to safe",
            )

        df = df.sort_values("date").reset_index(drop=True)
        ma100 = df["close"].rolling(window=100).mean()
        latest_price = float(df["close"].iloc[-1])
        latest_ma100 = float(ma100.iloc[-1])

        if np.isnan(latest_ma100):
            return MarketGuardResult(
                is_safe=True,
                index_code=self._index_code,
                index_price=latest_price,
                message="MA100 is NaN, defaulting to safe",
            )

        is_safe = latest_price > latest_ma100
        pct = (latest_price - latest_ma100) / latest_ma100 * 100

        if is_safe:
            msg = f"Index {self._index_code} above MA100 ({latest_price:.2f} > {latest_ma100:.2f}, +{pct:.1f}%)"
        else:
            msg = f"Index {self._index_code} below MA100 ({latest_price:.2f} < {latest_ma100:.2f}, {pct:.1f}%)"

        return MarketGuardResult(
            is_safe=is_safe,
            index_code=self._index_code,
            index_price=latest_price,
            index_ma100=latest_ma100,
            message=msg,
        )
