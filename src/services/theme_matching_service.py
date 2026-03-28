# -*- coding: utf-8 -*-
"""Theme matching service for identifying hot theme stocks."""

from difflib import SequenceMatcher
from typing import List


class ThemeMatchingService:
    """Service for matching stocks to hot themes."""

    THEME_MATCH_THRESHOLD = 0.80

    def fuzzy_match(self, text1: str, text2: str) -> float:
        """
        Calculate fuzzy match score between two strings.
        Returns score between 0 and 1.
        """
        if not text1 or not text2:
            return 0.0

        text1_lower = text1.lower()
        text2_lower = text2.lower()

        if text1_lower == text2_lower:
            return 1.0

        matcher = SequenceMatcher(None, text1_lower, text2_lower)
        return matcher.ratio()

    def keyword_match(self, stock_name: str, keywords: List[str], boards: List[str] | None = None) -> float:
        """
        Calculate keyword match score.
        Returns the ratio of matched keywords to total keywords.
        """
        if not keywords:
            return 0.0

        search_space = [stock_name.lower()]
        search_space.extend(str(board).lower() for board in (boards or []) if str(board).strip())

        matched_count = 0
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if any(keyword_lower in candidate for candidate in search_space):
                matched_count += 1

        return matched_count / len(keywords)

    def calculate_theme_match_score(
        self,
        boards: List[str],
        stock_name: str,
        theme_name: str,
        keywords: List[str],
    ) -> float:
        """
        Calculate overall theme match score.
        Formula: board_match * 0.55 + name_match * 0.20 + keyword_match * 0.25
        """
        # Board match: max score among all boards
        board_match = 0.0
        if boards:
            board_match = max(
                self.fuzzy_match(board, theme_name) for board in boards
            )

        # Name match
        name_match = self.fuzzy_match(stock_name, theme_name)

        # Keyword match
        keyword_match = self.keyword_match(stock_name, keywords, boards=boards)

        # Weighted score
        score = (
            board_match * 0.55 + name_match * 0.20 + keyword_match * 0.25
        )

        # Strong board confirmation should satisfy the hard gate even when the
        # stock name itself does not resemble the theme name.
        if board_match >= 0.95 or (board_match >= 0.75 and keyword_match >= 0.5):
            score = max(score, self.THEME_MATCH_THRESHOLD)

        return score

    def is_hot_theme_stock(
        self,
        boards: List[str],
        stock_name: str,
        theme_name: str,
        keywords: List[str],
    ) -> bool:
        """
        Check if stock matches hot theme.
        Returns True if score >= 0.80, False otherwise.
        """
        score = self.calculate_theme_match_score(
            boards=boards,
            stock_name=stock_name,
            theme_name=theme_name,
            keywords=keywords,
        )
        return score >= self.THEME_MATCH_THRESHOLD
