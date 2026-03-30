# -*- coding: utf-8 -*-
"""Candidate board recall from local board vocabulary.

Uses exact hits, substring overlap, and keyword matching — no embeddings.
"""

from typing import Any, Dict, List, Optional


class BoardCandidateRecallService:
    """Recall candidate boards from a local board name vocabulary."""

    def __init__(self, board_names: Optional[List[str]] = None) -> None:
        self._board_names: List[str] = list(board_names or [])

    def set_board_names(self, board_names: List[str]) -> None:
        self._board_names = list(board_names)

    def recall_candidates(
        self,
        theme_name: str,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return scored candidate boards for a single theme part.

        Scoring layers (deterministic, no embeddings):
        1. Exact hit: score 1.0
        2. Substring overlap (theme in board or board in theme): score 0.7
        3. Keyword overlap: score 0.5
        """
        if not theme_name or not self._board_names:
            return []

        theme_lower = theme_name.strip().lower()
        kw_lower = [k.strip().lower() for k in (keywords or []) if k.strip()]
        scored: List[Dict[str, Any]] = []

        for board in self._board_names:
            board_lower = board.strip().lower()
            score = 0.0
            reasons: List[str] = []

            # Layer 1: exact hit
            if board_lower == theme_lower:
                score = max(score, 1.0)
                reasons.append("exact_hit")

            # Layer 2: substring overlap
            if score < 1.0:
                if theme_lower in board_lower or board_lower in theme_lower:
                    score = max(score, 0.7)
                    reasons.append("substring_overlap")

            # Layer 3: keyword overlap
            if kw_lower:
                for kw in kw_lower:
                    if kw in board_lower:
                        score = max(score, 0.5)
                        if "keyword_overlap" not in reasons:
                            reasons.append("keyword_overlap")

            if score > 0:
                scored.append({
                    "board_name": board,
                    "score": score,
                    "match_reasons": reasons,
                })

        scored.sort(key=lambda c: -c["score"])
        return scored[:top_k]
