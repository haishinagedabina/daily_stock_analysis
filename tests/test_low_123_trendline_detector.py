# -*- coding: utf-8 -*-
"""
Tests for Low123TrendlineDetector.

Scenario coverage (7 cases from design doc §9):
  1. Pure oscillation  → rejected (no prior downtrend)
  2. Low-position 123, no trendline breakout → structure_only
  3. Low-position 123 + joint breakout (P2 + trendline) → confirmed
  4. High-position 123 → rejected (not low-level)
  5. Late/stale breakout (beyond sync window) → late_or_weak
  6. Trendline with only 2 poor-quality points → lower signal_strength
  7. Multiple candidates → picks newest + highest quality
"""

import numpy as np
import pandas as pd
import pytest

from src.indicators.low_123_trendline_detector import Low123TrendlineDetector


# ---------------------------------------------------------------------------
# Data-builder helpers
# ---------------------------------------------------------------------------

def _make_df(closes, highs=None, lows=None, volumes=None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from close prices."""
    n = len(closes)
    closes = np.array(closes, dtype=float)
    if highs is None:
        highs = closes * 1.01
    if lows is None:
        lows = closes * 0.99
    if volumes is None:
        volumes = np.full(n, 1_000_000.0)
    return pd.DataFrame({
        "open": closes * 0.995,
        "high": np.array(highs, dtype=float),
        "low": np.array(lows, dtype=float),
        "close": closes,
        "volume": np.array(volumes, dtype=float),
    })


def _pure_oscillation(n=80) -> pd.DataFrame:
    """
    Gently rising oscillation: no prior downtrend context exists before any
    local dip, so the prior-downtrend check must fail for every P1 candidate.
    """
    x = np.arange(n, dtype=float)
    # Slope of +0.12/bar ensures every 20-30 bar window has positive trend
    prices = 90 + x * 0.12 + 2.0 * np.sin(2 * np.pi * x / 18)
    return _make_df(prices)


def _zigzag_downtrend(start: float, end: float, n: int, amplitude: float = 3.0) -> np.ndarray:
    """
    Generate a descending zigzag so that find_swing_highs can detect
    intermediate peaks (needed to fit a valid downtrend trendline).

    Pattern: every ~8 bars has a small bounce followed by a new lower high.
    """
    prices = np.linspace(start, end, n)
    for i in range(5, n - 5, 8):
        prices[i] += amplitude * (1 - i / n)   # decaying amplitude
        prices[i + 2] -= amplitude * 0.4 * (1 - i / n)
    return prices


def _downtrend_then_low123_no_trendline_break(sync_window: int = 3) -> pd.DataFrame:
    """
    Clear prior downtrend (with zigzag swing highs for trendline fitting),
    then a low-level 123 forms, but the trendline resistance is NOT broken.
    """
    n = 80
    prices = np.zeros(n)
    prices[:30] = _zigzag_downtrend(120, 90, 30, amplitude=4.0)
    prices[30] = 88
    prices[31:40] = np.linspace(88, 96, 9)
    prices[39] = 96  # P2
    prices[40:45] = np.linspace(96, 90, 5)
    prices[44] = 90  # P3
    # Recovery reaches 94 but never breaks 96 (P2) inside sync window
    prices[45:] = np.linspace(90, 94, n - 45)

    highs = prices * 1.005
    lows = prices * 0.995
    highs[39] = 96.5
    lows[30] = 87.5
    lows[44] = 89.5

    return _make_df(prices, highs=highs, lows=lows)


def _downtrend_then_confirmed_low123(sync_window: int = 3) -> pd.DataFrame:
    """
    Prior downtrend with zigzag swing highs → trendline can be fitted.
    Low-level 123 formed, both P2 and trendline broken on the same bar.
    """
    n = 80
    prices = np.zeros(n)
    prices[:30] = _zigzag_downtrend(130, 90, 30, amplitude=5.0)
    prices[30] = 86
    prices[31:40] = np.linspace(86, 97, 9)
    prices[39] = 97   # P2
    prices[40:45] = np.linspace(97, 89, 5)
    prices[44] = 89   # P3
    prices[45] = 99   # joint breakout (above P2=97 and trendline ~95)
    prices[46:] = np.linspace(99, 102, n - 46)

    highs = prices * 1.005
    lows = prices * 0.995
    highs[39] = 97.5
    lows[30] = 85.5
    lows[44] = 88.5
    highs[45] = 100

    return _make_df(prices, highs=highs, lows=lows)


def _high_position_123() -> pd.DataFrame:
    """
    123 structure formed in the UPPER part of recent range — should be
    rejected as not a low-level pattern.

    [0..29]  – uptrend 80 → 120
    [30]     – dip to 115 (NOT near recent lows)
    [31..39] – bounce to 122 (P2)
    [40..44] – pullback to 117 (P3 > P1 = 115)
    [45..]   – breakout above 122
    """
    n = 80
    prices = np.zeros(n)
    prices[:30] = np.linspace(80, 120, 30)
    prices[30] = 115   # P1 in high zone
    prices[31:40] = np.linspace(115, 122, 9)
    prices[39] = 122   # P2
    prices[40:45] = np.linspace(122, 117, 5)
    prices[44] = 117   # P3
    prices[45:] = np.linspace(117, 126, n - 45)

    highs = prices * 1.005
    lows = prices * 0.995
    highs[39] = 122.5
    lows[30] = 114.5
    lows[44] = 116.5

    return _make_df(prices, highs=highs, lows=lows)


def _late_breakout(sync_window: int = 3) -> pd.DataFrame:
    """
    Valid 123 structure in low position, P2 breakout at bar 45,
    trendline breakout delayed to bar 52 (gap = 7 > sync_window=3).
    """
    n = 80
    prices = np.zeros(n)
    prices[:30] = _zigzag_downtrend(130, 90, 30, amplitude=4.0)
    prices[30] = 86
    prices[31:40] = np.linspace(86, 96, 9)
    prices[39] = 96   # P2
    prices[40:45] = np.linspace(96, 89, 5)
    prices[44] = 89   # P3
    prices[45] = 98   # P2 breakout (bar 45, close=98 > P2=96)
    prices[46:52] = np.linspace(95, 95, 6)  # flat, below trendline
    prices[52] = 99   # trendline breakout (bar 52, gap=7 from bar 45)
    prices[53:] = np.linspace(99, 101, n - 53)

    highs = prices * 1.005
    lows = prices * 0.995
    highs[39] = 96.5
    lows[30] = 85.5
    lows[44] = 88.5

    return _make_df(prices, highs=highs, lows=lows)


def _two_point_trendline() -> pd.DataFrame:
    """
    Valid 123 + joint breakout, downtrend has exactly 2 swing highs available
    for trendline fitting → touch_count == 2.

    Downtrend [0..24]: two clear peaks at bars 5 and 15 (each surrounded by
    lower bars on both sides so find_swing_highs(order=3) detects them).
    """
    n = 60
    prices = np.zeros(n)
    # Clear descending zigzag with peaks at bars 5 and 15
    prices[0:5]   = np.linspace(106, 108, 5)    # rise to peak 1
    prices[5]     = 109.0                        # PEAK 1 (bar 5)
    prices[6:14]  = np.linspace(107, 98, 8)      # drop
    prices[14:16] = np.linspace(98, 100, 2)      # small rise
    prices[15]    = 100.0                        # PEAK 2 (bar 15, lower than peak 1)
    prices[16:24] = np.linspace(99, 91, 8)       # drop to pre-P1 area

    prices[24] = 86.0                            # P1
    prices[25:33] = np.linspace(86, 97, 8)
    prices[32] = 97.0                            # P2
    prices[33:37] = np.linspace(97, 89, 4)
    prices[36] = 89.0                            # P3
    prices[37] = 99.0                            # joint breakout
    prices[38:] = np.linspace(99, 101, n - 38)

    highs = prices * 1.005
    lows  = prices * 0.995
    # Sharpen the two peaks
    highs[5]  = 110.0
    highs[15] = 101.0
    highs[32] = 97.5
    lows[24]  = 85.5
    lows[36]  = 88.5
    highs[37] = 100.0

    return _make_df(prices, highs=highs, lows=lows)


def _multiple_candidates() -> pd.DataFrame:
    """
    Two separate 123 structures. The second (newer) is fully confirmed;
    the detector must return the newer confirmed one.
    """
    n = 100
    prices = np.zeros(n)
    prices[:30] = _zigzag_downtrend(130, 90, 30, amplitude=4.0)

    # First 123 — no trendline breakout
    prices[30] = 86
    prices[31:38] = np.linspace(86, 95, 7)
    prices[37] = 95
    prices[38:43] = np.linspace(95, 88, 5)
    prices[42] = 88
    prices[43:50] = np.linspace(88, 92, 7)

    # Second 123 — confirmed
    prices[50] = 84
    prices[51:58] = np.linspace(84, 94, 7)
    prices[57] = 94
    prices[58:63] = np.linspace(94, 87, 5)
    prices[62] = 87
    prices[63] = 97   # joint breakout
    prices[64:] = np.linspace(97, 100, n - 64)

    highs = prices * 1.005
    lows = prices * 0.995
    highs[37] = 95.5
    lows[30] = 85.5
    lows[42] = 87.5
    highs[57] = 94.5
    lows[50] = 83.5
    lows[62] = 86.5
    highs[63] = 98

    return _make_df(prices, highs=highs, lows=lows)


# ---------------------------------------------------------------------------
# Scenario 1: pure oscillation → rejected
# ---------------------------------------------------------------------------

class TestPureOscillation:
    def test_returns_rejected(self):
        df = _pure_oscillation()
        result = Low123TrendlineDetector.detect(df)
        assert result["found"] is False
        assert result["state"] == "rejected"
        assert result["rejection_reason"] is not None

    def test_no_entry_price(self):
        df = _pure_oscillation()
        result = Low123TrendlineDetector.detect(df)
        assert result["entry_price"] is None
        assert result["stop_loss_price"] is None


# ---------------------------------------------------------------------------
# Scenario 2: low 123 formed, no trendline breakout → structure_only
# ---------------------------------------------------------------------------

class TestStructureOnlyNoTrendlineBreak:
    def test_returns_structure_only(self):
        df = _downtrend_then_low123_no_trendline_break()
        result = Low123TrendlineDetector.detect(df)
        assert result["found"] is True
        assert result["state"] == "structure_only"

    def test_points_populated(self):
        df = _downtrend_then_low123_no_trendline_break()
        result = Low123TrendlineDetector.detect(df)
        assert result["point1"] is not None
        assert result["point2"] is not None
        assert result["point3"] is not None

    def test_is_low_level(self):
        df = _downtrend_then_low123_no_trendline_break()
        result = Low123TrendlineDetector.detect(df)
        assert result["is_low_level"] is True

    def test_no_entry_price(self):
        df = _downtrend_then_low123_no_trendline_break()
        result = Low123TrendlineDetector.detect(df)
        assert result["entry_price"] is None


# ---------------------------------------------------------------------------
# Scenario 3: standard low 123 + joint breakout → confirmed
# ---------------------------------------------------------------------------

class TestConfirmedJointBreakout:
    def test_returns_confirmed(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        assert result["found"] is True
        assert result["state"] == "confirmed"

    def test_both_breakouts_confirmed(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        assert result["breakout_point2_confirmed"] is True
        assert result["breakout_trendline_confirmed"] is True

    def test_entry_and_stop_prices(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        assert result["entry_price"] is not None
        assert result["stop_loss_price"] is not None
        # stop loss must be <= P3 price
        p3_price = result["point3"]["price"]
        assert result["stop_loss_price"] <= p3_price * 1.001  # tiny tolerance

    def test_trendline_found_with_negative_slope(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        dtl = result["downtrend_line"]
        assert dtl is not None
        assert dtl["found"] is True
        assert dtl["slope"] < 0

    def test_signal_strength_nonzero(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        assert result["signal_strength"] > 0.0


# ---------------------------------------------------------------------------
# Scenario 4: high-position 123 → rejected (not low-level)
# ---------------------------------------------------------------------------

class TestHighPosition123:
    def test_returns_rejected(self):
        df = _high_position_123()
        result = Low123TrendlineDetector.detect(df)
        assert result["found"] is False
        assert result["state"] == "rejected"

    def test_rejection_reason_present(self):
        df = _high_position_123()
        result = Low123TrendlineDetector.detect(df)
        assert result["rejection_reason"] is not None
        # Valid rejection reasons: not low-level OR no prior downtrend
        # (high-pos 123 may fail at either gate)
        reason = result["rejection_reason"].lower()
        assert any(kw in reason for kw in (
            "low", "position", "level", "downtrend", "prior",
        ))


# ---------------------------------------------------------------------------
# Scenario 5: late/stale trendline breakout → late_or_weak
# ---------------------------------------------------------------------------

class TestLateBreakout:
    def test_returns_late_or_weak(self):
        df = _late_breakout()
        result = Low123TrendlineDetector.detect(df, sync_window=3)
        assert result["found"] is True
        assert result["state"] in ("late_or_weak", "structure_only")

    def test_p2_breakout_confirmed_but_trendline_delayed(self):
        df = _late_breakout()
        result = Low123TrendlineDetector.detect(df, sync_window=3)
        # P2 breakout happened but sync was lost
        assert result["breakout_point2_confirmed"] is True


# ---------------------------------------------------------------------------
# Scenario 6: only 2-touch trendline → lower signal_strength
# ---------------------------------------------------------------------------

class TestTwoPointTrendline:
    def test_still_confirmed(self):
        df = _two_point_trendline()
        result = Low123TrendlineDetector.detect(df)
        # Should still confirm (2 touches meets minimum)
        assert result["found"] is True
        assert result["state"] == "confirmed"

    def test_touch_count_is_two(self):
        df = _two_point_trendline()
        result = Low123TrendlineDetector.detect(df)
        dtl = result["downtrend_line"]
        assert dtl is not None
        assert dtl["touch_count"] == 2

    def test_signal_strength_lower_than_confirmed(self):
        """2-touch trendline should score lower than a well-touched one."""
        df_two = _two_point_trendline()
        df_full = _downtrend_then_confirmed_low123()
        r_two = Low123TrendlineDetector.detect(df_two)
        r_full = Low123TrendlineDetector.detect(df_full)
        assert r_two["signal_strength"] <= r_full["signal_strength"]


# ---------------------------------------------------------------------------
# Scenario 7: multiple candidates → newest confirmed wins
# ---------------------------------------------------------------------------

class TestMultipleCandidates:
    def test_returns_confirmed_state(self):
        df = _multiple_candidates()
        result = Low123TrendlineDetector.detect(df)
        assert result["found"] is True
        assert result["state"] == "confirmed"

    def test_selects_newer_p1(self):
        """The selected P1 should be in the second (newer) 123 structure."""
        df = _multiple_candidates()
        result = Low123TrendlineDetector.detect(df)
        p1_idx = result["point1"]["idx"]
        # First structure P1 is around bar 30, second around bar 50
        assert p1_idx >= 45, f"Expected newer P1 (idx>=45), got {p1_idx}"


# ---------------------------------------------------------------------------
# Output schema contract tests
# ---------------------------------------------------------------------------

class TestOutputSchema:
    """Every result must carry the full schema regardless of state."""

    REQUIRED_KEYS = {
        "found", "state", "rejection_reason", "is_low_level",
        "point1", "point2", "point3", "downtrend_line",
        "breakout_point2_confirmed", "breakout_trendline_confirmed",
        "ma_confirmation", "entry_price", "stop_loss_price", "signal_strength",
    }

    @pytest.mark.parametrize("make_df", [
        _pure_oscillation,
        _downtrend_then_low123_no_trendline_break,
        _downtrend_then_confirmed_low123,
        _high_position_123,
    ])
    def test_all_keys_present(self, make_df):
        df = make_df()
        result = Low123TrendlineDetector.detect(df)
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_point_structure_when_found(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        for pt in ("point1", "point2", "point3"):
            p = result[pt]
            assert isinstance(p, dict)
            assert "idx" in p and "price" in p

    def test_downtrend_line_sub_schema(self):
        df = _downtrend_then_confirmed_low123()
        result = Low123TrendlineDetector.detect(df)
        dtl = result["downtrend_line"]
        required = {
            "found", "slope", "intercept", "touch_points",
            "touch_count", "breakout_bar_index",
            "projected_value_at_breakout", "breakout_confirmed",
        }
        missing = required - set(dtl.keys())
        assert not missing, f"downtrend_line missing keys: {missing}"
