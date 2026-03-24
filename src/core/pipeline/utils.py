# -*- coding: utf-8 -*-
"""
流水线工具函数 - 纯函数，无 self 依赖
"""
from typing import Any, Dict, Optional


def safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
    """安全转换为字典"""
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            return None
    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            return None
    return None


def describe_volume_ratio(volume_ratio: float) -> str:
    """
    量比描述

    量比 = 当前成交量 / 过去5日平均成交量
    """
    if volume_ratio < 0.5:
        return "极度萎缩"
    elif volume_ratio < 0.8:
        return "明显萎缩"
    elif volume_ratio < 1.2:
        return "正常"
    elif volume_ratio < 2.0:
        return "温和放量"
    elif volume_ratio < 3.0:
        return "明显放量"
    else:
        return "巨量"


def compute_ma_status(close: float, ma5: float, ma10: float, ma20: float) -> str:
    """
    Compute MA alignment status from price and MA values.
    Logic mirrors storage._analyze_ma_status (Issue #234).
    """
    close = close or 0
    ma5 = ma5 or 0
    ma10 = ma10 or 0
    ma20 = ma20 or 0
    if close > ma5 > ma10 > ma20 > 0:
        return "多头排列 📈"
    elif close < ma5 < ma10 < ma20 and ma20 > 0:
        return "空头排列 📉"
    elif close > ma5 and ma5 > ma10:
        return "短期向好 🔼"
    elif close < ma5 and ma5 < ma10:
        return "短期走弱 🔽"
    else:
        return "震荡整理 ↔️"
