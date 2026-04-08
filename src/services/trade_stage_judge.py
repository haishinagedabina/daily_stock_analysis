# -*- coding: utf-8 -*-
"""
L5 交易阶段裁决 — 综合环境/题材/候选池/买点裁决 trade_stage。

硬规则（前序层否决后序层，不可推翻）:
  stand_aside  → 最高 WATCH
  defensive    → 禁止 ADD_ON_STRENGTH
  fading_theme → 最高 WATCH（有例外）
  non_theme    → 禁止 ADD_ON_STRENGTH
  no setup     → 最高 WATCH
  maturity=LOW → 最高 FOCUS
  无止损锚点   → 最高 FOCUS
"""

from __future__ import annotations

from src.schemas.trading_types import (
    CandidatePoolLevel,
    EntryMaturity,
    MarketEnvironment,
    MarketRegime,
    SetupType,
    ThemePosition,
    TradeStage,
)


class TradeStageJudge:

    def judge(
        self,
        env: MarketEnvironment,
        setup_type: SetupType,
        entry_maturity: EntryMaturity,
        pool_level: CandidatePoolLevel,
        theme_position: ThemePosition,
        has_stop_loss: bool,
    ) -> TradeStage:
        # ── 1. 环境硬门控 ───────────────────────────────────────────────────
        if env.regime == MarketRegime.STAND_ASIDE:
            return TradeStage.WATCH

        # ── 2. 显式拒绝：弱题材 + 无买点 + 低成熟度 ────────────────────────
        if (theme_position in (ThemePosition.FADING_THEME, ThemePosition.NON_THEME)
                and setup_type == SetupType.NONE
                and entry_maturity == EntryMaturity.LOW):
            return TradeStage.REJECT

        # ── 3. 无买点 → WATCH ────────────────────────────────────────────────
        if setup_type == SetupType.NONE:
            return TradeStage.WATCH

        # ── 4. 题材约束 ─────────────────────────────────────────────────────
        if theme_position == ThemePosition.FADING_THEME:
            return TradeStage.WATCH

        # ── 5. 成熟度约束 ───────────────────────────────────────────────────
        if entry_maturity == EntryMaturity.LOW:
            return TradeStage.FOCUS

        # ── 6. 止损锚点检查 ─────────────────────────────────────────────────
        if not has_stop_loss:
            return TradeStage.FOCUS

        # ── 7. 正向裁决 ─────────────────────────────────────────────────────
        ceiling = self._ceiling(env.regime, theme_position)

        if (entry_maturity == EntryMaturity.HIGH
                and pool_level == CandidatePoolLevel.LEADER_POOL):
            return self._cap(TradeStage.ADD_ON_STRENGTH, ceiling)

        if entry_maturity in (EntryMaturity.MEDIUM, EntryMaturity.HIGH):
            return self._cap(TradeStage.PROBE_ENTRY, ceiling)

        return TradeStage.FOCUS

    def _ceiling(self, regime: MarketRegime, theme: ThemePosition) -> TradeStage:
        """根据环境和题材确定阶段上限。"""
        # defensive → 禁止 add_on
        if regime == MarketRegime.DEFENSIVE:
            return TradeStage.PROBE_ENTRY

        # non_theme / follower_theme → 禁止 add_on
        if theme in (ThemePosition.NON_THEME, ThemePosition.FOLLOWER_THEME):
            return TradeStage.PROBE_ENTRY

        return TradeStage.ADD_ON_STRENGTH

    def _cap(self, stage: TradeStage, ceiling: TradeStage) -> TradeStage:
        """将 stage 限制在 ceiling 以下。"""
        order = [
            TradeStage.STAND_ASIDE,
            TradeStage.WATCH,
            TradeStage.FOCUS,
            TradeStage.PROBE_ENTRY,
            TradeStage.ADD_ON_STRENGTH,
        ]
        stage_idx = order.index(stage) if stage in order else 0
        ceiling_idx = order.index(ceiling) if ceiling in order else 0
        return order[min(stage_idx, ceiling_idx)]
