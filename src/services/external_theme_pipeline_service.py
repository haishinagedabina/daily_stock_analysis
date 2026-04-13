from __future__ import annotations

from typing import Any, Dict, List

from src.services.theme_context_ingest_service import OpenClawThemeContext
from src.services.theme_normalization_service import ThemeNormalizationService


class ExternalThemePipelineService:
    """Build a standalone summary for the external OpenClaw theme pipeline."""

    HOT_THEME_THRESHOLD = 70.0
    FOCUS_THEME_THRESHOLD = 85.0

    def build_summary(self, theme_context: OpenClawThemeContext) -> Dict[str, Any]:
        normalizer = ThemeNormalizationService()
        sorted_themes = sorted(
            list(theme_context.themes or []),
            key=lambda item: (float(item.heat_score), float(item.confidence)),
            reverse=True,
        )
        theme_summaries: List[Dict[str, Any]] = []
        for theme in sorted_themes:
            raw_name = str(theme.name or "").strip()
            if not raw_name:
                continue
            keywords = list(theme.keywords or [])
            normalized = normalizer.normalize_theme(raw_theme=raw_name, keywords=keywords)
            normalized_name = str(normalized.get("normalized_label") or raw_name).strip()
            theme_summaries.append(
                {
                    "name": normalized_name,
                    "normalized_name": normalized_name,
                    "raw_name": raw_name,
                    "normalization_status": normalized.get("status"),
                    "normalization_confidence": float(normalized.get("match_confidence", 0.0) or 0.0),
                    "normalization_match_reasons": list(normalized.get("match_reasons", []) or []),
                    "normalization_matched_boards": list(normalized.get("matched_boards", []) or []),
                    "heat_score": float(theme.heat_score),
                    "confidence": float(theme.confidence),
                    "catalyst_summary": theme.catalyst_summary,
                    "keyword_count": len(keywords),
                    "keywords": keywords,
                }
            )
        return {
            "source": theme_context.source,
            "trade_date": theme_context.trade_date,
            "market": theme_context.market,
            "accepted_theme_count": len(theme_summaries),
            "hot_theme_count": sum(
                1 for theme in theme_summaries if float(theme["heat_score"]) >= self.HOT_THEME_THRESHOLD
            ),
            "focus_theme_count": sum(
                1 for theme in theme_summaries if float(theme["heat_score"]) >= self.FOCUS_THEME_THRESHOLD
            ),
            "top_theme_names": list(dict.fromkeys(theme["name"] for theme in theme_summaries)),
            "themes": theme_summaries,
        }
