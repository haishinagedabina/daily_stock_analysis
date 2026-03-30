import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.board_sync_service import BoardSyncService
from src.storage import DatabaseManager


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill stock board memberships into the local database.")
    parser.add_argument("--codes", type=str, default="", help="Comma-separated stock codes to sync.")
    parser.add_argument("--limit", type=int, default=None, help="Limit how many stocks to process.")
    parser.add_argument("--market", type=str, default="cn", help="Target market, default is cn.")
    parser.add_argument("--source", type=str, default="efinance", help="Board data source label.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional delay between batches.")
    parser.add_argument("--dry-run", action="store_true", help="Only show which codes would be processed.")
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Reserved for future incremental refresh support. Currently behaves the same as a normal run.",
    )
    return parser.parse_args()


def resolve_target_codes(
    db_manager: Optional[DatabaseManager] = None,
    codes: Optional[List[str]] = None,
    market: str = "cn",
    limit: Optional[int] = None,
    stale_only: bool = False,
) -> List[str]:
    db = db_manager or DatabaseManager.get_instance()
    normalized_codes = [str(code).strip().upper() for code in (codes or []) if str(code).strip()]
    if normalized_codes:
        if not stale_only:
            return normalized_codes[:limit] if limit is not None else normalized_codes

        board_map = db.batch_get_instrument_board_names(normalized_codes, market=market)
        missing_codes = [code for code in normalized_codes if not board_map.get(code)]
        return missing_codes[:limit] if limit is not None else missing_codes

    instruments = db.list_instruments(
        market=market,
        listing_status="active",
        exclude_st=True,
    )
    instrument_codes = [
        str(item.get("code", "")).strip().upper()
        for item in instruments
        if str(item.get("code", "")).strip()
    ]
    if not stale_only:
        return instrument_codes[:limit] if limit is not None else instrument_codes

    board_map = db.batch_get_instrument_board_names(instrument_codes, market=market)
    missing_codes = [code for code in instrument_codes if not board_map.get(code)]
    return missing_codes[:limit] if limit is not None else missing_codes


def run_backfill(
    db_manager: Optional[DatabaseManager] = None,
    sync_service: Optional[BoardSyncService] = None,
    codes: Optional[List[str]] = None,
    market: str = "cn",
    source: str = "efinance",
    limit: Optional[int] = None,
    sleep_seconds: float = 0.0,
    dry_run: bool = False,
    stale_only: bool = False,
):
    db = db_manager or DatabaseManager.get_instance()
    service = sync_service or BoardSyncService(db_manager=db)
    target_codes = resolve_target_codes(
        db_manager=db,
        codes=codes,
        market=market,
        limit=limit,
        stale_only=stale_only,
    )

    if dry_run:
        return {
            "planned": len(target_codes),
            "codes": target_codes,
            "market": market,
            "source": source,
            "dry_run": True,
        }

    result = service.sync_codes(target_codes, market=market, source=source)
    result["codes"] = target_codes
    result["dry_run"] = False

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    codes = [item.strip().upper() for item in args.codes.split(",") if item.strip()]
    result = run_backfill(
        codes=codes or None,
        market=args.market,
        source=args.source,
        limit=args.limit,
        sleep_seconds=args.sleep_seconds,
        dry_run=args.dry_run,
        stale_only=args.stale_only,
    )
    logger.info("board backfill result: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
