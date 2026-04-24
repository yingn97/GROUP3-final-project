import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
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
from i18n import tr

# --- UI Styling & Config ---
st.set_page_config(
    page_title=tr('title'),
    page_icon="🤖",
    layout="wide",
)

# Colors & Style System
PRIMARY_COLOR = '#4f46e5'
POSITIVE_COLOR = '#10b981'
NEGATIVE_COLOR = '#ef4444'
NEUTRAL_COLOR = '#64748b'
CARD_BG = '#ffffff'

st.markdown(f"""
    <style>
    .stApp {{ background-color: #f8fafc; font-family: 'Inter', system-ui, sans-serif; font-size: 0.95rem; font-weight: 400; }}
    h1, h2, h3 {{ font-weight: 700 !important; color: #1e293b; }}
    [data-testid="stSidebar"] {{ background-color: #ffffff !important; border-right: 1px solid #e2e8f0; }}
    .metric-card {{ background-color: {CARD_BG}; padding: 18px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 12px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 20px; padding: 0 10px; border-bottom: 1px solid #e2e8f0; }}
    .stTabs [data-baseweb="tab-list"] button {{ font-size: 1.0rem; font-weight: 600; padding: 12px 0; }}
    div[data-testid="stMetricValue"] {{ font-size: 1.8rem; font-weight: 800; color: {PRIMARY_COLOR}; }}
    .stTable {{ font-size: 0.9rem; }}
    /* Compact scrollbar */
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
    </style>
""", unsafe_allow_html=True)

# --- Top Header with Language Switch ---
h_col1, h_col2 = st.columns([10, 1.5])
with h_col1:
    st.title(tr('title'))
with h_col2:
    st.session_state.lang = st.selectbox("", ['English', '中文'], index=0 if st.session_state.get('lang', 'English') == 'English' else 1, label_visibility="collapsed")

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

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"### {tr('sidebar_params')}")
    
    df_pnl, df_sig, df_price = load_data()
    
    if df_pnl is not None:
        # Date range limits
        min_date = datetime.date(2015, 1, 1)
        max_date = datetime.date(2024, 12, 31)

        # --- Helper functions for 2-way sync ---
        def on_slider_change():
            st.session_state.start_input = st.session_state.total_slider[0]
            st.session_state.end_input = st.session_state.total_slider[1]

        def on_input_change():
            # Clamp inputs to valid range
            s = max(min_date, min(max_date, st.session_state.start_input))
            e = max(min_date, min(max_date, st.session_state.end_input))
            if s > e: s, e = e, s
            st.session_state.total_slider = (s, e)

        def on_split_slider_change():
            st.session_state.split_input = st.session_state.split_date_slider

        def on_split_input_change():
            st.session_state.split_date_slider = st.session_state.split_input

        def on_t_slider_change():
            st.session_state.t_input = st.session_state.t_slider

        def on_t_input_change():
            st.session_state.t_slider = st.session_state.t_input

        # Initialize session state keys
        if 'total_slider' not in st.session_state:
            st.session_state.total_slider = (datetime.date(2015, 1, 1), datetime.date(2024, 12, 31))
        if 'start_input' not in st.session_state:
            st.session_state.start_input = st.session_state.total_slider[0]
        if 'end_input' not in st.session_state:
            st.session_state.end_input = st.session_state.total_slider[1]
        
        if 'split_date_slider' not in st.session_state:
            st.session_state.split_date_slider = datetime.date(2020, 1, 1)
        if 'split_input' not in st.session_state:
            st.session_state.split_input = st.session_state.split_date_slider

        # --- Sidebar Widgets ---
        st.slider(tr('date_range'), min_value=min_date, max_value=max_date, key='total_slider', on_change=on_slider_change)
        
        c1, c2 = st.columns(2)
        start_a = c1.date_input(tr('start_date'), min_value=min_date, max_value=max_date, key='start_input', on_change=on_input_change, label_visibility="collapsed")
        end_c = c2.date_input(tr('end_date'), min_value=min_date, max_value=max_date, key='end_input', on_change=on_input_change, label_visibility="collapsed")

        # Split point selection
        st.slider(tr('split_date'), min_value=start_a, max_value=end_c, key='split_date_slider', on_change=on_split_slider_change)
        split_b = st.date_input(tr('split_date'), min_value=start_a, max_value=end_c, key='split_input', on_change=on_split_input_change, label_visibility="collapsed")

        start_d, split_d, end_d = pd.to_datetime(start_a), pd.to_datetime(split_b), pd.to_datetime(end_c)
        
        comm_input = st.slider(tr('comm_rate'), 0.0, 0.0010, 0.0004, 0.0001, format="%.4f")
        
        st.markdown("---")
        
        # Calculate Best T1 for Training Period [start_d, split_d)
        # We define split_d as the inclusive start of OOS, so IS ends strictly BEFORE split_d
        is_pnl_all = df_pnl.loc[start_d:split_d]
        if split_d in is_pnl_all.index and len(is_pnl_all) > 1:
            is_pnl = is_pnl_all.iloc[:-1] # Exclude the split day from IS
        else:
            is_pnl = is_pnl_all
        
        is_pnl_adj = adjust_pnl_for_commission(is_pnl, df_sig.reindex(is_pnl.index), comm_input)
        is_sharpe = (is_pnl_adj.mean() * 252) / (is_pnl_adj.std() * np.sqrt(252))
        best_t1 = is_sharpe.idxmax() if not is_sharpe.isna().all() else 25

        # Determine actual labels
        is_end_date = is_pnl.index[-1].date() if not is_pnl.empty else split_b
        st.info(tr('training_info').format(start_a, is_end_date, best_t1))
        st.success(tr('testing_info').format(split_b, end_c))

        st.markdown("---")
        mode = st.radio(tr('selection_mode'), [tr('manual_t'), tr('wfa_dynamic')], index=1)
        
        if mode == tr('manual_t'):
            # Initialize with best_t1 if not already set by user
            if 't_initialized' not in st.session_state:
                st.session_state.t_slider = int(best_t1)
                st.session_state.t_input = int(best_t1)
                st.session_state.t_initialized = True
            
            st.slider(tr('entry_timing'), 21, 60, key='t_slider', on_change=on_t_slider_change)
            selected_t = st.number_input(tr('entry_timing'), 21, 60, key='t_input', on_change=on_t_input_change, label_visibility="collapsed")
        else:
            # If we go back to dynamic, we can clear the initialization flag 
            # so that next time it resets to the (potentially new) best_t1
            if 't_initialized' in st.session_state:
                del st.session_state['t_initialized']
            selected_t = 25 
        
        st.markdown("---")
        st.caption(tr('baseline_note'))

# --- Main Logic ---
if df_pnl is not None:
    @st.cache_data
    def get_cached_stats(rets, signals):
        return calculate_detailed_stats(rets, signals)

    df_pnl_adj = adjust_pnl_for_commission(df_pnl, df_sig, comm_input)
    
    if mode == tr('manual_t'):
        effective_start = start_d
        strat_rets = df_pnl_adj.loc[effective_start:end_d, selected_t]
        strat_signals = df_sig.loc[effective_start:end_d, selected_t]
        strat_name = tr('fixed_t_name').format(selected_t)
    else:
        roll_sharpe = df_pnl_adj.rolling(252).mean() / df_pnl_adj.rolling(252).std() * np.sqrt(252)
        df_selection = roll_sharpe.shift(1)
        
        # Option A: Filter out burn-in (approx 2015) for WFA
        # Find first date with a valid parameter selection
        valid_mask = df_selection.notna().any(axis=1)
        if valid_mask.any():
            wfa_first_date = df_selection.index[valid_mask][0]
            effective_start = max(start_d, wfa_first_date)
        else:
            effective_start = start_d
            
        sub_rets = df_pnl_adj.loc[effective_start:end_d]
        sub_sig = df_sig.loc[effective_start:end_d]
        sub_sel = df_selection.loc[effective_start:end_d].idxmax(axis=1)
        
        strat_rets = pd.Series([sub_rets.loc[d, int(t)] for d, t in sub_sel.items()], index=sub_rets.index)
        strat_signals = pd.Series([sub_sig.loc[d, int(t)] for d, t in sub_sel.items()], index=sub_sig.index)
        strat_name = tr('wfa_name')

    # Benchmarks for display period [effective_start, end_d]
    bench_rets_is = df_pnl_adj.loc[effective_start:end_d, int(best_t1)]
    
    # --- FOCUS: Out-of-Sample period (Inclusive of Split Date B) ---
    # Slice rets and signals starting EXACTLY from split_d
    strat_rets_oos = strat_rets.loc[split_d:end_d]
    strat_signals_oos = strat_signals.loc[split_d:end_d]
    bench_rets_is_oos = bench_rets_is.loc[split_d:end_d]

    # Calculate stats for the OOS period
    stats_oos = get_cached_stats(strat_rets_oos, strat_signals_oos)
    bench_oos_is = get_cached_stats(bench_rets_is_oos, df_sig.loc[split_d:end_d, int(best_t1)])
    
    # --- Tabs ---
    t_over, t_perf, t_sig = st.tabs([tr('tab_overview'), tr('tab_analysis'), tr('tab_signals')])
    
    with t_over:
        st.caption(tr('rel_baseline_help').format(best_t1))
        # 1. KPIs (OOS Only)
        k1, k2, k3, k4 = st.columns(4)
        def metric_card(col, label, val, delta, inv=False, prefix="", suffix=""):
            d_color = "normal" if not inv else "inverse"
            col.metric(label, f"{prefix}{val}{suffix}", delta, delta_color=d_color)

        metric_card(k1, tr('total_return'), f"{stats_oos['Total Return']:.1%}", f"{stats_oos['Total Return']-bench_oos_is['Total Return']:.1%}")
        metric_card(k2, tr('sharpe_ratio'), f"{stats_oos['Sharpe Ratio']:.2f}", f"{stats_oos['Sharpe Ratio']-bench_oos_is['Sharpe Ratio']:.2f}")
        metric_card(k3, tr('max_drawdown'), f"{stats_oos['Max Drawdown']:.1%}", f"{stats_oos['Max Drawdown']-bench_oos_is['Max Drawdown']:.1%}", inv=True)
        metric_card(k4, tr('win_rate'), f"{stats_oos['Win Rate']:.1%}", f"{stats_oos['Win Rate']-bench_oos_is['Win Rate']:.1%}")
        
        st.markdown("---")

        # 2. Key Charts (Vertical) - Rebased at Split Date B
        st.subheader(tr('cum_returns'))
        fig_r = go.Figure()
        
        # Plot OOS Equity Curves (already re-indexed to start at 1.0 by calculate_detailed_stats when sliced)
        fig_r.add_trace(go.Scatter(x=stats_oos['Equity Curve'].index, y=stats_oos['Equity Curve'], name=strat_name, line=dict(color=PRIMARY_COLOR, width=3)))
        fig_r.add_trace(go.Scatter(x=bench_oos_is['Equity Curve'].index, y=bench_oos_is['Equity Curve'], name=tr('is_baseline_name').format(best_t1), line=dict(color='#f59e0b', dash='dash', width=2)))
        
        fig_r.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_r, use_container_width=True)

        st.subheader(tr('max_dd_pct'))
        fig_d = go.Figure()
        fig_d.add_trace(go.Scatter(x=stats_oos['Drawdown Curve'].index, y=stats_oos['Drawdown Curve']*100, fill='tozeroy', name='DD', line=dict(color=NEGATIVE_COLOR)))
        fig_d.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_d, use_container_width=True)

    with t_perf:
        st.subheader(tr('comp_metrics'))
        def get_stat_series(st_val):
            return pd.Series({
                tr('total_return'): f"{st_val['Total Return']:.2%}",
                tr('ann_return'): f"{st_val['Annualized Return']:.2%}",
                tr('max_drawdown'): f"{st_val['Max Drawdown']:.2%}",
                tr('calmar'): f"{st_val['Calmar Ratio']:.2f}",
                tr('avg_pnl'): f"{st_val['Avg Trade PnL']:.4%}",
                tr('trade_count'): str(st_val['Trade Count']),
                tr('win_rate'): f"{st_val['Win Rate']:.2%}",
                tr('pl_ratio'): f"{st_val['P/L Ratio']:.2f}",
                tr('long_ratio'): f"{st_val['Long Ratio']:.2%}",
                tr('avg_daily'): f"{st_val['Avg Daily Return']:.4%}"
            })

        summary_df = pd.DataFrame({
            f"{tr('metrics')} ({strat_name})": get_stat_series(stats_oos),
            tr('benchmark').format(best_t1): get_stat_series(bench_oos_is)
        })
        st.table(summary_df)
        
        st.markdown("---")
        
        # Yearly Analysis - Compare Dynamic (WFA) vs Static (IS Best)
        st.subheader(f"{tr('yearly_perf')} ({strat_name})")
        years = strat_rets.loc[start_d:end_d].index.year.unique()
        
        # Calculate WFA Dynamic rets (even if not currently selected) for comparison
        roll_sharpe_all = df_pnl_adj.rolling(252).mean() / df_pnl_adj.rolling(252).std() * np.sqrt(252)
        selection_all = roll_sharpe_all.shift(1).apply(lambda row: best_t1 if row.isna().all() else row.idxmax(), axis=1)
        wfa_rets_full = pd.Series([df_pnl_adj.loc[d, int(t)] for d, t in selection_all.items()], index=df_pnl_adj.index)
        
        yearly_data = []
        for yr in years:
            # Current Selection (Manual or WFA)
            yr_current = strat_rets[strat_rets.index.year == yr]
            # Static (IS Best T1)
            yr_static = bench_rets_is[bench_rets_is.index.year == yr]
            
            yearly_data.append({'Year': str(yr), 'Return': yr_current.sum(), 'Type': strat_name})
            yearly_data.append({'Year': str(yr), 'Return': yr_static.sum(), 'Type': tr('benchmark').format(best_t1)})
        
        y_compare_df = pd.DataFrame(yearly_data)
        
        # Yearly Return Bar Chart (Grouped)
        fig_yr = px.bar(y_compare_df, x='Year', y='Return', color='Type', barmode='group',
                        color_discrete_map={tr('wfa_name'): PRIMARY_COLOR, tr('benchmark').format(best_t1): '#f59e0b'},
                        text_auto='.1%')
        fig_yr.update_layout(height=380, title=tr('yearly_ret_chart'), showlegend=True, xaxis_type='category')
        st.plotly_chart(fig_yr, use_container_width=True)
        
        # Table remains showing selected strategy details for audit
        yearly_metrics = []
        for yr in years:
            yr_rets = strat_rets[strat_rets.index.year == yr]
            yr_sigs = strat_signals[strat_signals.index.year == yr]
            y_st = calculate_detailed_stats(yr_rets, yr_sigs)
            y_st['Year'] = str(yr)
            yearly_metrics.append(y_st)
        
        y_df = pd.DataFrame(yearly_metrics)
        df_display = y_df.set_index('Year')[['Total Return', 'Annualized Return', 'Max Drawdown', 'Sharpe Ratio', 'Win Rate', 'Trade Count']]
        df_display.columns = [tr('col_total_return'), tr('col_ann_return'), tr('col_max_dd'), tr('col_sharpe'), tr('col_win_rate'), tr('col_trades')]
        
        final_format_dict = {
            tr('col_total_return'): '{:.2%}',
            tr('col_ann_return'): '{:.2%}',
            tr('col_max_dd'): '{:.2%}',
            tr('col_sharpe'): '{:.2f}',
            tr('col_win_rate'): '{:.2%}',
        }
        st.dataframe(df_display.style.format(final_format_dict), use_container_width=True)

        st.markdown("---")
        st.subheader(tr('t_evolution'))
        st.info(tr('t_evolution_info'))
        full_roll_sharpe = df_pnl_adj.rolling(252).mean() / df_pnl_adj.rolling(252).std() * np.sqrt(252)
        df_full_sel = full_roll_sharpe.shift(1)
        full_selection = df_full_sel.apply(lambda row: 25 if row.isna().all() else row.idxmax(), axis=1)
        full_selection = full_selection.loc['2016-01-01':]
        fig_t = px.line(x=full_selection.index, y=full_selection.values)
        fig_t.update_traces(line=dict(color=PRIMARY_COLOR, width=2))
        fig_t.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="T Value", xaxis_title="")
        st.plotly_chart(fig_t, use_container_width=True)

    with t_sig:
        st.subheader(f"{tr('price_signals')} ({strat_name})")
        st.info(tr('timing_info'))
        sub_price = df_price.loc[split_d:end_d]
        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(x=sub_price.index, y=sub_price['P_1500'], name="IF Daily Close", line=dict(color=NEUTRAL_COLOR, width=1)))
        
        # --- Fix: Align signals with price index to avoid IndexingError ---
        aligned_signals = strat_signals_oos.reindex(sub_price.index).fillna(0)
        
        longs = sub_price[aligned_signals == 1]
        shorts = sub_price[aligned_signals == -1]
        # -----------------------------------------------------------------
        fig_p.add_trace(go.Scatter(x=longs.index, y=longs['P_1500'], mode='markers', name=tr('open_long'), marker=dict(symbol='triangle-up', color=POSITIVE_COLOR, size=10)))
        fig_p.add_trace(go.Scatter(x=shorts.index, y=shorts['P_1500'], mode='markers', name=tr('open_short'), marker=dict(symbol='triangle-down', color=NEGATIVE_COLOR, size=10)))
        fig_p.update_layout(height=500, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.05))
        st.plotly_chart(fig_p, use_container_width=True)
        
        active_days = strat_signals_oos[strat_signals_oos != 0].index
        if len(active_days) > 0:
            st.markdown("---")
            st.subheader(f"{tr('simulated_trades')} ({strat_name})")
            
            # Prepare T History for display
            if mode == tr('manual_t'):
                t_history = pd.Series(selected_t, index=active_days)
            else:
                t_history = sub_sel.loc[active_days]

            # --- Refactor: Generate two rows per day (Entry & Exit) ---
            trade_rows = []
            for d in active_days:
                sig = strat_signals_oos.loc[d]
                ret = strat_rets_oos.loc[d]
                p_exit = sub_price.loc[d, 'P_1500']
                t_val = int(t_history.loc[d])
                
                # Back-calculate P_T from return for display
                # Raw_Ret = (P_Exit - P_T) / P_T
                raw_ret = (ret + comm_input) / sig if sig != 0 else 0
                p_entry = p_exit / (1 + raw_ret)
                
                # Entry Row
                trade_rows.append({
                    tr('col_date'): d.strftime('%Y-%m-%d'),
                    tr('col_time'): (datetime.datetime.combine(d, datetime.time(9, 30)) + datetime.timedelta(minutes=t_val)).strftime('%H:%M'),
                    tr('direction'): tr('buy') if sig > 0 else tr('sell'),
                    tr('col_price'): round(p_entry, 2),
                    tr('col_type'): tr('open_pos'),
                    tr('col_selected_t'): t_val,
                    tr('col_daily_ret'): "-",
                    tr('col_cum_pnl'): "-" 
                })
                
                # Exit Row
                trade_rows.append({
                    tr('col_date'): d.strftime('%Y-%m-%d'),
                    tr('col_time'): "15:00",
                    tr('direction'): tr('sell') if sig > 0 else tr('buy'),
                    tr('col_price'): round(p_exit, 2),
                    tr('col_type'): tr('close_pos'),
                    tr('col_selected_t'): t_val,
                    tr('col_daily_ret'): f"{ret:.2%}",
                    tr('col_cum_pnl'): f"{((1 + strat_rets_oos.loc[:d]).cumprod() - 1).iloc[-1]:.2%}"
                })

            sim_trades = pd.DataFrame(trade_rows)
            
            def color_signal(val):
                if val == tr('buy'): return f'color: {POSITIVE_COLOR}; font-weight: bold;'
                if val == tr('sell'): return f'color: {NEGATIVE_COLOR}; font-weight: bold;'
                return ''
                
            st.dataframe(
                sim_trades.style.map(color_signal, subset=[tr('direction')])
            )

else:
    st.error(tr('data_not_found'))
