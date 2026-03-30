# -*- coding: utf-8 -*-
"""Unit tests for BoardCandidateRecallService."""

import unittest
from src.services.board_candidate_recall_service import BoardCandidateRecallService


class BoardCandidateRecallTestCase(unittest.TestCase):
    """Test candidate board recall from a local board vocabulary."""

    def setUp(self) -> None:
        # Provide a mock board vocabulary directly
        self.board_names = [
            "锂电池",
            "锂电池概念",
            "锂矿概念",
            "创新药",
            "创新药概念",
            "AI智能体",
            "AIGC概念",
            "多模态AI",
            "机器人概念",
            "半导体概念",
            "芯片概念",
            "海南自贸港",
            "免税概念",
            "人工智能",
        ]
        self.service = BoardCandidateRecallService(board_names=self.board_names)

    def test_exact_board_name_hit(self) -> None:
        candidates = self.service.recall_candidates(theme_name="创新药")
        self.assertTrue(len(candidates) > 0)
        self.assertEqual(candidates[0]["board_name"], "创新药")
        self.assertIn("exact_hit", candidates[0]["match_reasons"])

    def test_substring_match(self) -> None:
        candidates = self.service.recall_candidates(theme_name="锂电")
        board_names = [c["board_name"] for c in candidates]
        self.assertIn("锂电池", board_names)
        self.assertIn("锂电池概念", board_names)

    def test_keyword_assisted_recall(self) -> None:
        candidates = self.service.recall_candidates(
            theme_name="医药生物", keywords=["创新药"],
        )
        board_names = [c["board_name"] for c in candidates]
        self.assertIn("创新药", board_names)

    def test_top_k_ordering(self) -> None:
        candidates = self.service.recall_candidates(
            theme_name="锂电池", top_k=3,
        )
        self.assertTrue(len(candidates) <= 3)
        # exact hit should be first
        self.assertEqual(candidates[0]["board_name"], "锂电池")

    def test_no_match_returns_empty(self) -> None:
        candidates = self.service.recall_candidates(theme_name="完全无关XYZ")
        self.assertEqual(candidates, [])

    def test_candidate_shape(self) -> None:
        candidates = self.service.recall_candidates(theme_name="AI智能体")
        self.assertTrue(len(candidates) > 0)
        c = candidates[0]
        self.assertIn("board_name", c)
        self.assertIn("score", c)
        self.assertIn("match_reasons", c)


if __name__ == "__main__":
    unittest.main()
