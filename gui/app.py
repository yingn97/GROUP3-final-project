import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import os
import sys
import datetime

# --- Configuration & Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))
from config import (
    BACKTEST_CONFIG, STRATEGY_PARAMS,
    DAILY_PNL_MATRIX_PATH, SIGNAL_MATRIX_PATH, IF_DAILY_PRICE_PATH
)
from performance import calculate_detailed_stats, adjust_pnl_for_commission
from database import BacktestDB

# Base commission from config
ORIGINAL_COMMISSION = STRATEGY_PARAMS.get('commission_rate', 0.0002)

# --- UI Styling ---
st.set_page_config(
    page_title="CTA Alpha Terminal v2.0",
    page_icon="🤖",
    layout="wide",
)

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; font-family: 'Inter', system-ui, sans-serif; }
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #e2e8f0; }
    .metric-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; padding: 0 20px; }
    </style>
""", unsafe_allow_html=True)

# --- Data Loading ---
@st.cache_data
def load_data():
    if not os.path.exists(DAILY_PNL_MATRIX_PATH): return None, None, None
    df_pnl = pd.read_parquet(DAILY_PNL_MATRIX_PATH)
    df_sig = pd.read_parquet(SIGNAL_MATRIX_PATH)
    df_price = pd.read_parquet(IF_DAILY_PRICE_PATH)
    df_pnl.index = pd.to_datetime(df_pnl.index)
    df_sig.index = pd.to_datetime(df_sig.index)
    df_price.index = pd.to_datetime(df_price.index)
    return df_pnl, df_sig, df_price

# Calculations now imported from src/performance.py

# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ Parameters")
    
    df_pnl, df_sig, df_price = load_data()
    
    if df_pnl is not None:
        # Default filters
        start_d, end_d = df_pnl.index.min(), df_pnl.index.max()
        best_t = 25 # Global fallback
        
        # Constrained date selection
        min_date = datetime.date(2015, 1, 1)
        max_date = datetime.date(2024, 12, 31)
        date_range = st.date_input(
            "Training/Optimization Range", 
            [datetime.date(2020, 1, 1), datetime.date(2024, 12, 31)], 
            min_value=min_date, 
            max_value=max_date
        )
        
        # Fixed Slider: added explicit step for fine-grained control
        comm_input = st.slider(
            "Commission Rate (e.g. 0.0002 = 万二)", 
            min_value=0.0, 
            max_value=0.0010, 
            value=0.0002, 
            step=0.0001, 
            format="%.4f"
        )
        
        st.markdown("---")
        mode = st.radio("Selection Mode", ["Manual Fixed T", "WFA Dynamic (1Y Window)"], index=0)
        
        if mode == "Manual Fixed T":
            selected_t = st.slider("Entry Timing (T)", 21, 60, 25)
        else:
            selected_t = 25 # Placeholder
            
        # Optimization Logic for Sidebar Info
        if isinstance(date_range, list) or isinstance(date_range, tuple):
            if len(date_range) == 2:
                start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
                is_pnl = adjust_pnl_for_commission(df_pnl.loc[start_d:end_d], df_sig.loc[start_d:end_d], comm_input)
                is_sharpe = (is_pnl.mean() * 252) / (is_pnl.std() * np.sqrt(252))
                best_t = is_sharpe.idxmax()
                st.success(f"Best T for selected range: **{best_t}**")
                st.caption(f"Sharpe: {is_sharpe[best_t]:.2f}")

# --- Main Logic ---
if df_pnl is not None:
    # 1. Adjust PnL
    df_pnl_adj = adjust_pnl_for_commission(df_pnl, df_sig, comm_input)
    
    # 2. Extract Strategy Returns
    if mode == "Manual Fixed T":
        strat_rets = df_pnl_adj.loc[start_d:end_d, selected_t]
        strat_signals = df_sig.loc[start_d:end_d, selected_t]
        strat_name = f"Fixed T={selected_t}"
    else:
        # Rolling WFA (252D window)
        # Note: For speed, we use the adjusted PnL for rolling calc too
        roll_sharpe = df_pnl_adj.rolling(252).mean() / df_pnl_adj.rolling(252).std() * np.sqrt(252)
        df_selection = roll_sharpe.shift(1)
        
        # Robust selection: handle all-NaN rows (the warmup period) by falling back to the optimized T
        selection = df_selection.apply(
            lambda row: best_t if row.isna().all() else row.idxmax(), axis=1
        )
        
        sub_rets = df_pnl_adj.loc[start_d:end_d]
        sub_sig = df_sig.loc[start_d:end_d]
        sub_sel = selection.loc[start_d:end_d]
        
        strat_rets = pd.Series([sub_rets.loc[d, int(t)] for d, t in sub_sel.items()], index=sub_rets.index)
        strat_signals = pd.Series([sub_sig.loc[d, int(t)] for d, t in sub_sel.items()], index=sub_sig.index)
        strat_name = "WFA Dynamic"

    bench_rets = df_pnl_adj.loc[start_d:end_d, 25] # Hardcoded benchmark
    
    # 3. Calculate Stats
    stats = calculate_detailed_stats(strat_rets, strat_signals)
    bench_stats = calculate_detailed_stats(bench_rets, df_sig.loc[start_d:end_d, 25])
    
    # --- Page Content ---
    t1, t2, t3 = st.tabs(["🚀 Dashboard", "📊 Deep Analysis & Tables", "📜 Trade Audit (SQLite)"])
    
    with t1:
        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Return", f"{stats['Total Return']:.1%}", f"{stats['Total Return']-bench_stats['Total Return']:.1%}")
        k2.metric("Sharpe Ratio", f"{stats['Annualized Return']/strat_rets.std()/np.sqrt(252):.2f}")
        k3.metric("Max Drawdown", f"{stats['Max Drawdown']:.1%}", delta_color="inverse")
        k4.metric("Win Rate", f"{stats['Win Rate']:.1%}")
        
        st.markdown("---")

        # 1. Price & Trading Signals (Full Width)
        st.subheader("1. Price & Trading Signals")
        sub_price = df_price.loc[start_d:end_d]
        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(x=sub_price.index, y=sub_price['P_1500'], name="IF Daily Close", line=dict(color='#94a3b8', width=1)))
        
        # Add Signals
        longs = sub_price[strat_signals == 1]
        shorts = sub_price[strat_signals == -1]
        fig_p.add_trace(go.Scatter(x=longs.index, y=longs['P_1500'], mode='markers', name='Long Entry', marker=dict(symbol='triangle-up', color='#10b981', size=10)))
        fig_p.add_trace(go.Scatter(x=shorts.index, y=shorts['P_1500'], mode='markers', name='Short Entry', marker=dict(symbol='triangle-down', color='#ef4444', size=10)))
        
        # Force x-axis limit to 2024-12-31
        fig_p.update_xaxes(range=[start_d, end_d])
        fig_p.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_p, use_container_width=True)

        # 2. Cumulative Returns (Full Width)
        st.subheader("2. Cumulative Returns")
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(x=stats['Equity Curve'].index, y=stats['Equity Curve'], name=strat_name, line=dict(color='#4f46e5', width=2.5)))
        fig_r.add_trace(go.Scatter(x=bench_stats['Equity Curve'].index, y=bench_stats['Equity Curve'], name="Baseline (T=25)", line=dict(color='#94a3b8', dash='dot')))
        fig_r.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_r, use_container_width=True)

        # 3. Max Drawdown (Full Width)
        st.subheader("3. Max Drawdown (%)")
        fig_d = go.Figure()
        fig_d.add_trace(go.Scatter(x=stats['Drawdown Curve'].index, y=stats['Drawdown Curve']*100, fill='tozeroy', name='DD', line=dict(color='#ef4444')))
        fig_d.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_d, use_container_width=True)
            
        # 4. T Parameter Evolution (Full Period Dynamic Trace)
        st.subheader("4. T Parameter Evolution (Adaptive Strategy Context)")
        st.info("💡 该图表展示 Dynamic 方案在 **2016-2024 全周期** 内的最优参数路径，作为自适应机制的背景参考，不随上方区间缩放而改变。")
        
        # Calculate full period WFA trace for the reference chart
        full_roll_sharpe = df_pnl_adj.rolling(252).mean() / df_pnl_adj.rolling(252).std() * np.sqrt(252)
        df_full_sel = full_roll_sharpe.shift(1)
        
        # Robust selection to avoid 'all NA values' error during first 252 days
        full_selection = df_full_sel.apply(
            lambda row: 25 if row.isna().all() else row.idxmax(), axis=1
        )
        
        # Slice from 2016 onwards as suggested for a cleaner start after warmup
        full_selection = full_selection.loc['2016-01-01':]
        
        fig_t = px.line(x=full_selection.index, y=full_selection.values)
        fig_t.update_traces(line=dict(color='#4f46e5', width=1.5))
        fig_t.update_xaxes(
            dtick="M12", # Every 12 months
            tickformat="%Y",
            tickmode="linear"
        )
        fig_t.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="T Value", xaxis_title="Full Project Timeline (Yearly Ticks)")
        st.plotly_chart(fig_t, use_container_width=True)

    with t2:
        st.subheader("📊 Comprehensive Metrics Table")
        
        # Helper to build a series of stats
        def get_stat_col(r, s):
            st = calculate_detailed_stats(r, s)
            return pd.Series({
                "Total Return": f"{st['Total Return']:.2%}",
                "Ann. Return": f"{st['Annualized Return']:.2%}",
                "Max DD": f"{st['Max Drawdown']:.2%}",
                "Ret/DD Ratio": f"{st['Calmar Ratio']:.2f}",
                "Avg PnL/Trade": f"{st['Avg Trade PnL']:.4%}",
                "Trade Count": str(st['Trade Count']),
                "Win Rate": f"{st['Win Rate']:.2%}",
                "P/L Ratio": f"{st['P/L Ratio']:.2f}",
                "Long Ratio": f"{st['Long Ratio']:.2%}",
                "Avg Daily Ret": f"{st['Avg Daily Return']:.4%}"
            })

        # Summary Table
        summary_df = pd.DataFrame({
            f"Strategy ({strat_name})": get_stat_col(strat_rets, strat_signals),
            "Benchmark (Fixed T=25)": get_stat_col(bench_rets, df_sig.loc[start_d:end_d, 25])
        })
        st.table(summary_df)
        
        st.markdown("---")
        st.subheader("📅 Yearly Performance (Dynamic Strategy)")
        years = strat_rets.index.year.unique()
        yearly_data = {}
        for yr in years:
            yr_rets = strat_rets[strat_rets.index.year == yr]
            yr_sigs = strat_signals[strat_signals.index.year == yr]
            yearly_data[str(yr)] = get_stat_col(yr_rets, yr_sigs)
        
        st.dataframe(pd.DataFrame(yearly_data).T, use_container_width=True)

    with t3:
        st.subheader("📜 Backtest & Trade Journal (SQLite)")
        db = BacktestDB()
        
        # 1. Backtest History
        st.write("### Backtest Run History")
        runs_df = db.get_all_runs()
        if not runs_df.empty:
            st.dataframe(runs_df, use_container_width=True)
            
            # 2. Latest Run Details
            latest_id = runs_df.iloc[0]['run_id']
            st.write(f"### Latest Trade Details (Run #{latest_id})")
            
            # Filters for the journal
            trades_raw = db.get_trades(latest_id)
            if not trades_raw.empty:
                f1, f2 = st.columns(2)
                type_filter = f1.multiselect("Filter by Type", trades_raw['trade_type'].unique())
                
                filtered_trades = trades_raw
                if type_filter:
                    filtered_trades = trades_raw[trades_raw['trade_type'].isin(type_filter)]
                
                st.dataframe(filtered_trades, use_container_width=True)
                
                # Simple count chart
                fig_tc = px.bar(
                    filtered_trades['trade_type'].value_counts(),
                    title="Trade Type Distribution",
                    labels={'value': 'Count', 'index': 'Type'},
                    color_discrete_sequence=['#4f46e5']
                )
                fig_tc.update_layout(height=300)
                st.plotly_chart(fig_tc, use_container_width=True)
            else:
                st.info("No trades found for the latest run.")
        else:
            st.warning("No backtest runs found in SQLite. Run `scripts/02_backtest_engine.py` first.")

else:
    st.error("Data files not found. Please run scripts/03_generate_pnl_matrix.py first.")
