import os
import pandas as pd
from collections import deque
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from config import logger, BACKTEST_CONFIG

from event import MarketEvent

class DataHandler(object):
    """
    DataHandler is an abstract base class providing an interface for
    all subsequent (inherited) data handlers (both historic and live).

    The goal of a (derived) DataHandler object is to output a generated
    set of bars (OLHCVI) for each symbol requested. 
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def get_latest_bar(self, symbol):
        """
        Returns the last bar updated.
        """
        raise NotImplementedError("Should implement get_latest_bar()")

    @abstractmethod
    def get_latest_bars(self, symbol, N=1):
        """
        Returns the last N bars updated.
        """
        raise NotImplementedError("Should implement get_latest_bars()")

    @abstractmethod
    def get_latest_bar_datetime(self, symbol):
        """
        Returns a Python datetime object for the last bar.
        """
        raise NotImplementedError("Should implement get_latest_bar_datetime()")

    @abstractmethod
    def get_latest_bar_value(self, symbol, val_type):
        """
        Returns one of the Open, High, Low, Close, Volume or OI
        from the last bar.
        """
        raise NotImplementedError("Should implement get_latest_bar_value()")

    @abstractmethod
    def update_bars(self):
        """
        Pushes the latest bars to the bars_symbol_data structure
        for all symbols in the symbol list.
        """
        raise NotImplementedError("Should implement update_bars()")


from collections import deque

class HistoricCSVDataHandler(DataHandler):
    """
    HistoricCSVDataHandler is designed to read CSV files for
    each requested symbol from disk and provide an interface
    to obtain the "latest" bar in a manner identical to a live
    trading interface. 
    """

class HistoricCSVDataHandler(DataHandler):
    """
    HistoricCSVDataHandler is designed to read partitioned Parquet and CSV files
    from the project's specific directory structure.
    """

    def __init__(self, events, csv_dir, symbol_list):
        self.events = events
        self.csv_dir = csv_dir
        self.symbol_list = symbol_list

        self.symbol_data = {}
        self.latest_symbol_data = {}
        self.continue_backtest = True       
        self.bar_index = 0
        self.total_bars = 0

        self._load_data()

    def _load_data(self):
        """
        Loads IF.csv and pre-computed alpha factor file.
        """
        logger.info(f"DataHandler: Loading IF data and pre-computed Alpha from {self.csv_dir}...")
        start_date_str = BACKTEST_CONFIG['start_date']
        end_date_str = BACKTEST_CONFIG['end_date']
        
        # 1. Load IF.csv
        if_path = os.path.join(self.csv_dir, "IF.csv")
        if os.path.exists(if_path):
            df_if = pd.read_csv(if_path)
            df_if.columns = [c.lower() for c in df_if.columns]
            df_if['datetime'] = pd.to_datetime(df_if['datetime'])
            df_if.set_index('datetime', inplace=True)
            df_if.sort_index(inplace=True)
        else:
            logger.error(f"DataHandler: IF.csv not found at {if_path}!")
            self.continue_backtest = False
            return

        # 2. Load Pre-computed Alpha (Daily Table)
        alpha_path = os.path.join(self.csv_dir, "alpha_consistency_daily.parquet")
        if os.path.exists(alpha_path):
            logger.info("DataHandler: Loading daily pre-computed Alpha factor matrix...")
            self.alpha_daily_df = pd.read_parquet(alpha_path)
            # Ensure the index is datetime for easy slicing later
            if 'date' in self.alpha_daily_df.columns:
                self.alpha_daily_df.set_index('date', inplace=True)
            if not isinstance(self.alpha_daily_df.index, pd.DatetimeIndex):
                self.alpha_daily_df.index = pd.to_datetime(self.alpha_daily_df.index)
        else:
            logger.warning(f"DataHandler: alpha_consistency_daily.parquet not found at {alpha_path}. Strategy may fail.")
            self.alpha_daily_df = None

        # Filter IF by date
        df_if = df_if.loc[start_date_str:end_date_str]
        
        # Check for duplicates
        duplicates = df_if.index.duplicated().sum()
        if duplicates > 0:
            logger.warning(f"DataHandler: Found {duplicates} duplicate timestamps. Dropping them.")
            df_if = df_if[~df_if.index.duplicated(keep='first')]

        self.symbol_data['IF'] = df_if
        self.symbol_list = ['IF'] 
        self.total_bars = len(df_if)
        
        logger.info(f"DataHandler: Loaded {self.total_bars} IF bars.")
        
        # Initialize itertuples and deque
        for s in self.symbol_list:
            self.symbol_data[s] = self.symbol_data[s].itertuples()
            self.latest_symbol_data[s] = deque(maxlen=300)

        logger.info("DataHandler: Data loading complete.")

    def _get_new_bar(self, symbol):
        """
        Returns the latest bar from the data feed.
        """
        for b in self.symbol_data[symbol]:
            yield b

    def get_latest_bar(self, symbol):
        try:
            return self.latest_symbol_data[symbol][-1]
        except (KeyError, IndexError):
            logger.debug(f"Symbol {symbol} or bar data not available.")
            raise

    def get_latest_bars(self, symbol, N=1):
        try:
            # deque slicing is slightly different, convert to list or use itertools
            # Since N is small (160), list conversion is okay
            return list(self.latest_symbol_data[symbol])[-N:]
        except KeyError:
            logger.debug(f"Symbol {symbol} not available.")
            raise

    def get_latest_bar_datetime(self, symbol):
        try:
            # itertuples: the first element (index 0) is the Index (datetime)
            return self.latest_symbol_data[symbol][-1][0]
        except (KeyError, IndexError):
            return None

    def get_latest_bar_value(self, symbol, val_type):
        try:
            # itertuples provides attributes like .close, .open
            return getattr(self.latest_symbol_data[symbol][-1], val_type)
        except (KeyError, IndexError, AttributeError):
            return None

    def update_bars(self):
        """
        Pushes the latest bar to the latest_symbol_data structure
        for all symbols in the symbol list.
        """
        for s in self.symbol_list:
            try:
                bar = next(self.symbol_data[s])
            except StopIteration:
                self.continue_backtest = False
            else:
                if bar is not None:
                    self.latest_symbol_data[s].append(bar)
        self.bar_index += 1
        self.events.put(MarketEvent())
