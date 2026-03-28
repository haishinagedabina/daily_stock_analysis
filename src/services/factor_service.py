from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from src.config import get_config
from src.storage import DatabaseManager, StockDaily
from src.indicators.ma_breakout_detector import MABreakoutDetector
from src.indicators.gap_detector import GapDetector
from src.indicators.limit_up_detector import LimitUpDetector
from src.indicators.divergence_detector import DivergenceDetector
from src.indicators.trendline_detector import TrendlineDetector
from src.indicators.pattern_detector import PatternDetector
from src.indicators.low_123_trendline_detector import Low123TrendlineDetector
from src.indicators.bottom_divergence_breakout_detector import (
    BottomDivergenceBreakoutDetector,
)


class FactorService:
    """从本地日线数据构建筛选输入。"""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        lookback_days: Optional[int] = None,
        breakout_lookback_days: Optional[int] = None,
        min_list_days: Optional[int] = None,
        theme_context: Optional[object] = None,
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
        self.theme_context = theme_context

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

        # 分批加载日线数据，防止一次性 OOM（5000 只 × 400 天 ≈ 200 万行）
        _FACTOR_BATCH_SIZE = 500
        all_bar_dicts: list = []
        for batch_start in range(0, len(codes), _FACTOR_BATCH_SIZE):
            batch_codes = codes[batch_start:batch_start + _FACTOR_BATCH_SIZE]
            with self.db.get_session() as session:
                rows = session.execute(
                    select(StockDaily)
                    .where(
                        StockDaily.code.in_(batch_codes),
                        StockDaily.date >= start_date,
                        StockDaily.date <= trade_date,
                    )
                    .order_by(StockDaily.code, StockDaily.date)
                ).scalars().all()
            all_bar_dicts.extend(
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
            )

        if not all_bar_dicts:
            return pd.DataFrame()

        bars = pd.DataFrame(all_bar_dicts)

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
                    "ma100": float(close_series.tail(min(len(close_series), 100)).mean()) if len(close_series) >= 100 else 0.0,
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

        # 应用热点题材因子富化
        if self.theme_context and not snapshot_df.empty:
            from src.services.hot_theme_factor_enricher import HotThemeFactorEnricher
            enricher = HotThemeFactorEnricher()
            enriched_records = []
            for record in snapshot_df.to_dict("records"):
                enriched = enricher.enrich_snapshot(
                    snapshot=record,
                    theme_context=self.theme_context,
                    boards=[]
                )
                enriched_records.append(enriched)
            snapshot_df = pd.DataFrame(enriched_records)

        if persist and not snapshot_df.empty:
            self.db.replace_factor_snapshots(trade_date=trade_date, snapshots=snapshot_df.to_dict("records"))
        return snapshot_df

    def get_latest_trade_date(
        self,
        universe_df: pd.DataFrame,
        min_coverage_ratio: float = 0.5,
    ) -> Optional[date]:
        """
        返回本地日线表中覆盖率足够的最新交易日。

        避免被少量"毒数据"（如部分同步导致的零星未来日期记录）污染：
        只有当某个日期拥有 >= universe 数量 * min_coverage_ratio 条记录时，
        才认定该日期为可用交易日。

        Args:
            universe_df: 股票池 DataFrame，需含 code 列
            min_coverage_ratio: 覆盖率下限，默认 0.5（至少覆盖一半股票池）
        """
        if universe_df is None or universe_df.empty:
            return None

        codes = [str(code) for code in universe_df["code"].dropna().tolist()]
        if not codes:
            return None

        min_count = max(1, int(len(codes) * min_coverage_ratio))

        with self.db.get_session() as session:
            # 按日期倒序查找，取第一个覆盖率达标的日期
            from sqlalchemy import desc
            row = session.execute(
                select(StockDaily.date, func.count(StockDaily.code.distinct()).label("cnt"))
                .where(StockDaily.code.in_(codes))
                .group_by(StockDaily.date)
                .having(func.count(StockDaily.code.distinct()) >= min_count)
                .order_by(desc(StockDaily.date))
                .limit(1)
            ).first()
        return row[0] if row else None

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

        # MA100 strategy factors
        ma100_factors = self._compute_ma100_factors(group, close_series, close)

        # Gap / limit-up factors
        gap_limit_factors = self._compute_gap_limit_factors(group)

        # MACD divergence factors
        macd_factors = self._compute_macd_divergence_factors(group)

        # Trendline factors
        trendline_factors = self._compute_trendline_factors(group)

        # 123 pattern factors
        pattern_123_factors, pattern_123_raw = self._compute_pattern_123_factors(group)

        # Bottom divergence double breakout factors
        bottom_div_factors = self._compute_bottom_divergence_factors(group)

        # MA100 + Low-123 combined factors (Strategy 2)
        ma100_low123_factors = self._compute_ma100_low123_combined_factors(
            ma100_factors, pattern_123_factors, pattern_123_raw, group
        )

        # MA100 + 60-min combined factors (Strategy 3)
        ma100_60min_factors = self._compute_ma100_60min_combined_factors(ma100_factors)

        return {
            "pct_chg_5d": pct_chg_5d,
            "pct_chg_20d": pct_chg_20d,
            "ma5_distance_pct": ma5_distance_pct,
            "amplitude": amplitude,
            "candle_pattern": candle_pattern,
            **ma100_factors,
            **gap_limit_factors,
            **macd_factors,
            **trendline_factors,
            **pattern_123_factors,
            **bottom_div_factors,
            **ma100_low123_factors,
            **ma100_60min_factors,
        }

    @staticmethod
    def _compute_ma100_factors(group: pd.DataFrame, close_series: pd.Series, close: float) -> dict:
        """Compute MA100-related factors for screening strategies C/D."""
        n = len(close_series)
        ma100 = float(close_series.tail(min(n, 100)).mean()) if n >= 100 else 0.0
        above_ma100 = close > ma100 if ma100 > 0 else False
        ma100_distance_pct = round((close - ma100) / ma100 * 100.0, 4) if ma100 > 0 else 0.0

        ma100_breakout = MABreakoutDetector.detect_breakout(group, ma_period=100) if n >= 100 else {}
        breakout_days = ma100_breakout.get("breakout_days", 0)

        pullback_ma100 = MABreakoutDetector.detect_pullback_support(group, ma_period=100) if n >= 100 else {}
        pullback_ma20 = MABreakoutDetector.detect_pullback_support(group, ma_period=20) if n >= 20 else {}

        # Stop-loss: highest MA below price
        ma20 = float(close_series.tail(min(n, 20)).mean()) if n >= 20 else 0.0
        stop_loss_price = 0.0
        stop_loss_ma = ""
        if ma20 > 0 and ma20 < close:
            stop_loss_price = round(ma20, 4)
            stop_loss_ma = "MA20"
        if ma100 > 0 and ma100 < close and ma100 > stop_loss_price:
            stop_loss_price = round(ma100, 4)
            stop_loss_ma = "MA100"

        return {
            "ma100": round(ma100, 4),
            "above_ma100": above_ma100,
            "ma100_distance_pct": ma100_distance_pct,
            "ma100_breakout_days": breakout_days,
            "pullback_ma100": pullback_ma100.get("is_pullback_support", False),
            "pullback_ma20": pullback_ma20.get("is_pullback_support", False),
            "stop_loss_price": stop_loss_price,
            "stop_loss_ma": stop_loss_ma,
        }

    @staticmethod
    def _compute_gap_limit_factors(group: pd.DataFrame) -> dict:
        """Compute gap and limit-up factors for screening strategy C."""
        gap_result = GapDetector.detect_breakaway_gap(group)
        pct_chg = float(group.iloc[-1].get("pct_chg", 0)) if not group.empty else 0.0
        limit_result = LimitUpDetector.is_breakout_limit_up(group)

        return {
            "gap_up": gap_result.get("is_gap_up", False),
            "gap_breakaway": gap_result.get("is_breakaway", False),
            "is_limit_up": limit_result.get("is_limit_up", False),
            "limit_up_breakout": limit_result.get("is_breakout_high", False),
        }

    @staticmethod
    def _compute_macd_divergence_factors(group: pd.DataFrame) -> dict:
        """Compute MACD divergence factors from daily data."""
        if len(group) < 35:
            return {
                "macd_bull_divergence": False,
                "macd_bear_divergence": False,
            }
        df_for_div = group[["close"]].copy()
        if "high" in group.columns:
            df_for_div["high"] = group["high"].values
        if "low" in group.columns:
            df_for_div["low"] = group["low"].values
        bull = DivergenceDetector.detect_bullish(df_for_div)
        bear = DivergenceDetector.detect_bearish(df_for_div)
        return {
            "macd_bull_divergence": bull.get("found", False),
            "macd_bear_divergence": bear.get("found", False),
        }

    @staticmethod
    def _compute_trendline_factors(group: pd.DataFrame) -> dict:
        """Compute trendline breakout factors for screening strategy A."""
        if len(group) < 20:
            return {"trendline_breakout": False, "trendline_touch_count": 0}
        tl_result = TrendlineDetector.detect_trendline_breakout(group)
        is_breakout = tl_result.get("breakout", False) and tl_result.get("direction") == "up"
        downtrend = tl_result.get("downtrend") or {}
        touch_count = downtrend.get("touch_count", 0) if is_breakout else 0
        return {
            "trendline_breakout": is_breakout,
            "trendline_touch_count": touch_count,
        }

    @staticmethod
    def _compute_pattern_123_factors(group: pd.DataFrame) -> tuple[dict, dict]:
        """Compute 123 bottom pattern factors for screening strategy B.

        Returns:
            (factors_dict, raw_detector_result) — the raw result is used by
            downstream combined-strategy methods to build detailed hit_reasons.
        """
        empty_raw: dict = {}
        if len(group) < 40:
            return {
                # Legacy fields (kept for backward compatibility)
                "pattern_123_bottom": False,
                "pattern_123_breakout": False,
                "pattern_123_higher_low_pct": 0.0,
                # New joint-detector fields
                "pattern_123_low_trendline": False,
                "pattern_123_state": "rejected",
                "pattern_123_entry_price": None,
                "pattern_123_stop_loss": None,
                "pattern_123_signal_strength": 0.0,
                "pattern_123_rejection_reason": "insufficient_data",
            }, empty_raw

        # Legacy (PatternDetector) — kept for backward compat
        legacy = PatternDetector.detect_123_bottom(group)
        found_legacy = legacy.get("found", False)
        confirmed_legacy = legacy.get("breakout_confirmed", False)
        higher_low_pct = 0.0
        if found_legacy and legacy.get("point1") and legacy.get("point3"):
            p1 = legacy["point1"]["price"]
            p3 = legacy["point3"]["price"]
            if p1 > 0:
                higher_low_pct = round((p3 - p1) / p1 * 100.0, 4)

        # Joint detector
        joint = Low123TrendlineDetector.detect(group)
        state = joint.get("state", "rejected")

        factors = {
            # Legacy fields
            "pattern_123_bottom": found_legacy,
            "pattern_123_breakout": confirmed_legacy,
            "pattern_123_higher_low_pct": higher_low_pct,
            # New joint-detector fields
            "pattern_123_low_trendline": state == "confirmed",
            "pattern_123_state": state,
            "pattern_123_entry_price": joint.get("entry_price"),
            "pattern_123_stop_loss": joint.get("stop_loss_price"),
            "pattern_123_signal_strength": joint.get("signal_strength", 0.0),
            "pattern_123_rejection_reason": joint.get("rejection_reason"),
        }
        return factors, joint

    @staticmethod
    def _compute_bottom_divergence_factors(group: pd.DataFrame) -> dict:
        """Compute bottom divergence double breakout factors."""
        if len(group) < 60:
            return {
                "bottom_divergence_double_breakout": False,
                "bottom_divergence_state": "rejected",
                "bottom_divergence_pattern_code": None,
                "bottom_divergence_pattern_label": None,
                "bottom_divergence_signal_strength": 0.0,
                "bottom_divergence_entry_price": None,
                "bottom_divergence_stop_loss": None,
                "bottom_divergence_horizontal_breakout": False,
                "bottom_divergence_trendline_breakout": False,
                "bottom_divergence_sync_breakout": False,
                "bottom_divergence_hit_reasons": [],
            }

        result = BottomDivergenceBreakoutDetector.detect(group)
        state = result.get("state", "rejected")

        return {
            "bottom_divergence_double_breakout": state == "confirmed",
            "bottom_divergence_state": state,
            "bottom_divergence_pattern_code": result.get("pattern_code"),
            "bottom_divergence_pattern_label": result.get("pattern_label"),
            "bottom_divergence_signal_strength": result.get("signal_strength", 0.0),
            "bottom_divergence_entry_price": result.get("entry_price"),
            "bottom_divergence_stop_loss": result.get("stop_loss_price"),
            "bottom_divergence_horizontal_breakout": result.get(
                "horizontal_breakout_confirmed", False
            ),
            "bottom_divergence_trendline_breakout": result.get(
                "trendline_breakout_confirmed", False
            ),
            "bottom_divergence_sync_breakout": result.get("double_breakout_sync", False),
            "bottom_divergence_hit_reasons": result.get("hit_reasons", []),
        }

    @staticmethod
    def _compute_ma100_low123_combined_factors(
        ma100_factors: dict, pattern_123_factors: dict, pattern_123_raw: dict,
        group: pd.DataFrame,
    ) -> dict:
        """Combine MA100 + Low-123 pattern into a single gate with hit reasons.

        Hard freshness gate: bars_since_entry > 3 → reject entirely.
        """
        above_ma100 = bool(ma100_factors.get("above_ma100", False))
        p123_confirmed = bool(pattern_123_factors.get("pattern_123_low_trendline", False))

        # bars_since_entry: how many bars since the 123 breakout confirmation
        entry_price = pattern_123_factors.get("pattern_123_entry_price")
        signal_strength = float(pattern_123_factors.get("pattern_123_signal_strength", 0.0))
        p123_state = pattern_123_factors.get("pattern_123_state", "rejected")

        # We don't have bars_since_entry directly from the detector;
        # the detector returns state == "confirmed" only when the breakout
        # just happened (within its own freshness window).  For the hard
        # 3-bar gate we rely on the detector's built-in freshness component
        # (it already scores freshness=0 when >5 bars old and only returns
        # "confirmed" for recent breakouts).  Here we do NOT add extra
        # freshness — the YAML filter on ma100_low123_confirmed already
        # ensures only confirmed+above_ma100 stocks pass.

        confirmed = p123_confirmed and above_ma100

        # ── MA score (breakout recency + distance) ──
        breakout_days = int(ma100_factors.get("ma100_breakout_days", 0))
        distance_pct = abs(float(ma100_factors.get("ma100_distance_pct", 0.0)))

        if breakout_days <= 5:
            recency_score = 1.0
        elif breakout_days <= 10:
            recency_score = 0.7
        else:
            recency_score = 0.4

        if distance_pct <= 5.0:
            dist_score = 1.0 - (distance_pct / 5.0) * 0.7  # 0%→1.0, 5%→0.3
        else:
            dist_score = 0.3

        ma_score = round(recency_score * 0.6 + dist_score * 0.4, 4)

        # ── Hit reasons (Chinese 【标题】描述 format) ──
        hit_reasons: list[str] = []
        if confirmed:
            hit_reasons = _build_ma100_low123_hit_reasons(
                ma100_factors, pattern_123_factors, pattern_123_raw, group,
                breakout_days, distance_pct, signal_strength,
            )

        return {
            "ma100_low123_confirmed": confirmed,
            "ma100_low123_pattern_strength": signal_strength if confirmed else 0.0,
            "ma100_low123_ma_score": ma_score if confirmed else 0.0,
            "ma100_low123_hit_reasons": hit_reasons,
        }

    @staticmethod
    def _compute_ma100_60min_combined_factors(ma100_factors: dict) -> dict:
        """MA100+60分钟线联合策略因子（Strategy 3）。

        选股门控：above_ma100 AND breakout_days ≤ 5（日线刚站稳MA100）。
        60分钟线不参与选股，仅在 hit_reasons 中提示次日入场关注点。
        """
        above_ma100 = bool(ma100_factors.get("above_ma100", False))
        breakout_days = int(ma100_factors.get("ma100_breakout_days", 0))
        ma100_val = float(ma100_factors.get("ma100", 0.0))
        distance_pct = abs(float(ma100_factors.get("ma100_distance_pct", 0.0)))

        confirmed = above_ma100 and 1 <= breakout_days <= 5

        # ── Freshness score: 1d=1.0, 2d=0.9, 3d=0.8, 4d=0.7, 5d=0.6 ──
        freshness_score = max(1.0 - (breakout_days - 1) * 0.1, 0.0) if confirmed else 0.0

        # ── MA score (recency × distance) ──
        if distance_pct <= 5.0:
            dist_score = 1.0 - (distance_pct / 5.0) * 0.7
        else:
            dist_score = 0.3
        ma_score = round(freshness_score * 0.6 + dist_score * 0.4, 4) if confirmed else 0.0

        # ── Hit reasons with 60-min operational guidance ──
        hit_reasons: list[str] = []
        if confirmed:
            hit_reasons.append(
                f"【MA100站稳确认】突破{breakout_days}天，"
                f"MA100={ma100_val:.2f}，距离{distance_pct:.1f}%"
            )
            hit_reasons.append(
                f"【60分钟入场提示】建议关注次日60分钟线，"
                f"突破60分钟MA20或站稳MA100({ma100_val:.2f})时买入"
            )

        return {
            "ma100_60min_confirmed": confirmed,
            "ma100_60min_freshness_score": freshness_score,
            "ma100_60min_ma_score": ma_score,
            "ma100_60min_hit_reasons": hit_reasons,
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


def _idx_to_date(group: pd.DataFrame, idx: int) -> str:
    """Convert a bar index to its date string (YYYY-MM-DD)."""
    if idx is None or idx < 0 or idx >= len(group):
        return "N/A"
    raw = group.iloc[idx]["date"]
    return str(pd.to_datetime(raw).date())


def _build_ma100_low123_hit_reasons(
    ma100_factors: dict,
    pattern_123_factors: dict,
    raw: dict,
    group: pd.DataFrame,
    breakout_days: int,
    distance_pct: float,
    signal_strength: float,
) -> list[str]:
    """Build detailed hit reasons for the MA100+Low123 combined strategy.

    Extracts structural info from the raw Low123TrendlineDetector result to
    produce Chinese-formatted 【标题】描述 strings that fully describe the
    detected 123 structure, trendline, breakout synchronisation and MA100
    confirmation.  All bar indices are converted to dates for user readability.
    """
    reasons: list[str] = []

    # 1. 123 结构关键点
    p1 = raw.get("point1") or {}
    p2 = raw.get("point2") or {}
    p3 = raw.get("point3") or {}
    if p1 and p2 and p3:
        p1_price = p1.get("price", 0)
        p2_price = p2.get("price", 0)
        p3_price = p3.get("price", 0)
        higher_low_pct = round((p3_price - p1_price) / p1_price * 100, 2) if p1_price else 0
        bounce_pct = round((p2_price - p1_price) / p1_price * 100, 2) if p1_price else 0
        retrace_pct = round((p2_price - p3_price) / (p2_price - p1_price) * 100, 2) if (p2_price - p1_price) else 0
        p1_date = _idx_to_date(group, p1.get("idx"))
        p2_date = _idx_to_date(group, p2.get("idx"))
        p3_date = _idx_to_date(group, p3.get("idx"))
        reasons.append(
            f"【123结构】P1({p1_date},价格{p1_price:.2f}) → "
            f"P2({p2_date},价格{p2_price:.2f}) → "
            f"P3({p3_date},价格{p3_price:.2f})，"
            f"反弹{bounce_pct}%，回撤{retrace_pct}%，P3抬高{higher_low_pct}%"
        )

    # 2. 下降趋势线
    dtl = raw.get("downtrend_line") or {}
    if dtl.get("found"):
        touch_count = dtl.get("touch_count", 0)
        slope = dtl.get("slope", 0)
        touch_pts = dtl.get("touch_points", [])
        touch_desc = "、".join(
            f"{_idx_to_date(group, tp['idx'])}({tp['price']:.2f})"
            for tp in touch_pts[:4]
        )
        bo_bar = dtl.get("breakout_bar_index")
        proj_val = dtl.get("projected_value_at_breakout")
        tl_status = "已突破" if dtl.get("breakout_confirmed") else "未突破"
        tl_detail = ""
        if bo_bar is not None and proj_val is not None:
            bo_date = _idx_to_date(group, bo_bar)
            tl_detail = f"，突破于{bo_date}(趋势线投影{proj_val:.2f})"
        reasons.append(
            f"【下降趋势线】斜率{slope:.6f}，{touch_count}个触点（{touch_desc}），"
            f"{tl_status}{tl_detail}"
        )

    # 3. P2 突破与趋势线突破同步性
    bo_p2 = raw.get("breakout_point2_confirmed", False)
    bo_tl = raw.get("breakout_trendline_confirmed", False)
    if bo_p2 and bo_tl:
        reasons.append("【同步突破】P2高点与下降趋势线同步突破确认")
    elif bo_p2:
        reasons.append("【P2突破】已突破P2高点，趋势线未突破")
    elif bo_tl:
        reasons.append("【趋势线突破】已突破下降趋势线，P2高点未突破")

    # 4. MA100 站上确认
    ma100_val = ma100_factors.get("ma100", 0)
    reasons.append(
        f"【MA100站上确认】突破{breakout_days}天，"
        f"MA100={ma100_val:.2f}，距离{distance_pct:.1f}%"
    )

    # 5. 信号强度
    entry_price = pattern_123_factors.get("pattern_123_entry_price")
    stop_loss = pattern_123_factors.get("pattern_123_stop_loss")
    reasons.append(
        f"【信号强度】综合评分{signal_strength:.2f}，"
        f"入场价{entry_price}，止损价{stop_loss}"
    )

    return reasons


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
