"""Strategy dispatcher — filters matched strategies by market regime.

Phase 2B module. Uses strategy YAML metadata (``applicable_market`` and
``system_role``) to determine which strategies are allowed under the
current market regime.  Runs *after* the screening engine has evaluated
all strategies, filtering the ``matched_strategies`` list per-candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.schemas.trading_types import MarketRegime

logger = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _StrategyMeta:
    """Cached metadata extracted from a StrategyScreeningRule."""
    name: str
    system_role: str            # entry_core, stock_pool, observation, ...
    strategy_family: str        # reversal, trend, momentum, auxiliary
    applicable_market: List[str]  # ["balanced", "aggressive", ...]


@dataclass
class DispatchResult:
    """Result of filtering a candidate's matched strategies."""
    allowed_strategies: List[str]
    blocked_strategies: List[str]
    reason: str


# ── Dispatcher ──────────────────────────────────────────────────────────────

class StrategyDispatcher:
    """Filters strategies based on market regime constraints.

    Dispatch rules:
    - ``stand_aside`` → only observation-role strategies
    - ``defensive`` → 保留 defensive 标记策略，同时放行非动量类 entry_core，
      通过后续池分级 / trade_stage 继续降级
    - ``balanced/aggressive`` → strategies whose ``applicable_market``
      includes the regime value
    """

    def __init__(self, strategy_rules: List[Any]) -> None:
        """Build internal metadata cache from StrategyScreeningRule objects.

        Parameters
        ----------
        strategy_rules:
            List of ``StrategyScreeningRule`` instances (from
            ``build_rules_from_skills``).
        """
        self._meta: Dict[str, _StrategyMeta] = {}
        for rule in strategy_rules:
            self._meta[rule.strategy_name] = _StrategyMeta(
                name=rule.strategy_name,
                system_role=rule.system_role or "",
                strategy_family=rule.strategy_family or "",
                applicable_market=list(rule.applicable_market or []),
            )

    def filter_strategies(
        self,
        matched_strategies: List[str],
        market_regime: MarketRegime,
    ) -> DispatchResult:
        """Filter a candidate's matched strategies by market regime.

        Parameters
        ----------
        matched_strategies:
            Strategy names the candidate was matched by (from screening).
        market_regime:
            Current market regime from L1.

        Returns
        -------
        DispatchResult with allowed / blocked lists and reason string.
        """
        if not matched_strategies:
            return DispatchResult(
                allowed_strategies=[],
                blocked_strategies=[],
                reason="no_strategies_to_filter",
            )

        allowed: List[str] = []
        blocked: List[str] = []

        for name in matched_strategies:
            meta = self._meta.get(name)
            if meta is None:
                # Unknown strategy — conservative: allow it
                allowed.append(name)
                continue

            if self._is_allowed(meta, market_regime):
                allowed.append(name)
            else:
                blocked.append(name)

        reason = self._build_reason(market_regime, allowed, blocked)
        return DispatchResult(
            allowed_strategies=allowed,
            blocked_strategies=blocked,
            reason=reason,
        )

    def get_allowed_rules(
        self,
        all_rules: List[Any],
        market_regime: MarketRegime,
    ) -> List[Any]:
        """事前过滤：返回当前环境允许的策略规则列表 (D5 修复)。

        在选股 *之前* 调用，确保只有环境允许的策略参与选股，
        而非事后清空候选已匹配的策略。

        Parameters
        ----------
        all_rules:
            全部 StrategyScreeningRule 列表（来自 build_rules_from_skills）。
        market_regime:
            当前 L1 市场环境。

        Returns
        -------
        当前环境允许的 StrategyScreeningRule 子列表。
        """
        allowed: List[Any] = []
        for rule in all_rules:
            meta = _StrategyMeta(
                name=rule.strategy_name,
                system_role=rule.system_role or "",
                strategy_family=rule.strategy_family or "",
                applicable_market=list(rule.applicable_market or []),
            )
            if self._is_allowed(meta, market_regime):
                allowed.append(rule)
        logger.info(
            "dispatcher pre-filter: regime=%s total=%d allowed=%d",
            market_regime.value, len(all_rules), len(allowed),
        )
        return allowed

    # ── private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _is_allowed(meta: _StrategyMeta, regime: MarketRegime) -> bool:
        """Check whether a strategy is allowed under the given regime."""
        # Hard rule: stand_aside allows ONLY observation strategies
        if regime == MarketRegime.STAND_ASIDE:
            return meta.system_role == "observation"

        # defensive 不是停手环境，应保留 reversal / trend 的核心买点，
        # 再交给后续 L3/L4/L5 做更严格的降级与封顶。
        if regime == MarketRegime.DEFENSIVE:
            if regime.value in meta.applicable_market:
                return True
            return (
                meta.system_role == "entry_core"
                and meta.strategy_family in {"reversal", "trend"}
            )

        # For other regimes, use the YAML applicable_market list
        return regime.value in meta.applicable_market

    @staticmethod
    def _build_reason(
        regime: MarketRegime,
        allowed: List[str],
        blocked: List[str],
    ) -> str:
        parts = [f"regime={regime.value}"]
        if blocked:
            parts.append(f"blocked=[{','.join(blocked)}]")
        if allowed:
            parts.append(f"allowed=[{','.join(allowed)}]")
        return "; ".join(parts)
