-- fix_none_setup_type.sql
-- 修复历史数据中 setup_type = 'none' 字符串应为 NULL 的问题
--
-- 根因: CandidateDecision.to_payload() 将 SetupType.NONE 枚举序列化为
-- 字符串 "none" 写入 DB，导致回测聚合器把它当作合法策略组。
-- 代码修复: src/schemas/trading_types.py to_payload() 已将 "none" 转为 NULL。
-- 本脚本清理已有数据。
--
-- 使用方法:
--   sqlite3 <your-db-path> < scripts/fix_none_setup_type.sql
-- 或在 Python 中:
--   with db.get_session() as session:
--       session.execute(text("UPDATE screening_candidates SET setup_type = NULL WHERE setup_type = 'none'"))
--       session.commit()

-- 1. 清理筛选候选表
UPDATE screening_candidates
SET    setup_type = NULL
WHERE  setup_type = 'none';

-- 2. 清理回测评估表 (snapshot 和 replayed 都可能受影响)
UPDATE five_layer_backtest_evaluations
SET    snapshot_setup_type = NULL
WHERE  snapshot_setup_type = 'none';

UPDATE five_layer_backtest_evaluations
SET    replayed_setup_type = NULL
WHERE  replayed_setup_type = 'none';

-- 3. 清理回测汇总表中 group_type='setup_type' 且 group_key='none' 的行
-- 这些汇总行基于错误数据生成，应该删除。下次重新运行回测会重新生成。
DELETE FROM five_layer_backtest_group_summaries
WHERE  group_type = 'setup_type'
AND    group_key = 'none';
