import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from src.config import Config
from src.storage import DatabaseManager


def _load_script_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "backfill_instrument_boards.py"
    spec = importlib.util.spec_from_file_location("backfill_instrument_boards", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeBoardSyncService:
    def __init__(self) -> None:
        self.calls = []

    def sync_codes(self, codes, market="cn", source="efinance"):
        self.calls.append(
            {
                "codes": list(codes),
                "market": market,
                "source": source,
            }
        )
        return {"processed": len(codes), "synced": len(codes), "missing": 0, "failed": 0}


class BackfillInstrumentBoardsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "board_backfill.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.db.upsert_instruments(
            [
                {"code": "600519", "name": "A", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "300750", "name": "B", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "000001", "name": "C", "market": "cn", "listing_status": "active", "is_st": False},
            ]
        )

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_resolve_target_codes_supports_explicit_codes_and_limit(self) -> None:
        module = _load_script_module()

        resolved_codes = module.resolve_target_codes(
            db_manager=self.db,
            codes=["300750", "600519"],
            market="cn",
            limit=1,
        )

        self.assertEqual(resolved_codes, ["300750"])

    def test_resolve_target_codes_stale_only_returns_codes_without_memberships(self) -> None:
        module = _load_script_module()
        self.db.replace_instrument_board_memberships(
            instrument_code="600519",
            memberships=[{"board_name": "Liquor", "board_type": "industry", "market": "cn", "source": "efinance"}],
            market="cn",
            source="efinance",
        )

        resolved_codes = module.resolve_target_codes(
            db_manager=self.db,
            market="cn",
            stale_only=True,
        )

        self.assertEqual(resolved_codes, ["000001", "300750"])

    def test_run_backfill_dry_run_does_not_call_sync_service(self) -> None:
        module = _load_script_module()
        service = _FakeBoardSyncService()

        result = module.run_backfill(
            db_manager=self.db,
            sync_service=service,
            codes=["600519", "300750"],
            dry_run=True,
        )

        self.assertEqual(result["planned"], 2)
        self.assertEqual(result["codes"], ["600519", "300750"])
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
