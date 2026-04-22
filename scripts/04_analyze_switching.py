import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add root and src directory to sys.path for importing src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from config import OUTPUT_DIR, DAILY_PNL_MATRIX_PATH, EXPERIMENT_PROTOCOL, logger
from performance import calculate_detailed_stats

PNL_MATRIX_PATH = DAILY_PNL_MATRIX_PATH
PLOT_PATH = os.path.join(OUTPUT_DIR, "switching_window_comparison.png")

def get_dynamic_rets(df_pnl, window, fallback_t):
    df_sharpe = pd.DataFrame(index=df_pnl.index)
    for col in df_pnl.columns:
        # Using vectorized rolling
        df_sharpe[col] = df_pnl[col].rolling(window=window).mean() / df_pnl[col].rolling(window=window).std() * np.sqrt(252)
    
    df_selection = df_sharpe.shift(1)
    # Use the IS-optimized T as fallback instead of hardcoded 38
    best_t = df_selection.apply(lambda row: fallback_t if row.isna().all() else row.idxmax(), axis=1)
    
    rets = pd.Series([df_pnl.loc[date, col] for date, col in best_t.items()], index=df_pnl.index)
    return rets, best_t


def main():
    logger.info("Loading PnL matrix...")
    df_pnl = pd.read_parquet(PNL_MATRIX_PATH)
    df_pnl.index = pd.to_datetime(df_pnl.index)
    
    # ── In-Sample Optimization ────────────────────────────────────────────
    is_start = EXPERIMENT_PROTOCOL['is_start']
    is_end   = EXPERIMENT_PROTOCOL['is_end']
    oos_start = EXPERIMENT_PROTOCOL['oos_start']
    oos_end   = EXPERIMENT_PROTOCOL['oos_end']
    
    logger.info(f"Finding Optimal Fixed T in Training Period ({is_start} to {is_end})...")
    df_is = df_pnl.loc[is_start:is_end]
    is_sharpe = (df_is.mean() * 252) / (df_is.std() * np.sqrt(252))
    best_is_t = is_sharpe.idxmax()
    logger.info(f"IS Optimal T identified: T={best_is_t} (Sharpe: {is_sharpe[best_is_t]:.2f})")
    
    # ── Dynamic Calculations ─────────────────────────────────────────────
    logger.info("Calculating Dynamic T (1-Year Window)...")
    rets_1y, best_t_1y = get_dynamic_rets(df_pnl, 252, best_is_t)
    
    logger.info("Calculating Dynamic T (6-Month Window)...")
    rets_6m, best_t_6m = get_dynamic_rets(df_pnl, 126, best_is_t)
    
    df_compare = pd.DataFrame({
        'Date': df_pnl.index,
        'Dyn_1Y': rets_1y.values,
        'Dyn_6M': rets_6m.values,
        f'Fixed_T{best_is_t}': df_pnl[best_is_t].values
    }).set_index('Date')
    
    # Selection for OOS comparison
    df_oos = df_compare.loc[oos_start:oos_end]
    
    # Plotting
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    (1 + df_oos['Dyn_1Y']).cumprod().plot(ax=ax1, label='Dynamic (1Y Window)', color='#E63946', linewidth=2)
    (1 + df_oos['Dyn_6M']).cumprod().plot(ax=ax1, label='Dynamic (6M Window)', color='#F1A7B4', linestyle='--')
    (1 + df_oos[f'Fixed_T{best_is_t}']).cumprod().plot(ax=ax1, label=f'Static Baseline (Fixed T={best_is_t})', color='#457B9D', alpha=0.6)
    
    ax1.set_title(f"Dynamic Window Comparison (OOS {oos_start[:4]}-{oos_end[:4]})", fontsize=14)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    best_t_1y.loc[oos_start:oos_end].plot(ax=ax2, label='1Y Choice', color='#E63946', alpha=0.5)
    best_t_6m.loc[oos_start:oos_end].plot(ax=ax2, label='6M Choice', color='#F1A7B4', alpha=0.5)
    ax2.set_title("Parameter Selection Drift", fontsize=12)
    ax2.set_ylim(20, 65)
    ax2.legend()
    
    plt.tight_layout()
    plt.savefig(PLOT_PATH)
    
    # Stats Table
    print(f"\nOOS Performance Stats ({oos_start[:4]}-{oos_end[:4]}):")
    stats = []
    for col in df_oos.columns:
        res = calculate_detailed_stats(df_oos[col])
        stats.append({
            'Window': col, 
            'AnnRet': f"{res['Annualized Return']:.2%}", 
            'Sharpe': f"{res['Sharpe Ratio']:.2f}", 
            'MaxDD': f"{res['Max Drawdown']:.2%}"
        })
    print(pd.DataFrame(stats))

if __name__ == "__main__":
    main()
