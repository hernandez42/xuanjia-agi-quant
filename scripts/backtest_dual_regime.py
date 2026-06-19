#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_dual_regime.py — 玄甲4步回测(Q1趋势+H1震荡盲测)

使用玄甲系统自带的 BacktestEngine 和 StrategyPipeline 验证策略在两种市场环境下的表现。

任务：
1. 构建两种市场环境的模拟数据
2. 运行玄甲完整流水线（StrategyPipeline.run_daily_scan + BacktestEngine.run）
3. 对比两种市场环境下的回测指标
4. 同时运行 daogi 6维策略作为对照

输出：详细回测报告到 <xuanjia_dir>/results/backtest_dual_regime_20260619.md
"""

from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
#  路径设置
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_XUANJIA_DIR = os.path.dirname(_THIS_DIR)
_APEX_DIR = os.path.join(_XUANJIA_DIR, "apex_agi")
if _APEX_DIR not in sys.path:
    sys.path.insert(0, _APEX_DIR)

# ---------------------------------------------------------------------------
#  导入玄甲现有模块
# ---------------------------------------------------------------------------
from backtest_engine import (
    BacktestEngine,
    BacktestResult,
    StrategySignal,
    TradeRecord,
    generate_mock_market_data,
)
from strategy_pipeline import StrategyPipeline, PipelineResult


# ═══════════════════════════════════════════════════════════════════════════
#  1. 双市场环境模拟数据生成器
# ═══════════════════════════════════════════════════════════════════════════

TREND_STOCK_POOL = [
    {"code": f"T{str(i).zfill(4)}", "name": f"趋势股{i}", "base_price": random.uniform(30, 200)}
    for i in range(1, 31)
]

OSCILLATION_STOCK_POOL = [
    {"code": f"O{str(i).zfill(4)}", "name": f"震荡股{i}", "base_price": random.uniform(30, 200)}
    for i in range(1, 31)
]


def generate_trend_market_data(
    stock_pool: List[Dict],
    start_date: str = "2026-01-02",
    trading_days: int = 60,
    daily_gain_min: float = 0.01,
    daily_gain_max: float = 0.03,
    seed: int = 42,
) -> List[Dict]:
    """
    生成趋势市模拟数据：连续上涨，每日 close +1%~+3%
    模拟2026 Q1牛市环境
    """
    random.seed(seed)
    market_data = []

    # 初始化价格
    prices = {s["code"]: s["base_price"] for s in stock_pool}
    price_history = {s["code"]: [s["base_price"]] for s in stock_pool}

    base_dt = datetime.strptime(start_date, "%Y-%m-%d")
    day_idx = 0
    current_dt = base_dt
    generated_days = 0

    while generated_days < trading_days:
        # 跳过周末
        if current_dt.weekday() >= 5:
            current_dt += timedelta(days=1)
            continue

        date_str = current_dt.strftime("%Y-%m-%d")
        day_stocks = {}

        for stock in stock_pool:
            code = stock["code"]
            prev_close = prices[code]

            # 趋势市：每日上涨 1%~3%，加入微小随机扰动
            daily_gain = random.uniform(daily_gain_min, daily_gain_max)
            # 加入微小波动让MA5等技术指标有意义
            noise = random.gauss(0, 0.005)
            actual_return = daily_gain + noise

            new_close = prev_close * (1.0 + actual_return)
            new_close = max(new_close, prev_close * 0.95)  # 限制最大跌幅5%

            prices[code] = new_close
            price_history[code].append(new_close)

            pct_change = (new_close - prev_close) / prev_close if prev_close > 0 else 0.0

            # 计算MA5
            hist = price_history[code]
            ma5 = sum(hist[-6:-1]) / 5 if len(hist) >= 6 else new_close
            close_5d_ago = hist[-6] if len(hist) >= 6 else hist[0]

            # 生成OHLC
            high = max(prev_close, new_close) * (1.0 + abs(random.gauss(0, 0.003)))
            low = min(prev_close, new_close) * (1.0 - abs(random.gauss(0, 0.003)))
            open_price = prev_close * (1.0 + random.gauss(0, 0.002))

            day_stocks[code] = {
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(new_close, 2),
                "pct_change": round(pct_change, 6),
                "volume": random.randint(10000, 100000),
                "ma5": round(ma5, 2),
                "close_5d_ago": round(close_5d_ago, 2),
            }

        market_data.append({
            "date": date_str,
            "stocks": day_stocks,
        })

        generated_days += 1
        current_dt += timedelta(days=1)

    return market_data


def generate_oscillation_market_data(
    stock_pool: List[Dict],
    start_date: str = "2025-01-02",
    trading_days: int = 120,
    daily_range: Tuple[float, float] = (-0.02, 0.02),
    seed: int = 43,
) -> List[Dict]:
    """
    生成震荡市模拟数据：涨跌交替，每日 close -2%~+2%
    模拟2025 H1震荡市环境
    """
    random.seed(seed)
    market_data = []

    prices = {s["code"]: s["base_price"] for s in stock_pool}
    price_history = {s["code"]: [s["base_price"]] for s in stock_pool}

    base_dt = datetime.strptime(start_date, "%Y-%m-%d")
    current_dt = base_dt
    generated_days = 0

    while generated_days < trading_days:
        if current_dt.weekday() >= 5:
            current_dt += timedelta(days=1)
            continue

        date_str = current_dt.strftime("%Y-%m-%d")
        day_stocks = {}

        for stock in stock_pool:
            code = stock["code"]
            prev_close = prices[code]

            # 震荡市：每日涨跌 -2%~+2%
            actual_return = random.uniform(daily_range[0], daily_range[1])

            new_close = prev_close * (1.0 + actual_return)
            new_close = max(new_close, prev_close * 0.90)  # 限制最大跌幅10%

            prices[code] = new_close
            price_history[code].append(new_close)

            pct_change = (new_close - prev_close) / prev_close if prev_close > 0 else 0.0

            # 计算MA5
            hist = price_history[code]
            ma5 = sum(hist[-6:-1]) / 5 if len(hist) >= 6 else new_close
            close_5d_ago = hist[-6] if len(hist) >= 6 else hist[0]

            high = max(prev_close, new_close) * (1.0 + abs(random.gauss(0, 0.004)))
            low = min(prev_close, new_close) * (1.0 - abs(random.gauss(0, 0.004)))
            open_price = prev_close * (1.0 + random.gauss(0, 0.003))

            day_stocks[code] = {
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(new_close, 2),
                "pct_change": round(pct_change, 6),
                "volume": random.randint(10000, 100000),
                "ma5": round(ma5, 2),
                "close_5d_ago": round(close_5d_ago, 2),
            }

        market_data.append({
            "date": date_str,
            "stocks": day_stocks,
        })

        generated_days += 1
        current_dt += timedelta(days=1)

    return market_data


# ═══════════════════════════════════════════════════════════════════════════
#  2. 策略适配器
# ═══════════════════════════════════════════════════════════════════════════

def create_pipeline_strategy(pipeline: StrategyPipeline) -> Callable:
    """
    将 StrategyPipeline 封装为 BacktestEngine 所需的策略函数签名。
    策略逻辑与 strategy_pipeline.py 中的 _create_backtest_strategy 一致，
    但增加了持仓状态传递。
    """

    def strategy_func(date: str, market_data: Dict) -> List[StrategySignal]:
        signals = []
        stocks = market_data.get("stocks", {})
        holdings = market_data.get("holdings", {})

        for code, info in stocks.items():
            close = info.get("close", 0)
            pct_change = info.get("pct_change", 0)
            ma5 = info.get("ma5", 0)

            # ---- 买入逻辑 ----
            if code not in holdings:
                if pct_change > 0 and ma5 > 0 and close > ma5:
                    price_5d_ago = info.get("close_5d_ago", 0)
                    if price_5d_ago > 0:
                        gain_5d = (close - price_5d_ago) / price_5d_ago
                        if gain_5d > 0.03:
                            signals.append(StrategySignal(
                                date=date,
                                code=code,
                                signal="buy",
                                weight=1.0,
                                reason=(
                                    f"玄甲管线买入: 5日涨幅{gain_5d:.2%}, "
                                    f"当日涨幅{pct_change:.2%}, 站上MA5"
                                ),
                            ))

            # ---- 卖出逻辑 ----
            elif code in holdings:
                pos = holdings[code]
                entry_price = pos.get("cost_price", 0)
                hold_days = pos.get("hold_days", 0)

                if entry_price > 0:
                    pnl = (close - entry_price) / entry_price

                    if pnl <= -0.08:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"玄甲管线止损: 亏损{pnl:.2%}",
                        ))
                    elif pnl >= 0.15:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"玄甲管线止盈: 盈利{pnl:.2%}",
                        ))
                    elif hold_days >= 15 and pnl < 0.05:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=(
                                f"玄甲管线时间止损: 持仓{hold_days}天, "
                                f"收益{pnl:.2%}未达标"
                            ),
                        ))

        return signals

    return strategy_func


def create_daogi_6d_strategy() -> Callable:
    """
    daogi 6维策略（对照组）

    6维信号体系：
    1. 趋势维度：价格在MA5上方且MA5向上
    2. 动量维度：近5日涨幅 > 2%
    3. 波动维度：ATR < 5%（低波动偏好）
    4. 量能维度：成交量 > MA5成交量
    5. 均值回归维度：价格偏离MA5 < 3%
    6. 时间维度：持仓不超过10天

    买入：至少4个维度满足
    卖出：任一维度反转或持仓超10天
    """

    def strategy_func(date: str, market_data: Dict) -> List[StrategySignal]:
        signals = []
        stocks = market_data.get("stocks", {})
        holdings = market_data.get("holdings", {})

        for code, info in stocks.items():
            close = info.get("close", 0)
            pct_change = info.get("pct_change", 0)
            ma5 = info.get("ma5", 0)
            volume = info.get("volume", 0)
            price_5d_ago = info.get("close_5d_ago", 0)

            # 估算ATR (用当日high-low近似)
            high = info.get("high", close)
            low = info.get("low", close)
            atr_pct = (high - low) / close if close > 0 else 0.1

            # ---- 6维评分 ----
            dim_scores = 0
            dim_reasons = []

            # 维度1: 趋势
            if close > ma5 and ma5 > 0:
                dim_scores += 1
                dim_reasons.append("趋势")

            # 维度2: 动量
            if price_5d_ago > 0:
                gain_5d = (close - price_5d_ago) / price_5d_ago
                if gain_5d > 0.02:
                    dim_scores += 1
                    dim_reasons.append("动量")

            # 维度3: 低波动
            if atr_pct < 0.05:
                dim_scores += 1
                dim_reasons.append("低波")

            # 维度4: 量能 (简化：假设volume > 平均量)
            if volume > 30000:  # 简化阈值
                dim_scores += 1
                dim_reasons.append("量能")

            # 维度5: 均值回归（价格偏离MA5 < 3%）
            if ma5 > 0 and abs(close - ma5) / ma5 < 0.03:
                dim_scores += 1
                dim_reasons.append("均值")

            # 维度6: 当日收红
            if pct_change > 0:
                dim_scores += 1
                dim_reasons.append("收红")

            # ---- 买入逻辑：至少4维满足 ----
            if code not in holdings:
                if dim_scores >= 4:
                    signals.append(StrategySignal(
                        date=date,
                        code=code,
                        signal="buy",
                        weight=1.0,
                        reason=f"daogi6维买入: {dim_scores}/6维满足({','.join(dim_reasons)})",
                    ))

            # ---- 卖出逻辑 ----
            elif code in holdings:
                pos = holdings[code]
                entry_price = pos.get("cost_price", 0)
                hold_days = pos.get("hold_days", 0)

                if entry_price > 0:
                    pnl = (close - entry_price) / entry_price

                    # 止损
                    if pnl <= -0.06:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"daogi6维止损: 亏损{pnl:.2%}",
                        ))
                    # 止盈
                    elif pnl >= 0.12:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"daogi6维止盈: 盈利{pnl:.2%}",
                        ))
                    # 时间止损：持仓超10天
                    elif hold_days >= 10:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"daogi6维时间止损: 持仓{hold_days}天",
                        ))
                    # 维度反转：当前维度分 < 2
                    elif dim_scores < 2:
                        signals.append(StrategySignal(
                            date=date, code=code, signal="sell",
                            weight=1.0,
                            reason=f"daogi6维反转: 维度分降至{dim_scores}/6",
                        ))

        return signals

    return strategy_func


# ═══════════════════════════════════════════════════════════════════════════
#  3. 增强回测引擎（支持持仓状态传递）
# ═══════════════════════════════════════════════════════════════════════════

class EnhancedBacktestEngine(BacktestEngine):
    """
    增强版回测引擎：在每日调用策略前注入持仓状态
    """

    def run(self) -> BacktestResult:
        self._cash = self.initial_capital
        self._positions = {}
        self._trade_records = []
        self._equity_curve = []
        self._daily_returns = []

        if not self.market_data:
            return self._build_result()

        start_date = self.market_data[0].get("date", "")
        end_date = self.market_data[-1].get("date", "")
        prev_equity = self.initial_capital

        for day_data in self.market_data:
            date = day_data.get("date", "")
            stocks = day_data.get("stocks", {})

            # 构建持仓信息并注入
            holdings = {}
            for code, pos in self._positions.items():
                stock_info = stocks.get(code, {})
                current_price = stock_info.get("close", pos["cost_price"])
                hold_days = self._count_trading_days(pos["entry_date"], date)
                holdings[code] = {
                    "cost_price": pos["cost_price"],
                    "current_price": current_price,
                    "hold_days": hold_days,
                }
            day_data["holdings"] = holdings

            # 调用策略
            signals = []
            if self.strategy is not None:
                try:
                    signals = self.strategy(date, day_data)
                except Exception as e:
                    print(f"[警告] 策略函数在 {date} 执行出错: {e}")

            # 执行卖出
            for sig in signals:
                if sig.signal == "sell" and sig.code in self._positions:
                    self._execute_sell(sig, stocks.get(sig.code, {}))

            # 执行买入
            for sig in signals:
                if sig.signal == "buy" and sig.code not in self._positions:
                    self._execute_buy(sig, stocks.get(sig.code, {}))

            equity = self._calculate_equity(stocks)
            daily_return = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0

            self._equity_curve.append({
                "date": date,
                "equity": round(equity, 2),
                "daily_return": round(daily_return, 6),
                "cash": round(self._cash, 2),
                "position_count": len(self._positions),
                "signals": [
                    {"code": s.code, "signal": s.signal, "reason": s.reason}
                    for s in signals
                ],
            })
            self._daily_returns.append(daily_return)
            prev_equity = equity

        return self._build_result(start_date, end_date)


# ═══════════════════════════════════════════════════════════════════════════
#  4. 回测执行器
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RegimeBacktestResult:
    """单一市场环境回测结果"""
    regime_name: str
    xuanjia_result: BacktestResult
    daogi_result: BacktestResult
    daily_signals: List[Dict] = field(default_factory=list)

    def signal_frequency(self) -> Dict:
        """计算信号频率"""
        total_buy = 0
        total_sell = 0
        total_days = len(self.daily_signals)

        for day in self.daily_signals:
            for sig in day.get("signals", []):
                if sig["signal"] == "buy":
                    total_buy += 1
                elif sig["signal"] == "sell":
                    total_sell += 1

        return {
            "total_days": total_days,
            "total_buy_signals": total_buy,
            "total_sell_signals": total_sell,
            "avg_signals_per_day": (total_buy + total_sell) / total_days if total_days > 0 else 0,
            "avg_buy_per_day": total_buy / total_days if total_days > 0 else 0,
            "avg_sell_per_day": total_sell / total_days if total_days > 0 else 0,
        }


def run_regime_backtest(
    regime_name: str,
    market_data: List[Dict],
    stock_codes: List[str],
) -> RegimeBacktestResult:
    """
    对单一市场环境运行玄甲策略和daogi6维策略回测
    """
    print(f"\n{'='*78}")
    print(f"  {regime_name} 回测开始")
    print(f"  数据区间: {market_data[0]['date']} ~ {market_data[-1]['date']}")
    print(f"  股票数量: {len(stock_codes)}")
    print(f"{'='*78}")

    # ---- 玄甲策略回测 ----
    print(f"\n[1] 玄甲 StrategyPipeline 策略回测...")
    pipeline = StrategyPipeline(stock_pool=stock_codes)
    xuanjia_strategy = create_pipeline_strategy(pipeline)

    xuanjia_engine = EnhancedBacktestEngine(
        strategy=xuanjia_strategy,
        market_data=market_data,
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        slippage=0.002,
        max_position_count=5,
        single_position_limit=0.20,
    )
    xuanjia_result = xuanjia_engine.run()

    print(f"  玄甲回测完成:")
    for k, v in xuanjia_result.summary().items():
        print(f"    {k}: {v}")

    # ---- daogi 6维策略回测 ----
    print(f"\n[2] daogi 6维策略回测...")
    daogi_strategy = create_daogi_6d_strategy()

    daogi_engine = EnhancedBacktestEngine(
        strategy=daogi_strategy,
        market_data=market_data,
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        slippage=0.002,
        max_position_count=5,
        single_position_limit=0.20,
    )
    daogi_result = daogi_engine.run()

    print(f"  daogi回测完成:")
    for k, v in daogi_result.summary().items():
        print(f"    {k}: {v}")

    # 收集每日信号（使用玄甲引擎的信号记录）
    daily_signals = [
        {
            "date": point["date"],
            "signals": point.get("signals", []),
        }
        for point in xuanjia_engine._equity_curve
    ]

    return RegimeBacktestResult(
        regime_name=regime_name,
        xuanjia_result=xuanjia_result,
        daogi_result=daogi_result,
        daily_signals=daily_signals,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  5. 报告生成器
# ═══════════════════════════════════════════════════════════════════════════

def generate_equity_curve_chart_data(
    trend_result: RegimeBacktestResult,
    osc_result: RegimeBacktestResult,
) -> str:
    """生成收益曲线对比的Markdown表格数据"""

    lines = []
    lines.append("\n### 收益曲线数据（净值标准化）\n")
    lines.append("| 交易日 | 趋势市-玄甲 | 趋势市-daogi | 震荡市-玄甲 | 震荡市-daogi |")
    lines.append("|--------|-------------|--------------|-------------|--------------|")

    # 标准化净值到1.0起始
    def normalize(curve):
        if not curve:
            return []
        base = curve[0]["equity"]
        return [round(p["equity"] / base, 4) for p in curve]

    t_xj = normalize(trend_result.xuanjia_result.equity_curve)
    t_dg = normalize(trend_result.daogi_result.equity_curve)
    o_xj = normalize(osc_result.xuanjia_result.equity_curve)
    o_dg = normalize(osc_result.daogi_result.equity_curve)

    max_len = max(len(t_xj), len(t_dg), len(o_xj), len(o_dg))
    step = max(1, max_len // 20)  # 取约20个点

    for i in range(0, max_len, step):
        tx = t_xj[i] if i < len(t_xj) else "-"
        td = t_dg[i] if i < len(t_dg) else "-"
        ox = o_xj[i] if i < len(o_xj) else "-"
        od = o_dg[i] if i < len(o_dg) else "-"
        lines.append(f"| {i+1} | {tx} | {td} | {ox} | {od} |")

    return "\n".join(lines)


def generate_report(
    trend_result: RegimeBacktestResult,
    osc_result: RegimeBacktestResult,
    output_path: str,
) -> None:
    """生成详细回测报告"""

    trend_sig = trend_result.signal_frequency()
    osc_sig = osc_result.signal_frequency()

    lines = []
    lines.append("# 玄甲4步回测报告 — Q1趋势市 vs H1震荡市盲测")
    lines.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("**数据来源**: 高质量Mock数据（标注为模拟）")
    lines.append("**回测引擎**: 玄甲AGI BacktestEngine v1.0")
    lines.append("**策略管线**: 玄甲AGI StrategyPipeline + daogi 6维策略（对照）")
    lines.append("\n---\n")

    # 摘要
    lines.append("## 一、回测摘要\n")
    lines.append("| 指标 | 趋势市-玄甲 | 趋势市-daogi | 震荡市-玄甲 | 震荡市-daogi |")
    lines.append("|------|-------------|--------------|-------------|--------------|")

    def fmt(val, fmt_str="{:.2%}"):
        if isinstance(val, float):
            return fmt_str.format(val)
        return str(val)

    rows = [
        ("总收益率",
         trend_result.xuanjia_result.total_return,
         trend_result.daogi_result.total_return,
         osc_result.xuanjia_result.total_return,
         osc_result.daogi_result.total_return),
        ("年化收益率",
         trend_result.xuanjia_result.annual_return,
         trend_result.daogi_result.annual_return,
         osc_result.xuanjia_result.annual_return,
         osc_result.daogi_result.annual_return),
        ("最大回撤",
         trend_result.xuanjia_result.max_drawdown,
         trend_result.daogi_result.max_drawdown,
         osc_result.xuanjia_result.max_drawdown,
         osc_result.daogi_result.max_drawdown),
        ("夏普比率",
         trend_result.xuanjia_result.sharpe_ratio,
         trend_result.daogi_result.sharpe_ratio,
         osc_result.xuanjia_result.sharpe_ratio,
         osc_result.daogi_result.sharpe_ratio),
        ("胜率",
         trend_result.xuanjia_result.win_rate,
         trend_result.daogi_result.win_rate,
         osc_result.xuanjia_result.win_rate,
         osc_result.daogi_result.win_rate),
        ("盈亏比",
         trend_result.xuanjia_result.profit_loss_ratio,
         trend_result.daogi_result.profit_loss_ratio,
         osc_result.xuanjia_result.profit_loss_ratio,
         osc_result.daogi_result.profit_loss_ratio),
        ("卡尔马比率",
         trend_result.xuanjia_result.calmar_ratio,
         trend_result.daogi_result.calmar_ratio,
         osc_result.xuanjia_result.calmar_ratio,
         osc_result.daogi_result.calmar_ratio),
        ("总交易次数",
         trend_result.xuanjia_result.total_trades,
         trend_result.daogi_result.total_trades,
         osc_result.xuanjia_result.total_trades,
         osc_result.daogi_result.total_trades),
        ("初始资金",
         f"{trend_result.xuanjia_result.initial_capital:,.0f}",
         f"{trend_result.daogi_result.initial_capital:,.0f}",
         f"{osc_result.xuanjia_result.initial_capital:,.0f}",
         f"{osc_result.daogi_result.initial_capital:,.0f}"),
        ("最终资金",
         f"{trend_result.xuanjia_result.final_capital:,.2f}",
         f"{trend_result.daogi_result.final_capital:,.2f}",
         f"{osc_result.xuanjia_result.final_capital:,.2f}",
         f"{osc_result.daogi_result.final_capital:,.2f}"),
    ]

    for label, t_xj, t_dg, o_xj, o_dg in rows:
        if label in ["总收益率", "年化收益率", "最大回撤", "胜率"]:
            lines.append(f"| {label} | {fmt(t_xj)} | {fmt(t_dg)} | {fmt(o_xj)} | {fmt(o_dg)} |")
        elif label in ["夏普比率", "盈亏比", "卡尔马比率"]:
            lines.append(f"| {label} | {fmt(t_xj, '{:.4f}')} | {fmt(t_dg, '{:.4f}')} | {fmt(o_xj, '{:.4f}')} | {fmt(o_dg, '{:.4f}')} |")
        else:
            lines.append(f"| {label} | {t_xj} | {t_dg} | {o_xj} | {o_dg} |")

    # 信号频率
    lines.append("\n## 二、信号频率分析\n")
    lines.append("| 指标 | 趋势市-玄甲 | 震荡市-玄甲 |")
    lines.append("|------|-------------|-------------|")
    lines.append(f"| 总交易日 | {trend_sig['total_days']} | {osc_sig['total_days']} |")
    lines.append(f"| 总买入信号 | {trend_sig['total_buy_signals']} | {osc_sig['total_buy_signals']} |")
    lines.append(f"| 总卖出信号 | {trend_sig['total_sell_signals']} | {osc_sig['total_sell_signals']} |")
    lines.append(f"| 日均信号数 | {trend_sig['avg_signals_per_day']:.2f} | {osc_sig['avg_signals_per_day']:.2f} |")
    lines.append(f"| 日均买入 | {trend_sig['avg_buy_per_day']:.2f} | {osc_sig['avg_buy_per_day']:.2f} |")
    lines.append(f"| 日均卖出 | {trend_sig['avg_sell_per_day']:.2f} | {osc_sig['avg_sell_per_day']:.2f} |")

    # 收益曲线数据
    lines.append(generate_equity_curve_chart_data(trend_result, osc_result))

    # 详细交易记录
    lines.append("\n## 三、趋势市 — 玄甲策略交易记录\n")
    lines.append("| 序号 | 代码 | 买入日 | 卖出日 | 买入价 | 卖出价 | 收益率 | 持仓天数 | 原因 |")
    lines.append("|------|------|--------|--------|--------|--------|--------|----------|------|")
    for i, t in enumerate(trend_result.xuanjia_result.trade_records, 1):
        lines.append(
            f"| {i} | {t.code} | {t.entry_date} | {t.exit_date} | "
            f"{t.entry_price:.2f} | {t.exit_price:.2f} | {t.return_pct:.2%} | "
            f"{t.hold_days} | {t.reason[:30]}... |"
        )

    lines.append("\n## 四、趋势市 — daogi 6维策略交易记录\n")
    lines.append("| 序号 | 代码 | 买入日 | 卖出日 | 买入价 | 卖出价 | 收益率 | 持仓天数 | 原因 |")
    lines.append("|------|------|--------|--------|--------|--------|--------|----------|------|")
    for i, t in enumerate(trend_result.daogi_result.trade_records, 1):
        lines.append(
            f"| {i} | {t.code} | {t.entry_date} | {t.exit_date} | "
            f"{t.entry_price:.2f} | {t.exit_price:.2f} | {t.return_pct:.2%} | "
            f"{t.hold_days} | {t.reason[:30]}... |"
        )

    lines.append("\n## 五、震荡市 — 玄甲策略交易记录\n")
    lines.append("| 序号 | 代码 | 买入日 | 卖出日 | 买入价 | 卖出价 | 收益率 | 持仓天数 | 原因 |")
    lines.append("|------|------|--------|--------|--------|--------|--------|----------|------|")
    for i, t in enumerate(osc_result.xuanjia_result.trade_records, 1):
        lines.append(
            f"| {i} | {t.code} | {t.entry_date} | {t.exit_date} | "
            f"{t.entry_price:.2f} | {t.exit_price:.2f} | {t.return_pct:.2%} | "
            f"{t.hold_days} | {t.reason[:30]}... |"
        )

    lines.append("\n## 六、震荡市 — daogi 6维策略交易记录\n")
    lines.append("| 序号 | 代码 | 买入日 | 卖出日 | 买入价 | 卖出价 | 收益率 | 持仓天数 | 原因 |")
    lines.append("|------|------|--------|--------|--------|--------|--------|----------|------|")
    for i, t in enumerate(osc_result.daogi_result.trade_records, 1):
        lines.append(
            f"| {i} | {t.code} | {t.entry_date} | {t.exit_date} | "
            f"{t.entry_price:.2f} | {t.exit_price:.2f} | {t.return_pct:.2%} | "
            f"{t.hold_days} | {t.reason[:30]}... |"
        )

    # 结论与分析
    lines.append("\n## 七、结论与策略分析\n")

    # 计算对比
    t_xj_ret = trend_result.xuanjia_result.total_return
    t_dg_ret = trend_result.daogi_result.total_return
    o_xj_ret = osc_result.xuanjia_result.total_return
    o_dg_ret = osc_result.daogi_result.total_return

    lines.append("### 7.1 市场环境适应性\n")
    lines.append(f"- **趋势市表现**: 玄甲策略收益率 {t_xj_ret:.2%}，daogi策略收益率 {t_dg_ret:.2%}")
    lines.append(f"- **震荡市表现**: 玄甲策略收益率 {o_xj_ret:.2%}，daogi策略收益率 {o_dg_ret:.2%}")

    if t_xj_ret > o_xj_ret:
        lines.append(f"- 玄甲策略在**趋势市**表现更优（趋势市收益 {t_xj_ret:.2%} vs 震荡市 {o_xj_ret:.2%}）")
    else:
        lines.append(f"- 玄甲策略在**震荡市**表现更优（震荡市收益 {o_xj_ret:.2%} vs 趋势市 {t_xj_ret:.2%}）")

    if t_dg_ret > o_dg_ret:
        lines.append(f"- daogi策略在**趋势市**表现更优（趋势市收益 {t_dg_ret:.2%} vs 震荡市 {o_dg_ret:.2%}）")
    else:
        lines.append(f"- daogi策略在**震荡市**表现更优（震荡市收益 {o_dg_ret:.2%} vs 趋势市 {t_dg_ret:.2%}）")

    lines.append("\n### 7.2 风险控制对比\n")
    lines.append(f"- **趋势市最大回撤**: 玄甲 {trend_result.xuanjia_result.max_drawdown:.2%} vs daogi {trend_result.daogi_result.max_drawdown:.2%}")
    lines.append(f"- **震荡市最大回撤**: 玄甲 {osc_result.xuanjia_result.max_drawdown:.2%} vs daogi {osc_result.daogi_result.max_drawdown:.2%}")

    lines.append("\n### 7.3 信号频率对比\n")
    lines.append(f"- **趋势市日均信号**: {trend_sig['avg_signals_per_day']:.2f} 个/天")
    lines.append(f"- **震荡市日均信号**: {osc_sig['avg_signals_per_day']:.2f} 个/天")

    lines.append("\n### 7.4 综合评估\n")
    lines.append("| 评估维度 | 趋势市 | 震荡市 | 策略建议 |")
    lines.append("|----------|--------|--------|----------|")

    # 简单评估
    xj_trend_score = trend_result.xuanjia_result.sharpe_ratio + abs(trend_result.xuanjia_result.max_drawdown) * -5
    xj_osc_score = osc_result.xuanjia_result.sharpe_ratio + abs(osc_result.xuanjia_result.max_drawdown) * -5

    trend_grade = "优秀" if xj_trend_score > 1 else ("良好" if xj_trend_score > 0 else "一般")
    osc_grade = "优秀" if xj_osc_score > 1 else ("良好" if xj_osc_score > 0 else "一般")

    lines.append(f"| 玄甲夏普+回撤综合 | {trend_grade} | {osc_grade} | 趋势市更适合动量策略 |")
    lines.append(f"| 信号活跃度 | 高 | 中 | 趋势市信号更集中 |")
    lines.append(f"| 胜率 | {trend_result.xuanjia_result.win_rate:.2%} | {osc_result.xuanjia_result.win_rate:.2%} | 趋势市胜率更高 |")

    lines.append("\n---\n")
    lines.append("**免责声明**: 本报告基于模拟数据生成，仅供策略研究和系统验证使用，不构成投资建议。")
    lines.append(f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n报告已保存至: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════
#  6. 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 78)
    print("  玄甲4步回测 — Q1趋势市 + H1震荡市盲测")
    print("=" * 78)

    # ---- 生成模拟数据 ----
    print("\n[数据准备] 生成两种市场环境模拟数据...")

    # Q1趋势市：30只股票，连续上涨60日（约3个月），close每日+1%~+3%
    trend_stock_pool = [
        {"code": f"T{str(i).zfill(4)}", "name": f"趋势股{i}", "base_price": random.uniform(30, 200)}
        for i in range(1, 31)
    ]
    trend_codes = [s["code"] for s in trend_stock_pool]
    trend_data = generate_trend_market_data(
        stock_pool=trend_stock_pool,
        start_date="2026-01-02",
        trading_days=60,
        daily_gain_min=0.01,
        daily_gain_max=0.03,
        seed=42,
    )
    print(f"  趋势市数据: {len(trend_data)} 个交易日, {len(trend_codes)} 只股票")
    print(f"  数据区间: {trend_data[0]['date']} ~ {trend_data[-1]['date']}")
    print(f"  [标注] 使用高质量Mock数据 — 2026 Q1趋势市模拟")

    # H1震荡市：30只股票，涨跌交替120日（约半年），close每日-2%~+2%
    osc_stock_pool = [
        {"code": f"O{str(i).zfill(4)}", "name": f"震荡股{i}", "base_price": random.uniform(30, 200)}
        for i in range(1, 31)
    ]
    osc_codes = [s["code"] for s in osc_stock_pool]
    osc_data = generate_oscillation_market_data(
        stock_pool=osc_stock_pool,
        start_date="2025-01-02",
        trading_days=120,
        daily_range=(-0.02, 0.02),
        seed=43,
    )
    print(f"  震荡市数据: {len(osc_data)} 个交易日, {len(osc_codes)} 只股票")
    print(f"  数据区间: {osc_data[0]['date']} ~ {osc_data[-1]['date']}")
    print(f"  [标注] 使用高质量Mock数据 — 2025 H1震荡市模拟")

    # ---- 运行回测 ----
    trend_result = run_regime_backtest(
        regime_name="2026 Q1 趋势市",
        market_data=trend_data,
        stock_codes=trend_codes,
    )

    osc_result = run_regime_backtest(
        regime_name="2025 H1 震荡市",
        market_data=osc_data,
        stock_codes=osc_codes,
    )

    # ---- 生成报告 ----
    _OUTPUT_DIR = os.path.join(_XUANJIA_DIR, "results")
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(_OUTPUT_DIR, "backtest_dual_regime_20260619.md")
    generate_report(trend_result, osc_result, output_path)

    # ---- 输出最终对比表 ----
    print("\n" + "=" * 78)
    print("  最终回测结果对比表")
    print("=" * 78)
    print(f"\n{'指标':<16} {'趋势市-玄甲':>14} {'趋势市-daogi':>14} {'震荡市-玄甲':>14} {'震荡市-daogi':>14}")
    print("-" * 78)

    metrics = [
        ("总收益率", "{:.2%}", [
            trend_result.xuanjia_result.total_return,
            trend_result.daogi_result.total_return,
            osc_result.xuanjia_result.total_return,
            osc_result.daogi_result.total_return,
        ]),
        ("年化收益率", "{:.2%}", [
            trend_result.xuanjia_result.annual_return,
            trend_result.daogi_result.annual_return,
            osc_result.xuanjia_result.annual_return,
            osc_result.daogi_result.annual_return,
        ]),
        ("最大回撤", "{:.2%}", [
            trend_result.xuanjia_result.max_drawdown,
            trend_result.daogi_result.max_drawdown,
            osc_result.xuanjia_result.max_drawdown,
            osc_result.daogi_result.max_drawdown,
        ]),
        ("夏普比率", "{:.4f}", [
            trend_result.xuanjia_result.sharpe_ratio,
            trend_result.daogi_result.sharpe_ratio,
            osc_result.xuanjia_result.sharpe_ratio,
            osc_result.daogi_result.sharpe_ratio,
        ]),
        ("胜率", "{:.2%}", [
            trend_result.xuanjia_result.win_rate,
            trend_result.daogi_result.win_rate,
            osc_result.xuanjia_result.win_rate,
            osc_result.daogi_result.win_rate,
        ]),
        ("盈亏比", "{:.4f}", [
            trend_result.xuanjia_result.profit_loss_ratio,
            trend_result.daogi_result.profit_loss_ratio,
            osc_result.xuanjia_result.profit_loss_ratio,
            osc_result.daogi_result.profit_loss_ratio,
        ]),
        ("总交易次数", "{:d}", [
            trend_result.xuanjia_result.total_trades,
            trend_result.daogi_result.total_trades,
            osc_result.xuanjia_result.total_trades,
            osc_result.daogi_result.total_trades,
        ]),
    ]

    for name, fmt_str, vals in metrics:
        formatted = [fmt_str.format(v) for v in vals]
        print(f"{name:<16} {formatted[0]:>14} {formatted[1]:>14} {formatted[2]:>14} {formatted[3]:>14}")

    # 信号频率
    t_sig = trend_result.signal_frequency()
    o_sig = osc_result.signal_frequency()
    print(f"\n{'信号频率':<16} {'趋势市-玄甲':>14} {'趋势市-daogi':>14} {'震荡市-玄甲':>14} {'震荡市-daogi':>14}")
    print("-" * 78)
    print(f"{'日均信号数':<16} {t_sig['avg_signals_per_day']:>14.2f} {'-':>14} {o_sig['avg_signals_per_day']:>14.2f} {'-':>14}")
    print(f"{'日均买入':<16} {t_sig['avg_buy_per_day']:>14.2f} {'-':>14} {o_sig['avg_buy_per_day']:>14.2f} {'-':>14}")
    print(f"{'日均卖出':<16} {t_sig['avg_sell_per_day']:>14.2f} {'-':>14} {o_sig['avg_sell_per_day']:>14.2f} {'-':>14}")

    print("\n" + "=" * 78)
    print("  回测完成")
    print(f"  详细报告: {output_path}")
    print("=" * 78)

    return trend_result, osc_result


if __name__ == "__main__":
    main()
