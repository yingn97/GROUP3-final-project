import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
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
FINAL_REPORT_PATH = os.path.join(OUTPUT_DIR, "IS_OOS_COMPARISON_REPORT.png")

COLOR_DYNAMIC = '#E63946' 
COLOR_FIXED = '#457B9D'    
COLOR_DRAWDOWN = '#F1A7B4'


def main():
    logger.info("Loading PnL matrix...")
    df_pnl = pd.read_parquet(PNL_MATRIX_PATH)
    df_pnl.index = pd.to_datetime(df_pnl.index)
    
    # 1. In-Sample (IS) Optimization
    is_start = EXPERIMENT_PROTOCOL['is_start']
    is_end   = EXPERIMENT_PROTOCOL['is_end']
    oos_start = EXPERIMENT_PROTOCOL['oos_start']
    oos_end   = EXPERIMENT_PROTOCOL['oos_end']
    
    df_is = df_pnl.loc[is_start:is_end]
    is_sharpes = (df_is.mean() * 252) / (df_is.std() * np.sqrt(252))
    best_is_t = is_sharpes.idxmax()
    logger.info(f"Optimal T in Training Period ({is_start} to {is_end}) is T={best_is_t} with Sharpe={is_sharpes[best_is_t]:.2f}")

    # 2. Dynamic Strategy (1Y rolling)
    df_roll_sharpe = pd.DataFrame(index=df_pnl.index)
    for col in df_pnl.columns:
        df_roll_sharpe[col] = df_pnl[col].rolling(window=252).mean() / df_pnl[col].rolling(window=252).std() * np.sqrt(252)
    
    df_selection = df_roll_sharpe.shift(1)
    # Fallback to IS best if not enough history
    best_t_per_day = df_selection.apply(lambda row: best_is_t if row.isna().all() else row.idxmax(), axis=1) 
    
    dynamic_rets = pd.Series([df_pnl.loc[date, col] for date, col in best_t_per_day.items()], index=df_pnl.index)
    
    # 3. Out-of-Sample (OOS) Comparison
    
    df_oos_comparison = pd.DataFrame({
        'Dynamic_T': dynamic_rets.loc[oos_start:oos_end],
        f'Fixed_T{best_is_t}': df_pnl.loc[oos_start:oos_end, best_is_t]
    })
    
    best_t_oos = best_t_per_day.loc[oos_start:oos_end]
    
    curves = (1 + df_oos_comparison).cumprod()
    dds = curves / curves.cummax() - 1

    # Plot
    fig = plt.figure(figsize=(16, 12), dpi=150, facecolor='white')
    gs = gridspec.GridSpec(3, 2, height_ratios=[3, 1, 1])
    
    # --- SUBPLOT 1: Equity Curves ---
    ax_main = fig.add_subplot(gs[0, :])
    ax_main.plot(curves.index, curves['Dynamic_T'], label='Dynamic Switching (1Y Window)', color=COLOR_DYNAMIC, linewidth=2.5)
    ax_main.plot(curves.index, curves[f'Fixed_T{best_is_t}'], label=f'IS Optimal Baseline (Fixed T={best_is_t})', color=COLOR_FIXED, linestyle='--')
    
    ax_main.set_title("OOS Validation (2020-2024): Dynamic vs Static (IS Trained 2015-2019)", fontsize=16, fontweight='bold', pad=15)
    ax_main.set_ylabel("Normalized Equity (Start=1.0)", fontsize=14)
    ax_main.grid(True, linestyle='--', alpha=0.4)
    ax_main.legend(fontsize=12, loc='upper left')
    
    stats_data = []
    for col in df_oos_comparison.columns:
        stats = calculate_detailed_stats(df_oos_comparison[col])
        stats_data.append([
            col, 
            f"{stats['Total Return']:.1%}", 
            f"{stats['Annualized Return']:.1%}", 
            f"{stats['Sharpe Ratio']:.2f}", 
            f"{stats['Max Drawdown']:.1%}"
        ])
        
    table = ax_main.table(cellText=stats_data, 
                         colLabels=['Strategy', 'Total Return', 'Ann. Return', 'Sharpe', 'Max Drawdown'], 
                         loc='bottom', bbox=[0.55, 0.05, 0.42, 0.20])
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    # --- SUBPLOT 2: Drawdown Chart ---
    ax_dd = fig.add_subplot(gs[1, :])
    ax_dd.fill_between(dds.index, dds['Dynamic_T'], 0, color=COLOR_DRAWDOWN, alpha=0.3, label='Dynamic MaxDD')
    ax_dd.plot(dds.index, dds['Dynamic_T'], color=COLOR_DYNAMIC, linewidth=1, alpha=0.7)
    ax_dd.plot(dds.index, dds[f'Fixed_T{best_is_t}'], color=COLOR_FIXED, linewidth=1, linestyle='--', alpha=0.5)
    ax_dd.set_title("Risk Profile: OOS Drawdowns", fontsize=12, loc='left')
    ax_dd.set_ylim(dds.min().min() * 1.1, 0.02)
    ax_dd.grid(True, axis='y', alpha=0.3)
    
    # --- SUBPLOT 3: Parameter Drift ---
    ax_drift = fig.add_subplot(gs[2, :])
    ax_drift.step(best_t_oos.index, best_t_oos.values, color=COLOR_DYNAMIC, where='post', alpha=0.7, label='Dynamic Chosen T')
    ax_drift.axhline(best_is_t, color=COLOR_FIXED, linestyle='--', alpha=0.8, label='IS Optimal T')
    ax_drift.set_title("Parameter Adaptation During OOS", fontsize=12, loc='left')
    ax_drift.set_xlabel("Time", fontsize=12)
    ax_drift.set_ylabel("T Value", fontsize=12)
    ax_drift.set_ylim(20, 65)
    ax_drift.legend(loc='lower right')
    ax_drift.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(FINAL_REPORT_PATH)
    logger.info(f"OOS Validation Report Saved at {FINAL_REPORT_PATH}")
    
    print(f"\nIS Optimal T (2015-2019): {best_is_t}")
    print("\nOOS Stats (2020-2024):")
    print(pd.DataFrame(stats_data, columns=['Strategy', 'Total Return', 'Ann. Return', 'Sharpe', 'Max Drawdown']))

if __name__ == "__main__":
    main()
