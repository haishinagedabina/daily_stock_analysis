from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.repositories.board_repository import BoardRepository
from src.storage import DatabaseManager


class BoardSyncService:
    """Fetch and persist board memberships for stocks."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        fetcher_manager: Optional[Any] = None,
        board_repository: Optional[BoardRepository] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self.fetcher_manager = fetcher_manager
        self.repo = board_repository or BoardRepository(db_manager=self.db)

    def sync_codes(self, codes: List[str], market: str = "cn", source: str = "efinance") -> Dict[str, int]:
        processed = 0
        synced = 0
        missing = 0
        failed = 0

        for code in [str(item).strip().upper() for item in codes if str(item).strip()]:
            processed += 1
            try:
                raw_boards = self._get_fetcher_manager().get_belong_boards(code)
                memberships = self._normalize_memberships(raw_boards, market=market, source=source)
                if memberships:
                    self.repo.replace_memberships(
                        instrument_code=code,
                        memberships=memberships,
                        market=market,
                        source=source,
                    )
                    synced += 1
                else:
                    missing += 1
            except Exception:
                failed += 1

        return {
            "processed": processed,
            "synced": synced,
            "missing": missing,
            "failed": failed,
        }

    def _get_fetcher_manager(self) -> Any:
        if self.fetcher_manager is not None:
            return self.fetcher_manager

        from data_provider.base import DataFetcherManager

        self.fetcher_manager = DataFetcherManager()
        return self.fetcher_manager

    @staticmethod
    def _normalize_memberships(raw_boards: Any, market: str, source: str) -> List[Dict[str, Any]]:
        if not isinstance(raw_boards, list):
            return []

        normalized: List[Dict[str, Any]] = []
        seen = set()
        for item in raw_boards:
            board_name = ""
            board_type = "unknown"
            if isinstance(item, dict):
                board_name = str(
                    item.get("name")
                    or item.get("board_name")
                    or item.get("所属板块")
                    or item.get("industry")
                    or item.get("concept")
                    or ""
                ).strip()
                board_type = str(
                    item.get("type")
                    or item.get("board_type")
                    or item.get("type_name")
                    or "unknown"
                ).strip() or "unknown"
            elif item is not None:
                board_name = str(item).strip()

            if not board_name:
                continue

            identity = (board_name, board_type)
            if identity in seen:
                continue
            seen.add(identity)
            normalized.append(
                {
                    "board_name": board_name,
                    "board_type": board_type,
                    "market": market,
                    "source": source,
                }
            )

        return normalized
