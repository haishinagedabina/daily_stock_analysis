# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 存储层
===================================

职责：
1. 管理 SQLite 数据库连接（单例模式）
2. 定义 ORM 数据模型
3. 提供数据存取接口
4. 实现智能更新逻辑（断点续传）
"""

import atexit
from contextlib import contextmanager
import hashlib
import json
import logging
import re
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Tuple

import pandas as pd
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
    select,
    and_,
    delete,
    desc,
    event,
    update,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError

from src.config import get_config

logger = logging.getLogger(__name__)

# SQLAlchemy ORM 基类
Base = declarative_base()

if TYPE_CHECKING:
    from src.search_service import SearchResponse


# === 数据模型定义 ===

class StockDaily(Base):
    """
    股票日线数据模型
    
    存储每日行情数据和计算的技术指标
    支持多股票、多日期的唯一约束
    """
    __tablename__ = 'stock_daily'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 股票代码（如 600519, 000001）
    code = Column(String(10), nullable=False, index=True)
    
    # 交易日期
    date = Column(Date, nullable=False, index=True)
    
    # OHLC 数据
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    
    # 成交数据
    volume = Column(Float)  # 成交量（股）
    amount = Column(Float)  # 成交额（元）
    pct_chg = Column(Float)  # 涨跌幅（%）
    
    # 技术指标
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    volume_ratio = Column(Float)  # 量比
    
    # 数据来源
    data_source = Column(String(50))  # 记录数据来源（如 AkshareFetcher）
    
    # 更新时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 唯一约束：同一股票同一日期只能有一条数据
    __table_args__ = (
        UniqueConstraint('code', 'date', name='uix_code_date'),
        Index('ix_code_date', 'code', 'date'),
    )
    
    def __repr__(self):
        return f"<StockDaily(code={self.code}, date={self.date}, close={self.close})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'date': self.date,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
            'pct_chg': self.pct_chg,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'volume_ratio': self.volume_ratio,
            'data_source': self.data_source,
        }


class NewsIntel(Base):
    """
    新闻情报数据模型

    存储搜索到的新闻情报条目，用于后续分析与查询
    """
    __tablename__ = 'news_intel'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联用户查询操作
    query_id = Column(String(64), index=True)

    # 股票信息
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))

    # 搜索上下文
    dimension = Column(String(32), index=True)  # latest_news / risk_check / earnings / market_analysis / industry
    query = Column(String(255))
    provider = Column(String(32), index=True)

    # 新闻内容
    title = Column(String(300), nullable=False)
    snippet = Column(Text)
    url = Column(String(1000), nullable=False)
    source = Column(String(100))
    published_date = Column(DateTime, index=True)

    # 入库时间
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    query_source = Column(String(32), index=True)  # bot/web/cli/system
    requester_platform = Column(String(20))
    requester_user_id = Column(String(64))
    requester_user_name = Column(String(64))
    requester_chat_id = Column(String(64))
    requester_message_id = Column(String(64))
    requester_query = Column(String(255))

    __table_args__ = (
        UniqueConstraint('url', name='uix_news_url'),
        Index('ix_news_code_pub', 'code', 'published_date'),
    )

    def __repr__(self) -> str:
        return f"<NewsIntel(code={self.code}, title={self.title[:20]}...)>"


class AnalysisHistory(Base):
    """
    分析结果历史记录模型

    保存每次分析结果，支持按 query_id/股票代码检索
    """
    __tablename__ = 'analysis_history'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联查询链路
    query_id = Column(String(64), index=True)

    # 股票信息
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))
    report_type = Column(String(16), index=True)

    # 核心结论
    sentiment_score = Column(Integer)
    operation_advice = Column(String(20))
    trend_prediction = Column(String(50))
    analysis_summary = Column(Text)

    # 详细数据
    raw_result = Column(Text)
    news_content = Column(Text)
    context_snapshot = Column(Text)

    # 狙击点位（用于回测）
    ideal_buy = Column(Float)
    secondary_buy = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)

    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_analysis_code_time', 'code', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'code': self.code,
            'name': self.name,
            'report_type': self.report_type,
            'sentiment_score': self.sentiment_score,
            'operation_advice': self.operation_advice,
            'trend_prediction': self.trend_prediction,
            'analysis_summary': self.analysis_summary,
            'raw_result': self.raw_result,
            'news_content': self.news_content,
            'context_snapshot': self.context_snapshot,
            'ideal_buy': self.ideal_buy,
            'secondary_buy': self.secondary_buy,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BacktestResult(Base):
    """单条分析记录的回测结果。"""

    __tablename__ = 'backtest_results'

    id = Column(Integer, primary_key=True, autoincrement=True)

    analysis_history_id = Column(
        Integer,
        ForeignKey('analysis_history.id'),
        nullable=False,
        index=True,
    )

    # 冗余字段，便于按股票筛选
    code = Column(String(10), nullable=False, index=True)
    analysis_date = Column(Date, index=True)

    # 回测参数
    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')

    # 状态
    eval_status = Column(String(16), nullable=False, default='pending')
    evaluated_at = Column(DateTime, default=datetime.now, index=True)

    # 建议快照（避免未来分析字段变化导致回测不可解释）
    operation_advice = Column(String(20))
    position_recommendation = Column(String(8))  # long/cash

    # 价格与收益
    start_price = Column(Float)
    end_close = Column(Float)
    max_high = Column(Float)
    min_low = Column(Float)
    stock_return_pct = Column(Float)

    # 方向与结果
    direction_expected = Column(String(16))  # up/down/flat/not_down
    direction_correct = Column(Boolean, nullable=True)
    outcome = Column(String(16))  # win/loss/neutral

    # 目标价命中（仅 long 且配置了止盈/止损时有意义）
    stop_loss = Column(Float)
    take_profit = Column(Float)
    hit_stop_loss = Column(Boolean)
    hit_take_profit = Column(Boolean)
    first_hit = Column(String(16))  # take_profit/stop_loss/ambiguous/neither/not_applicable
    first_hit_date = Column(Date)
    first_hit_trading_days = Column(Integer)

    # 模拟执行（long-only）
    simulated_entry_price = Column(Float)
    simulated_exit_price = Column(Float)
    simulated_exit_reason = Column(String(24))  # stop_loss/take_profit/window_end/cash/ambiguous_stop_loss
    simulated_return_pct = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            'analysis_history_id',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_analysis_window_version',
        ),
        Index('ix_backtest_code_date', 'code', 'analysis_date'),
    )


class BacktestSummary(Base):
    """回测汇总指标（按股票或全局）。"""

    __tablename__ = 'backtest_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)

    scope = Column(String(16), nullable=False, index=True)  # overall/stock
    code = Column(String(16), index=True)

    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')
    computed_at = Column(DateTime, default=datetime.now, index=True)

    # 计数
    total_evaluations = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    insufficient_count = Column(Integer, default=0)
    long_count = Column(Integer, default=0)
    cash_count = Column(Integer, default=0)

    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)

    # 准确率/胜率
    direction_accuracy_pct = Column(Float)
    win_rate_pct = Column(Float)
    neutral_rate_pct = Column(Float)

    # 收益
    avg_stock_return_pct = Column(Float)
    avg_simulated_return_pct = Column(Float)

    # 目标价触发统计（仅 long 且配置止盈/止损时统计）
    stop_loss_trigger_rate = Column(Float)
    take_profit_trigger_rate = Column(Float)
    ambiguous_rate = Column(Float)
    avg_days_to_first_hit = Column(Float)

    # 诊断字段（JSON 字符串）
    advice_breakdown_json = Column(Text)
    diagnostics_json = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            'scope',
            'code',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_summary_scope_code_window_version',
        ),
    )


class ConversationMessage(Base):
    """
    Agent 对话历史记录表
    """
    __tablename__ = 'conversation_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)


class InstrumentMaster(Base):
    """正式股票池主数据。"""

    __tablename__ = "instrument_master"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    market = Column(String(16), nullable=False, default="cn", index=True)
    exchange = Column(String(16), nullable=True, index=True)
    listing_status = Column(String(16), nullable=False, default="active", index=True)
    is_st = Column(Boolean, nullable=False, default=False, index=True)
    industry = Column(String(64))
    list_date = Column(Date, nullable=True, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "exchange": self.exchange,
            "listing_status": self.listing_status,
            "is_st": self.is_st,
            "industry": self.industry,
            "list_date": self.list_date.isoformat() if self.list_date else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DailyFactorSnapshot(Base):
    """日度因子快照。"""

    __tablename__ = "daily_factor_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)
    code = Column(String(16), nullable=False, index=True)
    close = Column(Float)
    pct_chg = Column(Float)
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    ma60 = Column(Float)
    volume_ratio = Column(Float)
    turnover_rate = Column(Float)
    trend_score = Column(Float)
    liquidity_score = Column(Float)
    risk_flags_json = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("trade_date", "code", name="uix_factor_snapshot_trade_code"),
        Index("ix_factor_snapshot_trade_code", "trade_date", "code"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "code": self.code,
            "close": self.close,
            "pct_chg": self.pct_chg,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "ma60": self.ma60,
            "volume_ratio": self.volume_ratio,
            "turnover_rate": self.turnover_rate,
            "trend_score": self.trend_score,
            "liquidity_score": self.liquidity_score,
            "risk_flags": json.loads(self.risk_flags_json) if self.risk_flags_json else [],
        }


class ScreeningRun(Base):
    """全市场筛选任务记录。"""

    __tablename__ = "screening_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    market = Column(String(16), nullable=False, default="cn", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    universe_size = Column(Integer, nullable=False, default=0)
    candidate_count = Column(Integer, nullable=False, default=0)
    ai_top_k = Column(Integer, nullable=False, default=0)
    config_snapshot = Column(Text)
    error_summary = Column(Text)
    started_at = Column(DateTime, default=datetime.now, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    # -- Notification lifecycle fields --
    trigger_type = Column(String(32), nullable=False, default="manual")
    notification_status = Column(String(32), nullable=True)
    notification_attempts = Column(Integer, nullable=False, default=0)
    notification_sent_at = Column(DateTime, nullable=True)
    notification_error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_screening_run_trade_market", "trade_date", "market"),
    )

    def to_dict(self) -> Dict[str, Any]:
        snapshot = json.loads(self.config_snapshot) if self.config_snapshot else {}
        return {
            "run_id": self.run_id,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "market": self.market,
            "mode": snapshot.get("mode", "balanced"),
            "status": self.status,
            "universe_size": self.universe_size,
            "candidate_count": self.candidate_count,
            "ai_top_k": self.ai_top_k,
            "config_snapshot": snapshot,
            "error_summary": self.error_summary,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "trigger_type": self.trigger_type or "manual",
            "notification_status": self.notification_status,
            "notification_attempts": self.notification_attempts or 0,
            "notification_sent_at": self.notification_sent_at.isoformat() if self.notification_sent_at else None,
            "notification_error": self.notification_error,
        }


class ScreeningCandidate(Base):
    """全市场筛选候选结果。"""

    __tablename__ = "screening_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("screening_runs.run_id"), nullable=False, index=True)
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))
    rank = Column(Integer, nullable=False, index=True)
    rule_score = Column(Float, nullable=False, default=0.0)
    selected_for_ai = Column(Boolean, nullable=False, default=False)
    rule_hits_json = Column(Text)
    factor_snapshot_json = Column(Text)
    ai_query_id = Column(String(64), index=True)
    ai_summary = Column(Text)
    ai_operation_advice = Column(String(20))
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("run_id", "code", name="uix_screening_candidate_run_code"),
        Index("ix_screening_candidate_run_rank", "run_id", "rank"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "code": self.code,
            "name": self.name,
            "rank": self.rank,
            "rule_score": self.rule_score,
            "selected_for_ai": self.selected_for_ai,
            "rule_hits": json.loads(self.rule_hits_json) if self.rule_hits_json else [],
            "factor_snapshot": json.loads(self.factor_snapshot_json) if self.factor_snapshot_json else {},
            "ai_query_id": self.ai_query_id,
            "ai_summary": self.ai_summary,
            "ai_operation_advice": self.ai_operation_advice,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatabaseManager:
    """
    数据库管理器 - 单例模式
    
    职责：
    1. 管理数据库连接池
    2. 提供 Session 上下文管理
    3. 封装数据存取操作
    """
    
    _instance: Optional['DatabaseManager'] = None
    _initialized: bool = False
    _screening_status_transitions = {
        "pending": {
            "pending",
            "resolving_universe",
            "syncing_universe",
            "ingesting",
            "factorizing",
            "screening",
            "ai_enriching",
            "failed",
        },
        "resolving_universe": {"resolving_universe", "syncing_universe", "ingesting", "failed"},
        "syncing_universe": {"syncing_universe", "ingesting", "failed"},
        "ingesting": {"ingesting", "factorizing", "failed"},
        "factorizing": {"factorizing", "screening", "failed"},
        "screening": {"screening", "ai_enriching", "completed", "completed_with_ai_degraded", "failed"},
        "ai_enriching": {"ai_enriching", "completed", "completed_with_ai_degraded", "failed"},
        "completed": {"completed"},
        "completed_with_ai_degraded": {"completed_with_ai_degraded"},
        "failed": {"failed"},
    }
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_url: 数据库连接 URL（可选，默认从配置读取）
        """
        if getattr(self, '_initialized', False):
            return
        
        if db_url is None:
            config = get_config()
            db_url = config.get_db_url()
        
        # 创建数据库引擎
        self._engine = create_engine(
            db_url,
            echo=False,  # 设为 True 可查看 SQL 语句
            pool_pre_ping=True,  # 连接健康检查
        )
        if db_url.startswith("sqlite"):
            @event.listens_for(self._engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-redef]
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        
        # 创建 Session 工厂
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
        )
        
        # Create tables first, then apply lightweight inline schema migrations
        # for backward-compatible upgrades on existing SQLite databases.
        Base.metadata.create_all(self._engine)
        self._apply_inline_migrations()

        self._initialized = True
        logger.info(f"数据库初始化完成: {db_url}")

        # 注册退出钩子，确保程序退出时关闭数据库连接
        atexit.register(DatabaseManager._cleanup_engine, self._engine)
    
    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        if cls._instance is not None:
            if hasattr(cls._instance, '_engine') and cls._instance._engine is not None:
                cls._instance._engine.dispose()
            cls._instance._initialized = False
            cls._instance = None

    @classmethod
    def _cleanup_engine(cls, engine) -> None:
        """
        清理数据库引擎（atexit 钩子）

        确保程序退出时关闭所有数据库连接，避免 ResourceWarning

        Args:
            engine: SQLAlchemy 引擎对象
        """
        try:
            if engine is not None:
                engine.dispose()
                logger.debug("数据库引擎已清理")
        except Exception as e:
            logger.warning(f"清理数据库引擎时出错: {e}")

    def _apply_inline_migrations(self) -> None:
        """Apply lightweight backward-compatible schema migrations.

        This keeps existing SQLite data files usable after adding new columns,
        especially for local/Docker deployments that copy old databases to new
        machines. The migration is intentionally additive-only.
        """
        try:
            dialect = self._engine.dialect.name
            if dialect == "sqlite":
                self._migrate_sqlite_screening_runs_notification_fields()
        except Exception as exc:
            logger.exception("Inline database migration failed: %s", exc)
            raise

    def _migrate_sqlite_screening_runs_notification_fields(self) -> None:
        """Ensure screening_runs has notification-related columns on SQLite."""
        expected_columns = {
            "trigger_type": "ALTER TABLE screening_runs ADD COLUMN trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual'",
            "notification_status": "ALTER TABLE screening_runs ADD COLUMN notification_status VARCHAR(32)",
            "notification_attempts": "ALTER TABLE screening_runs ADD COLUMN notification_attempts INTEGER NOT NULL DEFAULT 0",
            "notification_sent_at": "ALTER TABLE screening_runs ADD COLUMN notification_sent_at DATETIME",
            "notification_error": "ALTER TABLE screening_runs ADD COLUMN notification_error TEXT",
        }

        with self._engine.begin() as conn:
            existing = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(screening_runs)").fetchall()
            }
            missing = [name for name in expected_columns if name not in existing]
            if not missing:
                return

            logger.info(
                "Applying inline SQLite migration for screening_runs, missing columns: %s",
                ", ".join(missing),
            )
            for column_name in missing:
                conn.exec_driver_sql(expected_columns[column_name])

            conn.exec_driver_sql(
                "UPDATE screening_runs "
                "SET trigger_type='manual' "
                "WHERE trigger_type IS NULL OR TRIM(trigger_type)=''"
            )
            conn.exec_driver_sql(
                "UPDATE screening_runs "
                "SET notification_status='pending' "
                "WHERE notification_status IS NULL AND trigger_type='scheduled'"
            )
            conn.exec_driver_sql(
                "UPDATE screening_runs "
                "SET notification_status='skipped' "
                "WHERE notification_status IS NULL AND COALESCE(trigger_type, 'manual')!='scheduled'"
            )
            conn.exec_driver_sql(
                "UPDATE screening_runs "
                "SET notification_attempts=0 "
                "WHERE notification_attempts IS NULL"
            )
            logger.info("Inline SQLite migration for screening_runs completed")
    
    def get_session(self) -> Session:
        """
        获取数据库 Session
        
        使用示例:
            with db.get_session() as session:
                # 执行查询
                session.commit()  # 如果需要
        """
        if not getattr(self, '_initialized', False) or not hasattr(self, '_SessionLocal'):
            raise RuntimeError(
                "DatabaseManager 未正确初始化。"
                "请确保通过 DatabaseManager.get_instance() 获取实例。"
            )
        session = self._SessionLocal()
        try:
            return session
        except Exception:
            session.close()
            raise

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def has_today_data(self, code: str, target_date: Optional[date] = None) -> bool:
        """
        检查是否已有指定日期的数据
        
        用于断点续传逻辑：如果已有数据则跳过网络请求
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            是否存在数据
        """
        if target_date is None:
            target_date = date.today()
        # 注意：这里的 target_date 语义是“自然日”，而不是“最新交易日”。
        # 在周末/节假日/非交易日运行时，即使数据库已有最新交易日数据，这里也会返回 False。
        # 该行为目前保留（按需求不改逻辑）。
        
        with self.get_session() as session:
            result = session.execute(
                select(StockDaily).where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date == target_date
                    )
                )
            ).scalar_one_or_none()
            
            return result is not None
    
    def get_latest_data(
        self, 
        code: str, 
        days: int = 2
    ) -> List[StockDaily]:
        """
        获取最近 N 天的数据
        
        用于计算"相比昨日"的变化
        
        Args:
            code: 股票代码
            days: 获取天数
            
        Returns:
            StockDaily 对象列表（按日期降序）
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(StockDaily.code == code)
                .order_by(desc(StockDaily.date))
                .limit(days)
            ).scalars().all()
            
            return list(results)

    def save_news_intel(
        self,
        code: str,
        name: str,
        dimension: str,
        query: str,
        response: 'SearchResponse',
        query_context: Optional[Dict[str, str]] = None
    ) -> int:
        """
        保存新闻情报到数据库

        去重策略：
        - 优先按 URL 去重（唯一约束）
        - URL 缺失时按 title + source + published_date 进行软去重

        关联策略：
        - query_context 记录用户查询信息（平台、用户、会话、原始指令等）
        """
        if not response or not response.results:
            return 0

        saved_count = 0
        query_ctx = query_context or {}
        current_query_id = (query_ctx.get("query_id") or "").strip()

        with self.get_session() as session:
            try:
                for item in response.results:
                    title = (item.title or '').strip()
                    url = (item.url or '').strip()
                    source = (item.source or '').strip()
                    snippet = (item.snippet or '').strip()
                    published_date = self._parse_published_date(item.published_date)

                    if not title and not url:
                        continue

                    url_key = url or self._build_fallback_url_key(
                        code=code,
                        title=title,
                        source=source,
                        published_date=published_date
                    )

                    # 优先按 URL 或兜底键去重
                    existing = session.execute(
                        select(NewsIntel).where(NewsIntel.url == url_key)
                    ).scalar_one_or_none()

                    if existing:
                        existing.name = name or existing.name
                        existing.dimension = dimension or existing.dimension
                        existing.query = query or existing.query
                        existing.provider = response.provider or existing.provider
                        existing.snippet = snippet or existing.snippet
                        existing.source = source or existing.source
                        existing.published_date = published_date or existing.published_date
                        existing.fetched_at = datetime.now()

                        if query_context:
                            # Keep the first query_id to avoid overwriting historical links.
                            if not existing.query_id and current_query_id:
                                existing.query_id = current_query_id
                            existing.query_source = (
                                query_context.get("query_source") or existing.query_source
                            )
                            existing.requester_platform = (
                                query_context.get("requester_platform") or existing.requester_platform
                            )
                            existing.requester_user_id = (
                                query_context.get("requester_user_id") or existing.requester_user_id
                            )
                            existing.requester_user_name = (
                                query_context.get("requester_user_name") or existing.requester_user_name
                            )
                            existing.requester_chat_id = (
                                query_context.get("requester_chat_id") or existing.requester_chat_id
                            )
                            existing.requester_message_id = (
                                query_context.get("requester_message_id") or existing.requester_message_id
                            )
                            existing.requester_query = (
                                query_context.get("requester_query") or existing.requester_query
                            )
                    else:
                        try:
                            with session.begin_nested():
                                record = NewsIntel(
                                    code=code,
                                    name=name,
                                    dimension=dimension,
                                    query=query,
                                    provider=response.provider,
                                    title=title,
                                    snippet=snippet,
                                    url=url_key,
                                    source=source,
                                    published_date=published_date,
                                    fetched_at=datetime.now(),
                                    query_id=current_query_id or None,
                                    query_source=query_ctx.get("query_source"),
                                    requester_platform=query_ctx.get("requester_platform"),
                                    requester_user_id=query_ctx.get("requester_user_id"),
                                    requester_user_name=query_ctx.get("requester_user_name"),
                                    requester_chat_id=query_ctx.get("requester_chat_id"),
                                    requester_message_id=query_ctx.get("requester_message_id"),
                                    requester_query=query_ctx.get("requester_query"),
                                )
                                session.add(record)
                                session.flush()
                            saved_count += 1
                        except IntegrityError:
                            # 单条 URL 唯一约束冲突（如并发插入），仅跳过本条，保留本批其余成功项
                            logger.debug("新闻情报重复（已跳过）: %s %s", code, url_key)

                session.commit()
                logger.info(f"保存新闻情报成功: {code}, 新增 {saved_count} 条")

            except Exception as e:
                session.rollback()
                logger.error(f"保存新闻情报失败: {e}")
                raise

        return saved_count

    def get_recent_news(self, code: str, days: int = 7, limit: int = 20) -> List[NewsIntel]:
        """
        获取指定股票最近 N 天的新闻情报
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(
                    and_(
                        NewsIntel.code == code,
                        NewsIntel.fetched_at >= cutoff_date
                    )
                )
                .order_by(desc(NewsIntel.fetched_at))
                .limit(limit)
            ).scalars().all()

            return list(results)

    def get_news_intel_by_query_id(self, query_id: str, limit: int = 20) -> List[NewsIntel]:
        """
        根据 query_id 获取新闻情报列表

        Args:
            query_id: 分析记录唯一标识
            limit: 返回数量限制

        Returns:
            NewsIntel 列表（按发布时间或抓取时间倒序）
        """
        from sqlalchemy import func

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(NewsIntel.query_id == query_id)
                .order_by(
                    desc(func.coalesce(NewsIntel.published_date, NewsIntel.fetched_at)),
                    desc(NewsIntel.fetched_at)
                )
                .limit(limit)
            ).scalars().all()

            return list(results)

    def save_analysis_history(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str],
        context_snapshot: Optional[Dict[str, Any]] = None,
        save_snapshot: bool = True
    ) -> int:
        """
        保存分析结果历史记录
        """
        if result is None:
            return 0

        sniper_points = self._extract_sniper_points(result)
        raw_result = self._build_raw_result(result)
        context_text = None
        if save_snapshot and context_snapshot is not None:
            context_text = self._safe_json_dumps(context_snapshot)

        record = AnalysisHistory(
            query_id=query_id,
            code=result.code,
            name=result.name,
            report_type=report_type,
            sentiment_score=result.sentiment_score,
            operation_advice=result.operation_advice,
            trend_prediction=result.trend_prediction,
            analysis_summary=result.analysis_summary,
            raw_result=self._safe_json_dumps(raw_result),
            news_content=news_content,
            context_snapshot=context_text,
            ideal_buy=sniper_points.get("ideal_buy"),
            secondary_buy=sniper_points.get("secondary_buy"),
            stop_loss=sniper_points.get("stop_loss"),
            take_profit=sniper_points.get("take_profit"),
            created_at=datetime.now(),
        )

        with self.get_session() as session:
            try:
                session.add(record)
                session.commit()
                return 1
            except Exception as e:
                session.rollback()
                logger.error(f"保存分析历史失败: {e}")
                return 0

    def get_analysis_history(
        self,
        code: Optional[str] = None,
        query_id: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[AnalysisHistory]:
        """
        Query analysis history records.

        Notes:
        - If query_id is provided, perform exact lookup and ignore days window.
        - If query_id is not provided, apply days-based time filtering.
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            conditions = []

            if query_id:
                conditions.append(AnalysisHistory.query_id == query_id)
            else:
                conditions.append(AnalysisHistory.created_at >= cutoff_date)

            if code:
                conditions.append(AnalysisHistory.code == code)

            results = session.execute(
                select(AnalysisHistory)
                .where(and_(*conditions))
                .order_by(desc(AnalysisHistory.created_at))
                .limit(limit)
            ).scalars().all()

            return list(results)
    
    def get_analysis_history_paginated(
        self,
        code: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Tuple[List[AnalysisHistory], int]:
        """
        分页查询分析历史记录（带总数）
        
        Args:
            code: 股票代码筛选
            start_date: 开始日期（含）
            end_date: 结束日期（含）
            offset: 偏移量（跳过前 N 条）
            limit: 每页数量
            
        Returns:
            Tuple[List[AnalysisHistory], int]: (记录列表, 总数)
        """
        from sqlalchemy import func
        
        with self.get_session() as session:
            conditions = []
            
            if code:
                conditions.append(AnalysisHistory.code == code)
            if start_date:
                # created_at >= start_date 00:00:00
                conditions.append(AnalysisHistory.created_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                # created_at < end_date+1 00:00:00 (即 <= end_date 23:59:59)
                conditions.append(AnalysisHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
            
            # 构建 where 子句
            where_clause = and_(*conditions) if conditions else True
            
            # 查询总数
            total_query = select(func.count(AnalysisHistory.id)).where(where_clause)
            total = session.execute(total_query).scalar() or 0
            
            # 查询分页数据
            data_query = (
                select(AnalysisHistory)
                .where(where_clause)
                .order_by(desc(AnalysisHistory.created_at))
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(data_query).scalars().all()
            
            return list(results), total
    
    def get_analysis_history_by_id(self, record_id: int) -> Optional[AnalysisHistory]:
        """
        根据数据库主键 ID 查询单条分析历史记录
        
        由于 query_id 可能重复（批量分析时多条记录共享同一 query_id），
        使用主键 ID 确保精确查询唯一记录。
        
        Args:
            record_id: 分析历史记录的主键 ID
            
        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            result = session.execute(
                select(AnalysisHistory).where(AnalysisHistory.id == record_id)
            ).scalars().first()
            return result

    def upsert_instruments(self, instruments: List[Dict[str, Any]]) -> int:
        """批量写入或更新股票池主数据。"""
        if not instruments:
            return 0

        with self.session_scope() as session:
            normalized_items = []
            for item in instruments:
                code = str(item["code"]).strip().upper()
                normalized_items.append((code, item))

            existing_codes = [code for code, _ in normalized_items]
            existing_records = session.execute(
                select(InstrumentMaster).where(InstrumentMaster.code.in_(existing_codes))
            ).scalars().all()
            record_map = {record.code: record for record in existing_records}

            for code, item in normalized_items:
                record = record_map.get(code)
                if record is None:
                    record = InstrumentMaster(code=code)
                    session.add(record)
                    record_map[code] = record

                record.name = item.get("name") or code
                record.market = item.get("market") or "cn"
                record.exchange = item.get("exchange")
                record.listing_status = item.get("listing_status") or "active"
                record.is_st = bool(item.get("is_st", False))
                record.industry = item.get("industry")
                record.list_date = item.get("list_date")
                record.updated_at = datetime.now()

        return len(instruments)

    def get_instrument(self, code: str) -> Optional[Dict[str, Any]]:
        """根据代码查询单个股票池主数据。"""
        with self.get_session() as session:
            record = session.execute(
                select(InstrumentMaster).where(InstrumentMaster.code == str(code).strip().upper())
            ).scalar_one_or_none()
            return record.to_dict() if record else None

    def list_instruments(
        self,
        market: Optional[str] = None,
        listing_status: Optional[str] = None,
        exclude_st: bool = False,
        codes: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """查询股票池主数据列表。"""
        with self.get_session() as session:
            stmt = select(InstrumentMaster).order_by(InstrumentMaster.code)
            if market:
                stmt = stmt.where(InstrumentMaster.market == market)
            if listing_status:
                stmt = stmt.where(InstrumentMaster.listing_status == listing_status)
            if exclude_st:
                stmt = stmt.where(InstrumentMaster.is_st.is_(False))
            if codes:
                normalized_codes = [str(code).strip().upper() for code in codes if str(code).strip()]
                stmt = stmt.where(InstrumentMaster.code.in_(normalized_codes))
            if limit is not None:
                stmt = stmt.limit(limit)

            rows = session.execute(stmt).scalars().all()
            return [row.to_dict() for row in rows]

    def replace_factor_snapshots(self, trade_date: date, snapshots: List[Dict[str, Any]]) -> int:
        """按交易日全量替换因子快照。"""
        with self.session_scope() as session:
            session.execute(
                delete(DailyFactorSnapshot).where(DailyFactorSnapshot.trade_date == trade_date)
            )
            for item in snapshots:
                session.add(
                    DailyFactorSnapshot(
                        trade_date=trade_date,
                        code=str(item["code"]).strip().upper(),
                        close=item.get("close"),
                        pct_chg=item.get("pct_chg"),
                        ma5=item.get("ma5"),
                        ma10=item.get("ma10"),
                        ma20=item.get("ma20"),
                        ma60=item.get("ma60"),
                        volume_ratio=item.get("volume_ratio"),
                        turnover_rate=item.get("turnover_rate"),
                        trend_score=item.get("trend_score"),
                        liquidity_score=item.get("liquidity_score"),
                        risk_flags_json=self._safe_json_dumps(item.get("risk_flags", [])),
                        created_at=datetime.now(),
                    )
                )
        return len(snapshots)

    def list_factor_snapshots(self, trade_date: date, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """查询指定交易日的因子快照。"""
        with self.get_session() as session:
            stmt = (
                select(DailyFactorSnapshot)
                .where(DailyFactorSnapshot.trade_date == trade_date)
                .order_by(DailyFactorSnapshot.code)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [row.to_dict() for row in rows]

    def create_screening_run(
        self,
        trade_date: date,
        market: str = "cn",
        config_snapshot: Optional[Dict[str, Any]] = None,
        status: str = "pending",
        ai_top_k: int = 0,
        run_id: Optional[str] = None,
        return_created: bool = False,
        trigger_type: str = "manual",
    ) -> Any:
        """创建筛选任务记录并返回 run_id。"""
        if run_id is None:
            run_id = f"run-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        # Derive notification_status default from trigger_type
        notification_status = "pending" if trigger_type == "scheduled" else "skipped"

        record = ScreeningRun(
            run_id=run_id,
            trade_date=trade_date,
            market=market,
            status=status,
            ai_top_k=ai_top_k,
            config_snapshot=self._safe_json_dumps(config_snapshot or {}),
            started_at=datetime.now(),
            trigger_type=trigger_type,
            notification_status=notification_status,
        )

        created = True
        with self.session_scope() as session:
            try:
                session.add(record)
                session.flush()
            except IntegrityError:
                session.rollback()
                created = False

        if return_created:
            return run_id, created
        return run_id

    def update_screening_run_status(
        self,
        run_id: str,
        status: str,
        trade_date: Optional[date] = None,
        universe_size: Optional[int] = None,
        candidate_count: Optional[int] = None,
        error_summary: Optional[str] = None,
    ) -> bool:
        """更新筛选任务状态。"""
        with self.session_scope() as session:
            record = session.execute(
                select(ScreeningRun).where(ScreeningRun.run_id == run_id)
            ).scalar_one_or_none()
            if record is None:
                return False

            allowed_statuses = self._screening_status_transitions.get(record.status, {record.status})
            if status not in allowed_statuses:
                return False

            record.status = status
            if trade_date is not None:
                record.trade_date = trade_date
            if universe_size is not None:
                record.universe_size = universe_size
            if candidate_count is not None:
                record.candidate_count = candidate_count
            if error_summary is not None:
                record.error_summary = error_summary
            if status in {"completed", "completed_with_ai_degraded", "failed"}:
                if record.completed_at is None:
                    record.completed_at = datetime.now()
            elif record.completed_at is not None:
                record.completed_at = None
            return True

    def update_notification_status(
        self,
        run_id: str,
        notification_status: str,
        notification_error: Optional[str] = None,
    ) -> bool:
        """Update notification lifecycle fields on a screening run."""
        with self.session_scope() as session:
            record = session.execute(
                select(ScreeningRun).where(ScreeningRun.run_id == run_id)
            ).scalar_one_or_none()
            if record is None:
                return False
            record.notification_status = notification_status
            record.notification_attempts = (record.notification_attempts or 0) + 1
            if notification_status == "sent":
                record.notification_sent_at = datetime.now()
            if notification_error is not None:
                record.notification_error = notification_error
            return True

    def get_screening_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取单次筛选任务。"""
        with self.get_session() as session:
            record = session.execute(
                select(ScreeningRun).where(ScreeningRun.run_id == run_id)
            ).scalar_one_or_none()
            return record.to_dict() if record else None

    def find_latest_screening_run(
        self,
        market: str = "cn",
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the latest screening run for the same effective request snapshot."""
        expected_identity = self._screening_run_identity(config_snapshot or {})
        with self.get_session() as session:
            rows = session.execute(
                select(ScreeningRun)
                .where(ScreeningRun.market == market)
                .order_by(desc(ScreeningRun.started_at))
            ).scalars().all()

            for row in rows:
                payload = row.to_dict()
                if self._screening_run_identity(payload.get("config_snapshot", {})) == expected_identity:
                    return payload
        return None

    def reset_screening_run_for_rerun(
        self,
        run_id: str,
        config_snapshot: Optional[Dict[str, Any]] = None,
        ai_top_k: Optional[int] = None,
    ) -> bool:
        """Reset a failed screening run so it can be re-executed in place."""
        with self.session_scope() as session:
            values = {
                "status": "pending",
                "universe_size": 0,
                "candidate_count": 0,
                "error_summary": None,
                "completed_at": None,
                "started_at": datetime.now(),
            }
            if config_snapshot is not None:
                values["config_snapshot"] = self._safe_json_dumps(config_snapshot)
            if ai_top_k is not None:
                values["ai_top_k"] = ai_top_k

            result = session.execute(
                update(ScreeningRun)
                .where(
                    ScreeningRun.run_id == run_id,
                    ScreeningRun.status == "failed",
                )
                .values(**values)
            )
            if result.rowcount == 0:
                return False

            session.execute(
                delete(ScreeningCandidate).where(ScreeningCandidate.run_id == run_id)
            )
            return True

    def update_screening_run_context(
        self,
        run_id: str,
        config_snapshot_updates: Optional[Dict[str, Any]] = None,
        ai_top_k: Optional[int] = None,
    ) -> bool:
        """Update the persisted config snapshot or ai_top_k for an existing run."""
        with self.session_scope() as session:
            record = session.execute(
                select(ScreeningRun).where(ScreeningRun.run_id == run_id)
            ).scalar_one_or_none()
            if record is None:
                return False

            if config_snapshot_updates:
                snapshot = json.loads(record.config_snapshot) if record.config_snapshot else {}
                snapshot.update(config_snapshot_updates)
                record.config_snapshot = self._safe_json_dumps(snapshot)
            if ai_top_k is not None:
                record.ai_top_k = ai_top_k
            return True

    @staticmethod
    def _screening_run_identity(config_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Build a stable identity used for screening run idempotency."""
        return {
            "requested_trade_date": str(config_snapshot.get("requested_trade_date") or ""),
            "mode": str(config_snapshot.get("mode") or "balanced"),
            "stock_codes": sorted(
                {
                    str(code).strip().upper()
                    for code in (config_snapshot.get("stock_codes") or [])
                    if str(code).strip()
                }
            ),
            "candidate_limit": config_snapshot.get("candidate_limit"),
            "ai_top_k": config_snapshot.get("ai_top_k"),
            "screening_min_list_days": config_snapshot.get("screening_min_list_days"),
            "screening_min_volume_ratio": config_snapshot.get("screening_min_volume_ratio"),
            "screening_min_avg_amount": config_snapshot.get("screening_min_avg_amount"),
            "screening_breakout_lookback_days": config_snapshot.get("screening_breakout_lookback_days"),
            "screening_factor_lookback_days": config_snapshot.get("screening_factor_lookback_days"),
            "screening_ingest_failure_threshold": config_snapshot.get("screening_ingest_failure_threshold", 0.02),
        }

    def list_screening_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """按开始时间倒序列出筛选任务。"""
        with self.get_session() as session:
            rows = session.execute(
                select(ScreeningRun)
                .order_by(desc(ScreeningRun.started_at))
                .limit(limit)
            ).scalars().all()
            return [row.to_dict() for row in rows]

    def save_screening_candidates(self, run_id: str, candidates: List[Dict[str, Any]]) -> int:
        """批量保存筛选候选结果。"""
        with self.session_scope() as session:
            session.execute(
                delete(ScreeningCandidate).where(ScreeningCandidate.run_id == run_id)
            )

            for item in candidates:
                session.add(
                    ScreeningCandidate(
                        run_id=run_id,
                        code=item["code"],
                        name=item.get("name"),
                        rank=int(item.get("rank", 0)),
                        rule_score=float(item.get("rule_score", 0.0)),
                        selected_for_ai=bool(item.get("selected_for_ai", False)),
                        rule_hits_json=self._safe_json_dumps(item.get("rule_hits", [])),
                        factor_snapshot_json=self._safe_json_dumps(item.get("factor_snapshot", {})),
                        ai_query_id=item.get("ai_query_id"),
                        ai_summary=item.get("ai_summary"),
                        ai_operation_advice=item.get("ai_operation_advice"),
                        created_at=datetime.now(),
                    )
                )

        return len(candidates)

    def list_screening_candidates(
        self,
        run_id: str,
        limit: int = 100,
        with_ai_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """查询某次筛选任务的候选结果。"""
        with self.get_session() as session:
            stmt = (
                select(ScreeningCandidate)
                .where(ScreeningCandidate.run_id == run_id)
                .order_by(ScreeningCandidate.rank)
            )
            if with_ai_only:
                stmt = stmt.where(ScreeningCandidate.selected_for_ai.is_(True))
            rows = session.execute(stmt).scalars().all()
            return self._enrich_screening_candidates([row.to_dict() for row in rows])[:limit]

    def get_screening_candidate_detail(self, run_id: str, code: str) -> Optional[Dict[str, Any]]:
        """查询某次筛选任务下单只候选的完整详情。"""
        with self.get_session() as session:
            rows = session.execute(
                select(ScreeningCandidate)
                .where(ScreeningCandidate.run_id == run_id)
                .order_by(ScreeningCandidate.rank)
            ).scalars().all()
            if not rows:
                return None

        enriched = self._enrich_screening_candidates([row.to_dict() for row in rows])
        item = next((candidate for candidate in enriched if candidate.get("code") == code), None)
        if item is None:
            return None

        item["analysis_history"] = self._build_screening_analysis_history_ref(
            query_id=item.get("ai_query_id"),
            code=item.get("code"),
        )
        return item

    def _enrich_screening_candidates(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for item in items:
            news_records = []
            ai_query_id = item.get("ai_query_id")
            if ai_query_id:
                news_records = self.get_news_intel_by_query_id(ai_query_id, limit=3)

            news_titles = [record.title for record in news_records if getattr(record, "title", None)]
            news_count = len(news_records)
            has_ai_analysis = bool(item.get("ai_summary") or item.get("ai_operation_advice"))
            recommendation_source = "rules_plus_ai" if has_ai_analysis else "rules_only"
            final_score = round(
                float(item.get("rule_score", 0.0))
                + self._screening_ai_bonus(item.get("ai_operation_advice"))
                + min(news_count, 3),
                2,
            )

            reason_parts = [f"规则得分 {float(item.get('rule_score', 0.0)):.1f}"]
            if has_ai_analysis:
                reason_parts.append(f"AI 建议 {item.get('ai_operation_advice') or '已分析'}")
            else:
                reason_parts.append("按规则结果输出")
            if news_count:
                reason_parts.append(f"新闻补充 {news_count} 条")

            enriched_item = {
                **item,
                "has_ai_analysis": has_ai_analysis,
                "news_count": news_count,
                "news_summary": "；".join(news_titles[:2]) if news_titles else None,
                "recommendation_source": recommendation_source,
                "recommendation_reason": "；".join(reason_parts),
                "final_score": final_score,
            }
            enriched.append(enriched_item)

        ordered = sorted(
            enriched,
            key=lambda item: (-float(item["final_score"]), -float(item["rule_score"]), int(item["rank"])),
        )
        for index, item in enumerate(ordered, start=1):
            item["final_rank"] = index
        return ordered

    def _build_screening_analysis_history_ref(self, query_id: Optional[str], code: Optional[str]) -> Optional[Dict[str, Any]]:
        if not query_id or not code:
            return None
        record = self.get_latest_analysis_by_query_id_and_code(query_id=query_id, code=code)
        if record is None:
            return None
        return {
            "id": record.id,
            "query_id": record.query_id,
            "stock_code": record.code,
            "stock_name": record.name,
            "report_type": record.report_type,
            "operation_advice": record.operation_advice,
            "trend_prediction": record.trend_prediction,
            "sentiment_score": record.sentiment_score,
            "analysis_summary": record.analysis_summary,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    def _screening_ai_bonus(operation_advice: Optional[str]) -> float:
        mapping = {
            "买入": 8.0,
            "加仓": 6.0,
            "关注": 4.0,
            "持有": 2.0,
            "观望": 0.0,
            "减仓": -4.0,
            "卖出": -8.0,
        }
        return mapping.get(str(operation_advice or "").strip(), 0.0)

    def get_latest_analysis_by_query_id(self, query_id: str) -> Optional[AnalysisHistory]:
        """
        根据 query_id 查询最新一条分析历史记录

        query_id 在批量分析时可能重复，故返回最近创建的一条。

        Args:
            query_id: 分析记录关联的 query_id

        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            result = session.execute(
                select(AnalysisHistory)
                .where(AnalysisHistory.query_id == query_id)
                .order_by(desc(AnalysisHistory.created_at))
                .limit(1)
            ).scalars().first()
            return result

    def get_latest_analysis_by_query_id_and_code(self, query_id: str, code: str) -> Optional[AnalysisHistory]:
        """根据 query_id 和股票代码查询最新分析历史记录。"""
        with self.get_session() as session:
            result = session.execute(
                select(AnalysisHistory)
                .where(
                    AnalysisHistory.query_id == query_id,
                    AnalysisHistory.code == code,
                )
                .order_by(desc(AnalysisHistory.created_at))
                .limit(1)
            ).scalars().first()
            return result
    
    def get_data_range(
        self, 
        code: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockDaily]:
        """
        获取指定日期范围的数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            StockDaily 对象列表
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date >= start_date,
                        StockDaily.date <= end_date
                    )
                )
                .order_by(StockDaily.date)
            ).scalars().all()
            
            return list(results)
    
    def save_daily_data(
        self, 
        df: pd.DataFrame, 
        code: str,
        data_source: str = "Unknown"
    ) -> int:
        """
        保存日线数据到数据库
        
        策略：
        - 使用 UPSERT 逻辑（存在则更新，不存在则插入）
        - 跳过已存在的数据，避免重复
        
        Args:
            df: 包含日线数据的 DataFrame
            code: 股票代码
            data_source: 数据来源名称
            
        Returns:
            新增/更新的记录数
        """
        if df is None or df.empty:
            logger.warning(f"保存数据为空，跳过 {code}")
            return 0
        
        saved_count = 0
        
        with self.get_session() as session:
            try:
                for _, row in df.iterrows():
                    # 解析日期
                    row_date = row.get('date')
                    if isinstance(row_date, str):
                        row_date = datetime.strptime(row_date, '%Y-%m-%d').date()
                    elif isinstance(row_date, datetime):
                        row_date = row_date.date()
                    elif isinstance(row_date, pd.Timestamp):
                        row_date = row_date.date()
                    
                    # 检查是否已存在
                    existing = session.execute(
                        select(StockDaily).where(
                            and_(
                                StockDaily.code == code,
                                StockDaily.date == row_date
                            )
                        )
                    ).scalar_one_or_none()
                    
                    if existing:
                        # 更新现有记录
                        existing.open = row.get('open')
                        existing.high = row.get('high')
                        existing.low = row.get('low')
                        existing.close = row.get('close')
                        existing.volume = row.get('volume')
                        existing.amount = row.get('amount')
                        existing.pct_chg = row.get('pct_chg')
                        existing.ma5 = row.get('ma5')
                        existing.ma10 = row.get('ma10')
                        existing.ma20 = row.get('ma20')
                        existing.volume_ratio = row.get('volume_ratio')
                        existing.data_source = data_source
                        existing.updated_at = datetime.now()
                    else:
                        # 创建新记录
                        record = StockDaily(
                            code=code,
                            date=row_date,
                            open=row.get('open'),
                            high=row.get('high'),
                            low=row.get('low'),
                            close=row.get('close'),
                            volume=row.get('volume'),
                            amount=row.get('amount'),
                            pct_chg=row.get('pct_chg'),
                            ma5=row.get('ma5'),
                            ma10=row.get('ma10'),
                            ma20=row.get('ma20'),
                            volume_ratio=row.get('volume_ratio'),
                            data_source=data_source,
                        )
                        session.add(record)
                        saved_count += 1
                
                session.commit()
                logger.info(f"保存 {code} 数据成功，新增 {saved_count} 条")
                
            except Exception as e:
                session.rollback()
                logger.error(f"保存 {code} 数据失败: {e}")
                raise
        
        return saved_count
    
    def get_analysis_context(
        self, 
        code: str,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取分析所需的上下文数据
        
        返回今日数据 + 昨日数据的对比信息
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            包含今日数据、昨日对比等信息的字典
        """
        if target_date is None:
            target_date = date.today()
        # 注意：尽管入参提供了 target_date，但当前实现实际使用的是“最新两天数据”（get_latest_data），
        # 并不会按 target_date 精确取当日/前一交易日的上下文。
        # 因此若未来需要支持“按历史某天复盘/重算”的可解释性，这里需要调整。
        # 该行为目前保留（按需求不改逻辑）。
        
        # 获取最近2天数据
        recent_data = self.get_latest_data(code, days=2)
        
        if not recent_data:
            logger.warning(f"未找到 {code} 的数据")
            return None
        
        today_data = recent_data[0]
        yesterday_data = recent_data[1] if len(recent_data) > 1 else None
        
        context = {
            'code': code,
            'date': today_data.date.isoformat(),
            'today': today_data.to_dict(),
        }
        
        if yesterday_data:
            context['yesterday'] = yesterday_data.to_dict()
            
            # 计算相比昨日的变化
            if yesterday_data.volume and yesterday_data.volume > 0:
                context['volume_change_ratio'] = round(
                    today_data.volume / yesterday_data.volume, 2
                )
            
            if yesterday_data.close and yesterday_data.close > 0:
                context['price_change_ratio'] = round(
                    (today_data.close - yesterday_data.close) / yesterday_data.close * 100, 2
                )
            
            # 均线形态判断
            context['ma_status'] = self._analyze_ma_status(today_data)
        
        return context
    
    def _analyze_ma_status(self, data: StockDaily) -> str:
        """
        分析均线形态
        
        判断条件：
        - 多头排列：close > ma5 > ma10 > ma20
        - 空头排列：close < ma5 < ma10 < ma20
        - 震荡整理：其他情况
        """
        # 注意：这里的均线形态判断基于“close/ma5/ma10/ma20”静态比较，
        # 未考虑均线拐点、斜率、或不同数据源复权口径差异。
        # 该行为目前保留（按需求不改逻辑）。
        close = data.close or 0
        ma5 = data.ma5 or 0
        ma10 = data.ma10 or 0
        ma20 = data.ma20 or 0
        
        if close > ma5 > ma10 > ma20 > 0:
            return "多头排列 📈"
        elif close < ma5 < ma10 < ma20 and ma20 > 0:
            return "空头排列 📉"
        elif close > ma5 and ma5 > ma10:
            return "短期向好 🔼"
        elif close < ma5 and ma5 < ma10:
            return "短期走弱 🔽"
        else:
            return "震荡整理 ↔️"

    @staticmethod
    def _parse_published_date(value: Optional[str]) -> Optional[datetime]:
        """
        解析发布时间字符串（失败返回 None）
        """
        if not value:
            return None

        if isinstance(value, datetime):
            return value

        text = str(value).strip()
        if not text:
            return None

        # 优先尝试 ISO 格式
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _safe_json_dumps(data: Any) -> str:
        """
        安全序列化为 JSON 字符串
        """
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return json.dumps(str(data), ensure_ascii=False)

    @staticmethod
    def _build_raw_result(result: Any) -> Dict[str, Any]:
        """
        生成完整分析结果字典
        """
        data = result.to_dict() if hasattr(result, "to_dict") else {}
        data.update({
            'data_sources': getattr(result, 'data_sources', ''),
            'raw_response': getattr(result, 'raw_response', None),
        })
        return data

    @staticmethod
    def _parse_sniper_value(value: Any) -> Optional[float]:
        """
        Parse a sniper point value from various formats to float.

        Handles: numeric types, plain number strings, Chinese price formats
        like "18.50元", range formats like "18.50-19.00", and text with
        embedded numbers while filtering out MA indicators.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v if v > 0 else None

        text = str(value).replace(',', '').replace('，', '').strip()
        if not text or text == '-' or text == '—' or text == 'N/A':
            return None

        # 尝试直接解析纯数字字符串
        try:
            return float(text)
        except ValueError:
            pass

        # 优先截取 "：" 到 "元" 之间的价格，避免误提取 MA5/MA10 等技术指标数字
        colon_pos = max(text.rfind("："), text.rfind(":"))
        yuan_pos = text.find("元", colon_pos + 1 if colon_pos != -1 else 0)
        if yuan_pos != -1:
            segment_start = colon_pos + 1 if colon_pos != -1 else 0
            segment = text[segment_start:yuan_pos]
            
            # 使用 finditer 并过滤掉 MA 开头的数字
            matches = list(re.finditer(r"-?\d+(?:\.\d+)?", segment))
            valid_numbers = []
            for m in matches:
                # 检查前面是否是 "MA" (忽略大小写)
                start_idx = m.start()
                if start_idx >= 2:
                    prefix = segment[start_idx-2:start_idx].upper()
                    if prefix == "MA":
                        continue
                valid_numbers.append(m.group())
            
            if valid_numbers:
                try:
                    return abs(float(valid_numbers[-1]))
                except ValueError:
                    pass

        # 兜底：无"元"字时，先截去第一个括号后的内容，避免误提取括号内技术指标数字
        # 例如 "1.52-1.53 (回踩MA5/10附近)" → 仅在 "1.52-1.53 " 中搜索
        paren_pos = len(text)
        for paren_char in ('(', '（'):
            pos = text.find(paren_char)
            if pos != -1:
                paren_pos = min(paren_pos, pos)
        search_text = text[:paren_pos].strip() or text  # 括号前为空时降级用全文

        valid_numbers = []
        for m in re.finditer(r"\d+(?:\.\d+)?", search_text):
            start_idx = m.start()
            if start_idx >= 2 and search_text[start_idx-2:start_idx].upper() == "MA":
                continue
            valid_numbers.append(m.group())
        if valid_numbers:
            try:
                return float(valid_numbers[-1])
            except ValueError:
                pass
        return None

    def _extract_sniper_points(self, result: Any) -> Dict[str, Optional[float]]:
        """
        Extract sniper point values from an AnalysisResult.

        Tries multiple extraction paths to handle different dashboard structures:
        1. result.get_sniper_points() (standard path)
        2. Direct dashboard dict traversal with various nesting levels
        3. Fallback from raw_result dict if available
        """
        raw_points = {}

        # Path 1: standard method
        if hasattr(result, "get_sniper_points"):
            raw_points = result.get_sniper_points() or {}

        # Path 2: direct dashboard traversal when standard path yields empty values
        if not any(raw_points.get(k) for k in ("ideal_buy", "secondary_buy", "stop_loss", "take_profit")):
            dashboard = getattr(result, "dashboard", None)
            if isinstance(dashboard, dict):
                raw_points = self._find_sniper_in_dashboard(dashboard) or raw_points

        # Path 3: try raw_result for agent mode results
        if not any(raw_points.get(k) for k in ("ideal_buy", "secondary_buy", "stop_loss", "take_profit")):
            raw_response = getattr(result, "raw_response", None)
            if isinstance(raw_response, dict):
                raw_points = self._find_sniper_in_dashboard(raw_response) or raw_points

        return {
            "ideal_buy": self._parse_sniper_value(raw_points.get("ideal_buy")),
            "secondary_buy": self._parse_sniper_value(raw_points.get("secondary_buy")),
            "stop_loss": self._parse_sniper_value(raw_points.get("stop_loss")),
            "take_profit": self._parse_sniper_value(raw_points.get("take_profit")),
        }

    @staticmethod
    def _find_sniper_in_dashboard(d: dict) -> Optional[Dict[str, Any]]:
        """
        Recursively search for sniper_points in a dashboard dict.
        Handles various nesting: dashboard.battle_plan.sniper_points,
        dashboard.dashboard.battle_plan.sniper_points, etc.
        """
        if not isinstance(d, dict):
            return None

        # Direct: d has sniper_points keys at top level
        if "ideal_buy" in d:
            return d

        # d.sniper_points
        sp = d.get("sniper_points")
        if isinstance(sp, dict) and sp:
            return sp

        # d.battle_plan.sniper_points
        bp = d.get("battle_plan")
        if isinstance(bp, dict):
            sp = bp.get("sniper_points")
            if isinstance(sp, dict) and sp:
                return sp

        # d.dashboard.battle_plan.sniper_points (double-nested)
        inner = d.get("dashboard")
        if isinstance(inner, dict):
            bp = inner.get("battle_plan")
            if isinstance(bp, dict):
                sp = bp.get("sniper_points")
                if isinstance(sp, dict) and sp:
                    return sp

        return None

    @staticmethod
    def _build_fallback_url_key(
        code: str,
        title: str,
        source: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        生成无 URL 时的去重键（确保稳定且较短）
        """
        date_str = published_date.isoformat() if published_date else ""
        raw_key = f"{code}|{title}|{source}|{date_str}"
        digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        return f"no-url:{code}:{digest}"

    def save_conversation_message(self, session_id: str, role: str, content: str) -> None:
        """
        保存 Agent 对话消息
        """
        with self.session_scope() as session:
            msg = ConversationMessage(
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(msg)

    def get_conversation_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取 Agent 对话历史
        """
        with self.session_scope() as session:
            stmt = select(ConversationMessage).filter(
                ConversationMessage.session_id == session_id
            ).order_by(ConversationMessage.created_at.desc()).limit(limit)
            messages = session.execute(stmt).scalars().all()

            # 倒序返回，保证时间顺序
            return [{"role": msg.role, "content": msg.content} for msg in reversed(messages)]

    def get_chat_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取聊天会话列表（从 conversation_messages 聚合）

        Returns:
            按最近活跃时间倒序的会话列表，每条包含 session_id, title, message_count, last_active
        """
        from sqlalchemy import func

        with self.session_scope() as session:
            # 聚合每个 session 的消息数和最后活跃时间
            stmt = (
                select(
                    ConversationMessage.session_id,
                    func.count(ConversationMessage.id).label("message_count"),
                    func.min(ConversationMessage.created_at).label("created_at"),
                    func.max(ConversationMessage.created_at).label("last_active"),
                )
                .group_by(ConversationMessage.session_id)
                .order_by(desc(func.max(ConversationMessage.created_at)))
                .limit(limit)
            )
            rows = session.execute(stmt).all()

            results = []
            for row in rows:
                sid = row.session_id
                # 取该会话第一条 user 消息作为标题
                first_user_msg = session.execute(
                    select(ConversationMessage.content)
                    .where(
                        and_(
                            ConversationMessage.session_id == sid,
                            ConversationMessage.role == "user",
                        )
                    )
                    .order_by(ConversationMessage.created_at)
                    .limit(1)
                ).scalar()
                title = (first_user_msg or "新对话")[:60]

                results.append({
                    "session_id": sid,
                    "title": title,
                    "message_count": row.message_count,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_active": row.last_active.isoformat() if row.last_active else None,
                })
            return results

    def get_conversation_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取单个会话的完整消息列表（用于前端恢复历史）
        """
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.created_at)
                .limit(limit)
            )
            messages = session.execute(stmt).scalars().all()
            return [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ]

    def delete_conversation_session(self, session_id: str) -> int:
        """
        删除指定会话的所有消息

        Returns:
            删除的消息数
        """
        with self.session_scope() as session:
            result = session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.session_id == session_id
                )
            )
            return result.rowcount


# 便捷函数
def get_db() -> DatabaseManager:
    """获取数据库管理器实例的快捷方式"""
    return DatabaseManager.get_instance()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    db = get_db()
    
    print("=== 数据库测试 ===")
    print(f"数据库初始化成功")
    
    # 测试检查今日数据
    has_data = db.has_today_data('600519')
    print(f"茅台今日是否有数据: {has_data}")
    
    # 测试保存数据
    test_df = pd.DataFrame({
        'date': [date.today()],
        'open': [1800.0],
        'high': [1850.0],
        'low': [1780.0],
        'close': [1820.0],
        'volume': [10000000],
        'amount': [18200000000],
        'pct_chg': [1.5],
        'ma5': [1810.0],
        'ma10': [1800.0],
        'ma20': [1790.0],
        'volume_ratio': [1.2],
    })
    
    saved = db.save_daily_data(test_df, '600519', 'TestSource')
    print(f"保存测试数据: {saved} 条")
    
    # 测试获取上下文
    context = db.get_analysis_context('600519')
    print(f"分析上下文: {context}")
