# -*- coding: utf-8 -*-
"""
分析 Mixin - 负责单股技术分析、上下文增强、实时数据叠加
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

import pandas as pd

from data_provider.realtime_types import ChipDistribution
from data_provider.us_index_mapping import is_us_stock_code
from src.analyzer import AnalysisResult, fill_chip_structure_if_needed, fill_price_position_if_needed
from src.enums import ReportType
from src.search_service import SearchService
from src.stock_analyzer import TrendAnalysisResult
from src.core.pipeline.utils import safe_to_dict, describe_volume_ratio, compute_ma_status
from src.core.pipeline._typing import PipelineMixin

logger = logging.getLogger(__name__)


class AnalysisMixin(PipelineMixin):
    """负责股票技术分析及上下文增强的相关方法"""

    def analyze_stock(self, code: str, report_type: ReportType, query_id: str) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）

        流程：
        1. 获取实时行情（量比、换手率）
        2. 获取筹码分布
        3. 进行趋势分析（基于交易理念）
        4. 多维度情报搜索（最新消息+风险排查+业绩预期）
        5. 从数据库获取分析上下文
        6. 调用 AI 进行综合分析
        """
        try:
            stock_name = self.fetcher_manager.get_stock_name(code)

            # Step 1: 获取实时行情
            realtime_quote = None
            try:
                realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                if realtime_quote:
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                    turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                    logger.info(
                        f"{stock_name}({code}) 实时行情: 价格={realtime_quote.price}, "
                        f"量比={volume_ratio}, 换手率={turnover_rate}% "
                        f"(来源: {realtime_quote.source.value if hasattr(realtime_quote, 'source') else 'unknown'})"
                    )
                else:
                    logger.info(f"{stock_name}({code}) 实时行情获取失败或已禁用，将使用历史数据进行分析")
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 获取实时行情失败: {e}")

            if not stock_name:
                stock_name = f'股票{code}'

            # Step 2: 获取筹码分布
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(
                        f"{stock_name}({code}) 筹码分布: 获利比例={chip_data.profit_ratio:.1%}, "
                        f"90%集中度={chip_data.concentration_90:.2%}"
                    )
                else:
                    logger.debug(f"{stock_name}({code}) 筹码分布获取失败或已禁用")
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 获取筹码分布失败: {e}")

            # Agent 模式判断
            use_agent = getattr(self.config, 'agent_mode', False)
            if not use_agent:
                configured_skills = getattr(self.config, 'agent_skills', [])
                if configured_skills and configured_skills != ['all']:
                    use_agent = True
                    logger.info(f"{stock_name}({code}) Auto-enabled agent mode due to configured skills: {configured_skills}")

            # Step 2.5: 基本面能力聚合
            fundamental_context = None
            try:
                fundamental_context = self.fetcher_manager.get_fundamental_context(
                    code,
                    budget_seconds=getattr(self.config, 'fundamental_stage_timeout_seconds', 1.5),
                )
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 基本面聚合失败: {e}")
                fundamental_context = self.fetcher_manager.build_failed_fundamental_context(code, str(e))

            try:
                self.db.save_fundamental_snapshot(
                    query_id=query_id,
                    code=code,
                    payload=fundamental_context,
                    source_chain=fundamental_context.get("source_chain", []),
                    coverage=fundamental_context.get("coverage", {}),
                )
            except Exception as e:
                logger.debug(f"{stock_name}({code}) 基本面快照写入失败: {e}")

            # Step 3: 趋势分析
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                end_date = date.today()
                start_date = end_date - timedelta(days=max(self.config.data_fetch_days * 2, 300))
                historical_bars = self.db.get_data_range(code, start_date, end_date)
                if historical_bars:
                    df = pd.DataFrame([bar.to_dict() for bar in historical_bars])
                    if self.config.enable_realtime_quote and realtime_quote:
                        df = self._augment_historical_with_realtime(df, realtime_quote, code)
                    trend_result = self.trend_analyzer.analyze(df, code)
                    logger.info(
                        f"{stock_name}({code}) 趋势分析: {trend_result.trend_status.value}, "
                        f"买入信号={trend_result.buy_signal.value}, 评分={trend_result.signal_score}"
                    )
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 趋势分析失败: {e}", exc_info=True)

            if use_agent:
                logger.info(f"{stock_name}({code}) 启用 Agent 模式进行分析")
                return self._analyze_with_agent(
                    code, report_type, query_id, stock_name,
                    realtime_quote, chip_data, fundamental_context, trend_result,
                )

            # Step 4: 多维度情报搜索
            news_context = None
            if self.search_service.is_available:
                logger.info(f"{stock_name}({code}) 开始多维度情报搜索...")
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code, stock_name=stock_name, max_searches=5
                )
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(len(r.results) for r in intel_results.values() if r.success)
                    logger.info(f"{stock_name}({code}) 情报搜索完成: 共 {total_results} 条结果")
                    logger.debug(f"{stock_name}({code}) 情报搜索结果:\n{news_context}")
                    try:
                        query_context = self._build_query_context(query_id=query_id)
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code, name=stock_name, dimension=dim_name,
                                    query=response.query, response=response,
                                    query_context=query_context
                                )
                    except Exception as e:
                        logger.warning(f"{stock_name}({code}) 保存新闻情报失败: {e}")
            else:
                logger.info(f"{stock_name}({code}) 搜索服务不可用，跳过情报搜索")

            # Step 4.5: Social sentiment intelligence (US stocks only)
            if self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        logger.info(f"{stock_name}({code}) Social sentiment data retrieved")
                        news_context = (news_context + "\n\n" + social_context) if news_context else social_context
                except Exception as e:
                    logger.warning(f"{stock_name}({code}) Social sentiment fetch failed: {e}")

            # Step 5: 获取分析上下文
            context = self.db.get_analysis_context(code)
            if context is None:
                logger.warning(f"{stock_name}({code}) 无法获取历史行情数据，将仅基于新闻和实时行情分析")
                context = {
                    'code': code, 'stock_name': stock_name,
                    'date': date.today().isoformat(),
                    'data_missing': True, 'today': {}, 'yesterday': {}
                }

            # Step 6: 增强上下文
            enhanced_context = self._enhance_context(
                context, realtime_quote, chip_data, trend_result, stock_name, fundamental_context,
            )

            # Step 7: 调用 AI 分析
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)

            if result:
                result.query_id = query_id
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')

            if result and chip_data:
                fill_chip_structure_if_needed(result, chip_data)

            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)

            # Step 8: 保存分析历史
            if result:
                try:
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data,
                    )
                    self.db.save_analysis_history(
                        result=result, query_id=query_id,
                        report_type=report_type.value, news_content=news_context,
                        context_snapshot=context_snapshot,
                        save_snapshot=self.save_context_snapshot,
                    )
                except Exception as e:
                    logger.warning(f"{stock_name}({code}) 保存分析历史失败: {e}")

            return result

        except Exception as e:
            logger.error(f"{code} 分析失败: {e}")
            logger.exception(f"{code} 详细错误信息:")
            return None

    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = "",
        fundamental_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """增强分析上下文：添加实时行情、筹码分布、趋势分析、基本面等"""
        enhanced = context.copy()

        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name

        enhanced['news_window_days'] = getattr(self.search_service, "news_window_days", 3)

        if realtime_quote:
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'change_pct': getattr(realtime_quote, 'change_pct', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': describe_volume_ratio(volume_ratio) if volume_ratio else '无数据',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': getattr(realtime_quote, 'source', None),
            }
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}

        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }

        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }

        # Issue #234: Override today with realtime OHLC + trend MA for intraday analysis
        if realtime_quote and trend_result and trend_result.ma5 > 0:
            price = getattr(realtime_quote, 'price', None)
            if price is not None and price > 0:
                yesterday_close = None
                if enhanced.get('yesterday') and isinstance(enhanced['yesterday'], dict):
                    yesterday_close = enhanced['yesterday'].get('close')
                orig_today = enhanced.get('today') or {}
                open_p = (
                    getattr(realtime_quote, 'open_price', None)
                    or getattr(realtime_quote, 'pre_close', None)
                    or yesterday_close
                    or orig_today.get('open')
                    or price
                )
                high_p = getattr(realtime_quote, 'high', None) or price
                low_p = getattr(realtime_quote, 'low', None) or price
                vol = getattr(realtime_quote, 'volume', None)
                amt = getattr(realtime_quote, 'amount', None)
                pct = getattr(realtime_quote, 'change_pct', None)
                realtime_today = {
                    'close': price, 'open': open_p, 'high': high_p, 'low': low_p,
                    'ma5': trend_result.ma5, 'ma10': trend_result.ma10, 'ma20': trend_result.ma20,
                }
                if vol is not None:
                    realtime_today['volume'] = vol
                if amt is not None:
                    realtime_today['amount'] = amt
                if pct is not None:
                    realtime_today['pct_chg'] = pct
                for k, v in orig_today.items():
                    if k not in realtime_today and v is not None:
                        realtime_today[k] = v
                enhanced['today'] = realtime_today
                enhanced['ma_status'] = compute_ma_status(
                    price, trend_result.ma5, trend_result.ma10, trend_result.ma20
                )
                enhanced['date'] = date.today().isoformat()
                if yesterday_close is not None:
                    try:
                        yc = float(yesterday_close)
                        if yc > 0:
                            enhanced['price_change_ratio'] = round((price - yc) / yc * 100, 2)
                    except (TypeError, ValueError):
                        pass
                if vol is not None and enhanced.get('yesterday'):
                    yest_vol = (
                        enhanced['yesterday'].get('volume')
                        if isinstance(enhanced['yesterday'], dict)
                        else None
                    )
                    if yest_vol is not None:
                        try:
                            yv = float(yest_vol)
                            if yv > 0:
                                enhanced['volume_change_ratio'] = round(float(vol) / yv, 2)
                        except (TypeError, ValueError):
                            pass

        enhanced['is_index_etf'] = SearchService.is_index_or_etf(
            context.get('code', ''), enhanced.get('stock_name', stock_name)
        )
        enhanced["fundamental_context"] = (
            fundamental_context
            if isinstance(fundamental_context, dict)
            else self.fetcher_manager.build_failed_fundamental_context(
                context.get("code", ""), "invalid fundamental context",
            )
        )

        return enhanced

    def _augment_historical_with_realtime(
        self, df: pd.DataFrame, realtime_quote: Any, code: str
    ) -> pd.DataFrame:
        """
        Augment historical OHLCV with today's realtime quote for intraday MA calculation.
        Issue #234: Use realtime price instead of yesterday's close for technical indicators.
        """
        if df is None or df.empty or 'close' not in df.columns:
            return df
        if realtime_quote is None:
            return df
        price = getattr(realtime_quote, 'price', None)
        if price is None or not (isinstance(price, (int, float)) and price > 0):
            return df

        enable_realtime_tech = getattr(self.config, 'enable_realtime_technical_indicators', True)
        if not enable_realtime_tech:
            return df
        import src.core.pipeline as _pkg
        market = _pkg.get_market_for_stock(code)
        if market and not _pkg.is_market_open(market, date.today()):
            return df

        last_val = df['date'].max()
        last_date = (
            last_val.date() if hasattr(last_val, 'date') else
            (last_val if isinstance(last_val, date) else pd.Timestamp(last_val).date())
        )
        yesterday_close = float(df.iloc[-1]['close']) if len(df) > 0 else price
        open_p = (
            getattr(realtime_quote, 'open_price', None)
            or getattr(realtime_quote, 'pre_close', None)
            or yesterday_close
        )
        high_p = getattr(realtime_quote, 'high', None) or price
        low_p = getattr(realtime_quote, 'low', None) or price
        vol = getattr(realtime_quote, 'volume', None) or 0
        amt = getattr(realtime_quote, 'amount', None)
        pct = getattr(realtime_quote, 'change_pct', None)

        if last_date >= date.today():
            df = df.copy()
            idx = df.index[-1]
            df.loc[idx, 'close'] = price
            if open_p is not None:
                df.loc[idx, 'open'] = open_p
            if high_p is not None:
                df.loc[idx, 'high'] = high_p
            if low_p is not None:
                df.loc[idx, 'low'] = low_p
            if vol:
                df.loc[idx, 'volume'] = vol
            if amt is not None:
                df.loc[idx, 'amount'] = amt
            if pct is not None:
                df.loc[idx, 'pct_chg'] = pct
        else:
            new_row = {
                'code': code, 'date': date.today(),
                'open': open_p, 'high': high_p, 'low': low_p, 'close': price,
                'volume': vol,
                'amount': amt if amt is not None else 0,
                'pct_chg': pct if pct is not None else 0,
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        return df

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
    ) -> Dict[str, Any]:
        """构建分析上下文快照"""
        return {
            "enhanced_context": enhanced_context,
            "news_content": news_content,
            "realtime_quote_raw": safe_to_dict(realtime_quote),
            "chip_distribution_raw": safe_to_dict(chip_data),
        }

    @staticmethod
    def _compute_ma_status(close: float, ma5: float, ma10: float, ma20: float) -> str:
        """Static wrapper for backward compatibility (tests call StockAnalysisPipeline._compute_ma_status)."""
        return compute_ma_status(close, ma5, ma10, ma20)

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """Static wrapper for backward compatibility."""
        return safe_to_dict(value)

    @staticmethod
    def _describe_volume_ratio(volume_ratio: float) -> str:
        """Instance wrapper for backward compatibility."""
        return describe_volume_ratio(volume_ratio)
