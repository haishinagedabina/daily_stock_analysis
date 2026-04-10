from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.notification import NotificationService
from src.services.screening_task_service import ScreeningTaskService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

_COMPLETED_STATUSES = {"completed", "completed_with_ai_degraded"}

# ---------------------------------------------------------------------------
# Audit-content constants
# ---------------------------------------------------------------------------

# AI operation advice → score bonus mapping (mirrors DatabaseManager._screening_ai_bonus)
_AI_BONUS_MAP: Dict[str, float] = {
    "买入": 8.0,
    "加仓": 6.0,
    "关注": 4.0,
    "持有": 2.0,
    "观望": 0.0,
    "减仓": -4.0,
    "卖出": -8.0,
}

# Rule hit key → Chinese display name
_RULE_HIT_ZH: Dict[str, str] = {
    "trend_aligned": "趋势对齐",
    "volume_expanding": "放量",
    "near_breakout": "临近突破",
    "liquidity_ok": "流动性合格",
}

# Number of top candidates that receive the full audit block; the rest get a summary line.
_AUDIT_TOP_N_DEFAULT = 5

# ---------------------------------------------------------------------------
# Five-layer decision label mappings (Phase 3B-2)
# ---------------------------------------------------------------------------

_REGIME_LABELS: Dict[str, str] = {
    "aggressive": "进攻",
    "balanced": "均衡",
    "defensive": "防守",
    "stand_aside": "观望",
}

_STAGE_LABELS: Dict[str, str] = {
    "probe_entry": "试探进场",
    "add_on_strength": "强势加仓",
    "focus": "重点关注",
    "watch": "观察",
    "stand_aside": "观望",
    "reject": "拒绝",
}

_SETUP_LABELS: Dict[str, str] = {
    "bottom_divergence_breakout": "底背离突破",
    "low123_breakout": "123结构突破",
    "trend_breakout": "趋势突破",
    "trend_pullback": "趋势回踩",
    "gap_breakout": "缺口突破",
    "limitup_structure": "涨停结构突破",
    "none": "无",
}


# ---------------------------------------------------------------------------
# Module-level private helpers
# ---------------------------------------------------------------------------


def _fmt_amount(val: Any) -> str:
    """Format a raw avg_amount value into a human-readable string (亿 / 万 / raw)."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "N/A"
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:.0f}"


def _fmt_percent(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "N/A"
    return f"{v * 100:.0f}%"


def _get_rule_hits(item: Dict[str, Any]) -> List[str]:
    """Extract rule_hits list from a candidate dict, handling JSON string or list."""
    rule_hits = item.get("rule_hits")
    if rule_hits is None:
        raw = item.get("rule_hits_json") or "[]"
        rule_hits = json.loads(raw) if isinstance(raw, str) else raw
    elif isinstance(rule_hits, str):
        rule_hits = json.loads(rule_hits or "[]")
    return list(rule_hits) if rule_hits else []


def _get_factor_snapshot(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract factor_snapshot dict from a candidate dict, handling JSON string or dict."""
    factor = item.get("factor_snapshot")
    if factor is None:
        raw = item.get("factor_snapshot_json") or "{}"
        factor = json.loads(raw) if isinstance(raw, str) else raw
    elif isinstance(factor, str):
        factor = json.loads(factor or "{}")
    return dict(factor) if factor else {}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScreeningNotificationError(Exception):
    """Base exception for screening notification failures."""


class ScreeningRunNotFoundError(ScreeningNotificationError):
    """Raised when the target screening run does not exist."""


class ScreeningRunNotReadyError(ScreeningNotificationError):
    """Raised when the target screening run is not ready for notification."""


class ScreeningNotificationDeliveryError(ScreeningNotificationError):
    """Raised when notification delivery fails for all channels."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ScreeningNotificationService:
    """全市场筛选推荐名单通知服务。"""

    def __init__(
        self,
        screening_task_service: Optional[ScreeningTaskService] = None,
        notifier: Optional[NotificationService] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.screening_task_service = screening_task_service or ScreeningTaskService()
        self.notifier = notifier or NotificationService()
        self.db = db_manager or DatabaseManager.get_instance()

    # ------------------------------------------------------------------
    # Idempotent notification entry point
    # ------------------------------------------------------------------

    @staticmethod
    def can_notify(run: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """Check whether a run is eligible for notification.

        Returns dict with ``allowed`` (bool) and optional ``reason``.
        """
        status = run.get("status", "")
        if status not in _COMPLETED_STATUSES:
            return {"allowed": False, "reason": "run_not_completed"}

        ns = run.get("notification_status") or "pending"
        if ns == "sent":
            # v1: never allow re-send of already-sent
            return {"allowed": False, "reason": "already_sent"}
        if ns == "pending" or ns == "failed":
            return {"allowed": True}
        if ns == "skipped":
            if force:
                return {"allowed": True}
            return {"allowed": False, "reason": "skipped_need_force"}
        return {"allowed": False, "reason": f"unknown_status_{ns}"}

    def notify_run(self, run_id: str, force: bool = False) -> Dict[str, Any]:
        """Idempotent notification entry point for a screening run.

        1. Fetch run and validate
        2. Gate via ``can_notify``
        3. Build message, send, update notification status
        """
        run = self.screening_task_service.get_run(run_id)
        if run is None:
            raise ScreeningRunNotFoundError("筛选任务不存在")
        if run.get("status") not in _COMPLETED_STATUSES:
            raise ScreeningRunNotReadyError("筛选任务尚未完成，暂不可推送")

        gate = self.can_notify(run, force=force)
        if not gate["allowed"]:
            reason = gate.get("reason", "unknown")
            return {"skipped": True, "reason": reason, "run_id": run_id}

        # Build notification content
        candidates = self.screening_task_service.list_candidates(run_id=run_id, limit=10)
        content = self.build_run_notification(run=run, candidates=candidates)
        stock_codes = [str(item.get("code")) for item in candidates if item.get("code")]

        # Attempt delivery
        try:
            self.notifier.save_report_to_file(content, filename=f"screening_{run_id}.md")
            success = self.notifier.send(content, email_stock_codes=stock_codes or None)
        except Exception as exc:
            self._mark_notification_failed(run_id, str(exc))
            return {
                "success": False,
                "notification_status": "failed",
                "run_id": run_id,
                "error": str(exc),
            }

        if success:
            self._mark_notification_sent(run_id)
            return {
                "success": True,
                "notification_status": "sent",
                "run_id": run_id,
                "candidate_count": len(candidates),
            }
        else:
            self._mark_notification_failed(run_id, "delivery returned false")
            return {
                "success": False,
                "notification_status": "failed",
                "run_id": run_id,
                "error": "delivery returned false",
            }

    # ------------------------------------------------------------------
    # Status persistence helpers
    # ------------------------------------------------------------------

    def _mark_notification_sent(self, run_id: str) -> None:
        self.db.update_notification_status(run_id=run_id, notification_status="sent")

    def _mark_notification_failed(self, run_id: str, error: str) -> None:
        self.db.update_notification_status(
            run_id=run_id,
            notification_status="failed",
            notification_error=error,
        )

    # ------------------------------------------------------------------
    # Audit-content helpers (new)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_score_breakdown(item: Dict[str, Any]) -> Dict[str, Any]:
        """Build a structured score breakdown for a single candidate.

        Returns:
            {
                "rule_score": float,
                "ai_bonus": float,
                "news_bonus": int,
                "final_score": float,
                "rule_breakdown": [{"name": str, "score": float, "reason": str}, ...]
            }
        The breakdown faithfully mirrors the formulas in ScreenerService._score()
        and DatabaseManager._enrich_screening_candidates(). No scoring logic is changed.
        """
        rule_hits = _get_rule_hits(item)
        factor = _get_factor_snapshot(item)

        rule_score = float(item.get("rule_score") or 0.0)
        advice = item.get("ai_operation_advice") or ""
        ai_bonus = _AI_BONUS_MAP.get(advice, 0.0)
        news_count = int(item.get("news_count") or 0)
        news_bonus = min(news_count, 3)
        final_score = round(rule_score + ai_bonus + news_bonus, 2)

        # Extract raw factor values used in score formula
        close = float(factor.get("close") or 0.0)
        ma5 = float(factor.get("ma5") or 0.0)
        ma10 = float(factor.get("ma10") or 0.0)
        ma20 = float(factor.get("ma20") or 0.0)
        volume_ratio = float(factor.get("volume_ratio") or 0.0)
        breakout_ratio = float(factor.get("breakout_ratio") or 0.0)

        rule_breakdown: List[Dict[str, Any]] = []

        # --- discrete rule hits ---
        if "trend_aligned" in rule_hits:
            rule_breakdown.append({
                "name": "趋势对齐",
                "score": 40.0,
                "reason": (
                    f"close({close:.2f}) >= MA20({ma20:.2f}) "
                    f"且 MA5({ma5:.2f}) >= MA10({ma10:.2f}) >= MA20({ma20:.2f})"
                ),
            })
        if "volume_expanding" in rule_hits:
            rule_breakdown.append({
                "name": "放量条件",
                "score": 30.0,
                "reason": f"volume_ratio={volume_ratio:.2f}",
            })
        if "near_breakout" in rule_hits:
            rule_breakdown.append({
                "name": "临近突破",
                "score": 20.0,
                "reason": f"breakout_ratio={breakout_ratio:.4f} >= 0.995",
            })
        if "liquidity_ok" in rule_hits:
            rule_breakdown.append({
                "name": "流动性合格",
                "score": 10.0,
                "reason": "avg_amount 达到阈值",
            })

        # --- continuous weighted components (mirrors ScreenerService._score) ---
        breakout_premium = max(breakout_ratio - 1.0, 0.0) * 1000
        if breakout_premium > 0:
            rule_breakdown.append({
                "name": "突破溢价加分",
                "score": round(breakout_premium, 1),
                "reason": f"max({breakout_ratio:.4f} - 1, 0) × 1000",
            })

        volume_supplement = min(volume_ratio, 3.0)
        if volume_supplement > 0:
            rule_breakdown.append({
                "name": "量比补充分",
                "score": round(volume_supplement, 2),
                "reason": f"min({volume_ratio:.2f}, 3.0)",
            })

        return {
            "rule_score": rule_score,
            "ai_bonus": ai_bonus,
            "news_bonus": news_bonus,
            "final_score": final_score,
            "rule_breakdown": rule_breakdown,
        }

    @staticmethod
    def _build_factor_snapshot_summary(item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract raw factor values from a candidate's factor_snapshot.

        Returns a dict with close, ma5/ma10/ma20, volume_ratio, breakout_ratio,
        avg_amount (raw + human-readable), days_since_listed, is_st.
        """
        factor = _get_factor_snapshot(item)

        avg_amount_raw = factor.get("avg_amount")
        return {
            "close": factor.get("close"),
            "ma5": factor.get("ma5"),
            "ma10": factor.get("ma10"),
            "ma20": factor.get("ma20"),
            "volume_ratio": factor.get("volume_ratio"),
            "breakout_ratio": factor.get("breakout_ratio"),
            "avg_amount": avg_amount_raw,
            "avg_amount_readable": _fmt_amount(avg_amount_raw),
            "days_since_listed": factor.get("days_since_listed"),
            "is_st": factor.get("is_st"),
        }

    def _format_candidate_audit_block(self, item: Dict[str, Any]) -> List[str]:
        """Format a single candidate as a full audit block (used for Top N).

        Sections: [总览] [五层决策] [评分汇总] [审计证据] [原始指标]
                  [AI增强] (if available)  [新闻增强] (if available)
        """
        code = item.get("code", "-")
        name = item.get("name") or code
        final_rank = item.get("final_rank", "-")
        source = item.get("recommendation_source") or "rules_only"
        source_text = "AI 增强" if source == "rules_plus_ai" else "规则输出"

        breakdown = self._build_score_breakdown(item)
        snapshot = self._build_factor_snapshot_summary(item)
        rule_hits = _get_rule_hits(item)

        # Use item's authoritative final_score when available; fall back to computed value.
        final_score_display = (
            float(item["final_score"]) if item.get("final_score") is not None
            else breakdown["final_score"]
        )
        rule_score_display = float(item.get("rule_score") or breakdown["rule_score"])

        lines: List[str] = [f"### {final_rank}. {name} ({code})", ""]

        # [总览]
        lines.append("**[总览]**")
        lines.append(f"- 来源: `{source_text}`")
        lines.append(
            f"- 最终评分: **{final_score_display:.1f}** | 规则分: **{rule_score_display:.1f}**"
        )
        lines.append("")

        # [五层决策] — shown when any five-layer field is present
        trade_stage = item.get("trade_stage")
        has_five_layer = trade_stage is not None or item.get("setup_type") is not None
        if has_five_layer:
            lines.append("**[五层决策]**")
            stage_label = _STAGE_LABELS.get(trade_stage or "", trade_stage or "N/A")
            lines.append(f"- 交易阶段: **{stage_label}**")
            setup = item.get("setup_type") or ""
            setup_label = _SETUP_LABELS.get(setup, setup or "N/A")
            lines.append(f"- 买点类型: {setup_label}")
            lines.append(
                f"- 成熟度: {item.get('entry_maturity', 'N/A')} | "
                f"风险: {item.get('risk_level', 'N/A')} | "
                f"新鲜度: {_fmt_percent(item.get('setup_freshness'))}"
            )
            lines.append(
                f"- 题材: {item.get('theme_tag', 'N/A')} | "
                f"题材地位: {item.get('theme_position', 'N/A')} | "
                f"候选池: {item.get('candidate_pool_level', 'N/A')}"
            )

            # Trade plan details for actionable stages
            trade_plan = item.get("trade_plan")
            if trade_plan and isinstance(trade_plan, dict):
                lines.append(
                    f"- 止损: {trade_plan.get('stop_loss_rule', 'N/A')}"
                )
                lines.append(
                    f"- 仓位: {trade_plan.get('initial_position', 'N/A')} | "
                    f"持仓期: {trade_plan.get('holding_expectation', 'N/A')}"
                )
                if trade_plan.get("execution_note"):
                    lines.append(f"- 执行备注: {trade_plan['execution_note']}")
                if trade_plan.get("add_rule"):
                    lines.append(f"- 加仓: {trade_plan['add_rule']}")
            lines.append("")

        # [评分汇总]
        lines.append("**[评分汇总]**")
        lines.append(f"- 规则分：{rule_score_display:.1f}")
        ai_sign = "+" if breakdown["ai_bonus"] >= 0 else ""
        lines.append(f"- AI加分：{ai_sign}{breakdown['ai_bonus']:.1f}")
        lines.append(f"- 新闻加分：+{breakdown['news_bonus']}")
        lines.append(f"- 最终总分：{final_score_display:.1f}")
        lines.append("")

        # [规则分拆解]
        lines.append("**[规则分拆解]**")
        for rb in breakdown["rule_breakdown"]:
            lines.append(f"- {rb['name']}：+{rb['score']} → {rb['reason']}")
        if not breakdown["rule_breakdown"]:
            lines.append("- （无规则命中）")
        lines.append("")

        # [审计证据]
        hit_texts = [_RULE_HIT_ZH.get(h, h) for h in rule_hits]
        lines.append(f"**[审计证据]** {' | '.join(hit_texts) if hit_texts else '无'}")
        lines.append("")

        # [原始指标]
        lines.append("**[原始指标]**")
        close = snapshot.get("close")
        ma5 = snapshot.get("ma5")
        ma10 = snapshot.get("ma10")
        ma20 = snapshot.get("ma20")
        close_str = f"{float(close):.2f}" if close is not None else "N/A"
        ma5_str = f"{float(ma5):.2f}" if ma5 is not None else "N/A"
        ma10_str = f"{float(ma10):.2f}" if ma10 is not None else "N/A"
        ma20_str = f"{float(ma20):.2f}" if ma20 is not None else "N/A"
        lines.append(
            f"- close: {close_str} | ma5/ma10/ma20: {ma5_str} / {ma10_str} / {ma20_str}"
        )
        vr = snapshot.get("volume_ratio")
        br = snapshot.get("breakout_ratio")
        vr_str = f"{float(vr):.2f}" if vr is not None else "N/A"
        br_str = f"{float(br):.4f}" if br is not None else "N/A"
        lines.append(f"- volume_ratio: {vr_str} | breakout_ratio: {br_str}")
        lines.append(
            f"- avg_amount: {snapshot['avg_amount_readable']} | "
            f"days_since_listed: {snapshot.get('days_since_listed', 'N/A')} | "
            f"is_st: {snapshot.get('is_st', 'N/A')}"
        )
        lines.append("")

        # [AI增强] — shown when any AI-related field is present
        has_ai = bool(
            item.get("has_ai_analysis")
            or item.get("ai_operation_advice")
            or item.get("ai_summary")
        )
        if has_ai:
            lines.append("**[AI增强]**")
            advice = item.get("ai_operation_advice") or ""
            ai_sign = "+" if breakdown["ai_bonus"] >= 0 else ""
            lines.append(
                f"- 操作建议: {advice} | AI加分: {ai_sign}{breakdown['ai_bonus']:.1f}"
            )
            if item.get("ai_summary"):
                lines.append(f"- AI摘要: {item['ai_summary']}")
            lines.append("")

        # [新闻增强] — shown when news_count > 0 or news_summary is present
        news_count = int(item.get("news_count") or 0)
        has_news = news_count > 0 or bool(item.get("news_summary"))
        if has_news:
            lines.append("**[新闻增强]**")
            lines.append(f"- 新闻条数: {news_count} | 新闻加分: +{breakdown['news_bonus']}")
            if item.get("news_summary"):
                lines.append(f"- 新闻摘要: {item['news_summary']}")
            lines.append("")

        return lines

    def _format_candidate_summary_block(self, item: Dict[str, Any]) -> List[str]:
        """Format a single candidate as a compact summary line (used for rank > audit_top_n)."""
        code = item.get("code", "-")
        name = item.get("name") or code
        final_rank = item.get("final_rank", "-")
        final_score = item.get("final_score")
        score_text = f"{float(final_score):.1f}" if final_score is not None else "N/A"
        source = item.get("recommendation_source") or "rules_only"
        source_text = "AI 增强" if source == "rules_plus_ai" else "规则输出"
        stage = item.get("trade_stage")
        stage_text = f" | {_STAGE_LABELS.get(stage, stage)}" if stage else ""
        return [
            f"### {final_rank}. {name} ({code}) — {score_text}分{stage_text} | 来源: {source_text}",
            "",
        ]

    # ------------------------------------------------------------------
    # Main notification builder (extended)
    # ------------------------------------------------------------------

    def build_run_notification(
        self,
        run: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        audit_top_n: int = _AUDIT_TOP_N_DEFAULT,
    ) -> str:
        """Build the full Markdown notification content for a screening run.

        Top ``audit_top_n`` candidates are rendered as full audit blocks that include
        score breakdown, factor snapshot, AI/news sections, and raw indicator values.
        Remaining candidates are rendered as compact one-line summaries.
        """
        trade_date = run.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
        mode = run.get("mode") or "balanced"
        status = run.get("status") or "completed"
        universe_size = int(run.get("universe_size") or 0)
        candidate_count = int(run.get("candidate_count") or len(candidates))

        # Extract market_regime from candidates (all share the same regime)
        regime = self._extract_regime(candidates)
        regime_label = _REGIME_LABELS.get(regime, "") if regime else ""
        title_suffix = f" | {regime_label}" if regime_label else ""

        lines = [
            f"# 📣 {trade_date} 全市场筛选推荐名单{title_suffix}",
            "",
            (
                f"> run_id: `{run.get('run_id', '-')}` | "
                f"模式: `{mode}` | "
                f"候选数: **{candidate_count}** | "
                f"股票池规模: **{universe_size}**"
            ),
            "",
        ]

        if status == "completed_with_ai_degraded":
            lines.extend(
                [
                    "> ⚠️ AI 二筛已降级，本次结果以规则输出为主，候选中仅保留已成功回链的 AI/新闻增强信息。",
                    "",
                ]
            )

        if regime == "stand_aside":
            lines.extend(
                [
                    "> 当前市场处于观望期，以下为观察列表，不含交易计划。",
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

        for idx, item in enumerate(candidates, 1):
            if idx <= audit_top_n:
                lines.extend(self._format_candidate_audit_block(item))
            else:
                lines.extend(self._format_candidate_summary_block(item))

        lines.extend(
            [
                "---",
                "",
                f"*通知生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_regime(candidates: List[Dict[str, Any]]) -> Optional[str]:
        """Extract market_regime from candidates (all share the same regime)."""
        for c in candidates:
            regime = c.get("market_regime")
            if regime:
                return regime
        return None

    # ------------------------------------------------------------------
    # Legacy entry point (preserved for backward compatibility)
    # ------------------------------------------------------------------

    def send_run_notification(
        self, run_id: str, limit: int = 10, with_ai_only: bool = False
    ) -> Dict[str, Any]:
        run = self.screening_task_service.get_run(run_id)
        if run is None:
            raise ScreeningRunNotFoundError("筛选任务不存在")
        if run.get("status") not in _COMPLETED_STATUSES:
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
