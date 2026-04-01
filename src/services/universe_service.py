from __future__ import annotations

from datetime import date
from typing import List, Optional

import pandas as pd

from data_provider.base import DataFetcherManager
from src.services.board_sync_service import BoardSyncService
from src.storage import DatabaseManager


class LocalUniverseNotReadyError(RuntimeError):
    """Raised when local instrument_master is unavailable for screening."""


class UniverseService:
    """解析本次筛选应使用的股票池。"""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        fetcher_manager: Optional[DataFetcherManager] = None,
        board_sync_service: Optional[BoardSyncService] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self.fetcher_manager = fetcher_manager
        self.board_sync_service = board_sync_service or BoardSyncService(db_manager=self.db)

    def resolve_universe(self, stock_codes: Optional[List[str]] = None) -> pd.DataFrame:
        requested_codes = [str(item).strip().upper() for item in (stock_codes or []) if str(item).strip()]

        if requested_codes:
            code_set = set(requested_codes)
            local_rows = self.db.list_instruments(codes=list(code_set))
            filtered = pd.DataFrame(local_rows) if local_rows else pd.DataFrame(columns=["code", "name", "list_date"])

            found_codes = set(filtered["code"].tolist()) if not filtered.empty else set()
            missing_codes = [code for code in requested_codes if code not in found_codes]
            if missing_codes:
                fallback_rows = pd.DataFrame(
                    [
                        {"code": code, "name": code, "list_date": None}
                        for code in missing_codes
                    ]
                )
                filtered = pd.concat([filtered, fallback_rows], ignore_index=True)
            return self._normalize_universe(filtered)

        local_universe = self.db.list_instruments(market="cn", listing_status="active", exclude_st=True)
        if local_universe:
            return self._normalize_universe(pd.DataFrame(local_universe))

        raise LocalUniverseNotReadyError("本地 instrument_master 为空，请先执行 universe 同步")

    def sync_universe(self, market: str = "cn") -> dict:
        """从远端数据源同步股票池主数据到 instrument_master。"""
        stock_list_df = self._fetch_stock_list()
        if stock_list_df is None or stock_list_df.empty:
            error_suffix = f": {'; '.join(self._last_fetch_errors)}" if self._last_fetch_errors else ""
            raise RuntimeError(f"未能从任何数据源获取股票池主数据{error_suffix}")

        instruments = self._build_instrument_rows(stock_list_df, market=market)
        incoming_codes = sorted(
            {
                str(item.get("code", "")).strip().upper()
                for item in instruments
                if str(item.get("code", "")).strip()
            }
        )
        existing_rows = self.db.list_instruments(codes=incoming_codes) if incoming_codes else []
        existing_codes = {
            str(item.get("code", "")).strip().upper()
            for item in existing_rows
            if str(item.get("code", "")).strip()
        }
        new_codes = [code for code in incoming_codes if code not in existing_codes]

        saved_count = self.db.upsert_instruments(instruments)
        board_sync_result = None
        if new_codes:
            board_sync_result = self.board_sync_service.sync_codes(new_codes, market=market, source="efinance")
        return {
            "saved_count": saved_count,
            "source": self._last_source_name,
            "market": market,
            "new_count": len(new_codes),
            "new_codes": new_codes,
            "board_sync_result": board_sync_result,
        }

    def _fetch_stock_list(self) -> Optional[pd.DataFrame]:
        manager = self.fetcher_manager or DataFetcherManager()
        self._last_source_name = None
        self._last_fetch_errors: List[str] = []
        for fetcher in getattr(manager, "_fetchers", []):
            if not hasattr(fetcher, "get_stock_list"):
                continue
            fetcher_name = fetcher.__class__.__name__
            try:
                df = fetcher.get_stock_list()
            except Exception as exc:
                self._last_fetch_errors.append(f"{fetcher_name}: {exc}")
                continue
            if df is not None and not df.empty:
                try:
                    normalized = self._normalize_universe(df)
                except Exception as exc:
                    self._last_fetch_errors.append(f"{fetcher_name}: {exc}")
                    continue
                if normalized.empty:
                    self._last_fetch_errors.append(f"{fetcher_name}: empty_normalized_result")
                    continue
                self._last_source_name = fetcher_name
                return normalized
        return None

    @staticmethod
    def _build_instrument_rows(df: pd.DataFrame, market: str = "cn") -> List[dict]:
        normalized = UniverseService._normalize_universe(df)
        instruments: List[dict] = []
        for row in normalized.to_dict("records"):
            code = row["code"]
            instruments.append(
                {
                    "code": code,
                    "name": row["name"],
                    "market": market,
                    "exchange": UniverseService._infer_exchange(code),
                    "listing_status": "active",
                    "is_st": row["is_st"],
                    "industry": row.get("industry"),
                    "list_date": UniverseService._parse_list_date(row.get("list_date")),
                }
            )
        return instruments

    @staticmethod
    def _normalize_universe(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", "name", "is_st", "list_date", "industry", "listing_status"])

        normalized = df.copy()
        normalized = normalized.dropna(subset=["code"])
        normalized["code"] = normalized["code"].astype(str).str.strip().str.upper()
        normalized = normalized[~normalized["code"].isin({"", "NONE", "NAN", "NULL"})]
        if normalized.empty:
            return pd.DataFrame(columns=["code", "name", "is_st", "list_date", "industry"])
        normalized["name"] = normalized.get("name", normalized["code"]).fillna(normalized["code"]).astype(str)
        normalized["list_date"] = normalized.get("list_date")
        normalized["industry"] = normalized.get("industry")
        normalized["listing_status"] = normalized.get("listing_status", "active")
        normalized["is_st"] = normalized["name"].str.upper().str.contains("ST", regex=False)
        normalized = normalized.drop_duplicates(subset=["code"], keep="first")
        return normalized[["code", "name", "is_st", "list_date", "industry", "listing_status"]].reset_index(drop=True)

    @staticmethod
    def _infer_exchange(code: str) -> str:
        if code.startswith(("600", "601", "603", "605")):
            return "SSE"
        if code.startswith(("000", "001", "002", "003", "300")):
            return "SZSE"
        if code.startswith(("430", "83", "87", "92")):
            return "BSE"
        return "CN"

    @staticmethod
    def _parse_list_date(value: object) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if pd.isna(value):
            return None
        try:
            parsed = pd.to_datetime(value, errors="coerce")
        except Exception:
            return None
        if pd.isna(parsed):
            return None
        return parsed.date()
