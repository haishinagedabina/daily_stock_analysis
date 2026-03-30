from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.storage import DatabaseManager


class BoardRepository:
    """Board persistence access layer."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def upsert_boards(self, boards: List[Dict[str, Any]]) -> int:
        return self.db.upsert_boards(boards)

    def replace_memberships(
        self,
        instrument_code: str,
        memberships: List[Dict[str, Any]],
        market: str = "cn",
        source: Optional[str] = None,
    ) -> int:
        return self.db.replace_instrument_board_memberships(
            instrument_code=instrument_code,
            memberships=memberships,
            market=market,
            source=source,
        )

    def batch_get_board_names_by_codes(
        self,
        codes: List[str],
        market: str = "cn",
    ) -> Dict[str, List[str]]:
        return self.db.batch_get_instrument_board_names(codes=codes, market=market)
