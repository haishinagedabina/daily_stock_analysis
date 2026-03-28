# -*- coding: utf-8 -*-
"""TDD: Integration test for OpenClaw endpoint with strategy filtering."""

import pytest
from datetime import date
from src.services.screening_task_service import ScreeningTaskService
from src.services.theme_context_ingest_service import ExternalTheme, OpenClawThemeContext
from src.agent.skills.base import SkillManager


class TestOpenClawEndpointIntegration:
    """Test that OpenClaw endpoint correctly filters strategies end-to-end."""

    def test_openclaw_run_only_returns_extreme_strength_combo(self):
        """RED: OpenClaw run should only return candidates with extreme_strength_combo strategy."""
        # Setup
        skill_manager = SkillManager()
        skill_manager.load_builtin_strategies()
        service = ScreeningTaskService(skill_manager=skill_manager)

        # Create theme context (simulating OpenClaw input)
        theme_context = OpenClawThemeContext(
            source="openclaw",
            trade_date=date.today().isoformat(),
            market="cn",
            themes=[
                ExternalTheme(
                    name="AI芯片",
                    heat_score=85.0,
                    confidence=0.9,
                    catalyst_summary="AI芯片板块受政策利好刺激",
                    keywords=["AI", "芯片", "算力"],
                    evidence=[],
                )
            ],
            accepted_at="2026-03-27T15:00:00",
        )

        # Inject theme context
        service._theme_context = theme_context

        # Execute run with only extreme_strength_combo strategy
        result = service.execute_run(
            trade_date=None,
            stock_codes=None,
            mode="balanced",
            candidate_limit=50,
            ai_top_k=10,
            market="cn",
            trigger_type="openclaw",
            strategy_names=["extreme_strength_combo"],
        )

        # Verify run was created
        assert result["run_id"] is not None
        run_id = result["run_id"]

        # Retrieve candidates from database
        candidates = service.db.list_screening_candidates(run_id=run_id, limit=100)

        # Verify all candidates only have extreme_strength_combo
        if candidates:
            for candidate in candidates:
                matched_strategies = candidate.get("matched_strategies", [])
                assert matched_strategies == ["extreme_strength_combo"], \
                    f"Candidate {candidate['code']} has wrong strategies: {matched_strategies}"

        # Cleanup
        service.db.delete_screening_run(run_id)
