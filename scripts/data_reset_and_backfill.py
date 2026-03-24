# -*- coding: utf-8 -*-
"""
数据重置与历史回填脚本

解决的问题：
- stock_daily 中大量股票只有 1-2 行数据（增量 sync 遗留）
- STOCK_LIST 股票只有 ~45 行，远不够 MA100/趋势线/形态策略所需的 200+
- 需要全面重置并回填足够的历史数据

工作流程：
1. 备份旧数据库
2. 清空 stock_daily 表
3. 回填 STOCK_LIST + 指数的 300 天历史
4. 批量回填筛选宇宙（Pytdx 为主，无限速）

使用方法：
  python scripts/data_reset_and_backfill.py --reset --backfill-watchlist
  python scripts/data_reset_and_backfill.py --backfill-universe --batch-size 50
  python scripts/data_reset_and_backfill.py --reset --backfill-watchlist --backfill-universe
"""

import argparse
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_db_path() -> str:
    from src.config import get_config
    config = get_config()
    return getattr(config, "database_path", "./data/stock_analysis.db")


def backup_database(db_path: str) -> str:
    if not os.path.exists(db_path):
        logger.warning(f"数据库文件不存在: {db_path}")
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{ts}"
    shutil.copy2(db_path, backup_path)
    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    logger.info(f"数据库已备份: {backup_path} ({size_mb:.2f} MB)")
    return backup_path


def reset_stock_daily():
    """清空 stock_daily 表，保留其他表。"""
    import sqlite3
    db_path = get_db_path()

    backup_database(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stock_daily")
    before = cur.fetchone()[0]
    cur.execute("DELETE FROM stock_daily")
    conn.commit()
    cur.execute("VACUUM")
    conn.commit()
    conn.close()

    logger.info(f"已清空 stock_daily 表: 删除 {before} 行")


def get_stock_list() -> list:
    from src.config import get_config
    config = get_config()
    return list(config.stock_list)


def get_indices() -> list:
    return ["sh000001", "sh000300", "sh000905"]


def backfill_watchlist(days: int = 350):
    """回填 STOCK_LIST + 主要指数的历史数据。"""
    from data_provider.base import DataFetcherManager
    from src.storage import DatabaseManager

    stocks = get_stock_list()
    indices = get_indices()
    targets = stocks + indices

    logger.info(f"开始回填自选股+指数: {targets}, 天数={days}")

    fm = DataFetcherManager()
    db = DatabaseManager.get_instance()

    success = 0
    failed = []

    for code in targets:
        try:
            logger.info(f"[下载] {code} ...")
            df, source = fm.get_daily_data(code, days=days)
            if df is not None and not df.empty:
                saved = db.save_daily_data(df, code, data_source=source)
                logger.info(f"  -> {code}: {len(df)} 行获取, {saved} 行保存, 来源={source}")
                success += 1
            else:
                logger.warning(f"  -> {code}: 无数据返回")
                failed.append(code)
        except Exception as e:
            logger.error(f"  -> {code}: 失败 - {e}")
            failed.append(code)

    logger.info(f"自选股回填完成: 成功={success}, 失败={len(failed)}")
    if failed:
        logger.warning(f"失败列表: {failed}")


def backfill_universe(days: int = 300, batch_size: int = 50, max_stocks: int = 0):
    """
    批量回填筛选宇宙的历史数据。

    优先使用 Pytdx（无限速），回退到其他数据源。
    """
    from data_provider.base import DataFetcherManager, DataFetchError
    from src.storage import DatabaseManager

    db = DatabaseManager.get_instance()
    fm = DataFetcherManager()

    instruments = db.list_instruments(market="cn", listing_status="active", exclude_st=True)
    if not instruments:
        logger.warning("instrument_master 为空，需要先同步股票池主数据")
        logger.info("尝试通过 akshare 获取 A 股列表...")
        instruments = _fetch_instrument_list_from_akshare(db)

    if not instruments:
        logger.error("无法获取股票池列表，退出")
        return

    all_codes = [item["code"] for item in instruments]
    if max_stocks > 0:
        all_codes = all_codes[:max_stocks]

    logger.info(f"筛选宇宙共 {len(all_codes)} 只股票，每批 {batch_size}，天数={days}")

    existing_counts = _get_existing_row_counts(db)

    needs_backfill = []
    for code in all_codes:
        if existing_counts.get(code, 0) < 150:
            needs_backfill.append(code)

    logger.info(f"需要回填的股票: {len(needs_backfill)} (已有 150+ 行的跳过: {len(all_codes) - len(needs_backfill)})")

    total = len(needs_backfill)
    success = 0
    failed = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = needs_backfill[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info(f"--- 批次 {batch_num}/{total_batches} ({len(batch)} 只) ---")

        for code in batch:
            try:
                df, source = fm.get_daily_data(code, days=days)
                if df is not None and not df.empty:
                    saved = db.save_daily_data(df, code, data_source=source)
                    success += 1
                    if success % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = success / elapsed * 60 if elapsed > 0 else 0
                        logger.info(
                            f"进度: {success}/{total} 成功, {failed} 失败, "
                            f"速率={rate:.0f} 只/分钟, "
                            f"已用时={elapsed:.0f}s"
                        )
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                if failed <= 10:
                    logger.warning(f"  {code}: {e}")

        if i + batch_size < total:
            time.sleep(0.5)

    elapsed = time.time() - start_time
    logger.info(
        f"宇宙回填完成: 成功={success}, 失败={failed}, "
        f"总耗时={elapsed:.0f}s ({elapsed/60:.1f}分钟)"
    )


def _get_existing_row_counts(db) -> dict:
    """查询每只股票在 stock_daily 中的行数。"""
    import sqlite3
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT code, COUNT(*) FROM stock_daily GROUP BY code")
    counts = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return counts


def _fetch_instrument_list_from_akshare(db) -> list:
    """从 akshare 获取 A 股列表并写入 instrument_master。"""
    try:
        import akshare as ak
        logger.info("从东方财富获取 A 股列表...")
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return []

        instruments = []
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            name = str(row.get("名称", "")).strip()
            if code and len(code) == 6:
                instruments.append({"code": code, "name": name})

        if instruments:
            saved = db.sync_instruments(instruments)
            logger.info(f"已同步 {saved} 只股票到 instrument_master")

        return instruments
    except Exception as e:
        logger.error(f"akshare 获取 A 股列表失败: {e}")
        return []


def verify_data():
    """验证数据完整性。"""
    import sqlite3
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM stock_daily")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT code) FROM stock_daily")
    distinct = cur.fetchone()[0]

    cur.execute(
        "SELECT code, COUNT(*) as cnt FROM stock_daily "
        "GROUP BY code HAVING cnt >= 200 ORDER BY cnt DESC"
    )
    good = cur.fetchall()

    cur.execute(
        "SELECT code, COUNT(*) as cnt FROM stock_daily "
        "GROUP BY code HAVING cnt >= 100 AND cnt < 200"
    )
    ok = cur.fetchall()

    cur.execute(
        "SELECT code, COUNT(*) as cnt FROM stock_daily "
        "GROUP BY code HAVING cnt < 100"
    )
    insufficient = cur.fetchall()

    cur.execute("SELECT MIN(date), MAX(date) FROM stock_daily")
    date_range = cur.fetchone()

    conn.close()

    logger.info("=== 数据验证报告 ===")
    logger.info(f"总行数: {total}")
    logger.info(f"独立股票数: {distinct}")
    logger.info(f"日期范围: {date_range[0]} ~ {date_range[1]}")
    logger.info(f"200+ 行（满足 MA100）: {len(good)} 只")
    logger.info(f"100-199 行（部分可用）: {len(ok)} 只")
    logger.info(f"< 100 行（数据不足）: {len(insufficient)} 只")

    stock_list = get_stock_list()
    for code in stock_list:
        cur2 = sqlite3.connect(db_path).cursor()
        cur2.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM stock_daily WHERE code=?",
            (code,),
        )
        r = cur2.fetchone()
        status = "✓" if r[2] >= 200 else "✗"
        logger.info(f"  {status} {code}: {r[0]} ~ {r[1]}, rows={r[2]}")

    return len(good), len(ok), len(insufficient)


def main():
    parser = argparse.ArgumentParser(description="数据重置与历史回填")
    parser.add_argument("--reset", action="store_true", help="清空 stock_daily 表")
    parser.add_argument("--backfill-watchlist", action="store_true", help="回填自选股+指数")
    parser.add_argument("--backfill-universe", action="store_true", help="回填筛选宇宙")
    parser.add_argument("--days", type=int, default=350, help="回填天数（日历日，默认 350）")
    parser.add_argument("--batch-size", type=int, default=50, help="宇宙回填每批数量")
    parser.add_argument("--max-stocks", type=int, default=0, help="宇宙回填最大数量（0=全部）")
    parser.add_argument("--verify", action="store_true", help="仅验证数据")

    args = parser.parse_args()

    if args.verify:
        verify_data()
        return

    if not any([args.reset, args.backfill_watchlist, args.backfill_universe]):
        parser.print_help()
        return

    if args.reset:
        logger.info("=" * 50)
        logger.info("Step 1: 数据重置")
        logger.info("=" * 50)
        reset_stock_daily()

    if args.backfill_watchlist:
        logger.info("=" * 50)
        logger.info("Step 2: 回填自选股 + 指数")
        logger.info("=" * 50)
        backfill_watchlist(days=args.days)

    if args.backfill_universe:
        logger.info("=" * 50)
        logger.info("Step 3: 回填筛选宇宙")
        logger.info("=" * 50)
        backfill_universe(
            days=args.days,
            batch_size=args.batch_size,
            max_stocks=args.max_stocks,
        )

    logger.info("=" * 50)
    logger.info("数据验证")
    logger.info("=" * 50)
    verify_data()


if __name__ == "__main__":
    main()
