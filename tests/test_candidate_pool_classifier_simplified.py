# -*- coding: utf-8 -*-
"""Tests for simplified candidate-pool classification rules."""

import unittest

from src.schemas.trading_types import CandidatePoolLevel, ThemePosition
from src.services.candidate_pool_classifier import CandidatePoolClassifier


class CandidatePoolClassifierSimplifiedTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.classifier = CandidatePoolClassifier()

    def test_main_theme_limit_up_stock_can_enter_leader_pool(self) -> None:
        result = self.classifier.classify(
            leader_score=0.0,
            extreme_strength_score=0.0,
            theme_position=ThemePosition.MAIN_THEME,
            is_limit_up=True,
        )
        self.assertEqual(result, CandidatePoolLevel.LEADER_POOL)

    def test_secondary_theme_limit_up_stock_can_enter_leader_pool(self) -> None:
        result = self.classifier.classify(
            leader_score=0.0,
            extreme_strength_score=0.0,
            theme_position=ThemePosition.SECONDARY_THEME,
            is_limit_up=True,
        )
        self.assertEqual(result, CandidatePoolLevel.LEADER_POOL)

    def test_follower_theme_limit_up_stock_stays_in_focus_list(self) -> None:
        result = self.classifier.classify(
            leader_score=99.0,
            extreme_strength_score=99.0,
            theme_position=ThemePosition.FOLLOWER_THEME,
            is_limit_up=True,
        )
        self.assertEqual(result, CandidatePoolLevel.FOCUS_LIST)

    def test_non_limit_up_main_theme_stock_does_not_enter_leader_pool(self) -> None:
        result = self.classifier.classify(
            leader_score=99.0,
            extreme_strength_score=99.0,
            theme_position=ThemePosition.MAIN_THEME,
            is_limit_up=False,
        )
        self.assertEqual(result, CandidatePoolLevel.FOCUS_LIST)

    def test_non_theme_stock_cannot_enter_leader_pool_even_if_limit_up(self) -> None:
        result = self.classifier.classify(
            leader_score=99.0,
            extreme_strength_score=99.0,
            theme_position=ThemePosition.NON_THEME,
            is_limit_up=True,
        )
        self.assertEqual(result, CandidatePoolLevel.WATCHLIST)
