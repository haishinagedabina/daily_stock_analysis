# -*- coding: utf-8 -*-
"""
流水线 Mixin 共享类型存根

所有 Mixin 类通过继承 PipelineMixin 获取 IDE/类型检查器所需的属性声明。
该模块不含任何运行时副作用：if TYPE_CHECKING 块在运行时被跳过。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from bot.models import BotMessage
    from data_provider import DataFetcherManager
    from src.analyzer import GeminiAnalyzer
    from src.config import Config
    from src.notification import NotificationService
    from src.search_service import SearchService
    from src.services.social_sentiment_service import SocialSentimentService
    from src.stock_analyzer import StockTrendAnalyzer


class PipelineMixin:
    """
    Mixin 基类 — 仅用于类型检查，无运行时行为。

    声明由 StockAnalysisPipeline.__init__ 提供的共享属性，
    使 IDE 和 mypy/pyright 能正确推断所有 Mixin 方法中的 self 属性类型。
    """

    if TYPE_CHECKING:
        config: "Config"
        db: Any  # DatabaseInterface（具体类型由 src.storage 提供）
        fetcher_manager: "DataFetcherManager"
        trend_analyzer: "StockTrendAnalyzer"
        analyzer: "GeminiAnalyzer"
        notifier: "NotificationService"
        search_service: "SearchService"
        social_sentiment_service: "SocialSentimentService"
        source_message: Optional["BotMessage"]
        query_id: Optional[str]
        query_source: str
        save_context_snapshot: bool
        max_workers: int
