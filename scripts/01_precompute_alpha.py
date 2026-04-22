import os
import polars as pl
import numpy as np
import datetime
from tqdm import tqdm
import logging
from joblib import Parallel, delayed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add root and src directory to sys.path for importing src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from config import STOCKS_DIR, ALPHA_PATH, logger

# Paths
STOCK_DB = STOCKS_DIR # Use standardized name
OUTPUT_PATH = ALPHA_PATH

def calculate_r_for_window(price_matrix):
    """
    Optimized PCA calculation for small T, large N.
    X is (N, T). M = X^T X is (T, T).
    """
    if price_matrix.shape[1] < 2:
        return None
    
    # price_matrix: (N_stocks, T_minutes)
    # Normalize by the first column (9:30 open)
    first_prices = price_matrix[:, 0].reshape(-1, 1)
    mask = (first_prices.flatten() > 0)
    if not any(mask): return None
    
    P_norm = price_matrix[mask] / first_prices[mask]
    
    # Center the normalized data
    X = P_norm - np.mean(P_norm, axis=1, keepdims=True)
    
    try:
        # M = X.T @ X is (T, T)
        M = np.dot(X.T, X)
        eigenvalues = np.linalg.eigvalsh(M)
        max_lambda = eigenvalues[-1]
        sum_lambda = np.sum(eigenvalues)
        if sum_lambda <= 1e-9: return None
        return (max_lambda / sum_lambda) * 100.0
    except:
        return None

def process_day(date_str):
    """
    Process a single day's data using Polars for speed.
    """
    p_path = os.path.join(STOCK_DB, f"date={date_str}", "data.parquet")
    if not os.path.exists(p_path):
        return None
    
    try:
        # Use Polars for super-fast reading and pivoting
        # We only need 'code', 'trade_time', and 'close'
        df = pl.read_parquet(p_path, columns=['code', 'trade_time', 'close'])
        
        if df.is_empty(): 
            return None
        
        # Pivot to (Minute, Stock)
        # Polars pivot is significantly faster than Pandas
        day_pivot = df.pivot(
            on='code',
            index='trade_time',
            values='close'
        ).sort('trade_time')
        
        # Extract the first 61 minutes (09:30 to 10:30 approx)
        day_pivot = day_pivot.head(61)
        
        if len(day_pivot) < 21: 
            return None
        
        # Drop trade_time column and convert to numpy for PCA (N_stocks, T_total)
        # Transpose so it is (Stocks, Minutes)
        data_values = day_pivot.drop('trade_time').to_numpy().T
        
        # Filter out stocks with NaN if any (PCA needs clean matrix)
        # data_values shape: (N, T)
        valid_mask = ~np.any(np.isnan(data_values), axis=1)
        data_values = data_values[valid_mask]
        
        if data_values.shape[0] < 10: # Minimum stocks required
            return None

        results = {}
        for t in range(21, 61):
            if t <= data_values.shape[1]:
                # Window from 0 to t
                window = data_values[:, :t]
                r = calculate_r_for_window(window)
                results[f'R_{t}'] = r
        
        results['date'] = date_str
        return results
    except Exception as e:
        logger.error(f"Error processing {date_str}: {e}")
        return None

def main():
    logger.info("Initializing High-Performance Polars Alpha Pre-computation...")
    
    if not os.path.exists(STOCK_DB):
        logger.error(f"Source DB not found at {STOCK_DB}")
        return

    date_folders = sorted([d for d in os.listdir(STOCK_DB) if d.startswith('date=')])
    dates = [d.split('=')[1] for d in date_folders]
    
    logger.info(f"Processing {len(dates)} days using Polars + Joblib...")

    # Polars is internally multithreaded, but for I/O bound tasks like reading 2700 small files,
    # multprocessing is still beneficial to saturate SSD I/O and CPU.
    num_workers = min(os.cpu_count(), 8)
    daily_results = Parallel(n_jobs=num_workers)(
        delayed(process_day)(d) for d in tqdm(dates)
    )
    
    # 3. Collect and Save
    valid_results = [r for r in daily_results if r is not None]
    if not valid_results:
        logger.warning("No valid results found. Parquet not saved.")
        return
        
    final_df = pl.DataFrame(valid_results)
    
    # Convert date and sort
    final_df = final_df.with_columns(
        pl.col("date").str.to_date()
    ).sort("date")
    
    # Save to Parquet
    final_df.write_parquet(OUTPUT_PATH)
    logger.info(f"DONE! Polars-Optimized Alpha Matrix saved to {OUTPUT_PATH}")
    logger.info(f"Shape: {final_df.shape}")

if __name__ == "__main__":
    main()
