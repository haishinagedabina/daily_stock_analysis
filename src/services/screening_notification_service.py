from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.notification import NotificationService
from src.services.screening_task_service import ScreeningTaskService


class ScreeningNotificationError(Exception):
    """Base exception for screening notification failures."""


class ScreeningRunNotFoundError(ScreeningNotificationError):
    """Raised when the target screening run does not exist."""


class ScreeningRunNotReadyError(ScreeningNotificationError):
    """Raised when the target screening run is not ready for notification."""


class ScreeningNotificationDeliveryError(ScreeningNotificationError):
    """Raised when notification delivery fails for all channels."""


class ScreeningNotificationService:
    """全市场筛选推荐名单通知服务。"""

    def __init__(
        self,
        screening_task_service: Optional[ScreeningTaskService] = None,
        notifier: Optional[NotificationService] = None,
    ) -> None:
        self.screening_task_service = screening_task_service or ScreeningTaskService()
        self.notifier = notifier or NotificationService()

    def build_run_notification(self, run: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
        trade_date = run.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
        mode = run.get("mode") or "balanced"
        status = run.get("status") or "completed"
        universe_size = int(run.get("universe_size") or 0)
        candidate_count = int(run.get("candidate_count") or len(candidates))

        lines = [
            f"# 📣 {trade_date} 全市场筛选推荐名单",
            "",
            f"> run_id: `{run.get('run_id', '-')}` | 模式: `{mode}` | 候选数: **{candidate_count}** | 股票池规模: **{universe_size}**",
            "",
        ]
        if status == "completed_with_ai_degraded":
            lines.extend(
                [
                    "> ⚠️ AI 二筛已降级，本次结果以规则输出为主，候选中仅保留已成功回链的 AI/新闻增强信息。",
                    "",
                ]
            )

        if not candidates:
            lines.extend(
                [
                    "## 今日结果",
                    "",
                    "本次筛选未产生可推送候选。",
                    "",
                ]
            )
            return "\n".join(lines)

        lines.extend(["## Top 推荐", ""])
        for item in candidates:
            code = item.get("code", "-")
            name = item.get("name") or code
            final_rank = item.get("final_rank", "-")
            final_score = item.get("final_score")
            score_text = f"{float(final_score):.1f}" if final_score is not None else "N/A"
            source = item.get("recommendation_source") or "rules_only"
            source_text = "AI 增强" if source == "rules_plus_ai" else "规则输出"
            lines.append(f"### {final_rank}. {name} ({code})")
            lines.append("")
            lines.append(f"- 来源: `{source_text}`")
            lines.append(f"- 最终评分: **{score_text}** | 规则分: **{float(item.get('rule_score', 0.0)):.1f}**")
            if item.get("recommendation_reason"):
                lines.append(f"- 推荐理由: {item['recommendation_reason']}")
            if item.get("ai_summary"):
                lines.append(f"- AI 摘要: {item['ai_summary']}")
            if item.get("news_summary"):
                lines.append(f"- 新闻补充: {item['news_summary']}")
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                f"*通知生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            ]
        )
        return "\n".join(lines)

    def send_run_notification(self, run_id: str, limit: int = 10, with_ai_only: bool = False) -> Dict[str, Any]:
        run = self.screening_task_service.get_run(run_id)
        if run is None:
            raise ScreeningRunNotFoundError("筛选任务不存在")
        if run.get("status") not in {"completed", "completed_with_ai_degraded"}:
            raise ScreeningRunNotReadyError("筛选任务尚未完成，暂不可推送")

        candidates = self.screening_task_service.list_candidates(
            run_id=run_id,
            limit=limit,
            with_ai_only=with_ai_only,
        )
        content = self.build_run_notification(run=run, candidates=candidates)
        stock_codes = [str(item.get("code")) for item in candidates if item.get("code")]
        report_path = self.notifier.save_report_to_file(content, filename=f"screening_{run_id}.md")
        success = self.notifier.send(content, email_stock_codes=stock_codes or None)
        if not success:
            raise ScreeningNotificationDeliveryError("筛选推荐通知发送失败")
        return {
            "success": True,
            "message": "筛选推荐通知发送成功",
            "run_id": run_id,
            "candidate_count": len(candidates),
            "report_path": report_path,
        }
