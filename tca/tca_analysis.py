"""
tca_analysis.py — High-Precision Transaction Cost Analysis (v3.5+)
==================================================================
This tool connects to the SQLite backtest database and Parquet equity storage
to provide an exact breakdown of trading friction impact.
"""

import os
import sys
import pandas as pd
import numpy as np

# ── Standardised Path Reference ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from config import logger
from database import BacktestDB

def run_precision_tca(run_id=None):
    """
    Connects to the database, retrieves the specified run (or latest),
    and performs a precise cost-benefit analysis.
    """
    db = BacktestDB()
    
    # 1. Select the Run
    if run_id is None:
        run_id = db.get_latest_run_id()
        if run_id is None:
            logger.error("No backtest runs found in database. Run 02_backtest_engine.py first.")
            return
    
    # 2. Fetch Metadata & Trades
    runs_df = db.get_all_runs()
    run_meta = runs_df[runs_df['run_id'] == run_id].iloc[0]
    trades_df = db.get_trades(run_id)
    
    if trades_df.empty:
        logger.warning(f"Run #{run_id} has no trade records.")
        return

    # 3. Load Equity Curve from Parquet
    equity_path = run_meta['equity_csv_path'] # Now points to .parquet in engine
    if not os.path.exists(equity_path):
        logger.error(f"Equity Parquet file not found at {equity_path}")
        return
    
    df_equity = pd.read_parquet(equity_path)
    
    # ─────────────────────────────────────────────────────────────────────────
    # COST CALCULATIONS
    # ─────────────────────────────────────────────────────────────────────────
    total_commission = trades_df['commission'].sum()
    total_volume = trades_df['fill_cost'].sum()
    num_trades = len(trades_df)
    
    initial_cap = run_meta['initial_capital']
    final_equity = df_equity['total'].iloc[-1]
    net_profit = final_equity - initial_cap
    
    # Calculate "Gross Profit" (What if commission was zero?)
    gross_profit = net_profit + total_commission
    total_friction_bps = (total_commission / total_volume * 10000) if total_volume > 0 else 0
    profit_erosion = (total_commission / gross_profit) if gross_profit > 0 else 0
    
    # ─────────────────────────────────────────────────────────────────────────
    # TERMINAL REPORT
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "█"*60)
    print(f"       HIGH-PRECISION TCA REPORT (Run #{run_id})       ")
    print("█"*60)
    
    print(f"  [Strategy]       {run_meta['strategy_name']} (T={run_meta['t_minutes']})")
    print(f"  [Period]         {run_meta['start_date']} to {run_meta['end_date']}")
    print(f"  [Trading Volume] CNY {total_volume:,.2f} ({num_trades} fills)")
    print("-" * 60)
    
    print(f"  [Gross Profit]   CNY {gross_profit:,.2f} (Before costs)")
    print(f"  [Total Costs]    CNY {total_commission:,.2f} (Commissions)")
    print(f"  [Net Profit]     CNY {net_profit:,.2f} (After costs)")
    print("-" * 60)
    
    print(f"  [Cost Efficiency Metrics]")
    print(f"  ● Average Friction:    {total_friction_bps:.2f} bps (of volume)")
    print(f"  ● Profit Erosion:      {profit_erosion:.2%}")
    print(f"  ● Net Sharpe Ratio:    {run_meta['sharpe_ratio']:.2f}")
    
    # If erosion > 50%, show a warning
    if profit_erosion > 0.5:
        print("\n  ⚠️ WARNING: High Profit Erosion detected!")
        print("  Trading costs are consuming more than 50% of gross alpha.")
        print("  Consider lowering trade frequency or optimising execution.")
        
    print("█"*60 + "\n")

if __name__ == "__main__":
    # If a run ID is passed as CLI argument, use it
    target_run = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_precision_tca(target_run)
