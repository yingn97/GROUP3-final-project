import os
import pandas as pd
import numpy as np

# Add root and src directory to sys.path for importing src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from config import (
    STRATEGY_PARAMS, ALPHA_PATH, IF_CSV, 
    DAILY_PNL_MATRIX_PATH, SIGNAL_MATRIX_PATH, IF_DAILY_PRICE_PATH,
    logger
)

COMMISSION = STRATEGY_PARAMS['commission_rate'] # 0.0004 (Double-sided)
STOP_LOSS = STRATEGY_PARAMS['stop_loss_pct']     # 0.6% -> Total Loss 0.64%

def main():
    logger.info("Loading Alpha data...")
    df_alpha = pd.read_parquet(ALPHA_PATH)
    if 'date' in df_alpha.columns:
        df_alpha.set_index('date', inplace=True)
    
    t_range = range(21, 61)
    df_thresh = df_alpha.rolling(window=60).mean().shift(1)
    
    logger.info("Loading IF prices...")
    df_if = pd.read_csv(IF_CSV, parse_dates=['datetime'])
    df_if.set_index('datetime', inplace=True)
    df_if.sort_index(inplace=True)

    # 1. Advanced Vectorized Price Extraction (Precision Mode)
    logger.info("Calculating backward cumulative high/low for precise stop-loss...")
    # rev_high.loc[t] gives the max price from time t until end of day
    # We group by date to ensure we don't look across days
    df_if['rev_high'] = df_if.groupby(df_if.index.date)['high'].transform(lambda x: x[::-1].cummax()[::-1])
    df_if['rev_low'] = df_if.groupby(df_if.index.date)['low'].transform(lambda x: x[::-1].cummin()[::-1])
    
    # Extract baseline prices
    df_0930 = df_if.at_time('09:30')[['open', 'close', 'rev_high', 'rev_low']]
    df_0930.columns = ['P_0930_open', 'P_0930_close', 'H_0930', 'L_0930']
    df_0930.index = df_0930.index.normalize()
    
    df_1500 = df_if.groupby(df_if.index.date).last()[['close']]
    df_1500.columns = ['P_1500']
    df_1500.index = pd.to_datetime(df_1500.index)

    price_master = df_0930.join(df_1500, how='inner')
    pnl_matrix = pd.DataFrame(index=df_alpha.index)
    signal_matrix = pd.DataFrame(index=df_alpha.index)

    for t in t_range:
        logger.info(f"Processing T={t} (Precise Stop-Loss)...")
        
        # Get P_T and High/Low from T onwards
        target_times = (price_master.index + pd.Timedelta(hours=9, minutes=30+t))
        # Use reindex with nearest to catch the bar at exactly T minutes
        data_at_t = df_if[['close', 'rev_high', 'rev_low']].reindex(target_times, method='nearest')
        data_at_t.index = price_master.index # Date index
        
        p_t = data_at_t['close']
        h_t_onwards = data_at_t['rev_high']
        l_t_onwards = data_at_t['rev_low']

        # Signals
        cond_alpha = df_alpha[f'R_{t}'] > df_thresh[f'R_{t}']
        cond_long = p_t > price_master['P_0930_open']
        cond_short = p_t < price_master['P_0930_open']
        
        signals = pd.Series(0, index=df_alpha.index)
        signals.loc[cond_alpha & cond_long] = 1
        signals.loc[cond_alpha & cond_short] = -1
        
        signal_matrix[t] = signals

        # Join data
        df_t = pd.DataFrame({
            'signal': signals,
            'p_t': p_t,
            'p_1500': price_master['P_1500'],
            'h_post': h_t_onwards,
            'l_post': l_t_onwards
        }).dropna()
        
        # Returns
        raw_ret = (df_t['p_1500'] - df_t['p_t']) / df_t['p_t']
        daily_ret = df_t['signal'] * raw_ret
        
        # PRECISE STOP LOSS
        sl_long = (df_t['l_post'] < df_t['p_t'] * (1 - STOP_LOSS)) & (df_t['signal'] == 1)
        sl_short = (df_t['h_post'] > df_t['p_t'] * (1 + STOP_LOSS)) & (df_t['signal'] == -1)
        
        daily_ret.loc[sl_long | sl_short] = -STOP_LOSS
        
        # Costs (Original backtest uses fixed 0.0002)
        daily_ret.loc[df_t['signal'] != 0] -= COMMISSION
        
        pnl_matrix[t] = daily_ret

    pnl_matrix.to_parquet(DAILY_PNL_MATRIX_PATH)
    signal_matrix.to_parquet(SIGNAL_MATRIX_PATH)
    price_master.to_parquet(IF_DAILY_PRICE_PATH)
    
    logger.info(f"PNL Matrix saved to {DAILY_PNL_MATRIX_PATH}. Shape: {pnl_matrix.shape}")
    logger.info(f"Signal Matrix and Daily Price exported for GUI.")

if __name__ == "__main__":
    main()
