# -*- coding: utf-8 -*-
"""
数据获取 Mixin - 负责股票数据拉取、保存及查询上下文构建
"""
import logging
from datetime import date
from typing import Dict, Optional, Tuple

from src.core.pipeline._typing import PipelineMixin

logger = logging.getLogger(__name__)


class DataMixin(PipelineMixin):
    """负责数据获取/保存及查询上下文相关方法"""

    def fetch_and_save_stock_data(
        self,
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据（DB 优先 + 增量拉取）

        策略：
        1. DB 有今日数据 → 跳过
        2. DB 数据新鲜（≤3 自然日）且行数充足 → 跳过全量拉取，仅增量补齐
        3. DB 行数不足或无数据 → 全量拉取 data_fetch_days
        4. 外部拉取失败但 DB 有数据 → 降级使用 DB 数据
        """
        stock_name = ""
        try:
            stock_name = self.fetcher_manager.get_stock_name(code)
            today = date.today()

            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"{stock_name}({code}) 今日数据已存在，跳过获取")
                return True, None

            db_row_count = self.db.get_stock_row_count(code)
            db_latest_date = self.db.get_latest_date(code)
            min_required_rows = max(self.config.data_fetch_days, 200)

            if not force_refresh and db_row_count >= min_required_rows and self.db.is_data_fresh(code):
                logger.info(
                    f"{stock_name}({code}) DB 数据充足且新鲜 "
                    f"(rows={db_row_count}, latest={db_latest_date})，跳过拉取"
                )
                return True, None

            if db_row_count >= min_required_rows and db_latest_date is not None:
                stale_days = (today - db_latest_date).days
                fetch_days = min(stale_days + 5, 30)
                logger.info(
                    f"{stock_name}({code}) DB 有 {db_row_count} 行, "
                    f"最新 {db_latest_date}, 增量拉取最近 {fetch_days} 天"
                )
            else:
                fetch_days = self.config.data_fetch_days
                if db_row_count > 0:
                    logger.info(
                        f"{stock_name}({code}) DB 行数不足 "
                        f"({db_row_count}/{min_required_rows}), 全量拉取 {fetch_days} 天"
                    )
                else:
                    logger.info(f"{stock_name}({code}) DB 无数据，全量拉取 {fetch_days} 天")

            df, source_name = self.fetcher_manager.get_daily_data(code, days=fetch_days)

            if df is None or df.empty:
                if db_row_count > 0:
                    logger.warning(
                        f"{stock_name}({code}) 增量拉取无数据返回，"
                        f"但 DB 已有 {db_row_count} 行，继续使用 DB 数据"
                    )
                    return True, None
                return False, "获取数据为空且 DB 无历史数据"

            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(
                f"{stock_name}({code}) 数据保存成功 "
                f"(来源={source_name}, 拉取={fetch_days}天, 新增/更新={saved_count})"
            )
            return True, None

        except Exception as e:
            error_msg = f"获取/保存数据失败: {str(e)}"
            logger.error(f"{stock_name}({code}) {error_msg}")
            if self.db.get_stock_row_count(code) > 0:
                logger.warning(f"{stock_name}({code}) 拉取失败但 DB 有历史数据，降级使用")
                return True, None
            return False, error_msg

    def _resolve_query_source(self, query_source: Optional[str]) -> str:
        """
        解析请求来源。

        优先级（从高到低）：
        1. 显式传入的 query_source
        2. 存在 source_message 时推断为 "bot"
        3. 存在 query_id 时推断为 "web"
        4. 默认 "system"
        """
        if query_source:
            return query_source
        if self.source_message:
            return "bot"
        if self.query_id:
            return "web"
        return "system"

    def _build_query_context(self, query_id: Optional[str] = None) -> Dict[str, str]:
        """生成用户查询关联信息"""
        effective_query_id = query_id or self.query_id or ""

        context: Dict[str, str] = {
            "query_id": effective_query_id,
            "query_source": self.query_source or "",
        }

        if self.source_message:
            context.update({
                "requester_platform": self.source_message.platform or "",
                "requester_user_id": self.source_message.user_id or "",
                "requester_user_name": self.source_message.user_name or "",
                "requester_chat_id": self.source_message.chat_id or "",
                "requester_message_id": self.source_message.message_id or "",
                "requester_query": self.source_message.content or "",
            })

        return context
