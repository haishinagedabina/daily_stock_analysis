# -*- coding: utf-8 -*-
"""
A股自选股智能分析系统 - 核心分析流水线（调度主入口）

职责：
1. 初始化所有服务模块
2. 调度单股处理流程（数据获取 → 分析 → 通知）
3. 管理并发控制（ThreadPoolExecutor）
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

# NOTE: DataFetcherManager, GeminiAnalyzer, NotificationService, SearchService,
# get_config, and get_db are imported lazily inside __init__ (not at module level)
# so that tests can patch them via src.core.pipeline.* before instantiation.
from src.config import Config
from src.services.social_sentiment_service import SocialSentimentService
from src.enums import ReportType
from src.stock_analyzer import StockTrendAnalyzer
from src.core.market_guard import MarketGuard, MarketGuardResult
from src.analyzer import AnalysisResult
from bot.models import BotMessage

from src.core.pipeline.data_mixin import DataMixin
from src.core.pipeline.analysis_mixin import AnalysisMixin
from src.core.pipeline.agent_mixin import AgentMixin
from src.core.pipeline.notification_mixin import NotificationMixin

logger = logging.getLogger(__name__)


class StockAnalysisPipeline(DataMixin, AnalysisMixin, AgentMixin, NotificationMixin):
    """
    股票分析主流程调度器

    通过 Mixin 组合模式分解职责：
    - DataMixin：数据获取与保存
    - AnalysisMixin：技术分析与上下文增强
    - AgentMixin：Agent 模式分析
    - NotificationMixin：报告生成与多渠道推送
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        source_message: Optional[BotMessage] = None,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None,
    ):
        # Late imports so tests can patch src.core.pipeline.* before instantiation
        import src.core.pipeline as _pkg
        _get_config = _pkg.get_config
        _get_db = _pkg.get_db
        _DataFetcherManager = _pkg.DataFetcherManager
        _GeminiAnalyzer = _pkg.GeminiAnalyzer
        _NotificationService = _pkg.NotificationService
        _SearchService = _pkg.SearchService

        self.config = config or _get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.source_message = source_message
        self.query_id = query_id
        self.query_source = self._resolve_query_source(query_source)
        self.save_context_snapshot = (
            self.config.save_context_snapshot if save_context_snapshot is None else save_context_snapshot
        )

        self.db = _get_db()
        self.fetcher_manager = _DataFetcherManager()
        self.trend_analyzer = StockTrendAnalyzer()
        self.analyzer = _GeminiAnalyzer()
        self.notifier = _NotificationService(source_message=source_message)

        self.search_service = _SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            brave_keys=self.config.brave_api_keys,
            serpapi_keys=self.config.serpapi_keys,
            minimax_keys=self.config.minimax_api_keys,
            news_max_age_days=self.config.news_max_age_days,
            news_strategy_profile=getattr(self.config, "news_strategy_profile", "short"),
        )

        logger.info(f"调度器初始化完成，最大并发数: {self.max_workers}")
        logger.info("已启用趋势分析器 (MA5>MA10>MA20 多头判断)")

        if self.config.enable_realtime_quote:
            logger.info(f"实时行情已启用 (优先级: {self.config.realtime_source_priority})")
        else:
            logger.info("实时行情已禁用，将使用历史收盘价")
        if self.config.enable_chip_distribution:
            logger.info("筹码分布分析已启用")
        else:
            logger.info("筹码分布分析已禁用")
        if self.search_service.is_available:
            logger.info("搜索服务已启用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜索服务未启用（未配置 API Key）")

        self.social_sentiment_service = SocialSentimentService(
            api_key=self.config.social_sentiment_api_key,
            api_url=self.config.social_sentiment_api_url,
        )
        if self.social_sentiment_service.is_available:
            logger.info("Social sentiment service enabled (Reddit/X/Polymarket, US stocks only)")

    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE,
        analysis_query_id: Optional[str] = None,
        system_context: Optional[str] = None,
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程：数据获取 → AI 分析 → 单股推送（可选）

        此方法被线程池调用，需处理好异常。
        """
        logger.info(f"========== 开始处理 {code} ==========")

        try:
            success, error = self.fetch_and_save_stock_data(code)
            if not success:
                logger.warning(f"[{code}] 数据获取失败: {error}")

            if skip_analysis:
                logger.info(f"[{code}] 跳过 AI 分析（dry-run 模式）")
                return None

            effective_query_id = analysis_query_id or self.query_id or uuid.uuid4().hex
            result = self.analyze_stock(code, report_type, query_id=effective_query_id, system_context=system_context)

            if result:
                if not result.success:
                    logger.warning(f"[{code}] 分析未成功: {result.error_message or '未知错误'}")
                else:
                    logger.info(f"[{code}] 分析完成: {result.operation_advice}, 评分 {result.sentiment_score}")

                if single_stock_notify and self.notifier.is_available():
                    try:
                        if report_type == ReportType.FULL:
                            report_content = self.notifier.generate_dashboard_report([result])
                            logger.info(f"[{code}] 使用完整报告格式")
                        elif report_type == ReportType.BRIEF:
                            report_content = self.notifier.generate_brief_report([result])
                            logger.info(f"[{code}] 使用简洁报告格式")
                        else:
                            report_content = self.notifier.generate_single_stock_report(result)
                            logger.info(f"[{code}] 使用精简报告格式")

                        if self.notifier.send(report_content, email_stock_codes=[code]):
                            logger.info(f"[{code}] 单股推送成功")
                        else:
                            logger.warning(f"[{code}] 单股推送失败")
                    except Exception as e:
                        logger.error(f"[{code}] 单股推送异常: {e}")

            return result

        except Exception as e:
            logger.exception(f"[{code}] 处理过程发生未知异常: {e}")
            return None

    def run(
        self,
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True,
        merge_notification: bool = False,
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程

        流程：
        1. 获取待分析的股票列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知
        """
        start_time = time.time()

        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list

        if not stock_codes:
            logger.error("未配置自选股列表，请在 .env 文件中设置 STOCK_LIST")
            return []

        logger.info(f"===== 开始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"并发数: {self.max_workers}, 模式: {'仅获取数据' if dry_run else '完整分析'}")

        # Market-level MA100 risk check (advisory, never blocks)
        try:
            guard = MarketGuard(fetcher_manager=self.fetcher_manager)
            self._market_guard_result = guard.check()
            if self._market_guard_result.is_safe:
                logger.info(f"MarketGuard: {self._market_guard_result.message}")
            else:
                logger.warning(f"MarketGuard: {self._market_guard_result.message}")
        except Exception as e:
            logger.warning(f"MarketGuard check failed: {e}")
            self._market_guard_result = MarketGuardResult(is_safe=True, message=f"Guard error: {e}")

        # 批量预取实时行情（≥5 只时有效）
        if len(stock_codes) >= 5:
            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(f"已启用批量预取架构：一次拉取全市场数据，{len(stock_codes)} 只股票共享缓存")

        if not dry_run:
            self.fetcher_manager.prefetch_stock_names(stock_codes, use_bulk=False)

        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        if report_type_str == 'brief':
            report_type = ReportType.BRIEF
        elif report_type_str == 'full':
            report_type = ReportType.FULL
        else:
            report_type = ReportType.SIMPLE
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(f"已启用单股推送模式：每分析完一只股票立即推送（报告类型: {report_type_str}）")

        results: List[AnalysisResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_code = {
                executor.submit(
                    self.process_single_stock,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=single_stock_notify and send_notification,
                    report_type=report_type,
                    analysis_query_id=uuid.uuid4().hex,
                ): code
                for code in stock_codes
            }

            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)

                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        logger.debug(f"等待 {analysis_delay} 秒后继续下一只股票...")
                        time.sleep(analysis_delay)
                except Exception as e:
                    logger.error(f"[{code}] 任务执行失败: {e}")

        elapsed_time = time.time() - start_time

        if dry_run:
            success_count = sum(1 for code in stock_codes if self.db.has_today_data(code))
        else:
            success_count = len(results)
        fail_count = len(stock_codes) - success_count

        logger.info("===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 耗时: {elapsed_time:.2f} 秒")

        if results and not dry_run:
            self._save_local_report(results, report_type)

        if results and send_notification and not dry_run:
            if single_stock_notify:
                logger.info("单股推送模式：跳过汇总推送，仅保存报告到本地")
                self._send_notifications(results, report_type, skip_push=True)
            elif merge_notification:
                logger.info("合并推送模式：跳过本次推送，将在个股+大盘复盘后统一发送")
                self._send_notifications(results, report_type, skip_push=True)
            else:
                self._send_notifications(results, report_type)

        return results
