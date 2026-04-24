import numpy as np
import pandas as pd

def create_sharpe_ratio(returns, periods=252):
    """
    Create the Sharpe ratio for the strategy, based on a 
    benchmark of zero (i.e. no risk-free rate information).
    
    Default periods is 252 (daily). For 1-min data usage, 
    use 252 * 240.
    """
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return np.sqrt(periods) * (np.mean(returns) / np.std(returns))

def create_drawdowns(equity_curve):
    """
    Calculate the largest peak-to-trough drawdown of the PnL curve
    as well as the duration of the drawdown.
    """
    # P4 Performance: Use Pandas vectorization instead of for-loop
    # High Water Mark
    hwm = equity_curve.cummax()
    
    # Max Drawdown should be calculated as (HWM - Equity) / HWM for percentage
    drawdown_pct = (hwm - equity_curve) / hwm
    
    # Duration: This is slightly harder to vectorize purely but can be done 
    # by identifying stretches where drawdown > 0
    is_in_drawdown = drawdown_pct > 0
    
    # Use a trick to calculate duration: group by switches entre 0 and >0
    if not is_in_drawdown.any():
        return -drawdown_pct.max(), 0
        
    # Calculate group IDs for contiguous drawdown periods
    drawdown_groups = (is_in_drawdown != is_in_drawdown.shift()).cumsum()
    durations = is_in_drawdown[is_in_drawdown].groupby(drawdown_groups).transform('count')
    
    # Return as negative value as per user request
    return -drawdown_pct.max(), durations.max() if not durations.empty else 0

def display_performance_report(equity_curve, trades=None):
    """
    Prints a detailed performance summary of the backtest.
    """
    returns = equity_curve['returns'].dropna()
    total_return = (equity_curve['total'].iloc[-1] - equity_curve['total'].iloc[0]) / equity_curve['total'].iloc[0]
    sharpe = create_sharpe_ratio(returns)
    max_dd, dd_duration = create_drawdowns(equity_curve['total'])
    
    print("\n" + "="*50)
    print("      STRATEGY PERFORMANCE SUMMARY      ")
    print("="*50)
    print(f"Total Return:         {total_return:.2%}")
    print(f"Annualized Return:    {returns.mean() * 252:.2%}")
    print(f"Sharpe Ratio:         {sharpe:.2f}")
    print(f"Max Drawdown:         {max_dd:.2%}")
    print(f"Max Drawdown Duration: {dd_duration} bars")
    
    if trades is not None and not trades.empty:
        total_trades = len(trades)
        # Assuming trades dataframe has a 'pnl' column if we process it
        win_rate = None
        if 'pnl' in trades.columns:
            wins = len(trades[trades['pnl'] > 0])
            win_rate = wins / total_trades if total_trades > 0 else 0
            print(f"Total Trades:         {total_trades}")
            print(f"Win Rate:             {win_rate:.2%}")
    else:
        total_trades = None
        win_rate = None
    
    print("="*50 + "\n")

    return {
        'total_return':  total_return,
        'annual_return': float(returns.mean() * 252),
        'sharpe_ratio':  sharpe,
        'max_drawdown':  max_dd,
        'win_rate':      win_rate,
        'total_trades':  total_trades,
    }

def calculate_detailed_stats(rets, signals=None):
    """
    Calculates a comprehensive dictionary of performance metrics.
    Used by both GUI and standalone analysis scripts.
    """
    if len(rets) == 0: 
        return {
            "Total Return": 0.0, "Annualized Return": 0.0, "Sharpe Ratio": 0.0,
            "Max Drawdown": 0.0, "Calmar Ratio": 0.0, "Avg Trade PnL": 0.0,
            "Trade Count": 0, "Win Rate": 0.0, "P/L Ratio": 0.0, "Long Ratio": 0.0,
            "Avg Daily Return": 0.0, "Equity Curve": pd.Series([1.0]), "Drawdown Curve": pd.Series([0.0])
        }
    
    # Equity Curve
    eq = (1 + rets).cumprod()
    total_ret = eq.iloc[-1] - 1
    
    # Annualized Metrics
    ann_ret = rets.mean() * 252
    ann_vol = rets.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol != 0 else 0
    
    # Drawdown
    peak = eq.cummax()
    dd = (eq - peak) / peak
    max_dd = dd.min()
    
    # Trade Stats (Only if signals provided)
    if signals is not None:
        trade_mask = (signals != 0)
        trades_pnl = rets[trade_mask]
        num_trades = int(trade_mask.sum())
        
        win_rate = (trades_pnl > 0).sum() / num_trades if num_trades > 0 else 0
        avg_trade_pnl = trades_pnl.mean() if num_trades > 0 else 0
        
        # Profit/Loss Ratio
        avg_gain = trades_pnl[trades_pnl > 0].mean() if (trades_pnl > 0).any() else 0
        avg_loss = abs(trades_pnl[trades_pnl < 0].mean()) if (trades_pnl < 0).any() else 0
        pl_ratio = avg_gain / avg_loss if avg_loss != 0 else 0
        
        # Long/Short Ratio
        num_long = (signals == 1).sum()
        long_ratio = num_long / num_trades if num_trades > 0 else 0
    else:
        num_trades = 0
        win_rate = 0
        avg_trade_pnl = 0
        pl_ratio = 0
        long_ratio = 0
    
    return {
        "Total Return": total_ret,
        "Annualized Return": ann_ret,
        "Sharpe Ratio": sharpe,
        "Max Drawdown": max_dd,
        "Calmar Ratio": ann_ret / abs(max_dd) if max_dd != 0 else 0,
        "Avg Trade PnL": avg_trade_pnl,
        "Trade Count": num_trades,
        "Win Rate": win_rate,
        "P/L Ratio": pl_ratio,
        "Long Ratio": long_ratio,
        "Avg Daily Return": rets.mean(),
        "Equity Curve": eq,
        "Drawdown Curve": dd
    }

def adjust_pnl_for_commission(df_pnl, df_sig, new_comm, original_comm=0.0004):
    """
    Adjusts a PnL matrix/series based on new commission rate.
    Uses the logic: NewPnL = OldPnL + OriginalComm - NewComm (for each trade).
    """
    adj_matrix = df_pnl.copy()
    traded_mask = (df_sig != 0)
    adj_matrix[traded_mask] += (original_comm - new_comm)
    return adj_matrix
