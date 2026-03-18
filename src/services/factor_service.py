from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import func, select

from src.config import get_config
from src.storage import DatabaseManager, StockDaily


class FactorService:
    """从本地日线数据构建筛选输入。"""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        lookback_days: Optional[int] = None,
        breakout_lookback_days: Optional[int] = None,
        min_list_days: Optional[int] = None,
    ) -> None:
        config = get_config()
        self.db = db_manager or DatabaseManager.get_instance()
        self.lookback_days = (
            lookback_days if lookback_days is not None else config.screening_factor_lookback_days
        )
        self.min_list_days = (
            min_list_days if min_list_days is not None else config.screening_min_list_days
        )
        self.breakout_lookback_days = (
            breakout_lookback_days
            if breakout_lookback_days is not None
            else config.screening_breakout_lookback_days
        )

    def build_factor_snapshot(
        self,
        universe_df: pd.DataFrame,
        trade_date: Optional[date] = None,
        persist: bool = False,
    ) -> pd.DataFrame:
        if universe_df is None or universe_df.empty:
            return pd.DataFrame()

        if trade_date is None:
            trade_date = datetime.now().date()

        codes = [str(code) for code in universe_df["code"].dropna().tolist()]
        if not codes:
            return pd.DataFrame()

        start_date = trade_date - timedelta(days=self.lookback_days * 2)
        with self.db.get_session() as session:
            rows = session.execute(
                select(StockDaily)
                .where(StockDaily.code.in_(codes), StockDaily.date >= start_date, StockDaily.date <= trade_date)
                .order_by(StockDaily.code, StockDaily.date)
            ).scalars().all()

        if not rows:
            return pd.DataFrame()

        bars = pd.DataFrame(
            [
                {
                    "code": row.code,
                    "date": row.date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "amount": row.amount,
                    "pct_chg": row.pct_chg,
                }
                for row in rows
            ]
        )

        snapshots = []
        universe_map = universe_df.set_index("code").to_dict("index")
        for code, group in bars.groupby("code"):
            group = group.sort_values("date").reset_index(drop=True)
            if len(group) < 20:
                continue

            latest_trade_date = pd.to_datetime(group.iloc[-1]["date"]).date()
            if latest_trade_date != trade_date:
                continue

            latest = group.iloc[-1]
            close_series = group["close"].astype(float)
            volume_series = group["volume"].astype(float).fillna(0.0)
            amount_series = group["amount"].astype(float).fillna(0.0)
            info = universe_map.get(code, {})
            list_date = info.get("list_date")
            if list_date:
                list_date = pd.to_datetime(list_date).date()
                days_since_listed = max((trade_date - list_date).days, 0)
            else:
                days_since_listed = 9999

            prior_bars = group.iloc[:-1]
            rolling_high = float(prior_bars["high"].tail(self.breakout_lookback_days).max()) if not prior_bars.empty else 0.0
            breakout_ratio = float(latest["close"]) / rolling_high if rolling_high else 0.0
            prior_amount = amount_series.iloc[:-1]
            prior_volume = volume_series.iloc[:-1]
            avg_amount = float(prior_amount.tail(5).mean()) if not prior_amount.empty else 0.0
            avg_volume = float(prior_volume.tail(5).mean()) if not prior_volume.empty else 0.0
            volume_ratio = float(latest["volume"]) / avg_volume if avg_volume else 0.0
            turnover_rate = round(min(volume_ratio * 2.0, 100.0), 4)
            trend_score = self._compute_trend_score(
                close=float(latest["close"]),
                ma5=float(close_series.tail(5).mean()),
                ma10=float(close_series.tail(10).mean()),
                ma20=float(close_series.tail(20).mean()),
                breakout_ratio=breakout_ratio,
            )
            liquidity_score = self._compute_liquidity_score(avg_amount=avg_amount, volume_ratio=volume_ratio)
            risk_flags = self._build_risk_flags(
                is_st=bool(info.get("is_st", False)),
                days_since_listed=int(days_since_listed),
                volume_ratio=volume_ratio,
                breakout_ratio=breakout_ratio,
            )

            extended = self._compute_extended_factors(group, latest, close_series)

            snapshots.append(
                {
                    "code": code,
                    "name": info.get("name") or code,
                    "close": float(latest["close"]),
                    "ma5": float(close_series.tail(5).mean()),
                    "ma10": float(close_series.tail(10).mean()),
                    "ma20": float(close_series.tail(20).mean()),
                    "ma60": float(close_series.tail(min(len(close_series), 60)).mean()),
                    "volume_ratio": round(volume_ratio, 4),
                    "avg_amount": round(avg_amount, 2),
                    "breakout_ratio": round(breakout_ratio, 4),
                    "pct_chg": float(latest["pct_chg"] or 0.0),
                    "is_st": bool(info.get("is_st", False)),
                    "days_since_listed": int(days_since_listed),
                    "turnover_rate": turnover_rate,
                    "trend_score": trend_score,
                    "liquidity_score": liquidity_score,
                    "risk_flags": risk_flags,
                    **extended,
                }
            )

        snapshot_df = pd.DataFrame(snapshots)
        if persist and not snapshot_df.empty:
            self.db.replace_factor_snapshots(trade_date=trade_date, snapshots=snapshot_df.to_dict("records"))
        return snapshot_df

    def get_latest_trade_date(self, universe_df: pd.DataFrame) -> Optional[date]:
        """返回当前股票池在本地日线表中的最新交易日。"""
        if universe_df is None or universe_df.empty:
            return None

        codes = [str(code) for code in universe_df["code"].dropna().tolist()]
        if not codes:
            return None

        with self.db.get_session() as session:
            latest = session.execute(
                select(func.max(StockDaily.date)).where(StockDaily.code.in_(codes))
            ).scalar_one_or_none()
        return latest

    @staticmethod
    def _compute_trend_score(close: float, ma5: float, ma10: float, ma20: float, breakout_ratio: float) -> float:
        score = 0.0
        if close >= ma20:
            score += 25.0
        if ma5 >= ma10 >= ma20:
            score += 45.0
        if breakout_ratio >= 1.0:
            score += 15.0
        elif breakout_ratio >= 0.995:
            score += 10.0
        return round(min(score, 100.0), 2)

    @staticmethod
    def _compute_liquidity_score(avg_amount: float, volume_ratio: float) -> float:
        amount_score = min(avg_amount / 1_000_000, 80.0)
        volume_score = min(volume_ratio * 10, 20.0)
        return round(min(amount_score + volume_score, 100.0), 2)

    def _build_risk_flags(
        self,
        is_st: bool,
        days_since_listed: int,
        volume_ratio: float,
        breakout_ratio: float,
    ) -> list[str]:
        flags = []
        if is_st:
            flags.append("st")
        if days_since_listed < self.min_list_days:
            flags.append("new_listing")
        if volume_ratio < 1.0:
            flags.append("low_volume")
        if breakout_ratio < 0.98:
            flags.append("far_from_breakout")
        return flags

    def _compute_extended_factors(
        self,
        group: pd.DataFrame,
        latest: pd.Series,
        close_series: pd.Series,
    ) -> dict:
        """Compute additional factor dimensions used by strategy screening."""
        close = float(latest["close"])
        ma5 = float(close_series.tail(5).mean()) if len(close_series) >= 5 else close

        pct_chg_5d = 0.0
        if len(close_series) >= 6:
            prev_5 = float(close_series.iloc[-6])
            pct_chg_5d = round((close - prev_5) / prev_5 * 100.0, 4) if prev_5 else 0.0

        pct_chg_20d = 0.0
        if len(close_series) >= 21:
            prev_20 = float(close_series.iloc[-21])
            pct_chg_20d = round((close - prev_20) / prev_20 * 100.0, 4) if prev_20 else 0.0

        ma5_distance_pct = round(abs(close - ma5) / ma5 * 100.0, 4) if ma5 else 0.0

        high = float(latest.get("high", close))
        low = float(latest.get("low", close))
        prev_close = float(close_series.iloc[-2]) if len(close_series) >= 2 else close
        amplitude = round((high - low) / prev_close * 100.0, 4) if prev_close else 0.0

        tail_bars = group.tail(5) if len(group) >= 5 else group.tail(1)
        candle_pattern = self._detect_candle_pattern(tail_bars)

        return {
            "pct_chg_5d": pct_chg_5d,
            "pct_chg_20d": pct_chg_20d,
            "ma5_distance_pct": ma5_distance_pct,
            "amplitude": amplitude,
            "candle_pattern": candle_pattern,
        }

    @staticmethod
    def _detect_candle_pattern(bars: pd.DataFrame) -> str:
        """Detect basic candlestick pattern from recent bars.

        Returns a pattern identifier string. Operates on the last row for single-bar
        patterns, and on all rows for multi-bar patterns.
        """
        if bars.empty:
            return "unknown"

        latest = bars.iloc[-1]
        o, h, l, c = float(latest["open"]), float(latest["high"]), float(latest["low"]), float(latest["close"])
        pct = float(latest.get("pct_chg", 0.0) or 0.0)
        body = abs(c - o)
        total_range = h - l if h > l else 0.001

        body_ratio = body / total_range

        if body_ratio < 0.15 and total_range / max(l, 0.01) > 0.02:
            return "doji"

        if pct >= 5.0 and body_ratio > 0.6 and c > o:
            return "big_yang"

        if pct <= -5.0 and body_ratio > 0.6 and c < o:
            return "big_yin"

        if len(bars) >= 5:
            pattern = _detect_one_yang_three_yin(bars)
            if pattern:
                return pattern

        return "normal"


def _detect_one_yang_three_yin(bars: pd.DataFrame) -> str | None:
    """Detect the one-yang-three-yin pattern across last 5 bars."""
    if len(bars) < 5:
        return None

    last5 = bars.tail(5).reset_index(drop=True)
    day1 = last5.iloc[0]
    day5 = last5.iloc[4]

    d1_o, d1_c = float(day1["open"]), float(day1["close"])
    d5_o, d5_c = float(day5["open"]), float(day5["close"])

    if d1_c <= d1_o or (d1_c - d1_o) / max(d1_o, 0.01) < 0.02:
        return None

    for i in range(1, 4):
        bar = last5.iloc[i]
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])
        if bar_low < d1_o:
            return None
        if bar_close > d1_c:
            return None

    if d5_c <= d5_o or d5_c < d1_c:
        return None

    return "one_yang_three_yin"
