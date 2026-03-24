# -*- coding: utf-8 -*-
"""
src.core.pipeline 包 - 向后兼容入口

保持原有 `from src.core.pipeline import StockAnalysisPipeline` 的导入路径不变。
"""

import logging

# Re-export service constructors so tests can patch them via src.core.pipeline.*
# Order matters: these must be imported BEFORE main.py so __init__'s late imports get the right values.
from src.config import get_config
from src.storage import get_db
from data_provider import DataFetcherManager
from src.analyzer import GeminiAnalyzer
from src.notification import NotificationService, NotificationChannel
from src.search_service import SearchService
from src.core.trading_calendar import get_market_for_stock, is_market_open  # re-export for test patching

from src.core.pipeline.main import StockAnalysisPipeline

# Shared logger: notification_mixin uses getLogger("src.core.pipeline") so that
# patching src.core.pipeline.logger.warning in tests affects the same Logger instance.
logger = logging.getLogger(__name__)

__all__ = [
    "StockAnalysisPipeline",
    "NotificationChannel",
    "get_config", "get_db",
    "DataFetcherManager", "GeminiAnalyzer", "NotificationService", "SearchService",
    "logger",
]
