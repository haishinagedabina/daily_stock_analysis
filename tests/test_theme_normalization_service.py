# -*- coding: utf-8 -*-
"""Unit tests for ThemeNormalizationService."""

import unittest
from src.services.theme_normalization_service import ThemeNormalizationService


class ThemeSplittingTestCase(unittest.TestCase):
    """Test compound theme splitting."""

    def setUp(self) -> None:
        self.service = ThemeNormalizationService()

    def test_split_slash_separated_theme(self) -> None:
        parts = self.service.split_theme("锂电池/锂矿")
        self.assertEqual(parts, ["锂电池", "锂矿"])

    def test_split_chinese_punctuation_separator(self) -> None:
        parts = self.service.split_theme("锂电池／锂矿")
        self.assertEqual(parts, ["锂电池", "锂矿"])

    def test_split_multiple_parts(self) -> None:
        parts = self.service.split_theme("AI Agent/大模型/算力")
        self.assertEqual(parts, ["AI Agent", "大模型", "算力"])

    def test_split_single_theme_no_separator(self) -> None:
        parts = self.service.split_theme("创新药")
        self.assertEqual(parts, ["创新药"])

    def test_split_trims_whitespace(self) -> None:
        parts = self.service.split_theme(" 锂电池 / 锂矿 ")
        self.assertEqual(parts, ["锂电池", "锂矿"])

    def test_split_deduplicates(self) -> None:
        parts = self.service.split_theme("锂电池/锂电池")
        self.assertEqual(parts, ["锂电池"])


class AliasResolutionTestCase(unittest.TestCase):
    """Test alias-based theme normalization."""

    def setUp(self) -> None:
        self.service = ThemeNormalizationService()

    def test_exact_alias_hit(self) -> None:
        result = self.service.resolve_alias("AI Agent")
        self.assertIsNotNone(result)
        self.assertIn("AI智能体", result["matched_boards"])
        self.assertIn("alias_hit", result["match_reasons"])

    def test_alias_returns_multiple_boards(self) -> None:
        result = self.service.resolve_alias("锂价反弹")
        self.assertIsNotNone(result)
        self.assertTrue(len(result["matched_boards"]) >= 2)

    def test_unresolved_theme_returns_none(self) -> None:
        result = self.service.resolve_alias("完全不存在的主题XYZ")
        self.assertIsNone(result)

    def test_alias_case_insensitive(self) -> None:
        result = self.service.resolve_alias("ai agent")
        self.assertIsNotNone(result)
        self.assertIn("AI智能体", result["matched_boards"])


class NormalizeThemeTestCase(unittest.TestCase):
    """Test the full single-theme normalization (split + alias)."""

    def setUp(self) -> None:
        self.service = ThemeNormalizationService()

    def test_normalize_theme_uses_alias_map(self) -> None:
        result = self.service.normalize_theme(
            raw_theme="AI Agent", keywords=["Agent"],
        )
        self.assertEqual(result["raw_theme"], "AI Agent")
        self.assertIn("AI智能体", result["matched_boards"])
        self.assertIn("alias_hit", result["match_reasons"])
        self.assertEqual(result["status"], "high_confidence")

    def test_normalize_compound_theme_resolves_both_parts(self) -> None:
        result = self.service.normalize_theme(
            raw_theme="AI Agent/大模型", keywords=["AI"],
        )
        self.assertIn("AI智能体", result["matched_boards"])
        # 大模型 should also resolve via alias
        boards = result["matched_boards"]
        self.assertTrue(
            any("AIGC" in b or "AI" in b or "大模型" in b for b in boards),
            f"Expected a board related to 大模型 in {boards}",
        )

    def test_normalize_unresolved_theme_stays_unresolved(self) -> None:
        result = self.service.normalize_theme(
            raw_theme="完全未知主题XYZ", keywords=[],
        )
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["matched_boards"], [])


class PipelineIntegrationTestCase(unittest.TestCase):
    """Test the full normalization pipeline: alias-first, recall fallback, status."""

    def setUp(self) -> None:
        # Provide board vocabulary for recall fallback
        self.board_names = [
            "锂电池", "锂电池概念", "锂矿概念",
            "创新药", "创新药概念",
            "AI智能体", "AIGC概念", "多模态AI",
            "机器人概念", "半导体概念", "芯片概念",
            "海南自贸港", "免税概念", "人工智能",
            "光伏概念", "储能概念",
        ]
        self.service = ThemeNormalizationService()
        self.service.set_board_vocabulary(self.board_names)

    def test_alias_first_behavior(self) -> None:
        """When alias matches, recall should not override."""
        result = self.service.normalize_theme(
            raw_theme="AI Agent", keywords=["Agent"],
        )
        self.assertEqual(result["status"], "high_confidence")
        self.assertIn("AI智能体", result["matched_boards"])
        self.assertIn("alias_hit", result["match_reasons"])

    def test_recall_fallback_when_alias_misses(self) -> None:
        """When alias has no match, recall from board vocabulary kicks in."""
        result = self.service.normalize_theme(
            raw_theme="光伏", keywords=["光伏"],
        )
        # "光伏" is not in aliases but "光伏概念" is in board_names
        self.assertTrue(len(result["matched_boards"]) > 0)
        self.assertIn("光伏概念", result["matched_boards"])
        self.assertIn("recall", result["match_reasons"][0])  # recall-related reason
        self.assertIn(result["status"], {"high_confidence", "weak_match"})

    def test_unresolved_when_nothing_matches(self) -> None:
        result = self.service.normalize_theme(
            raw_theme="完全未知概念XYZ", keywords=[],
        )
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["matched_boards"], [])

    def test_compound_theme_alias_plus_recall(self) -> None:
        """Compound theme where one part hits alias, another falls to recall."""
        result = self.service.normalize_theme(
            raw_theme="AI Agent/光伏", keywords=["AI", "光伏"],
        )
        boards = result["matched_boards"]
        self.assertIn("AI智能体", boards)
        self.assertIn("光伏概念", boards)

    def test_confidence_and_reasons_consistent(self) -> None:
        result = self.service.normalize_theme(
            raw_theme="锂价反弹", keywords=["锂"],
        )
        self.assertGreater(result["match_confidence"], 0)
        self.assertTrue(len(result["match_reasons"]) > 0)
        self.assertIn(result["status"], {"high_confidence", "weak_match", "unresolved"})


class RealWorldRegressionTestCase(unittest.TestCase):
    """Regression tests from real-world themes that previously produced zero matches."""

    def setUp(self) -> None:
        self.board_names = [
            "锂电池", "锂电池概念", "锂矿概念",
            "创新药", "创新药概念", "医药生物",
            "AI智能体", "AIGC概念", "多模态AI",
            "机器人概念", "半导体概念", "芯片概念",
            "海南自贸港", "免税概念", "人工智能",
            "光伏概念", "储能概念", "新能源",
        ]
        self.service = ThemeNormalizationService()
        self.service.set_board_vocabulary(self.board_names)

    def test_lithium_battery_slash_lithium_mine(self) -> None:
        """锂电池/锂矿 should resolve to both lithium boards."""
        result = self.service.normalize_theme(
            raw_theme="锂电池/锂矿", keywords=["锂"],
        )
        boards = result["matched_boards"]
        self.assertIn("锂电池", boards)
        self.assertIn("锂电池概念", boards)
        self.assertIn("锂矿概念", boards)
        self.assertNotEqual(result["status"], "unresolved")

    def test_ai_agent_slash_large_model(self) -> None:
        """AI Agent/大模型 should resolve to AI-related boards."""
        result = self.service.normalize_theme(
            raw_theme="AI Agent/大模型", keywords=["AI", "Agent", "大模型"],
        )
        boards = result["matched_boards"]
        self.assertIn("AI智能体", boards)
        self.assertTrue(
            any("AIGC" in b or "多模态" in b for b in boards),
            f"Expected AIGC or 多模态 board in {boards}",
        )
        self.assertNotEqual(result["status"], "unresolved")

    def test_innovative_drug_slash_pharma(self) -> None:
        """创新药/医药生物 should resolve to pharma boards."""
        result = self.service.normalize_theme(
            raw_theme="创新药/医药生物", keywords=["创新药", "医药"],
        )
        boards = result["matched_boards"]
        self.assertIn("创新药", boards)
        self.assertNotEqual(result["status"], "unresolved")

    def test_hainan_ftp_slash_duty_free(self) -> None:
        """海南自贸港/免税 should resolve to both boards."""
        result = self.service.normalize_theme(
            raw_theme="海南自贸港/免税", keywords=["海南", "免税"],
        )
        boards = result["matched_boards"]
        self.assertIn("海南自贸港", boards)
        self.assertIn("免税概念", boards)
        self.assertNotEqual(result["status"], "unresolved")

    def test_lithium_price_rebound(self) -> None:
        """锂价反弹 should resolve via alias to lithium boards."""
        result = self.service.normalize_theme(
            raw_theme="锂价反弹", keywords=["锂"],
        )
        boards = result["matched_boards"]
        self.assertIn("锂矿概念", boards)
        self.assertIn("锂电池概念", boards)
        self.assertEqual(result["status"], "high_confidence")

    def test_innovative_drug_overseas(self) -> None:
        """创新药出海 should resolve via alias."""
        result = self.service.normalize_theme(
            raw_theme="创新药出海", keywords=["创新药"],
        )
        boards = result["matched_boards"]
        self.assertIn("创新药", boards)
        self.assertEqual(result["status"], "high_confidence")

    def test_no_silent_unresolved_when_alias_exists(self) -> None:
        """Themes with known aliases must never silently become unresolved."""
        alias_themes = ["AI Agent", "大模型", "锂价反弹", "海南自贸港", "免税", "创新药"]
        for theme in alias_themes:
            result = self.service.normalize_theme(raw_theme=theme, keywords=[])
            self.assertNotEqual(
                result["status"], "unresolved",
                f"Theme '{theme}' should not be unresolved (has alias)",
            )
            self.assertTrue(
                len(result["matched_boards"]) > 0,
                f"Theme '{theme}' should have matched boards",
            )


if __name__ == "__main__":
    unittest.main()
