from __future__ import annotations

from typing import Any, Dict, List, Optional


class ThemePipelineFusionService:
    """Merge local and external theme pipeline summaries into a unified shape."""

    @staticmethod
    def _theme_key(theme: Dict[str, Any]) -> str:
        return str(theme.get("normalized_name") or theme.get("name") or "").strip()

    @staticmethod
    def _merge_theme(
        existing_theme: Dict[str, Any],
        incoming_theme: Dict[str, Any],
        incoming_source: str,
    ) -> Dict[str, Any]:
        merged = dict(existing_theme)
        matched_sources = list(merged.get("matched_sources", []) or [])
        raw_names = list(merged.get("raw_names", []) or [])
        if incoming_source not in matched_sources:
            matched_sources.append(incoming_source)
        incoming_raw_name = str(incoming_theme.get("raw_name") or incoming_theme.get("name") or "").strip()
        if incoming_raw_name and incoming_raw_name not in raw_names:
            raw_names.append(incoming_raw_name)

        for key, value in incoming_theme.items():
            if key not in merged or merged.get(key) in (None, "", [], {}):
                merged[key] = value

        merged["matched_sources"] = matched_sources
        merged["raw_names"] = raw_names
        return merged

    def merge(
        self,
        local_pipeline: Optional[Dict[str, Any]],
        external_pipeline: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        active_sources: List[str] = []
        trade_date = None
        market = None
        merged_by_name: Dict[str, Dict[str, Any]] = {}
        merged_order: List[str] = []

        def _append_theme(theme: Dict[str, Any], source: str) -> None:
            normalized_name = self._theme_key(theme)
            if not normalized_name:
                return
            raw_name = str(theme.get("raw_name") or theme.get("name") or normalized_name).strip()
            normalized_theme = {
                **dict(theme),
                "name": normalized_name,
                "normalized_name": normalized_name,
                "raw_name": raw_name,
                "raw_names": [raw_name] if raw_name else [],
                "source": source,
                "priority_source": source,
                "matched_sources": [source],
            }
            if normalized_name not in merged_by_name:
                merged_by_name[normalized_name] = normalized_theme
                merged_order.append(normalized_name)
                return
            merged_by_name[normalized_name] = self._merge_theme(
                existing_theme=merged_by_name[normalized_name],
                incoming_theme=normalized_theme,
                incoming_source=source,
            )

        if local_pipeline:
            active_sources.append("local")
            trade_date = local_pipeline.get("trade_date", trade_date)
            market = local_pipeline.get("market", market)
            for theme in local_pipeline.get("themes", []) or []:
                _append_theme(theme, "local")

        if external_pipeline:
            active_sources.append("external")
            trade_date = trade_date or external_pipeline.get("trade_date")
            market = market or external_pipeline.get("market")
            for theme in external_pipeline.get("themes", []) or []:
                _append_theme(theme, "external")

        merged_themes = [merged_by_name[name] for name in merged_order]
        selected_theme_names = [str(theme.get("name")) for theme in merged_themes if theme.get("name")]
        return {
            "trade_date": trade_date,
            "market": market,
            "active_sources": active_sources,
            "selected_theme_names": selected_theme_names,
            "merged_theme_count": len(merged_themes),
            "merged_themes": merged_themes,
        }
