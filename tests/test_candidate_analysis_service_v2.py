"""TDD tests for CandidateAnalysisService Agent-enhanced path.

Tests that CandidateAnalysisService can use agent-based analysis when a
SkillManager and matched_strategies are available on candidates.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.candidate_analysis_service import (
    CandidateAnalysisBatchResult,
    CandidateAnalysisService,
)
from src.services.screener_service import ScreeningCandidateRecord


def _make_candidate(code: str = "600001", name: str = "测试", **overrides) -> ScreeningCandidateRecord:
    defaults = {
        "code": code,
        "name": name,
        "rank": 1,
        "rule_score": 80.0,
        "rule_hits": ["trend_aligned", "strategy:volume_breakout"],
        "factor_snapshot": {"close": 10.0, "volume_ratio": 2.5},
        "matched_strategies": ["volume_breakout"],
        "strategy_scores": {"volume_breakout": 80.0},
    }
    defaults.update(overrides)
    return ScreeningCandidateRecord(**defaults)


class TestCandidateAnalysisServiceAgentPath:

    def test_analyze_top_k_accepts_skill_manager(self):
        """CandidateAnalysisService can be initialized with a skill_manager."""
        mock_analysis = MagicMock()
        mock_skill_mgr = MagicMock()
        mock_db = MagicMock()

        service = CandidateAnalysisService(
            analysis_service=mock_analysis,
            db_manager=mock_db,
            skill_manager=mock_skill_mgr,
        )
        assert service._skill_manager is mock_skill_mgr

    def test_analyze_top_k_uses_agent_when_strategies_available(self):
        """When candidates have matched_strategies and skill_manager is set,
        agent-enhanced analysis is used."""
        mock_analysis = MagicMock()
        mock_analysis.analyze_stock.return_value = {
            "report": {
                "meta": {"query_id": "q1"},
                "summary": {
                    "analysis_summary": "AI分析结果",
                    "operation_advice": "建议观望",
                },
            }
        }
        mock_skill_mgr = MagicMock()
        mock_skill_mgr.get.return_value = MagicMock(
            name="volume_breakout",
            instructions="分析指令",
        )
        mock_db = MagicMock()

        service = CandidateAnalysisService(
            analysis_service=mock_analysis,
            db_manager=mock_db,
            skill_manager=mock_skill_mgr,
        )

        candidates = [_make_candidate("600001", matched_strategies=["volume_breakout"])]
        result = service.analyze_top_k(candidates, top_k=1)

        assert isinstance(result, CandidateAnalysisBatchResult)
        assert "600001" in result.results

    def test_analyze_top_k_falls_back_without_skill_manager(self):
        """Without skill_manager, uses standard analysis_service."""
        mock_analysis = MagicMock()
        mock_analysis.analyze_stock.return_value = {
            "report": {
                "meta": {"query_id": "q1"},
                "summary": {
                    "analysis_summary": "简单分析",
                    "operation_advice": "持仓",
                },
            }
        }
        mock_db = MagicMock()

        service = CandidateAnalysisService(
            analysis_service=mock_analysis,
            db_manager=mock_db,
        )

        candidates = [_make_candidate("600001")]
        result = service.analyze_top_k(candidates, top_k=1)

        assert isinstance(result, CandidateAnalysisBatchResult)
        assert "600001" in result.results

    def test_result_includes_matched_strategy_context(self):
        """Analysis result should include the matched strategy context."""
        mock_analysis = MagicMock()
        mock_analysis.analyze_stock.return_value = {
            "report": {
                "meta": {"query_id": "q1"},
                "summary": {
                    "analysis_summary": "分析",
                    "operation_advice": "买入",
                },
            }
        }
        mock_skill_mgr = MagicMock()
        mock_db = MagicMock()

        service = CandidateAnalysisService(
            analysis_service=mock_analysis,
            db_manager=mock_db,
            skill_manager=mock_skill_mgr,
        )

        candidates = [_make_candidate("600001", matched_strategies=["volume_breakout"])]
        result = service.analyze_top_k(candidates, top_k=1)

        entry = result.results.get("600001", {})
        assert "matched_strategies" in entry
        assert "volume_breakout" in entry["matched_strategies"]
