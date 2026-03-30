# -*- coding: utf-8 -*-
"""Deterministic theme normalization: splitting, alias resolution, recall, and assembly."""

import json
import os
import re
from typing import Any, Dict, List, Optional

from src.services.board_candidate_recall_service import BoardCandidateRecallService

_SPLIT_PATTERN = re.compile(r"[/／、]")

_ALIAS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "theme_aliases.json",
)


def _load_alias_map(path: str = _ALIAS_FILE) -> Dict[str, Dict[str, Any]]:
    """Load alias vocabulary keyed by lower-cased raw_alias."""
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    alias_map: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("aliases", []):
        key = (entry.get("raw_alias") or "").strip().lower()
        if key:
            alias_map[key] = entry
    return alias_map


class ThemeNormalizationService:
    """Deterministic theme normalization via splitting, alias lookup, and board recall."""

    def __init__(self, alias_path: Optional[str] = None) -> None:
        path = alias_path or _ALIAS_FILE
        self._alias_map = _load_alias_map(path)
        self._recall_service = BoardCandidateRecallService()

    def set_board_vocabulary(self, board_names: List[str]) -> None:
        """Inject board vocabulary for candidate recall."""
        self._recall_service.set_board_names(board_names)

    # ------------------------------------------------------------------
    # Splitting
    # ------------------------------------------------------------------

    @staticmethod
    def split_theme(raw_theme: str) -> List[str]:
        """Split a compound theme label on '/' or '／' or '、'.

        Returns deduplicated, trimmed parts in original order.
        """
        parts = _SPLIT_PATTERN.split(raw_theme)
        seen: set = set()
        result: List[str] = []
        for p in parts:
            p = p.strip()
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        return result

    # ------------------------------------------------------------------
    # Alias resolution
    # ------------------------------------------------------------------

    def resolve_alias(self, theme_part: str) -> Optional[Dict[str, Any]]:
        """Look up a single theme part in the alias vocabulary.

        Returns a dict with matched_boards and match_reasons, or None.
        """
        key = theme_part.strip().lower()
        entry = self._alias_map.get(key)
        if entry is None:
            return None
        return {
            "normalized_label": entry.get("normalized_label", theme_part),
            "matched_boards": list(entry.get("matched_boards", [])),
            "match_reasons": ["alias_hit"],
        }

    # ------------------------------------------------------------------
    # Single-theme normalization (split + alias + recall)
    # ------------------------------------------------------------------

    def normalize_theme(
        self,
        raw_theme: str,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Normalize a single raw theme string.

        Pipeline:
        1. Split compound labels.
        2. Resolve each part via alias.
        3. For unresolved parts, fall back to candidate board recall.
        4. Merge results and classify confidence.
        """
        parts = self.split_theme(raw_theme)
        all_boards: List[str] = []
        all_reasons: List[str] = []
        labels: List[str] = []
        has_alias = False
        has_recall = False

        for part in parts:
            # Layer 1: alias match
            alias_result = self.resolve_alias(part)
            if alias_result is not None:
                has_alias = True
                for b in alias_result["matched_boards"]:
                    if b not in all_boards:
                        all_boards.append(b)
                for r in alias_result["match_reasons"]:
                    if r not in all_reasons:
                        all_reasons.append(r)
                labels.append(alias_result["normalized_label"])
                continue

            # Layer 2: candidate board recall fallback
            recall_candidates = self._recall_service.recall_candidates(
                theme_name=part, keywords=keywords, top_k=5,
            )
            if recall_candidates:
                has_recall = True
                for c in recall_candidates:
                    board = c["board_name"]
                    if board not in all_boards:
                        all_boards.append(board)
                    for r in c["match_reasons"]:
                        reason = f"recall_{r}"
                        if reason not in all_reasons:
                            all_reasons.append(reason)
                labels.append(part)

        # Classify confidence status
        if all_boards and has_alias:
            status = "high_confidence"
            confidence = 1.0
        elif all_boards and has_recall:
            status = "weak_match"
            confidence = 0.6
        else:
            status = "unresolved"
            confidence = 0.0
            labels = [raw_theme]

        # Promote to high_confidence if both alias and recall contributed
        if has_alias and has_recall and all_boards:
            status = "high_confidence"
            confidence = 0.9

        return {
            "raw_theme": raw_theme,
            "normalized_label": "/".join(labels),
            "matched_boards": all_boards,
            "match_confidence": confidence,
            "match_reasons": all_reasons,
            "status": status,
        }
