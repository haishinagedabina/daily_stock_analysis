# -*- coding: utf-8 -*-
"""Unit tests for system configuration service."""

import os
import tempfile
import unittest
from pathlib import Path

from src.config import Config
from src.core.config_manager import ConfigManager
from src.services.system_config_service import ConfigConflictError, SystemConfigService


class SystemConfigServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519,000001",
                    "GEMINI_API_KEY=secret-key-value",
                    "SCHEDULE_TIME=18:00",
                    "LOG_LEVEL=INFO",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        Config.reset_instance()

        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)

    def tearDown(self) -> None:
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        self.temp_dir.cleanup()

    def test_get_config_returns_raw_sensitive_values(self) -> None:
        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertIn("GEMINI_API_KEY", items)
        self.assertEqual(items["GEMINI_API_KEY"]["value"], "secret-key-value")
        self.assertFalse(items["GEMINI_API_KEY"]["is_masked"])
        self.assertTrue(items["GEMINI_API_KEY"]["raw_value_exists"])

    def test_update_preserves_masked_secret(self) -> None:
        old_version = self.manager.get_config_version()
        response = self.service.update(
            config_version=old_version,
            items=[
                {"key": "GEMINI_API_KEY", "value": "******"},
                {"key": "STOCK_LIST", "value": "600519,300750"},
            ],
            mask_token="******",
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["applied_count"], 1)
        self.assertEqual(response["skipped_masked_count"], 1)
        self.assertIn("STOCK_LIST", response["updated_keys"])

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["STOCK_LIST"], "600519,300750")
        self.assertEqual(current_map["GEMINI_API_KEY"], "secret-key-value")

    def test_validate_reports_invalid_time(self) -> None:
        validation = self.service.validate(items=[{"key": "SCHEDULE_TIME", "value": "25:70"}])
        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_format" for issue in validation["issues"]))

    def test_update_raises_conflict_for_stale_version(self) -> None:
        with self.assertRaises(ConfigConflictError):
            self.service.update(
                config_version="stale-version",
                items=[{"key": "STOCK_LIST", "value": "600519"}],
                reload_now=False,
            )

    def test_validate_reports_screening_top_k_exceeds_candidate_limit(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "SCREENING_CANDIDATE_LIMIT", "value": "10"},
                {"key": "SCREENING_AI_TOP_K", "value": "12"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "SCREENING_AI_TOP_K" and issue["code"] == "out_of_range_relation"
                for issue in validation["issues"]
            )
        )

    def test_validate_uses_default_candidate_limit_when_only_ai_top_k_is_updated(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "SCREENING_AI_TOP_K", "value": "40"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "SCREENING_AI_TOP_K" and issue["code"] == "out_of_range_relation"
                for issue in validation["issues"]
            )
        )

    def test_validate_rejects_non_finite_screening_number(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "SCREENING_MIN_VOLUME_RATIO", "value": "nan"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "SCREENING_MIN_VOLUME_RATIO" and issue["code"] == "invalid_type"
                for issue in validation["issues"]
            )
        )

    def test_validate_rejects_unrelated_update_when_existing_screening_defaults_are_invalid(self) -> None:
        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8")
            + "SCREENING_CANDIDATE_LIMIT=1\nSCREENING_AI_TOP_K=5\n",
            encoding="utf-8",
        )

        validation = self.service.validate(
            items=[
                {"key": "LOG_LEVEL", "value": "DEBUG"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "SCREENING_AI_TOP_K" and issue["code"] == "out_of_range_relation"
                for issue in validation["issues"]
            )
        )

    def test_get_config_normalizes_invalid_screening_default_mode(self) -> None:
        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8") + "SCREENING_DEFAULT_MODE=unknown\n",
            encoding="utf-8",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["SCREENING_DEFAULT_MODE"]["value"], "balanced")

    def test_get_config_normalizes_mixed_case_screening_default_mode(self) -> None:
        self.env_path.write_text(
            self.env_path.read_text(encoding="utf-8") + "SCREENING_DEFAULT_MODE=Aggressive\n",
            encoding="utf-8",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["SCREENING_DEFAULT_MODE"]["value"], "aggressive")

    def test_validate_accepts_mixed_case_screening_default_mode(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "SCREENING_DEFAULT_MODE", "value": "Aggressive"},
            ]
        )

        self.assertTrue(validation["valid"])

    def test_update_normalizes_screening_default_mode_before_persist(self) -> None:
        old_version = self.manager.get_config_version()

        response = self.service.update(
            config_version=old_version,
            items=[
                {"key": "SCREENING_DEFAULT_MODE", "value": "Aggressive"},
            ],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["SCREENING_DEFAULT_MODE"], "aggressive")


if __name__ == "__main__":
    unittest.main()
