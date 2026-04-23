# 📈 MFE5210 毕业项目：成份股一致性 CTA 策略系统

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Polars](https://img.shields.io/badge/引擎-Polars-CD792C.svg)](https://pola.rs/)
[![Streamlit](https://img.shields.io/badge/GUI-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/数据库-SQLite-003B57.svg)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **一套生产级、事件驱动的日内 CTA 回测系统**。基于学术论文中的"成份股一致性"策略，通过对沪深 300 成份股日内收益进行 PCA 分析来量化市场共振强度，据此交易 IF 股指期货。

---

## 🚀 核心特性

| 能力 | 说明 |
|---|---|
| **事件驱动引擎** | 经典 `DataHandler → Strategy → Portfolio → Execution` 循环 + 集中式事件队列，杜绝未来函数（Look-ahead Bias）。 |
| **Polars 高性能因子** | 离线 PCA 因子生成采用 Polars + Joblib 并行，~2500 个交易日 30 秒内完成。 |
| **混合持久化架构** | 重型时序数据（权益曲线、因子矩阵）存储为 **Parquet**；关系型元数据（交易流水、运行记录）存储在 **SQLite** 中。 |
| **向量化 WFA** | Walk-Forward Analysis 支持 1 年/6 月滚动窗口动态参数切换，完成样本外验证。 |
| **解耦绩效引擎** | 核心统计指标（Sharpe、回撤、Calmar、胜率、盈亏比）集中于 `src/performance.py`，引擎与 GUI 共用。 |
| **交互式仪表盘** | Streamlit + Plotly 前端，支持日期范围及 IS/OOS 分割的交互式滑动条、佣金敏感度调优、WFA 动态 vs 静态对比，以及通过 `gui/i18n.py` 实现的中英双语支持。 |
| **交易成本分析** | 独立 TCA 模块，直接查询 SQLite 交易日志，提供精确的佣金及滑点成本细分分析。 |

---

## 📂 项目结构

```text
5210final project/
├── src/                          # 核心引擎（事件驱动架构）
│   ├── config.py                 # 集中配置中心 & 路径管理
│   ├── data_handler.py           # 逐根K线推送行情引擎 (CSV + Parquet)
│   ├── strategy.py               # 一致性因子信号生成
│   ├── portfolio.py              # 持仓跟踪 & 0.6% 硬止损
│   ├── execution.py              # 模拟 OMS & 交易成本模型
│   ├── engine.py                 # 回测事件循环协调器
│   ├── event.py                  # 事件类层级 (Market/Signal/Order/Fill)
│   ├── database.py               # SQLite 持久化层（交易流水 & 运行记录）
│   └── performance.py            # Sharpe / 回撤 / Calmar / 详细统计
│
├── scripts/                      # 可执行流水线（按序号执行）
│   ├── 01_precompute_alpha.py    # [Polars] 离线 PCA 因子矩阵生成
│   ├── 02_backtest_engine.py     # 事件驱动回测（高精度验证）
│   ├── 03_generate_pnl_matrix.py # 向量化 PnL 矩阵（参数网格搜索）
│   ├── 04_analyze_switching.py   # 动态 vs 静态切换窗口对比
│   └── 05_oos_validation.py      # 样本内/样本外验证报告
│
├── gui/                          # 前端界面
│   ├── app.py                    # Streamlit 交互式仪表盘 (3 个标签页)
│   └── i18n.py                   # 双语翻译模块 (English / 中文)
│
├── tca/                          # 交易成本分析
│   └── tca_analysis.py           # 佣金 & 滑点细分工具
│
├── data/                         # 数据仓库（不纳入版本控制，详见下方）
│   ├── csi300_min_db/            # Hive 分区格式的分钟级成份股数据湖 (date=YYYY-MM-DD/)
│   ├── IF.csv                    # IF 主力连续合约 1 分钟 K 线
│   ├── alpha_consistency_daily.parquet  # 预计算 PCA 因子矩阵
│   ├── daily_pnl_matrix.parquet  # 全参数空间日收益矩阵
│   ├── signal_matrix.parquet     # 交易信号矩阵 (1 / -1 / 0)
│   ├── if_daily.parquet          # 日度价格摘要（GUI 专用）
│   └── trading_system.db         # SQLite 数据库 (包含交易流水及元数据)
│
├── output/                       # 生成的报告 & 图表
│   ├── IS_OOS_COMPARISON_REPORT.png
│   └── switching_window_comparison.png
│
├── cache/                        # Joblib 缓存（自动生成，不提交）
├── requirements.txt              # Python 依赖清单
├── .gitignore                    # Git 排除规则
├── LICENSE                       # MIT 许可证
└── README.md                     # 英文文档
```

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                      离线预计算阶段                          │
│  01_precompute_alpha.py  ──→  alpha_consistency_daily.parquet│
│  (Polars + Joblib 并行)        (Date × R_21..R_60)           │
└─────────────────────────────────┬────────────────────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │          事件驱动回测引擎              │
              │                                       │
              │  ┌──────────┐   ┌──────────────┐      │
              │  │DataHandler│──→│  事件队列     │     │
              │  └──────────┘   └──────┬───────┘      │
              │      MarketEvent       │               │
              │  ┌──────────┐   ┌──────▼───────┐      │
              │  │ Strategy  │◄──│   分发器     │     │
              │  └────┬─────┘   └──────┬───────┘      │
              │   SignalEvent          │               │
              │  ┌────▼─────┐   ┌──────▼───────┐      │
              │  │Portfolio  │──→│  Execution   │     │
              │  └────┬─────┘   └──────────────┘      │
              │   OrderEvent / FillEvent               │
              └───────┬───────────────────────────────┘
                      │
       ┌──────────────▼──────────────┐
       │       混合持久化层           │
       │  Parquet ← 权益曲线 / 因子  │
       │  SQLite  ← 交易流水 / KPI   │
       └──────────────┬──────────────┘
                      │
       ┌──────────────▼──────────────┐
       │   Streamlit GUI 仪表盘      │
       │  (共用 performance.py)      │
       │  🎯 核心概览 │ 📊 绩效拆解 │
       │  🔬 信号观察 │ 🌐 中英双语 │
       └─────────────────────────────┘
```

---

## 🧠 策略逻辑

系统在开盘后第 $T$ 分钟（$T \in [21, 60]$）计算一致性指标 $R_T$：

1. **因子计算**：对成份股在 **当日 09:30 至 09:30+T** 的归一化价格矩阵 $(N_{\text{stocks}} \times T)$ 进行 PCA 分解，$R_T$ = 第一主成分方差解释占比。
2. **入场触发**：$09\text{:}30 + T$ 时刻，若 $R_T >$ 过去 60 个交易日 **同一时刻 T** 的 $R_T$ 滚动均值。
3. **方向判断**：
   - **做多**：$P(T) > P(09\text{:}30)$
   - **做空**：$P(T) < P(09\text{:}30)$
4. **风控退出**：日内止损 0.6% 或 15:00 强制平仓。

---

## 🛠️ 安装与使用

### 环境要求

- Python ≥ 3.8
- 沪深 300 成份股 & IF 期货的历史 1 分钟 K 线数据（放置于 `data/` 目录）

> [!TIP]
> **快速上手**：本项目已在 `data/` 文件夹中内置了预计算的因子矩阵和收益矩阵。您可以跳过数据下载，直接执行 **启动可视化仪表盘**（步骤 3）来查看完整的历史回测结果。

### 📦 数据下载 (完整数据集)

只有当您需要重新执行因子预计算（步骤 1）时，才需要下载约 4.4GB 的原始股票数据：

- **链接**: [百度网盘](https://pan.baidu.com/s/1W8LwoMDjvlmDLpoHwpL7kw?pwd=tbs7)
- **提取码**: `tbs7`
- **使用方法**: 下载并解压 `csi300_min_db` 文件夹，将其放置在项目的 `data/` 目录下。

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 执行流水线（按序号运行）

```bash
# 步骤 1：生成 PCA 因子矩阵（约 30 秒）
python scripts/01_precompute_alpha.py

# 步骤 2：（可选）运行事件驱动回测进行精度验证
python scripts/02_backtest_engine.py --t 24 --start 2015-01-05 --end 2016-07-31

# 步骤 3：生成全参数 PnL 矩阵
python scripts/03_generate_pnl_matrix.py

# 步骤 4：（可选）对比不同切换窗口策略
python scripts/04_analyze_switching.py

# 步骤 5：生成 IS/OOS 验证报告
python scripts/05_oos_validation.py
```

### 3. 启动可视化仪表盘

```bash
streamlit run gui/app.py
```

可视化界面包含三个交互式标签页：
- **🎯 核心概览 (Overview)** — 显示核心 KPI 指标（总收益、夏普、最大回撤、胜率）以及权益曲线和回撤曲线。
- **📊 绩效拆解 (Analysis)** — 提供详细的绩效评估表、年度收益对比（WFA 动态 vs 静态基准柱状图）以及 T 参数的演化路径。
- **🔬 信号观察 (Signals)** — 价格与信号的叠加图表，以及包含执行价格、方向、选定 T 值和累计盈亏的模拟信号明细表。

通过侧边栏滑动条可以调整回测周期、样本内外分割点以及佣金率。支持在“静态 T（手动）”与“动态 WFA（自适应）”模式间切换。右上角可切换中英文界面。

### 4. (可选) 交易成本分析 (TCA)

```bash
python tca/tca_analysis.py
```

该脚本将读取 SQLite 数据库中最近完成的一次完整回测记录，并输出精确的 TCA 报告，包括毛利/净利对比、平均摩擦成本（bps）以及利润损耗比例。

---

## 📊 设计模式与关键决策

| 模式 | 位置 | 原因 |
|---|---|---|
| **事件驱动** | `src/engine.py` | 消除未来函数；贴近真实交易基础设施。 |
| **观察者模式** | 事件队列 | 各组件通过事件 (`MARKET → SIGNAL → ORDER → FILL`) 解耦通信。 |
| **策略模式** | `src/strategy.py` | 基于 `Strategy` 抽象基类统一接口，支持策略灵活替换。 |
| **混合存储** | `database.py` + Parquet | SQLite 处理关系查询（交易审计）；Parquet 处理列式分析（权益曲线）。 |
| **集中配置** | `src/config.py` | 路径、参数、实验协议的唯一真相源。 |
| **i18n (国际化)** | `gui/i18n.py` | 通过基于 Session State 的翻译字典实现中英双语支持。 |

---

## 📋 实验协议

| 阶段 | 时间区间 | 目的 |
|---|---|---|
| **样本内 (IS)** | 2015-01-01 → 2019-12-31 | 参数优化（$T \in [21, 60]$） |
| **样本外 (OOS)** | 2020-01-01 → 2024-12-31 | 策略验证 & 稳健性检验 |

> IS/OOS 划分在 `src/config.py → EXPERIMENT_PROTOCOL` 中统一定义，自动传播到所有分析脚本。

---

## 📄 许可证

本项目采用 MIT 许可证 — 详见 [LICENSE](LICENSE)。

---

*MFE5210：算法交易 — 毕业项目最终成果*
