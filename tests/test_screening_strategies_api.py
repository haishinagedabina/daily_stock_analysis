"""TDD tests for GET /api/v1/screening/strategies endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from server import app
    return TestClient(app)


class TestScreeningStrategiesEndpoint:

    @patch("api.v1.endpoints.screening.get_screening_strategies")
    def test_returns_strategy_list(self, mock_get, client):
        mock_get.return_value = [
            {
                "name": "volume_breakout",
                "display_name": "放量突破",
                "description": "检测放量突破阻力位信号。",
                "category": "trend",
                "has_screening_rules": True,
            },
            {
                "name": "bottom_volume",
                "display_name": "底部放量",
                "description": "检测底部放量信号。",
                "category": "reversal",
                "has_screening_rules": True,
            },
        ]

        resp = client.get("/api/v1/screening/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert len(data["strategies"]) == 2
        assert data["strategies"][0]["name"] == "volume_breakout"
        assert data["strategies"][0]["has_screening_rules"] is True

    @patch("api.v1.endpoints.screening.get_screening_strategies")
    def test_returns_empty_list_when_no_strategies(self, mock_get, client):
        mock_get.return_value = []
        resp = client.get("/api/v1/screening/strategies")
        assert resp.status_code == 200
        assert resp.json()["strategies"] == []

    @patch("api.v1.endpoints.screening.get_screening_strategies")
    def test_strategy_has_required_fields(self, mock_get, client):
        mock_get.return_value = [
            {
                "name": "test",
                "display_name": "测试",
                "description": "desc",
                "category": "trend",
                "has_screening_rules": False,
            },
        ]
        resp = client.get("/api/v1/screening/strategies")
        s = resp.json()["strategies"][0]
        assert "name" in s
        assert "display_name" in s
        assert "description" in s
        assert "category" in s
        assert "has_screening_rules" in s
