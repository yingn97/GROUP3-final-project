import os
import sys
import queue
import argparse
import pandas as pd
from datetime import datetime

# Add root and src directory to sys.path for importing src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from src.engine import BacktestEngine
from src.performance import display_performance_report
from src.config import DATA_DIR, STRATEGY_PARAMS, BACKTEST_CONFIG, OUTPUT_DIR, logger
from src.data_handler import HistoricCSVDataHandler
from src.strategy import ConsistencyStrategy
from src.portfolio import Portfolio
from src.execution import SimulatedExecutionHandler
from src.database import BacktestDB

def run_gold_standard_backtest(t_minutes, start_date, end_date):
    """
    Runs a high-precision, event-driven backtest for a specific T value.
    This is the final verification tool.
    """
    events = queue.Queue()
    
    # 1. Setup Parameters
    STRATEGY_PARAMS['T_minutes'] = t_minutes
    symbol_list = ['IF'] 
    
    logger.info(f"Gold Standard: Starting verification for T={t_minutes}")
    logger.info(f"Period: {start_date} to {end_date}")
    
    # 2. Initialize Components
    bars = HistoricCSVDataHandler(events, DATA_DIR, symbol_list)
    strategy = ConsistencyStrategy(bars, events)
    port = Portfolio(bars, events, pd.to_datetime(start_date), BACKTEST_CONFIG['initial_capital'])
    broker = SimulatedExecutionHandler(events, bars)
    
    # Override backtest config for the engine
    BACKTEST_CONFIG['end_date'] = end_date
    
    # 2b. Register this run in SQLite BEFORE starting the loop
    db = BacktestDB()
    run_id = db.start_run(
        t_minutes=t_minutes,
        start_date=start_date,
        end_date=end_date,
        initial_capital=BACKTEST_CONFIG['initial_capital'],
        commission_rate=STRATEGY_PARAMS['commission_rate'],
        stop_loss_pct=STRATEGY_PARAMS['stop_loss_pct'],
    )
    
    # 3. Execute Engine
    engine = BacktestEngine(events, bars, strategy, port, broker)
    engine.run()
    
    # 4. Generate Reports
    equity_df = port.create_equity_curve_dataframe()
    trades_df = pd.DataFrame(port.trades)
    
    if not equity_df.empty:
        # PnL per trade is now tracked in real-time by the Portfolio
        # No extra matching loop needed in the script layer.

        
        # 5. Save results (Hybrid approach: heavy series to Parquet)
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
            
        equity_file = os.path.join(OUTPUT_DIR, f"equity_T{t_minutes}_engine.parquet")
        equity_df.to_parquet(equity_file)
        
        print(f"\n[Success] Heavy data saved to:")
        print(f" - Equity (Parquet): {equity_file}")
        print(f" - Trades (SQLite):  Persisted in {db.db_path} (Run #{run_id})")
        
        # Print Beautiful Summary
        metrics = display_performance_report(equity_df, trades_df)

        # ── Persist to SQLite ───────────────────────────────────────────────
        # 1. Flush individual trades to trade_journal
        port.flush_trades_to_db(db, run_id)

        # 2. Finalise run with aggregate KPIs
        db.finish_run(
            run_id=run_id,
            metrics=metrics if isinstance(metrics, dict) else {},
            equity_csv_path=equity_file,
        )
        print(f"\n[DB] Run #{run_id} saved to {db.db_path}")
    else:
        logger.error("Backtest failed: No equity data generated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Final Verification Backtest Engine")
    parser.add_argument("--t", type=int, default=STRATEGY_PARAMS['T_minutes'], help="T minutes parameter")
    parser.add_argument("--start", type=str, default=BACKTEST_CONFIG['start_date'], help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=BACKTEST_CONFIG['end_date'], help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    run_gold_standard_backtest(args.t, args.start, args.end)
