#  MFE5210 Final Project: CTA Constituent Consistency Strategy

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Polars](https://img.shields.io/badge/Engine-Polars-CD792C.svg)](https://pola.rs/)
[![Streamlit](https://img.shields.io/badge/GUI-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/DB-SQLite-003B57.svg)](https://www.sqlite.org/)


> **A production-grade, event-driven intraday CTA backtesting system** based on the "Constituent Consistency" strategy from academic research. The system quantifies market resonance via PCA on CSI-300 stocks' intraday returns and trades the IF index futures accordingly.

---

##  Key Features

| Capability | Description |
|---|---|
| **Event-Driven Engine** | Classic `DataHandler → Strategy → Portfolio → Execution` loop with a centralized event queue, ensuring zero look-ahead bias. |
| **Polars-Powered Alpha** | Offline PCA factor generation using Polars + Joblib parallelism — processes ~2,500 trading days in under 30 seconds. |
| **Hybrid Persistence** | Heavy time-series data (equity curves, factor matrices) stored as **Parquet**; relational metadata (trade journals, run KPIs) stored in **SQLite**. |
| **Vectorized WFA** | Walk-Forward Analysis with 1-year/6-month rolling windows for dynamic parameter switching in out-of-sample validation. |
| **Decoupled Metrics** | Core calculations (Sharpe, Drawdown, Calmar, Win Rate, P/L Ratio) centralized in `src/performance.py`, shared by both the engine and the GUI. |
| **Interactive Dashboard** | Streamlit + Plotly front-end with interactive sliders for date range & IS/OOS split, commission sensitivity tuning, WFA dynamic vs static comparison, and bilingual (EN/CN) support via `gui/i18n.py`. |
| **Transaction Cost Analysis** | Dedicated TCA module querying SQLite trade journal for precise commission & slippage breakdown. |

---

##  Project Structure

```text
5210final project/
├── src/                          # Core Engine (Event-Driven Architecture)
│   ├── config.py                 # Centralized configuration & path management
│   ├── data_handler.py           # Bar-by-bar market data engine (CSV + Parquet)
│   ├── strategy.py               # Consistency factor signal generation
│   ├── portfolio.py              # Position tracking & 0.6% hard stop-loss
│   ├── execution.py              # Simulated OMS & transaction cost model
│   ├── engine.py                 # Main backtest event loop coordinator
│   ├── event.py                  # Event class hierarchy (Market/Signal/Order/Fill)
│   ├── database.py               # SQLite persistence layer (trade journal & runs)
│   └── performance.py            # Sharpe, Drawdown, Calmar & detailed statistics
│
├── scripts/                      # Executable Pipeline (run in order)
│   ├── 01_precompute_alpha.py    # [Polars] Offline PCA factor matrix generation
│   ├── 02_backtest_engine.py     # Event-driven backtest (gold-standard verification)
│   ├── 03_generate_pnl_matrix.py # Vectorized PnL matrix for parameter grid search
│   ├── 04_analyze_switching.py   # Dynamic vs Static switching window comparison
│   └── 05_oos_validation.py      # In-Sample / Out-of-Sample validation report
│
├── gui/                          # Front-End Interface
│   ├── app.py                    # Streamlit interactive dashboard (3 tabs)
│   └── i18n.py                   # Bilingual translation module (English / 中文)
│
├── tca/                          # Transaction Cost Analysis
│   └── tca_analysis.py           # Commission & slippage breakdown tools
│
├── data/                         # Data Repository (git-ignored, see below)
│   ├── csi300_min_db/            # Hive-style partitioned 1-min stock data (date=YYYY-MM-DD/)
│   ├── IF.csv                    # IF index futures continuous 1-min bars
│   ├── alpha_consistency_daily.parquet  # Pre-computed PCA factor matrix
│   ├── daily_pnl_matrix.parquet  # Full parameter-space daily PnL matrix
│   ├── signal_matrix.parquet     # Trading signal matrix (1 / -1 / 0)
│   ├── if_daily.parquet          # Daily price summary for GUI
│   └── trading_system.db         # SQLite database (trade journal & run metadata)
│
├── output/                       # Generated Reports & Charts
│   ├── IS_OOS_COMPARISON_REPORT.png
│   └── switching_window_comparison.png
│
├── cache/                        # Joblib cache (auto-generated, git-ignored)
├── requirements.txt              # Python dependencies
├── .gitignore                    # Git exclusion rules
└── README.md                     # Documentation (this file)
```

---

##  Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Offline Pre-computation                   │
│  01_precompute_alpha.py  ──→  alpha_consistency_daily.parquet│
│  (Polars + Joblib)             (Date × R_21..R_60)           │
└─────────────────────────────────┬────────────────────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │         Event-Driven Engine           │
              │                                       │
              │  ┌─────────┐    ┌──────────────┐      │
              │  │DataHandler│──→│  Event Queue  │     │
              │  └─────────┘    └──────┬───────┘      │
              │       MarketEvent      │               │
              │  ┌─────────┐    ┌──────▼───────┐      │
              │  │ Strategy │◄──│  Dispatcher   │     │
              │  └────┬────┘    └──────┬───────┘      │
              │   SignalEvent          │               │
              │  ┌────▼────┐    ┌──────▼───────┐      │
              │  │Portfolio │──→│  Execution    │     │
              │  └────┬────┘    └──────────────┘      │
              │   OrderEvent / FillEvent               │
              └───────┬───────────────────────────────┘
                      │
       ┌──────────────▼──────────────┐
       │     Hybrid Persistence      │
       │  Parquet ← equity curves    │
       │  SQLite  ← trade journal    │
       └──────────────┬──────────────┘
                      │
       ┌──────────────▼──────────────┐
       │   Streamlit GUI Dashboard   │
       │  (performance.py shared)    │
       │   Overview │  Analysis │
       │   Signals  │  EN/CN   │
       └─────────────────────────────┘
```

---

##  Strategy Summary

The strategy calculates a **Consistency Index** ($R_T$) using 1-minute bars of the 300 CSI stocks from 09:30 up to $T$ minutes later:

1. **Factor Computation**: Performs PCA on the normalized intraday price matrix $(N_{\text{stocks}} \times T)$. $R_T$ is the variance ratio explained by the 1st principal component.
2. **Entry Trigger**: At time $09\text{:}30 + T$, if $R_T >$ 60-day rolling mean of historical $R_T$ values at the same intra-day time.
3. **Direction**:
   - **LONG**: If $P(T) > P(09\text{:}30)$
   - **SHORT**: If $P(T) < P(09\text{:}30)$
4. **Exit Rules**: 0.6% intraday stop-loss or forced close at 15:00.

---

##  Installation & Usage

### Prerequisites

- Python ≥ 3.8
- Historical 1-min bar data for CSI-300 constituents and IF futures (placed in `data/`)

> [!TIP]
> **Quick Start**: This repository already includes pre-computed alpha and PnL matrices in the `data/` folder. You can skip the data download and run the **GUI Dashboard** (Step 3) immediately to see the full historical results.

###  Data Download (Full Dataset)

The raw 1-min stock data (~4.4GB) is required only if you wish to re-run the alpha pre-computation (Step 1). You can download it here:

- **Link**: [Baidu Netdisk](https://pan.baidu.com/s/1g630RZSzl2g1UYNhQTm9Dw?pwd=pejs)
- **Extraction Code**: `pejs`
- **Instructions**: Extract the `csi300_min_db` folder into the `data/` directory of this project.

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Pipeline (in order)

```bash
# Step 1: Generate PCA Alpha Factor Matrix (~30s)
python scripts/01_precompute_alpha.py

# Step 2: (Optional) Run event-driven backtest for verification
python scripts/02_backtest_engine.py --t 24 --start 2015-01-05 --end 2016-07-31

# Step 3: Generate full PnL matrix for parameter search
python scripts/03_generate_pnl_matrix.py

# Step 4: (Optional) Compare switching window strategies
python scripts/04_analyze_switching.py

# Step 5: Generate IS/OOS Validation Report
python scripts/05_oos_validation.py
```

### 3. Launch GUI Dashboard

```bash
streamlit run gui/app.py
```

The dashboard provides three interactive tabs:
- **Overview** — KPI cards (Total Return, Sharpe, Max Drawdown, Win Rate) with equity & drawdown curves
- **Analysis** — Comprehensive metrics table, yearly performance breakdown (WFA Dynamic vs Static bar chart), and T-parameter adaptive path
- **Signals** — Price & signal overlay chart with simulated trade history table (entry price, direction, selected T, cumulative PnL)

Use the sidebar sliders to adjust the backtest period, IS/OOS split point, and commission rate. Toggle between Static T (Manual) and Dynamic WFA (Adaptive) modes. Switch language via the top-right dropdown.

### 4. (Optional) Transaction Cost Analysis

```bash
python tca/tca_analysis.py
```

Reads the latest completed backtest run from the SQLite database and prints a precision TCA report including gross/net profit, average friction (bps), and profit erosion percentage.

---

##  Design Patterns & Key Decisions

| Pattern | Where | Why |
|---|---|---|
| **Event-Driven** | `src/engine.py` | Eliminates look-ahead bias; mirrors real trading infrastructure. |
| **Observer** | Event Queue | Components react to events (`MARKET → SIGNAL → ORDER → FILL`) without tight coupling. |
| **Strategy Pattern** | `src/strategy.py` | Swappable strategy implementations behind a common `Strategy` ABC interface. |
| **Hybrid Storage** | `database.py` + Parquet | SQLite for relational queries (trade audit); Parquet for columnar analytics (equity curves). |
| **Centralized Config** | `src/config.py` | Single source of truth for paths, parameters, and experiment protocol. |
| **i18n (Internationalization)** | `gui/i18n.py` | Bilingual (EN/CN) support via a session-state-driven translation dictionary. |

---

##  Experiment Protocol

| Phase | Period | Purpose |
|---|---|---|
| **In-Sample (IS)** | 2015-01-01 → 2019-12-31 | Parameter optimization ($T \in [21, 60]$) |
| **Out-of-Sample (OOS)** | 2020-01-01 → 2024-12-31 | Strategy validation & robustness check |

> The IS/OOS split is defined once in `src/config.py → EXPERIMENT_PROTOCOL` and propagated to all analysis scripts automatically.


---

*MFE5210: Algorithmic Trading — Final Project*
