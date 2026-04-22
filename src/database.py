"""
database.py — SQLite Persistence Layer (Hybrid Architecture)
============================================================
Responsibility:
  - "Light relational data" only: trade journal & backtest run metadata.
  - Heavy time-series data (equity curves, factor matrices) remain in Parquet.

Tables
------
  trade_journal  : every individual fill event (open / close / stop-loss / EOD)
  backtest_runs  : one row per completed backtest run with aggregate KPIs

Usage
-----
  from database import BacktestDB
  db = BacktestDB()          # opens / creates DB automatically
  run_id = db.start_run(...)
  db.log_trade(run_id, ...)
  db.finish_run(run_id, ...)
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime

# ── Resolve DB path from config ──────────────────────────────────────────────
try:
    from config import DB_PATH, logger
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import DB_PATH, logger


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────
_DDL_BACKTEST_RUNS = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    strategy_name   TEXT    NOT NULL DEFAULT 'ConsistencyStrategy',
    t_minutes       INTEGER,
    start_date      TEXT,
    end_date        TEXT,
    initial_capital REAL,
    total_return    REAL,
    annual_return   REAL,
    sharpe_ratio    REAL,
    max_drawdown    REAL,
    win_rate        REAL,
    total_trades    INTEGER,
    commission_rate REAL,
    stop_loss_pct   REAL,
    status          TEXT    NOT NULL DEFAULT 'RUNNING',
    equity_csv_path TEXT
);
"""

_DDL_TRADE_JOURNAL = """
CREATE TABLE IF NOT EXISTS trade_journal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    trade_time  TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    direction   TEXT    NOT NULL,   -- BUY / SELL
    quantity    REAL    NOT NULL,
    price       REAL    NOT NULL,
    fill_cost   REAL    NOT NULL,   -- price * qty * multiplier
    commission  REAL    NOT NULL,
    trade_type  TEXT,               -- OPEN_LONG / OPEN_SHORT / CLOSE / STOP_LOSS / EOD_EXIT
    realized_pnl REAL DEFAULT 0.0
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# BacktestDB Class
# ─────────────────────────────────────────────────────────────────────────────
class BacktestDB:
    """
    Thread-safe (single-threaded) SQLite interface for the backtest system.
    Opens a new connection per operation to avoid `check_same_thread` issues
    when called from different script contexts.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()
        logger.info(f"[DB] Connected → {self.db_path}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row          # allows dict-like row access
        conn.execute("PRAGMA journal_mode=WAL") # WAL for concurrency safety
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.execute(_DDL_BACKTEST_RUNS)
            conn.execute(_DDL_TRADE_JOURNAL)
        logger.debug("[DB] Schema verified / created.")

    # ── Backtest Run Lifecycle ────────────────────────────────────────────────

    def start_run(self,
                  t_minutes: int,
                  start_date: str,
                  end_date: str,
                  initial_capital: float,
                  commission_rate: float,
                  stop_loss_pct: float,
                  strategy_name: str = "ConsistencyStrategy") -> int:
        """
        Insert a new run record (status=RUNNING) and return its run_id.
        Call this BEFORE the backtest loop starts.
        """
        sql = """
            INSERT INTO backtest_runs
                (created_at, strategy_name, t_minutes, start_date, end_date,
                 initial_capital, commission_rate, stop_loss_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
        """
        params = (datetime.now().isoformat(timespec='seconds'),
                  strategy_name, t_minutes, start_date, end_date,
                  initial_capital, commission_rate, stop_loss_pct)
        with self._conn() as conn:
            cur = conn.execute(sql, params)
            run_id = cur.lastrowid
        logger.info(f"[DB] Run #{run_id} started (T={t_minutes}, {start_date}→{end_date})")
        return run_id

    def finish_run(self,
                   run_id: int,
                   metrics: dict,
                   equity_csv_path: str = None):
        """
        Update the run record with final KPIs (status=DONE).
        Call this AFTER the backtest completes and metrics are calculated.

        metrics dict keys (all optional, defaults to None):
            total_return, annual_return, sharpe_ratio,
            max_drawdown, win_rate, total_trades
        """
        sql = """
            UPDATE backtest_runs SET
                status          = 'DONE',
                total_return    = :total_return,
                annual_return   = :annual_return,
                sharpe_ratio    = :sharpe_ratio,
                max_drawdown    = :max_drawdown,
                win_rate        = :win_rate,
                total_trades    = :total_trades,
                equity_csv_path = :equity_csv_path
            WHERE run_id = :run_id
        """
        params = {
            'run_id':           run_id,
            'total_return':     metrics.get('total_return'),
            'annual_return':    metrics.get('annual_return'),
            'sharpe_ratio':     metrics.get('sharpe_ratio'),
            'max_drawdown':     metrics.get('max_drawdown'),
            'win_rate':         metrics.get('win_rate'),
            'total_trades':     metrics.get('total_trades'),
            'equity_csv_path':  equity_csv_path,
        }
        with self._conn() as conn:
            conn.execute(sql, params)
        logger.info(f"[DB] Run #{run_id} finished → Sharpe={metrics.get('sharpe_ratio', 'N/A'):.2f}")

    # ── Trade Journal ─────────────────────────────────────────────────────────

    def log_trade(self,
                  run_id: int,
                  trade_time,
                  symbol: str,
                  direction: str,
                  quantity: float,
                  price: float,
                  fill_cost: float,
                  commission: float,
                  trade_type: str = None,
                  realized_pnl: float = 0.0):
        """
        Persist a single fill event to trade_journal.
        trade_type should be one of:
            OPEN_LONG | OPEN_SHORT | CLOSE | STOP_LOSS | EOD_EXIT
        """
        sql = """
            INSERT INTO trade_journal
                (run_id, trade_time, symbol, direction, quantity,
                 price, fill_cost, commission, trade_type, realized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (run_id,
                  str(trade_time),
                  symbol, direction,
                  float(quantity), float(price),
                  float(fill_cost), float(commission),
                  trade_type, float(realized_pnl))
        with self._conn() as conn:
            conn.execute(sql, params)

    def log_trades_bulk(self, run_id: int, trades: list[dict]):
        """
        Bulk insert a list of trade dicts (same schema as log_trade kwargs).
        Faster than calling log_trade in a loop for post-hoc saving.
        """
        if not trades:
            return
        sql = """
            INSERT INTO trade_journal
                (run_id, trade_time, symbol, direction, quantity,
                 price, fill_cost, commission, trade_type, realized_pnl)
            VALUES (:run_id, :trade_time, :symbol, :direction, :quantity,
                    :price, :fill_cost, :commission, :trade_type, :realized_pnl)
        """
        rows = []
        for t in trades:
            row = t.copy()
            row['run_id'] = run_id
            # SQLite doesn't handle Pandas Timestamps, convert to ISO string
            if hasattr(row['trade_time'], 'isoformat'):
                row['trade_time'] = row['trade_time'].isoformat(timespec='seconds')
            else:
                row['trade_time'] = str(row['trade_time'])
                
            row['trade_type'] = row.get('trade_type')
            row['realized_pnl'] = float(row.get('realized_pnl', 0.0))
            rows.append(row)

        with self._conn() as conn:
            conn.executemany(sql, rows)
        logger.info(f"[DB] Run #{run_id}: {len(rows)} trades flushed to journal.")

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_all_runs(self) -> pd.DataFrame:
        """Return all backtest run metadata as a DataFrame."""
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM backtest_runs ORDER BY run_id DESC", conn)

    def get_trades(self, run_id: int) -> pd.DataFrame:
        """Return all trades for a specific run as a DataFrame."""
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM trade_journal WHERE run_id=? ORDER BY trade_time",
                conn, params=(run_id,))

    def get_latest_run_id(self) -> int | None:
        """Return the run_id of the most recent completed run."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id FROM backtest_runs WHERE status='DONE' ORDER BY run_id DESC LIMIT 1"
            ).fetchone()
        return row['run_id'] if row else None

    def reset_run(self, run_id: int):
        """Delete a run and its associated trades (cascades via FK)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM trade_journal   WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM backtest_runs   WHERE run_id=?", (run_id,))
        logger.warning(f"[DB] Run #{run_id} and all its trades have been deleted.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI Quick-Test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    db = BacktestDB()
    print("\n=== Existing Backtest Runs ===")
    df = db.get_all_runs()
    if df.empty:
        print("(no runs yet — database is freshly initialised)")
    else:
        print(df.to_string(index=False))
