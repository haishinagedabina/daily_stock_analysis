# -*- coding: utf-8 -*-
"""Unit tests for ThemeMatchingService."""

import unittest
from src.services.theme_matching_service import ThemeMatchingService


class ThemeMatchingServiceTestCase(unittest.TestCase):
    """Test ThemeMatchingService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = ThemeMatchingService()

    def test_fuzzy_match_exact(self) -> None:
        """Test fuzzy match with exact match."""
        score = self.service.fuzzy_match("机器人", "机器人")
        self.assertEqual(score, 1.0)

    def test_fuzzy_match_partial(self) -> None:
        """Test fuzzy match with partial match."""
        score = self.service.fuzzy_match("人形机器人", "机器人")
        self.assertGreater(score, 0.7)
        self.assertLess(score, 1.0)

    def test_fuzzy_match_no_match(self) -> None:
        """Test fuzzy match with no match."""
        score = self.service.fuzzy_match("芯片", "机器人")
        self.assertLess(score, 0.3)

    def test_fuzzy_match_case_insensitive(self) -> None:
        """Test fuzzy match is case insensitive."""
        score1 = self.service.fuzzy_match("Robot", "robot")
        self.assertEqual(score1, 1.0)

    def test_keyword_match_single_keyword(self) -> None:
        """Test keyword match with single keyword."""
        keywords = ["人形机器人"]
        score = self.service.keyword_match("人形机器人概念股", keywords)
        self.assertGreater(score, 0.7)

    def test_keyword_match_multiple_keywords(self) -> None:
        """Test keyword match with multiple keywords."""
        keywords = ["人形机器人", "丝杠", "减速器"]
        score = self.service.keyword_match("人形机器人丝杠减速器", keywords)
        self.assertEqual(score, 1.0)

    def test_keyword_match_partial_keywords(self) -> None:
        """Test keyword match with partial keywords."""
        keywords = ["人形机器人", "丝杠", "减速器"]
        score = self.service.keyword_match("人形机器人丝杠", keywords)
        self.assertGreater(score, 0.5)
        self.assertLess(score, 1.0)

    def test_keyword_match_no_keywords(self) -> None:
        """Test keyword match with no keywords."""
        keywords = []
        score = self.service.keyword_match("人形机器人", keywords)
        self.assertEqual(score, 0.0)

    def test_keyword_match_no_match(self) -> None:
        """Test keyword match with no match."""
        keywords = ["芯片", "GPU"]
        score = self.service.keyword_match("人形机器人", keywords)
        self.assertEqual(score, 0.0)

    def test_calculate_theme_match_score_exact_board_match(self) -> None:
        """Test theme match score with exact board match."""
        boards = ["机器人"]
        stock_name = "机器人"
        theme_name = "机器人"
        keywords = ["机器人"]

        score = self.service.calculate_theme_match_score(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        # board_match=1.0, name_match=1.0, keyword_match=1.0
        # score = 1.0*0.55 + 1.0*0.20 + 1.0*0.25 = 1.0
        self.assertEqual(score, 1.0)

    def test_calculate_theme_match_score_no_match(self) -> None:
        """Test theme match score with no match."""
        boards = ["芯片"]
        stock_name = "某芯片股票"
        theme_name = "机器人"
        keywords = ["人形机器人"]

        score = self.service.calculate_theme_match_score(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        self.assertLess(score, 0.3)

    def test_is_hot_theme_stock_above_threshold(self) -> None:
        """Test is_hot_theme_stock returns True when score >= 0.80."""
        boards = ["机器人"]
        stock_name = "机器人"
        theme_name = "机器人"
        keywords = ["机器人"]

        result = self.service.is_hot_theme_stock(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        self.assertTrue(result)

    def test_is_hot_theme_stock_below_threshold(self) -> None:
        """Test is_hot_theme_stock returns False when score < 0.80."""
        boards = ["其他"]
        stock_name = "某其他股票"
        theme_name = "机器人"
        keywords = ["人形机器人"]

        result = self.service.is_hot_theme_stock(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        self.assertFalse(result)

    def test_is_hot_theme_stock_empty_boards(self) -> None:
        """Test is_hot_theme_stock with empty boards but matching name and keywords."""
        boards = []
        stock_name = "机器人"
        theme_name = "机器人"
        keywords = ["机器人"]

        result = self.service.is_hot_theme_stock(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        # score = 0*0.55 + 1.0*0.20 + 1.0*0.25 = 0.45 < 0.80
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
