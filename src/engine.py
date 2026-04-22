import queue
import time
import pandas as pd
from tqdm import tqdm
from config import logger

class BacktestEngine(object):
    """
    The BacktestEngine coordinates the interaction between 
    DataHandler, Strategy, Portfolio and ExecutionHandler.
    """
    def __init__(self, events, bars, strategy, portfolio, execution):
        self.events = events
        self.bars = bars
        self.strategy = strategy
        self.portfolio = portfolio
        self.execution = execution

    def run(self):
        """
        Executes the backtest loop.
        """
        logger.info("Engine: Starting backtest event loop...")
        
        from config import BACKTEST_CONFIG
        end_date = pd.to_datetime(BACKTEST_CONFIG.get('end_date', '2099-12-31'))

        # Initialize progress bar
        pbar = tqdm(total=self.bars.total_bars, desc="Backtesting")

        while True:
            # 1. Update market bars
            if self.bars.continue_backtest:
                self.bars.update_bars()
                pbar.update(1)
                
                # Check End Date
                cur_dt = self.bars.get_latest_bar_datetime(self.bars.symbol_list[0])
                if cur_dt and cur_dt > end_date:
                    logger.info(f"Engine: Reached end_date {end_date}. Stopping.")
                    self.bars.continue_backtest = False
                    break
                if self.bars.bar_index % 1000 == 0:
                    logger.info(f"Engine: Progress - {self.bars.bar_index} bars processed")
            else:
                break

            # 2. Handle events in the queue
            while True:
                try:
                    event = self.events.get(False)
                except queue.Empty:
                    break
                else:
                    if event is not None:
                        if event.type == 'MARKET':
                            self.strategy.calculate_signals(event)
                            self.portfolio.update_timeindex(event)
                        elif event.type == 'SIGNAL':
                            self.portfolio.on_signal(event)
                        elif event.type == 'ORDER':
                            self.execution.execute_order(event)
                        elif event.type == 'FILL':
                            self.portfolio.update_positions_from_fill(event)
                            self.portfolio.update_holdings_from_fill(event)
        
        logger.info("Engine: Event loop finished.")
