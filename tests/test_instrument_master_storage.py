import os
import tempfile
import unittest
from datetime import date

from src.config import Config
from src.storage import DatabaseManager


class InstrumentMasterStorageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_instrument_master.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_upsert_and_query_active_instruments(self) -> None:
        saved = self.db.upsert_instruments(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "market": "cn",
                    "exchange": "SSE",
                    "listing_status": "active",
                    "is_st": False,
                    "industry": "白酒",
                    "list_date": date(2001, 8, 27),
                },
                {
                    "code": "000001",
                    "name": "*ST平安",
                    "market": "cn",
                    "exchange": "SZSE",
                    "listing_status": "active",
                    "is_st": True,
                    "industry": "银行",
                    "list_date": date(1991, 4, 3),
                },
                {
                    "code": "430001",
                    "name": "北交样本",
                    "market": "cn",
                    "exchange": "BSE",
                    "listing_status": "inactive",
                    "is_st": False,
                    "industry": "制造",
                    "list_date": date(2015, 6, 1),
                },
            ]
        )

        self.assertEqual(saved, 3)

        active = self.db.list_instruments(market="cn", listing_status="active", exclude_st=True)
        self.assertEqual([item["code"] for item in active], ["600519"])
        self.assertEqual(active[0]["industry"], "白酒")

        saved_again = self.db.upsert_instruments(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台股份",
                    "market": "cn",
                    "exchange": "SSE",
                    "listing_status": "active",
                    "is_st": False,
                    "industry": "高端白酒",
                    "list_date": date(2001, 8, 27),
                }
            ]
        )
        self.assertEqual(saved_again, 1)

        instrument = self.db.get_instrument("600519")
        self.assertEqual(instrument["name"], "贵州茅台股份")
        self.assertEqual(instrument["industry"], "高端白酒")


if __name__ == "__main__":
    unittest.main()
