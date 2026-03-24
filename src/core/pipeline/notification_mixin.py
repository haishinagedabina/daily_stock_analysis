# -*- coding: utf-8 -*-
"""
通知发送 Mixin - 负责报告生成、本地保存及多渠道推送
"""
import logging
import traceback
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, cast

from src.analyzer import AnalysisResult
from src.enums import ReportType
from src.notification import NotificationChannel
from src.core.pipeline._typing import PipelineMixin

# Use the package-level logger name so that patching src.core.pipeline.logger
# in tests affects the same Logger instance used here.
logger = logging.getLogger("src.core.pipeline")


class NotificationMixin(PipelineMixin):
    """负责汇总报告生成、本地保存及多渠道通知推送"""

    def _save_local_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
    ) -> None:
        """保存分析报告到本地文件（与通知推送解耦）"""
        try:
            report = self._generate_aggregate_report(results, report_type)
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"决策仪表盘日报已保存: {filepath}")
        except Exception as e:
            logger.error(f"保存本地报告失败: {e}")

    def _send_notifications(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
        skip_push: bool = False,
    ) -> None:
        """
        发送分析结果通知

        Args:
            results: 分析结果列表
            report_type: 报告类型
            skip_push: 是否跳过推送（仅保存到本地，用于单股推送模式）
        """
        try:
            logger.info("生成决策仪表盘日报...")
            report = self._generate_aggregate_report(results, report_type)

            if skip_push:
                return

            if not self.notifier.is_available():
                logger.info("通知渠道未配置，跳过推送")
                return

            channels = self.notifier.get_available_channels()
            context_success = self.notifier.send_to_context(report)

            from src.md2img import markdown_to_image

            channels_needing_image = {
                ch for ch in channels
                if ch.value in self.notifier._markdown_to_image_channels
            }
            non_wechat_channels_needing_image = {
                ch for ch in channels_needing_image if ch != NotificationChannel.WECHAT
            }

            def _get_md2img_hint() -> str:
                try:
                    engine = getattr(self.config, "md2img_engine", "wkhtmltoimage")
                except Exception:
                    engine = "wkhtmltoimage"
                return (
                    "npm i -g markdown-to-file" if engine == "markdown-to-file"
                    else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
                )

            image_bytes = None
            if non_wechat_channels_needing_image:
                image_bytes = markdown_to_image(
                    report, max_chars=self.notifier._markdown_to_image_max_chars
                )
                if image_bytes:
                    logger.info(
                        "Markdown 已转换为图片，将向 %s 发送图片",
                        [ch.value for ch in non_wechat_channels_needing_image],
                    )
                else:
                    logger.warning(
                        "Markdown 转图片失败，将回退为文本发送。请检查 MARKDOWN_TO_IMAGE_CHANNELS 配置并安装 %s",
                        _get_md2img_hint(),
                    )

            # 企业微信：只发精简版
            wechat_success = False
            if NotificationChannel.WECHAT in channels:
                if report_type == ReportType.BRIEF:
                    dashboard_content = self.notifier.generate_brief_report(results)
                else:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                logger.info(f"企业微信仪表盘长度: {len(dashboard_content)} 字符")
                logger.debug(f"企业微信推送内容:\n{dashboard_content}")
                wechat_image_bytes = None
                if NotificationChannel.WECHAT in channels_needing_image:
                    wechat_image_bytes = markdown_to_image(
                        dashboard_content,
                        max_chars=self.notifier._markdown_to_image_max_chars,
                    )
                    if wechat_image_bytes is None:
                        logger.warning(
                            "企业微信 Markdown 转图片失败，将回退为文本发送。请检查 MARKDOWN_TO_IMAGE_CHANNELS 配置并安装 %s",
                            _get_md2img_hint(),
                        )
                use_image = self.notifier._should_use_image_for_channel(
                    NotificationChannel.WECHAT, wechat_image_bytes
                )
                if use_image and wechat_image_bytes is not None:
                    wechat_success = self.notifier._send_wechat_image(wechat_image_bytes)
                else:
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

            # 其他渠道
            non_wechat_success = False
            stock_email_groups = getattr(self.config, 'stock_email_groups', []) or []
            for channel in channels:
                if channel == NotificationChannel.WECHAT:
                    continue
                non_wechat_success = self._send_to_channel(
                    channel, report, results, report_type,
                    image_bytes, stock_email_groups,
                ) or non_wechat_success

            success = wechat_success or non_wechat_success or context_success
            if success:
                logger.info("决策仪表盘推送成功")
            else:
                logger.warning("决策仪表盘推送失败")

        except Exception as e:
            logger.error(f"发送通知失败: {e}\n{traceback.format_exc()}")

    def _send_to_channel(
        self,
        channel: NotificationChannel,
        report: str,
        results: List[AnalysisResult],
        report_type: ReportType,
        image_bytes: Optional[bytes],
        stock_email_groups: List[Tuple[List[str], List[str]]],
    ) -> bool:
        """向单个非微信渠道发送通知，返回是否成功。"""
        from src.md2img import markdown_to_image

        if channel == NotificationChannel.FEISHU:
            return self.notifier.send_to_feishu(report)

        if channel == NotificationChannel.TELEGRAM:
            use_image = self.notifier._should_use_image_for_channel(channel, image_bytes)
            if use_image and image_bytes is not None:
                return self.notifier._send_telegram_photo(image_bytes)
            return self.notifier.send_to_telegram(report)

        if channel == NotificationChannel.EMAIL:
            return self._send_email_channel(
                report, results, report_type, image_bytes, stock_email_groups, channel
            )

        if channel == NotificationChannel.CUSTOM:
            use_image = self.notifier._should_use_image_for_channel(channel, image_bytes)
            if use_image and image_bytes is not None:
                return self.notifier._send_custom_webhook_image(image_bytes, fallback_content=report)
            return self.notifier.send_to_custom(report)

        if channel == NotificationChannel.PUSHPLUS:
            return self.notifier.send_to_pushplus(report)
        if channel == NotificationChannel.SERVERCHAN3:
            return self.notifier.send_to_serverchan3(report)
        if channel == NotificationChannel.DISCORD:
            return self.notifier.send_to_discord(report)
        if channel == NotificationChannel.PUSHOVER:
            return self.notifier.send_to_pushover(report)
        if channel == NotificationChannel.ASTRBOT:
            return self.notifier.send_to_astrbot(report)

        logger.warning(f"未知通知渠道: {channel}")
        return False

    def _send_email_channel(
        self,
        report: str,
        results: List[AnalysisResult],
        report_type: ReportType,
        image_bytes: Optional[bytes],
        stock_email_groups: List[Tuple[List[str], List[str]]],
        channel: NotificationChannel,
    ) -> bool:
        """处理邮件渠道的分组发送逻辑。"""
        from src.md2img import markdown_to_image

        if not stock_email_groups:
            use_image = self.notifier._should_use_image_for_channel(channel, image_bytes)
            if use_image and image_bytes is not None:
                return self.notifier._send_email_with_inline_image(image_bytes)
            return self.notifier.send_to_email(report)

        # 按股票-邮件组分组
        code_to_emails: Dict[str, Optional[List[str]]] = {}
        for r in results:
            if r.code not in code_to_emails:
                emails = []
                for stocks, emails_list in stock_email_groups:
                    if r.code in stocks:
                        emails.extend(emails_list)
                code_to_emails[r.code] = list(dict.fromkeys(emails)) if emails else None

        emails_to_results: Dict[Optional[Tuple[str, ...]], List[AnalysisResult]] = defaultdict(list)
        for r in results:
            recs = code_to_emails.get(r.code)
            key = tuple(recs) if recs else None
            emails_to_results[key].append(r)

        success = False
        for key, group_results in emails_to_results.items():
            grp_report = self._generate_aggregate_report(group_results, report_type)
            grp_image_bytes = None
            if channel.value in self.notifier._markdown_to_image_channels:
                grp_image_bytes = markdown_to_image(
                    grp_report, max_chars=self.notifier._markdown_to_image_max_chars
                )
            use_image = self.notifier._should_use_image_for_channel(channel, grp_image_bytes)
            receivers = list(key) if key is not None else None
            if use_image and grp_image_bytes is not None:
                result = self.notifier._send_email_with_inline_image(grp_image_bytes, receivers=receivers)
            else:
                result = self.notifier.send_to_email(grp_report, receivers=receivers)
            success = result or success
        return success

    def _generate_aggregate_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType,
    ) -> str:
        """Generate aggregate report with backward-compatible notifier fallback."""
        generator = getattr(self.notifier, "generate_aggregate_report", None)
        if callable(generator):
            return cast(str, generator(results, report_type))
        if report_type == ReportType.BRIEF and hasattr(self.notifier, "generate_brief_report"):
            return self.notifier.generate_brief_report(results)
        return self.notifier.generate_dashboard_report(results)
