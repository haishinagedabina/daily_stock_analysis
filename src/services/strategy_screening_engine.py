"""Strategy-driven screening engine.

Reads quantitative screening rules from strategy YAML definitions (via Skill
objects) and evaluates factor snapshots. Replaces the hardcoded rule logic
previously in ScreenerService with a configurable, multi-strategy evaluation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FilterCondition:
    field: str
    op: str
    value: Any = None
    value_ref: Optional[str] = None


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
    filters: List[FilterCondition] = field(default_factory=list)
    scoring: List[ScoringWeight] = field(default_factory=list)


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
        return all(self.evaluate_filter(fc, row) for fc in rule.filters)

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
        for fc in rule.filters:
            field_val = row.get(fc.field)
            if field_val is not None:
                hits.append(f"{fc.field}:{fc.op}:{fc.value or fc.value_ref}")
        return hits

    @staticmethod
    def _build_sorted_candidates(
        candidate_map: Dict[str, "_CandidateAccumulator"],
        candidate_limit: Optional[int],
    ) -> List[CandidateResult]:
        candidates: List[CandidateResult] = []
        for acc in candidate_map.values():
            final_score = max(acc.strategy_scores.values()) if acc.strategy_scores else 0.0
            unique_hits = list(dict.fromkeys(acc.rule_hits))
            candidates.append(CandidateResult(
                code=acc.code,
                name=acc.name,
                rank=0,
                final_score=round(final_score, 2),
                matched_strategies=list(dict.fromkeys(acc.matched_strategies)),
                strategy_scores=dict(acc.strategy_scores),
                rule_hits=unique_hits,
                factor_snapshot=acc.factor_snapshot,
            ))

        candidates.sort(key=lambda c: c.final_score, reverse=True)
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

        filters = [
            FilterCondition(
                field=f["field"],
                op=f["op"],
                value=f.get("value"),
                value_ref=f.get("value_ref"),
            )
            for f in screening.get("filters", [])
            if isinstance(f, dict) and "field" in f and "op" in f
        ]

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
        ))

    return rules


# ── Internal accumulator ─────────────────────────────────────────────────────

@dataclass
class _CandidateAccumulator:
    code: str
    name: str
    factor_snapshot: Dict[str, Any]
    strategy_scores: Dict[str, float] = field(default_factory=dict)
    matched_strategies: List[str] = field(default_factory=list)
    rule_hits: List[str] = field(default_factory=list)


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
