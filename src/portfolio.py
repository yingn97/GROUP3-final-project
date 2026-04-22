import os
import datetime
import pandas as pd
import numpy as np

from config import logger
from event import OrderEvent
from performance import create_sharpe_ratio, create_drawdowns

class Portfolio(object):
    """
    The Portfolio class handles the positions and market value of all
    instruments at a resolution of a "bar", i.e. second, minute, 5-min, etc.
    """

    def __init__(self, bars, events, start_date, initial_capital=1000000.0):
        self.bars = bars
        self.events = events
        self.symbol_list = self.bars.symbol_list
        self.start_date = start_date
        self.initial_capital = initial_capital
        self.multiplier = 300.0 # IF multiplier

        # P2 Memory Optimization: Only track tradeable symbols in positions/holdings
        # We don't need to store 300+ stock positions of 0 every minute.
        self.tradeable_symbols = [s for s in self.symbol_list if s == 'IF']
        
        self.all_positions = self._construct_all_positions()
        self.current_positions = dict((k, v) for k, v in [(s, 0) for s in self.tradeable_symbols])

        self.all_holdings = self._construct_all_holdings()
        self.current_holdings = self._construct_current_holdings()
        
        # Track current position risk
        self.position_risk = {'entry_price': 0, 'prev_entry_price': 0, 'qty': 0, 'prev_qty': 0, 'stopped_out_today': False, 'last_date': None}
        
        # Track all trades
        self.trades = []
        # Internal flag: reason for the most recent exit order
        self._last_exit_reason = 'CLOSE'

    def _construct_all_positions(self):
        """
        Constructs the positions list using the start_date
        to determine when the time index begins.
        """
        d = dict((k, v) for k, v in [(s, 0) for s in self.tradeable_symbols])
        d['datetime'] = self.start_date
        return [d]

    def _construct_all_holdings(self):
        """
        Constructs the holdings list using the start_date
        to determine when the time index begins.
        """
        d = dict((k, v) for k, v in [(s, 0.0) for s in self.tradeable_symbols])
        d['datetime'] = self.start_date
        d['cash'] = self.initial_capital
        d['commission'] = 0.0
        d['total'] = self.initial_capital
        return [d]

    def _construct_current_holdings(self):
        """
        This constructs the dictionary which will hold the instantaneous
        holdings of the portfolio.
        """
        d = dict((k, v) for k, v in [(s, 0.0) for s in self.tradeable_symbols])
        d['cash'] = self.initial_capital
        d['commission'] = 0.0
        d['total'] = self.initial_capital
        return d

    def update_timeindex(self, event):
        latest_datetime = self.bars.get_latest_bar_datetime(self.symbol_list[0])
        cur_date = latest_datetime.date()

        # Update positions
        dp = {'datetime': latest_datetime}
        for s in self.tradeable_symbols:
            dp[s] = self.current_positions[s]
        self.all_positions.append(dp)

        # Update holdings
        dh = {'datetime': latest_datetime}
        dh['cash'] = self.current_holdings['cash']
        dh['commission'] = self.current_holdings['commission']
        dh['total'] = self.current_holdings['cash']

        for s in self.tradeable_symbols:
            pnl = 0
            if self.current_positions[s] != 0:
                cur_price = self.bars.get_latest_bar_value(s, "close")
                entry_price = self.position_risk['entry_price']
                
                # Unrealized PnL = (Current - Entry) * Qty * Multiplier
                pnl = (cur_price - entry_price) * self.current_positions[s] * self.multiplier
            dh[s] = pnl
            dh['total'] += pnl
        
        self.all_holdings.append(dh)
        self.current_holdings['total'] = dh['total']
        
        # Check Stop Loss (0.6% of entry price)
        self._check_risk_management(latest_datetime, cur_date)

    def _check_risk_management(self, cur_time, cur_date):
        """
        Implements 0.6% daily stop loss and end-of-day exit.
        """
        # Reset stopped_out status on new day
        if self.position_risk['last_date'] != cur_date:
            self.position_risk['stopped_out_today'] = False
            self.position_risk['last_date'] = cur_date

        if self.current_positions['IF'] != 0:
            if self.position_risk['stopped_out_today']: return
            
            entry_price = self.position_risk['entry_price']
            cur_price = self.bars.get_latest_bar_value('IF', 'close')
            
            # PnL in percentage relative to entry
            pnl_points = (cur_price - entry_price) * (1 if self.current_positions['IF'] > 0 else -1)
            pnl_pct = pnl_points / entry_price
            
            # 1. Intra-day Stop Loss (0.6%)
            if pnl_pct < -0.006:
                logger.warning(f"Risk Management: Stop Loss triggered at {cur_time}. PnL: {pnl_pct:.2%}")
                self._last_exit_reason = 'STOP_LOSS'
                self._generate_exit_order('IF')
                self.position_risk['stopped_out_today'] = True
            
            # 2. End of Day Exit (15:00)
            elif cur_time.time() >= datetime.time(15, 0):
                logger.info(f"Risk Management: End of Day exit at {cur_time}")
                self._last_exit_reason = 'EOD_EXIT'
                self._generate_exit_order('IF')

    def _generate_exit_order(self, symbol):
        direction = 'SELL' if self.current_positions[symbol] > 0 else 'BUY'
        order = OrderEvent(symbol, 'MKT', abs(self.current_positions[symbol]), direction)
        self.events.put(order)

    def update_positions_from_fill(self, fill):
        """
        Takes a FillEvent object and updates the current positions
        to reflect the new quantity.
        """
        fill_dir = 0
        if fill.direction == 'BUY':
            fill_dir = 1
        if fill.direction == 'SELL':
            fill_dir = -1

        self.position_risk['prev_qty'] = self.current_positions[fill.symbol]
        self.position_risk['prev_entry_price'] = self.position_risk['entry_price']
        
        self.current_positions[fill.symbol] += fill_dir * fill.quantity
        
        # If direction changed or opening new, update entry price
        if self.current_positions[fill.symbol] != 0:
            self.position_risk['entry_price'] = fill.fill_cost / (fill.quantity * self.multiplier)
            self.position_risk['qty'] = self.current_positions[fill.symbol]

    def update_holdings_from_fill(self, fill):
        """
        Calculates realized PnL upon closing a position.
        """
        # 1. Deduct commission from cash
        self.current_holdings['commission'] += fill.commission
        self.current_holdings['cash'] -= fill.commission
        
        # ── Determine trade_type label ────────────────────────────────────
        prev_qty = self.position_risk.get('prev_qty', 0)
        if prev_qty == 0:
            # Opening a brand-new position
            trade_type = 'OPEN_LONG' if fill.direction == 'BUY' else 'OPEN_SHORT'
        else:
            # Closing or reversing — use the exit reason flag set by risk mgmt
            trade_type = getattr(self, '_last_exit_reason', 'CLOSE')
            self._last_exit_reason = 'CLOSE'  # reset after consuming

        # Log trade (with type)
        self.trades.append({
            'trade_time':  fill.timeindex,
            'symbol':      fill.symbol,
            'direction':   fill.direction,
            'quantity':    fill.quantity,
            'price':       fill.fill_cost / (fill.quantity * self.multiplier),
            'fill_cost':   fill.fill_cost,
            'commission':  fill.commission,
            'trade_type':  trade_type,
            'realized_pnl': 0.0,  # will be computed by 02_backtest_engine.py
        })
        
        # 2. Settle PnL into cash when closing or reversing
        # Case 1: Total exit (qty is now 0)
        # Case 2: Reversal (qty sign changed)
        # For simplicity, we calculate realized PnL based on the entry price
        # and the portion of the position that was closed.
        
        # We need to know previous quantity. Let's assume we were +/- 1.
        # If fill qty is 1 and now 0, we closed 1.
        # If fill qty is 2 and now -/+ 1, we closed 1 and opened 1.
        
        entry_price = self.position_risk['prev_entry_price']
        exit_price = fill.fill_cost / (fill.quantity * self.multiplier)
        # entry_dir was the direction of the PREVIOUS quantity
        entry_dir = 1 if self.position_risk['prev_qty'] > 0 else -1
        
        # Amount of position closed
        closed_qty = 0
        if self.current_positions[fill.symbol] == 0:
            closed_qty = fill.quantity
        elif (self.position_risk['prev_qty'] > 0 and self.current_positions[fill.symbol] < 0) or \
             (self.position_risk['prev_qty'] < 0 and self.current_positions[fill.symbol] > 0):
            closed_qty = abs(self.position_risk['prev_qty']) # Closed the original part
            
        if closed_qty > 0 and self.position_risk['prev_qty'] != 0:
            realized_pnl = (exit_price - entry_price) * entry_dir * closed_qty * self.multiplier
            self.current_holdings['cash'] += realized_pnl
            logger.info(f"Trade Closed/Reversed: Realized PnL = {realized_pnl:.2f}")

    def on_signal(self, event):
        """
        Acts on a SignalEvent to generate an OrderEvent.
        Supports position reversal (LONG <-> SHORT).
        """
        cur_date = event.datetime.date()
        if self.position_risk.get('stopped_out_today', False) and self.position_risk.get('last_date') == cur_date:
            return
            
        cur_pos = self.current_positions.get(event.symbol, 0)
        
        if event.signal_type == 'LONG':
            if cur_pos <= 0:
                # Reverse if short (-1 -> 1) or open if flat (0 -> 1)
                qty = 2 if cur_pos < 0 else 1
                order = OrderEvent(event.symbol, 'MKT', qty, 'BUY')
                self.events.put(order)
        elif event.signal_type == 'SHORT':
            if cur_pos >= 0:
                # Reverse if long (1 -> -1) or open if flat (0 -> -1)
                qty = 2 if cur_pos > 0 else 1
                order = OrderEvent(event.symbol, 'MKT', qty, 'SELL')
                self.events.put(order)
        elif event.signal_type == 'EXIT':
            if cur_pos != 0:
                direction = 'SELL' if cur_pos > 0 else 'BUY'
                order = OrderEvent(event.symbol, 'MKT', abs(cur_pos), direction)
                self.events.put(order)

    def create_equity_curve_dataframe(self):
        """
        Creates a pandas DataFrame from the all_holdings list of dictionaries.
        """
        curve = pd.DataFrame(self.all_holdings)
        if curve.empty:
            return pd.DataFrame(columns=['datetime', 'cash', 'commission', 'total', 'returns', 'equity_curve'])
        
        # Deduplicate before setting index to avoid ValueError: cannot reindex on an axis with duplicate labels
        curve = curve.drop_duplicates(subset='datetime', keep='last')
        
        curve.set_index('datetime', inplace=True)
        
        # Standard minute-level returns for equity curve
        curve['returns'] = curve['total'].pct_change()
        curve['equity_curve'] = (1.0 + curve['returns']).cumprod()
        curve['equity_curve'] = curve['equity_curve'].fillna(1.0)
        
        return curve

    def output_summary_stats(self):
        """
        Creates a list of summary statistics for the portfolio such
        as Sharpe Ratio and drawdown information.
        """
        curve = self.create_equity_curve_dataframe()
        total_return = curve['equity_curve'].iloc[-1]
        returns = curve['returns']
        pnl = curve['equity_curve']
        
        sharpe_ratio = create_sharpe_ratio(returns)
        max_dd, dd_duration = create_drawdowns(pnl)
        
        stats = [("Total Return", "%0.2f%%" % ((total_return - 1.0) * 100.0)),
                 ("Sharpe Ratio", "%0.2f" % sharpe_ratio),
                 ("Max Drawdown", "%0.2f%%" % (max_dd * 100.0)),
                 ("Drawdown Duration", "%d" % dd_duration)]
        return stats

    def flush_trades_to_db(self, db, run_id: int):
        """
        Bulk-write all trades accumulated in self.trades to SQLite.
        Call this once after the backtest loop completes.

        Parameters
        ----------
        db      : BacktestDB instance (from src.database)
        run_id  : The run_id returned by db.start_run()
        """
        if not self.trades:
            logger.warning("[Portfolio] flush_trades_to_db: no trades to flush.")
            return
        db.log_trades_bulk(run_id, self.trades)
        logger.info(f"[Portfolio] {len(self.trades)} trades flushed to DB run_id={run_id}.")
