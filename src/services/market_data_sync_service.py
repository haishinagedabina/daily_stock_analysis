from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from data_provider.base import DataFetchError, DataFetcherManager
from src.storage import DatabaseManager


class MarketDataSyncService:
    """全市场日线增量同步服务。"""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        fetcher_manager: Optional[DataFetcherManager] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self.fetcher_manager = fetcher_manager or DataFetcherManager()

    def sync_trade_date(
        self,
        trade_date: date,
        stock_codes: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, object]:
        if stock_codes:
            codes = [str(code).strip().upper() for code in stock_codes if str(code).strip()]
        else:
            instruments = self.db.list_instruments(market="cn", listing_status="active", exclude_st=True)
            codes = [item["code"] for item in instruments]

        synced = 0
        skipped = 0
        errors = []

        for code in codes:
            if not force and self.db.has_today_data(code, target_date=trade_date):
                skipped += 1
                continue

            try:
                df, source_name = self.fetcher_manager.get_daily_data(
                    code,
                    start_date=trade_date.isoformat(),
                    end_date=trade_date.isoformat(),
                    days=1,
                )
                if df is None or df.empty:
                    errors.append({"code": code, "reason": "empty_data"})
                    continue

                saved = self.db.save_daily_data(df, code, data_source=source_name)
                if saved > 0 or self.db.has_today_data(code, target_date=trade_date):
                    synced += 1
                else:
                    errors.append({"code": code, "reason": "save_failed"})
            except Exception as exc:
                if isinstance(exc, DataFetchError):
                    errors.append(self._build_fetch_error_record(code=code, detail=str(exc)))
                else:
                    errors.append({"code": code, "reason": str(exc)})

        missing_codes = [
            code for code in codes
            if not self.db.has_today_data(code, target_date=trade_date)
        ]
        available_count = len(codes) - len(missing_codes)
        success_rate = round((available_count / len(codes)), 4) if codes else 0.0
        refresh_success_rate = round((synced / len(codes)), 4) if codes else 0.0
        return {
            "trade_date": trade_date.isoformat(),
            "total": len(codes),
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "health_report": {
                "expected_count": len(codes),
                "available_count": available_count,
                "missing_count": len(missing_codes),
                "error_count": len(errors),
                "missing_codes": missing_codes,
                "success_rate": success_rate,
                "refresh_success_count": synced,
                "refresh_success_rate": refresh_success_rate,
                "summary": (
                    f"{trade_date.isoformat()} sync health: available={available_count}/{len(codes)}, "
                    f"refreshed={synced}/{len(codes)}, missing={len(missing_codes)}, errors={len(errors)}"
                ),
            },
        }

    @classmethod
    def _build_fetch_error_record(cls, code: str, detail: str) -> Dict[str, str]:
        return {
            "code": code,
            "reason": "empty_data" if cls._looks_like_data_unavailable(detail) else "fetch_failed",
            "detail": detail,
        }

    @staticmethod
    def _looks_like_data_unavailable(detail: str) -> bool:
        normalized = str(detail or "").strip().lower()
        if not normalized:
            return False
        blocking_markers = [
            "timeout",
            "timed out",
            "connect failed",
            "connection",
            "ssl",
            "proxy",
            "network",
            "503",
            "502",
            "429",
        ]
        if any(marker in normalized for marker in blocking_markers):
            return False
        empty_markers = [
            "未获取到",
            "未找到",
            "no data",
            "not found",
            "empty",
            "查无",
        ]
        return any(marker in normalized for marker in empty_markers)
