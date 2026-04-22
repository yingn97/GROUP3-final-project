import os

# Base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data Paths
DATA_DIR = os.path.join(BASE_DIR, "data")
STOCKS_DIR = os.path.join(DATA_DIR, "stocks")
IF_CSV = os.path.join(DATA_DIR, "IF.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PARQUET_DIR = os.path.join(OUTPUT_DIR, "parquet")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "trading_system.db")

# Pre-computed Parquet Paths
ALPHA_PATH = os.path.join(DATA_DIR, "alpha_consistency_daily.parquet")
DAILY_PNL_MATRIX_PATH = os.path.join(DATA_DIR, "daily_pnl_matrix.parquet")
SIGNAL_MATRIX_PATH = os.path.join(DATA_DIR, "signal_matrix.parquet")
IF_DAILY_PRICE_PATH = os.path.join(DATA_DIR, "if_daily.parquet")

# Strategy Parameters
STRATEGY_PARAMS = {
    'T_minutes': 24,          # Set to T=24 for user request
    'window_L': 160,          # Covariance window length
    'threshold_window': 60,   # Rolling mean period for R indicator
    'stop_loss_pct': 0.006,   # 0.6% daily stop loss
    'multiplier': 300.0,      # IF multiplier
    'commission_rate': 0.0002 # Double-sided万分之二 (simplified as 0.0002 per fill_cost)
}

# Backtest Configuration
BACKTEST_CONFIG = {
    'initial_capital': 1000000.0,
    'start_date': "2015-01-05",      # Start from available stock data
    'end_date': "2016-07-31",        # End of requested range
    'slippage': 0.0,
}

# ── Unified IS/OOS Experimental Protocol ─────────────────────────────────
# ALL validation scripts (04, 05, GUI) MUST use these dates.
# Changing the split point here automatically propagates everywhere.
EXPERIMENT_PROTOCOL = {
    'is_start':  "2015-01-01",   # In-Sample training begins
    'is_end':    "2019-12-31",   # In-Sample training ends
    'oos_start': "2020-01-01",   # Out-of-Sample validation begins
    'oos_end':   "2024-12-31",   # Out-of-Sample validation ends
}

# Logging Configuration
import logging
LOG_LEVEL = logging.INFO
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=LOG_LEVEL
)
logger = logging.getLogger("TradingSystem")
