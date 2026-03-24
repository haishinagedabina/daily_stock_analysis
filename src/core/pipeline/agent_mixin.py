# -*- coding: utf-8 -*-
"""
Agent 模式分析 Mixin - 负责 Agent 模式下的股票分析及结果转换
"""
import logging
import re
from typing import Any, Dict, Optional

from data_provider.realtime_types import ChipDistribution
from data_provider.us_index_mapping import is_us_stock_code
from src.analyzer import AnalysisResult, fill_chip_structure_if_needed, fill_price_position_if_needed
from src.enums import ReportType
from src.stock_analyzer import TrendAnalysisResult
from src.core.pipeline.utils import safe_to_dict
from src.core.pipeline._typing import PipelineMixin

logger = logging.getLogger(__name__)


class AgentMixin(PipelineMixin):
    """负责 Agent 模式分析及 AgentResult → AnalysisResult 转换"""

    def _analyze_with_agent(
        self,
        code: str,
        report_type: ReportType,
        query_id: str,
        stock_name: str,
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]] = None,
        trend_result: Optional[TrendAnalysisResult] = None,
    ) -> Optional[AnalysisResult]:
        """使用 Agent 模式分析单只股票。"""
        try:
            from src.agent.factory import build_agent_executor

            executor = build_agent_executor(
                self.config, getattr(self.config, 'agent_skills', None) or None
            )

            initial_context: Dict[str, Any] = {
                "stock_code": code,
                "stock_name": stock_name,
                "report_type": report_type.value,
                "fundamental_context": fundamental_context,
            }

            if realtime_quote:
                initial_context["realtime_quote"] = safe_to_dict(realtime_quote)
            if chip_data:
                initial_context["chip_distribution"] = safe_to_dict(chip_data)
            if trend_result:
                initial_context["trend_result"] = safe_to_dict(trend_result)

            # Social sentiment injection (US stocks only)
            if self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        existing = initial_context.get("news_context")
                        initial_context["news_context"] = (
                            existing + "\n\n" + social_context if existing else social_context
                        )
                        logger.info(f"[{code}] Agent mode: social sentiment data injected into news_context")
                except Exception as e:
                    logger.warning(f"[{code}] Agent mode: social sentiment fetch failed: {e}")

            message = f"请分析股票 {code} ({stock_name})，并生成决策仪表盘报告。"
            agent_result = executor.run(message, context=initial_context)

            result = self._agent_result_to_analysis_result(
                agent_result, code, stock_name, report_type, query_id
            )
            if result:
                result.query_id = query_id

            # Agent weak integrity: placeholder fill only
            if result and getattr(self.config, "report_integrity_enabled", False):
                from src.analyzer import check_content_integrity, apply_placeholder_fill

                pass_integrity, missing = check_content_integrity(result)
                if not pass_integrity:
                    apply_placeholder_fill(result, missing)
                    logger.info(
                        "[LLM完整性] integrity_mode=agent_weak 必填字段缺失 %s，已占位补全", missing
                    )

            if result and chip_data:
                fill_chip_structure_if_needed(result, chip_data)

            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)

            resolved_stock_name = result.name if result and result.name else stock_name

            # 保存新闻情报（Fixes #396）
            if self.search_service.is_available:
                try:
                    news_response = self.search_service.search_stock_news(
                        stock_code=code, stock_name=resolved_stock_name, max_results=5
                    )
                    if news_response.success and news_response.results:
                        query_context = self._build_query_context(query_id=query_id)
                        self.db.save_news_intel(
                            code=code, name=resolved_stock_name, dimension="latest_news",
                            query=news_response.query, response=news_response,
                            query_context=query_context,
                        )
                        logger.info(f"[{code}] Agent 模式: 新闻情报已保存 {len(news_response.results)} 条")
                except Exception as e:
                    logger.warning(f"[{code}] Agent 模式保存新闻情报失败: {e}")

            # 保存分析历史（用 snapshot_context 副本，避免修改已传给 executor 的 initial_context）
            if result:
                try:
                    snapshot_context = {**initial_context, "stock_name": resolved_stock_name}
                    self.db.save_analysis_history(
                        result=result, query_id=query_id,
                        report_type=report_type.value, news_content=None,
                        context_snapshot=snapshot_context,
                        save_snapshot=self.save_context_snapshot,
                    )
                except Exception as e:
                    logger.warning(f"[{code}] 保存 Agent 分析历史失败: {e}")

            return result

        except Exception as e:
            logger.error(f"[{code}] Agent 分析失败: {e}")
            logger.exception(f"[{code}] Agent 详细错误信息:")
            return None

    def _agent_result_to_analysis_result(
        self, agent_result: Any, code: str, stock_name: str,
        report_type: ReportType, query_id: str,
    ) -> AnalysisResult:
        """将 AgentResult 转换为 AnalysisResult。"""
        result = AnalysisResult(
            code=code,
            name=stock_name,
            sentiment_score=50,
            trend_prediction="未知",
            operation_advice="观望",
            success=agent_result.success,
            error_message=agent_result.error or None,
            data_sources=f"agent:{agent_result.provider}",
            model_used=agent_result.model or None,
        )

        if agent_result.success and agent_result.dashboard:
            dash = agent_result.dashboard
            ai_stock_name = str(dash.get("stock_name", "")).strip()
            if ai_stock_name and self._is_placeholder_stock_name(stock_name, code):
                result.name = ai_stock_name
            result.sentiment_score = max(0, min(100, self._safe_int(dash.get("sentiment_score"), 50)))
            result.trend_prediction = dash.get("trend_prediction", "未知")
            raw_advice = dash.get("operation_advice", "观望")
            if isinstance(raw_advice, dict):
                _signal_to_advice = {
                    "buy": "买入", "sell": "卖出", "hold": "持有",
                    "strong_buy": "强烈买入", "strong_sell": "强烈卖出",
                }
                raw_dt = str(dash.get("decision_type") or "hold").strip().lower()
                result.operation_advice = _signal_to_advice.get(raw_dt, "观望")
            else:
                result.operation_advice = str(raw_advice) if raw_advice else "观望"
            from src.agent.protocols import normalize_decision_signal

            result.decision_type = normalize_decision_signal(dash.get("decision_type", "hold"))
            result.analysis_summary = dash.get("analysis_summary", "")
            result.dashboard = dash.get("dashboard") or dash
        else:
            result.sentiment_score = 50
            result.operation_advice = "观望"
            if not result.error_message:
                result.error_message = "Agent 未能生成有效的决策仪表盘"

        return result

    @staticmethod
    def _is_placeholder_stock_name(name: str, code: str) -> bool:
        """Return True when the stock name is missing or placeholder-like."""
        if not name:
            return True
        normalized = str(name).strip()
        if not normalized:
            return True
        if normalized == code:
            return True
        if normalized.startswith("股票"):
            return True
        if "Unknown" in normalized:
            return True
        return False

    @staticmethod
    def _safe_int(value: Any, default: int = 50) -> int:
        """安全地将值转换为整数。"""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            match = re.search(r'-?\d+', value)
            if match:
                return int(match.group())
        return default
