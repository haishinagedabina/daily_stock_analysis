"""TDD tests for Skill / SkillManager screening extension.

Tests that YAML strategies with a ``screening`` section are parsed correctly,
and SkillManager exposes screening rules.
"""
from pathlib import Path

import pytest

from src.agent.skills.base import Skill, SkillManager, load_skill_from_yaml


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "strategies"


# ── Fixture helpers ──────────────────────────────────────────────────────────

@pytest.fixture()
def sample_strategy_yaml(tmp_path: Path) -> Path:
    """Create a minimal YAML strategy with screening rules."""
    content = """\
name: test_breakout
display_name: 测试突破
description: 测试用策略
category: trend
core_rules: [1, 2]
required_tools:
  - get_daily_history

screening:
  filters:
    - field: breakout_ratio
      op: ">="
      value: 0.995
    - field: volume_ratio
      op: ">="
      value: 2.0
  scoring:
    - field: breakout_ratio
      weight: 40
      bonus_above: 1.0
      bonus_multiplier: 1000
    - field: volume_ratio
      weight: 30
      cap: 5.0
    - field: trend_score
      weight: 20
    - field: liquidity_score
      weight: 10

instructions: |
  测试策略说明。
"""
    filepath = tmp_path / "test_breakout.yaml"
    filepath.write_text(content, encoding="utf-8")
    return filepath


@pytest.fixture()
def sample_strategy_no_screening(tmp_path: Path) -> Path:
    """YAML strategy without screening section (backward compatible)."""
    content = """\
name: legacy_strategy
display_name: 遗留策略
description: 没有 screening 段的策略
instructions: |
  旧版策略说明。
"""
    filepath = tmp_path / "legacy_strategy.yaml"
    filepath.write_text(content, encoding="utf-8")
    return filepath


@pytest.fixture()
def value_ref_strategy_yaml(tmp_path: Path) -> Path:
    """YAML with value_ref (cross-field comparison)."""
    content = """\
name: test_cross_field
display_name: 跨字段比较
description: 测试 value_ref
category: trend

screening:
  filters:
    - field: ma5
      op: ">="
      value_ref: ma10
    - field: close
      op: ">="
      value_ref: ma20

instructions: |
  测试说明。
"""
    filepath = tmp_path / "test_cross_field.yaml"
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ── Skill parsing tests ──────────────────────────────────────────────────────

class TestSkillScreeningParsing:
    def test_load_skill_with_screening_section(self, sample_strategy_yaml):
        skill = load_skill_from_yaml(sample_strategy_yaml)

        assert skill.name == "test_breakout"
        assert skill.screening is not None
        assert "filters" in skill.screening
        assert "scoring" in skill.screening

    def test_screening_filters_parsed(self, sample_strategy_yaml):
        skill = load_skill_from_yaml(sample_strategy_yaml)

        filters = skill.screening["filters"]
        assert len(filters) == 2
        assert filters[0]["field"] == "breakout_ratio"
        assert filters[0]["op"] == ">="
        assert filters[0]["value"] == 0.995

    def test_screening_scoring_parsed(self, sample_strategy_yaml):
        skill = load_skill_from_yaml(sample_strategy_yaml)

        scoring = skill.screening["scoring"]
        assert len(scoring) == 4
        assert scoring[0]["field"] == "breakout_ratio"
        assert scoring[0]["weight"] == 40
        assert scoring[0]["bonus_above"] == 1.0
        assert scoring[0]["bonus_multiplier"] == 1000

    def test_load_skill_without_screening_section(self, sample_strategy_no_screening):
        skill = load_skill_from_yaml(sample_strategy_no_screening)

        assert skill.name == "legacy_strategy"
        assert skill.screening is None

    def test_value_ref_filter_parsed(self, value_ref_strategy_yaml):
        skill = load_skill_from_yaml(value_ref_strategy_yaml)

        filters = skill.screening["filters"]
        assert filters[0]["field"] == "ma5"
        assert filters[0].get("value_ref") == "ma10"
        assert "value" not in filters[0]

    def test_screening_field_on_skill_dataclass(self):
        skill = Skill(
            name="test",
            display_name="测试",
            description="desc",
            instructions="inst",
            screening={"filters": [], "scoring": []},
        )
        assert skill.screening == {"filters": [], "scoring": []}

    def test_screening_default_none(self):
        skill = Skill(
            name="test",
            display_name="测试",
            description="desc",
            instructions="inst",
        )
        assert skill.screening is None


# ── SkillManager screening rule extraction tests ─────────────────────────────

class TestSkillManagerScreeningRules:
    def test_get_screening_rules_returns_only_skills_with_screening(
        self, sample_strategy_yaml, sample_strategy_no_screening
    ):
        manager = SkillManager()
        skill_with = load_skill_from_yaml(sample_strategy_yaml)
        skill_without = load_skill_from_yaml(sample_strategy_no_screening)
        manager.register(skill_with)
        manager.register(skill_without)

        rules = manager.get_screening_rules()
        assert len(rules) == 1
        assert rules[0].name == "test_breakout"

    def test_get_screening_rules_filters_by_names(self, tmp_path):
        manager = SkillManager()
        for name in ["alpha", "beta", "gamma"]:
            content = f"""\
name: {name}
display_name: {name}
description: desc
screening:
  filters: []
  scoring: []
instructions: |
  inst
"""
            fp = tmp_path / f"{name}.yaml"
            fp.write_text(content, encoding="utf-8")
            manager.register(load_skill_from_yaml(fp))

        rules = manager.get_screening_rules(strategy_names=["alpha", "gamma"])
        names = [r.name for r in rules]
        assert "alpha" in names
        assert "gamma" in names
        assert "beta" not in names

    def test_get_screening_rules_empty_when_no_screening_strategies(self):
        manager = SkillManager()
        skill = Skill(name="plain", display_name="p", description="d", instructions="i")
        manager.register(skill)

        assert manager.get_screening_rules() == []

    def test_load_builtin_strategies_includes_screening(self):
        manager = SkillManager()
        count = manager.load_builtin_strategies()

        assert count >= 5
        rules = manager.get_screening_rules()
        strategy_names = {r.name for r in rules}
        assert "volume_breakout" in strategy_names
        assert "bottom_volume" in strategy_names
        assert "ma_golden_cross" in strategy_names
        assert "shrink_pullback" in strategy_names
        assert "one_yang_three_yin" in strategy_names
