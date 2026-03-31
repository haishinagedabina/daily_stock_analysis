"""Strategy-driven screening engine.

Reads quantitative screening rules from strategy YAML definitions (via Skill
objects) and evaluates factor snapshots. Replaces the hardcoded rule logic
previously in ScreenerService with a configurable, multi-strategy evaluation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

# ── Chinese display mappings for rule hits ──────────────────────────────────

_RULE_HIT_CN_MAP: Dict[str, str] = {
    "is_hot_theme_stock": "属于热点题材",
    "above_ma100": "站上MA100均线",
    "pattern_123_low_trendline": "底部123形态",
    "gap_breakaway": "跳空突破",
    "is_limit_up": "涨停",
    "bottom_divergence_double_breakout": "底背离双突破",
}

_STRATEGY_CN_MAP: Dict[str, str] = {
    "extreme_strength_combo": "极端强势组合策略",
}

_PER_THEME_DEDUP_STRATEGIES = frozenset({"extreme_strength_combo"})


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FilterCondition:
    field: str
    op: str
    value: Any = None
    value_ref: Optional[str] = None


@dataclass(frozen=True)
class FilterGroup:
    mode: str
    conditions: List["FilterNode"] = field(default_factory=list)


FilterNode = Union[FilterCondition, FilterGroup]


@dataclass(frozen=True)
class ScoringWeight:
    field: str
    weight: float
    cap: Optional[float] = None
    bonus_above: Optional[float] = None
    bonus_multiplier: Optional[float] = None
    invert: bool = False


@dataclass
class StrategyScreeningRule:
    strategy_name: str
    display_name: str
    category: str
    filters: List[FilterNode] = field(default_factory=list)
    scoring: List[ScoringWeight] = field(default_factory=list)
    # -- 五层系统 metadata (Phase 1) --
    system_role: Optional[str] = None
    strategy_family: Optional[str] = None
    applicable_market: Optional[List[str]] = None
    applicable_theme: Optional[List[str]] = None
    setup_type: Optional[str] = None


@dataclass(frozen=True)
class CommonFilterConfig:
    exclude_st: bool = True
    min_list_days: int = 120
    min_avg_amount: float = 50_000_000


@dataclass
class CandidateResult:
    code: str
    name: str
    rank: int
    final_score: float
    matched_strategies: List[str]
    strategy_scores: Dict[str, float]
    rule_hits: List[str]
    factor_snapshot: Dict[str, Any]
    # -- 五层系统 metadata (Phase 1) --
    setup_type: Optional[str] = None
    strategy_family: Optional[str] = None


@dataclass
class MultiStrategyEvaluationResult:
    selected: List[CandidateResult]
    rejected: List[Dict[str, Any]]
    strategy_stats: Dict[str, int] = field(default_factory=dict)


# ── Engine ───────────────────────────────────────────────────────────────────

class StrategyScreeningEngine:
    """Generic rule evaluation engine for strategy-driven screening."""

    # ── public static helpers ────────────────────────────────────────────

    @staticmethod
    def evaluate_filter(fc: FilterCondition, row: Dict[str, Any]) -> bool:
        raw = row.get(fc.field)
        if raw is None:
            return False

        if fc.value_ref is not None:
            ref_val = row.get(fc.value_ref)
            if ref_val is None:
                return False
            return _compare(raw, fc.op, ref_val)

        return _compare(raw, fc.op, fc.value)

    @staticmethod
    def evaluate_score_component(sw: ScoringWeight, row: Dict[str, Any]) -> float:
        raw = row.get(sw.field)
        if raw is None:
            return 0.0

        try:
            val = float(raw)
        except (TypeError, ValueError):
            return 0.0

        effective_cap = sw.cap if sw.cap is not None else 100.0
        capped_val = min(val, effective_cap)

        if sw.invert:
            capped_val = max(effective_cap - capped_val, 0.0)

        base_score = sw.weight * (capped_val / effective_cap) if effective_cap > 0 else 0.0

        bonus = 0.0
        if sw.bonus_above is not None and sw.bonus_multiplier is not None:
            excess = max(val - sw.bonus_above, 0.0)
            bonus = excess * sw.bonus_multiplier

        return round(base_score + bonus, 4)

    # ── common filters ───────────────────────────────────────────────────

    def apply_common_filters(
        self, row: Dict[str, Any], config: CommonFilterConfig
    ) -> List[str]:
        reasons: List[str] = []
        if config.exclude_st and bool(row.get("is_st", False)):
            reasons.append("st_filtered")
        if float(row.get("days_since_listed") or 0) < config.min_list_days:
            reasons.append("listed_days_below_threshold")
        if float(row.get("avg_amount") or 0.0) < config.min_avg_amount:
            reasons.append("liquidity_below_threshold")
        return reasons

    # ── main evaluate ────────────────────────────────────────────────────

    def evaluate(
        self,
        snapshot_df: pd.DataFrame,
        rules: List[StrategyScreeningRule],
        common_filters: CommonFilterConfig,
        candidate_limit: Optional[int] = None,
    ) -> MultiStrategyEvaluationResult:
        if snapshot_df is None or snapshot_df.empty:
            return MultiStrategyEvaluationResult(selected=[], rejected=[])

        candidate_map: Dict[str, _CandidateAccumulator] = {}
        rejected: List[Dict[str, Any]] = []
        strategy_stats: Dict[str, int] = {r.strategy_name: 0 for r in rules}

        for row_dict in snapshot_df.to_dict("records"):
            code = str(row_dict.get("code", ""))
            name = str(row_dict.get("name", code))

            common_reasons = self.apply_common_filters(row_dict, common_filters)
            if common_reasons:
                rejected.append({
                    "code": code,
                    "name": name,
                    "rejection_reasons": common_reasons,
                })
                continue

            matched_any = False
            for rule in rules:
                if not self._passes_strategy_filters(rule, row_dict):
                    continue

                matched_any = True
                score = self._compute_strategy_score(rule, row_dict)
                strategy_stats[rule.strategy_name] = strategy_stats.get(rule.strategy_name, 0) + 1

                if code not in candidate_map:
                    candidate_map[code] = _CandidateAccumulator(
                        code=code, name=name, factor_snapshot=dict(row_dict),
                    )
                acc = candidate_map[code]
                acc.strategy_scores[rule.strategy_name] = score
                acc.matched_strategies.append(rule.strategy_name)
                acc.rule_hits.extend(self._build_rule_hits(rule, row_dict))
                # Track best entry_core setup metadata
                if rule.system_role == "entry_core" and score > acc._best_entry_core_score:
                    acc._best_entry_core_score = score
                    acc.best_setup_type = rule.setup_type
                    acc.best_strategy_family = rule.strategy_family

            if not matched_any:
                rejected.append({
                    "code": code,
                    "name": name,
                    "rejection_reasons": ["no_strategy_matched"],
                })

        selected = self._build_sorted_candidates(candidate_map, candidate_limit)
        return MultiStrategyEvaluationResult(
            selected=selected,
            rejected=rejected,
            strategy_stats=strategy_stats,
        )

    # ── private helpers ──────────────────────────────────────────────────

    def _passes_strategy_filters(
        self, rule: StrategyScreeningRule, row: Dict[str, Any]
    ) -> bool:
        return all(self._evaluate_filter_node(node, row) for node in rule.filters)

    def _compute_strategy_score(
        self, rule: StrategyScreeningRule, row: Dict[str, Any]
    ) -> float:
        total = sum(self.evaluate_score_component(sw, row) for sw in rule.scoring)
        return round(total, 2)

    @staticmethod
    def _build_rule_hits(
        rule: StrategyScreeningRule, row: Dict[str, Any]
    ) -> List[str]:
        hits = [f"strategy:{rule.strategy_name}"]
        for fc in _iter_filter_conditions(rule.filters):
            field_val = row.get(fc.field)
            if field_val is not None:
                hits.append(f"{fc.field}:{fc.op}:{fc.value or fc.value_ref}")
        # 只合并与当前策略相关的 hit_reasons（前缀匹配）
        for key, val in row.items():
            if key.endswith("_hit_reasons") and isinstance(val, list):
                prefix = key[: -len("_hit_reasons")]
                if rule.strategy_name.startswith(prefix):
                    hits.extend(val)
        return hits

    @staticmethod
    def _build_rule_hits_display(
        rule_hits: List[str], factor_snapshot: Dict[str, Any]
    ) -> List[str]:
        """Build human-readable Chinese labels for all hit rules."""
        display: List[str] = []
        # 1. Map filter field names from rule_hits to Chinese
        for hit in rule_hits:
            parts = hit.split(":")
            if len(parts) >= 3:
                field_name = parts[0]
                cn = _RULE_HIT_CN_MAP.get(field_name)
                if cn:
                    display.append(cn)
            elif hit.startswith("strategy:"):
                strategy = hit.split(":", 1)[1]
                cn = _STRATEGY_CN_MAP.get(strategy)
                if cn:
                    display.append(cn)
        # 2. Merge extreme_strength_reasons (already Chinese)
        reasons = factor_snapshot.get("extreme_strength_reasons")
        if isinstance(reasons, list):
            display.extend(reasons)
        return list(dict.fromkeys(display))

    def _evaluate_filter_node(self, node: FilterNode, row: Dict[str, Any]) -> bool:
        if isinstance(node, FilterCondition):
            return self.evaluate_filter(node, row)
        if isinstance(node, FilterGroup):
            if not node.conditions:
                return True
            if node.mode == "any":
                return any(self._evaluate_filter_node(child, row) for child in node.conditions)
            return all(self._evaluate_filter_node(child, row) for child in node.conditions)
        return False

    @staticmethod
    def _build_sorted_candidates(
        candidate_map: Dict[str, "_CandidateAccumulator"],
        candidate_limit: Optional[int],
    ) -> List[CandidateResult]:
        candidates: List[CandidateResult] = []
        for acc in candidate_map.values():
            final_score = sum(acc.strategy_scores.values()) if acc.strategy_scores else 0.0
            unique_hits = list(dict.fromkeys(acc.rule_hits))
            rule_hits_display = StrategyScreeningEngine._build_rule_hits_display(
                unique_hits, acc.factor_snapshot,
            )
            snapshot = dict(acc.factor_snapshot)
            snapshot["rule_hits_display"] = rule_hits_display
            candidates.append(CandidateResult(
                code=acc.code,
                name=acc.name,
                rank=0,
                final_score=round(final_score, 2),
                matched_strategies=list(dict.fromkeys(acc.matched_strategies)),
                strategy_scores=dict(acc.strategy_scores),
                rule_hits=unique_hits,
                factor_snapshot=snapshot,
                setup_type=acc.best_setup_type,
                strategy_family=acc.best_strategy_family,
            ))

        candidates.sort(key=lambda c: c.final_score, reverse=True)

        # Per-theme dedup: keep only the highest-scoring stock per primary_theme
        # for strategies that require 1 leader per theme.
        needs_dedup = any(
            s in _PER_THEME_DEDUP_STRATEGIES
            for c in candidates
            for s in c.matched_strategies
        )
        if needs_dedup:
            seen_themes: set = set()
            deduped: List[CandidateResult] = []
            for c in candidates:
                theme = c.factor_snapshot.get("primary_theme")
                is_dedup_strategy = any(s in _PER_THEME_DEDUP_STRATEGIES for s in c.matched_strategies)
                if is_dedup_strategy and theme:
                    if theme in seen_themes:
                        continue
                    seen_themes.add(theme)
                deduped.append(c)
            candidates = deduped

        if candidate_limit is not None:
            candidates = candidates[:candidate_limit]
        for idx, c in enumerate(candidates, start=1):
            c.rank = idx

        return candidates


# ── Rule builder from Skill ─────────────────────────────────────────────────

def build_rules_from_skills(
    skills: list,
) -> List[StrategyScreeningRule]:
    """Convert Skill objects (with ``screening`` dict) into typed rules."""
    rules: List[StrategyScreeningRule] = []
    for skill in skills:
        screening = getattr(skill, "screening", None)
        if not screening or not isinstance(screening, dict):
            continue

        filters = []
        for filter_item in screening.get("filters", []):
            parsed = _parse_filter_node(filter_item)
            if parsed is not None:
                filters.append(parsed)

        scoring = [
            ScoringWeight(
                field=s["field"],
                weight=float(s["weight"]),
                cap=s.get("cap"),
                bonus_above=s.get("bonus_above"),
                bonus_multiplier=s.get("bonus_multiplier"),
                invert=bool(s.get("invert", False)),
            )
            for s in screening.get("scoring", [])
            if isinstance(s, dict) and "field" in s and "weight" in s
        ]

        rules.append(StrategyScreeningRule(
            strategy_name=skill.name,
            display_name=getattr(skill, "display_name", skill.name),
            category=getattr(skill, "category", "trend"),
            filters=filters,
            scoring=scoring,
            system_role=getattr(skill, "system_role", None),
            strategy_family=getattr(skill, "strategy_family", None),
            applicable_market=getattr(skill, "applicable_market", None),
            applicable_theme=getattr(skill, "applicable_theme", None),
            setup_type=getattr(skill, "setup_type", None),
        ))

    return rules


def _parse_filter_node(raw: Any) -> Optional[FilterNode]:
    if not isinstance(raw, dict):
        return None
    if "field" in raw and "op" in raw:
        return FilterCondition(
            field=raw["field"],
            op=raw["op"],
            value=raw.get("value"),
            value_ref=raw.get("value_ref"),
        )
    for mode in ("all", "any"):
        items = raw.get(mode)
        if isinstance(items, list):
            children = [
                parsed
                for item in items
                for parsed in [_parse_filter_node(item)]
                if parsed is not None
            ]
            return FilterGroup(mode=mode, conditions=children)
    return None


def _iter_filter_conditions(nodes: List[FilterNode]) -> List[FilterCondition]:
    flattened: List[FilterCondition] = []
    for node in nodes:
        if isinstance(node, FilterCondition):
            flattened.append(node)
            continue
        if isinstance(node, FilterGroup):
            flattened.extend(_iter_filter_conditions(node.conditions))
    return flattened


# ── Internal accumulator ─────────────────────────────────────────────────────

@dataclass
class _CandidateAccumulator:
    code: str
    name: str
    factor_snapshot: Dict[str, Any]
    strategy_scores: Dict[str, float] = field(default_factory=dict)
    matched_strategies: List[str] = field(default_factory=list)
    rule_hits: List[str] = field(default_factory=list)
    # Track best entry_core setup metadata (highest-scoring entry_core rule wins)
    best_setup_type: Optional[str] = None
    best_strategy_family: Optional[str] = None
    _best_entry_core_score: float = 0.0


# ── Comparison helper ────────────────────────────────────────────────────────

def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "==" and isinstance(right, (str, bool)):
            return left == right
        if op == "!=" and isinstance(right, (str, bool)):
            return left != right

        lf, rf = float(left), float(right)
        if op == ">=":
            return lf >= rf
        if op == "<=":
            return lf <= rf
        if op == ">":
            return lf > rf
        if op == "<":
            return lf < rf
        if op == "==":
            return lf == rf
        if op == "!=":
            return lf != rf
    except (TypeError, ValueError):
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
    return False
