#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_engine.py — 玄甲AGI 回测框架

本模块实现一个完整的A股策略回测框架，包含：
1. StrategySignal — 策略信号数据类
2. TradeRecord — 交易记录数据类
3. BacktestResult — 回测结果数据类
4. BacktestEngine — 核心回测引擎（逐日模拟、指标计算、净值曲线生成）

支持任意策略函数接入，仅需实现签名为：
    strategy(date: str, market_data: dict) -> list[StrategySignal]

内置一个X大神策略回测演示，展示完整回测流程。
仅依赖标准库，无需第三方包。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


# ============================================================
#  数据类定义
# ============================================================

@dataclass
class StrategySignal:
    """
    策略信号

    策略函数每日输出一组信号，回测引擎据此执行交易。

    Attributes:
        date: 信号日期 (YYYY-MM-DD)
        code: 股票代码
        signal: 信号类型 — "buy" / "sell" / "hold"
        weight: 建议仓位权重（0~1），buy时为买入比例，sell时为卖出比例
        reason: 信号原因说明
    """
    date: str
    code: str
    signal: str       # "buy" / "sell" / "hold"
    weight: float = 1.0
    reason: str = ""


@dataclass
class TradeRecord:
    """
    交易记录

    记录每笔完整的交易（买入→卖出）。

    Attributes:
        entry_date: 买入日期
        exit_date: 卖出日期
        code: 股票代码
        entry_price: 买入价格
        exit_price: 卖出价格
        return_pct: 交易收益率（百分比）
        hold_days: 持仓天数
        reason: 交易原因（卖出时的原因）
    """
    entry_date: str
    exit_date: str
    code: str
    entry_price: float
    exit_price: float
    return_pct: float
    hold_days: int
    reason: str = ""


@dataclass
class BacktestResult:
    """
    回测结果

    汇总回测的所有关键指标和详细数据。

    Attributes:
        total_return: 总收益率
        annual_return: 年化收益率
        max_drawdown: 最大回撤（负数）
        sharpe_ratio: 夏普比率
        win_rate: 胜率
        profit_loss_ratio: 盈亏比（平均盈利/平均亏损）
        calmar_ratio: 卡尔马比率（年化收益/最大回撤绝对值）
        total_trades: 总交易次数
        trade_records: 所有交易记录列表
        equity_curve: 净值曲线 [{date, equity, daily_return}]
        start_date: 回测起始日期
        end_date: 回测结束日期
        initial_capital: 初始资金
        final_capital: 最终资金
    """
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    calmar_ratio: float = 0.0
    total_trades: int = 0
    trade_records: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0.0
    final_capital: float = 0.0

    def summary(self) -> Dict:
        """生成回测结果摘要字典"""
        return {
            "总收益率": f"{self.total_return:.2%}",
            "年化收益率": f"{self.annual_return:.2%}",
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.4f}",
            "胜率": f"{self.win_rate:.2%}",
            "盈亏比": f"{self.profit_loss_ratio:.4f}",
            "卡尔马比率": f"{self.calmar_ratio:.4f}",
            "总交易次数": self.total_trades,
            "回测区间": f"{self.start_date} ~ {self.end_date}",
            "初始资金": f"{self.initial_capital:,.2f}",
            "最终资金": f"{self.final_capital:,.2f}",
        }


# ============================================================
#  BacktestEngine — 核心回测引擎
# ============================================================

@dataclass
class BacktestEngine:
    """
    回测引擎

    逐日模拟交易过程，支持买入/卖出/持有信号。
    计算完整的回测指标体系。

    Usage:
        engine = BacktestEngine(
            strategy=my_strategy_func,
            market_data=daily_data_list,
            initial_capital=1_000_000,
        )
        result = engine.run()
        print(result.summary())
    """

    # ---------- 核心参数 ----------
    strategy: Callable[[str, Dict], List[StrategySignal]] = field(default=None)  # 策略函数
    market_data: List[Dict] = field(default_factory=list)                        # 历史日线数据
    initial_capital: float = 1_000_000.0                                        # 初始资金

    # ---------- 交易参数 ----------
    commission_rate: float = 0.0003       # 佣金费率（万三）
    stamp_tax_rate: float = 0.001         # 印花税率（千一，仅卖出时收取）
    slippage: float = 0.002              # 滑点（千二）
    max_position_count: int = 5          # 最大同时持仓数量
    single_position_limit: float = 0.20   # 单只持仓上限（占总资金比例）
    risk_free_rate: float = 0.03         # 无风险利率（年化）

    # ---------- 内部状态 ----------
    _cash: float = field(init=False, default=0.0)
    _positions: Dict[str, Dict] = field(init=False, default_factory=dict)  # {code: {shares, cost, entry_date}}
    _trade_records: List[TradeRecord] = field(init=False, default_factory=list)
    _equity_curve: List[Dict] = field(init=False, default_factory=list)
    _daily_returns: List[float] = field(init=False, default_factory=list)

    def run(self) -> BacktestResult:
        """
        执行回测

        逐日遍历市场数据，调用策略函数获取信号，执行交易，记录净值。

        Returns:
            BacktestResult 完整回测结果
        """
        # 初始化状态
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
            # 当日所有股票的行情数据
            stocks = day_data.get("stocks", {})

            # 调用策略函数获取当日信号
            signals = []
            if self.strategy is not None:
                try:
                    signals = self.strategy(date, day_data)
                except Exception as e:
                    print(f"[警告] 策略函数在 {date} 执行出错: {e}")

            # 执行卖出信号
            for sig in signals:
                if sig.signal == "sell" and sig.code in self._positions:
                    self._execute_sell(sig, stocks.get(sig.code, {}))

            # 执行买入信号
            for sig in signals:
                if sig.signal == "buy" and sig.code not in self._positions:
                    self._execute_buy(sig, stocks.get(sig.code, {}))

            # 计算当日总权益
            equity = self._calculate_equity(stocks)
            daily_return = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0

            self._equity_curve.append({
                "date": date,
                "equity": round(equity, 2),
                "daily_return": round(daily_return, 6),
                "cash": round(self._cash, 2),
                "position_count": len(self._positions),
            })
            self._daily_returns.append(daily_return)
            prev_equity = equity

        return self._build_result(start_date, end_date)

    def _execute_buy(self, signal: StrategySignal, stock_info: Dict) -> None:
        """
        执行买入操作

        考虑：可用资金、仓位上限、滑点、佣金
        """
        code = signal.code
        price = stock_info.get("close", 0.0)

        if price <= 0:
            return

        # 检查持仓数量限制
        if len(self._positions) >= self.max_position_count:
            return

        # 计算买入金额（考虑仓位限制）
        buy_amount = self._cash * signal.weight * self.single_position_limit
        buy_amount = min(buy_amount, self._cash)

        if buy_amount < 100 * price:  # 至少买一手
            return

        # 考虑滑点（买入时价格上浮）
        actual_price = price * (1.0 + self.slippage)

        # 计算可买股数（A股最少100股）
        shares = int(buy_amount / actual_price / 100) * 100
        if shares <= 0:
            return

        # 实际花费
        cost = shares * actual_price
        commission = max(cost * self.commission_rate, 5.0)  # 佣金最低5元
        total_cost = cost + commission

        if total_cost > self._cash:
            # 资金不足，减少股数
            available = self._cash - 5.0  # 预留佣金
            shares = int(available / actual_price / 100) * 100
            if shares <= 0:
                return
            cost = shares * actual_price
            commission = max(cost * self.commission_rate, 5.0)
            total_cost = cost + commission

        # 更新状态
        self._cash -= total_cost
        self._positions[code] = {
            "shares": shares,
            "cost_price": actual_price,
            "entry_date": signal.date,
            "entry_reason": signal.reason,
        }

    def _execute_sell(self, signal: StrategySignal, stock_info: Dict) -> None:
        """
        执行卖出操作

        考虑：滑点、佣金、印花税
        """
        code = signal.code
        price = stock_info.get("close", 0.0)

        if code not in self._positions or price <= 0:
            return

        pos = self._positions[code]
        shares = pos["shares"]

        # 考虑滑点（卖出时价格下浮）
        actual_price = price * (1.0 - self.slippage)

        # 卖出收入
        revenue = shares * actual_price
        commission = max(revenue * self.commission_rate, 5.0)
        stamp_tax = revenue * self.stamp_tax_rate  # 印花税（仅卖出）
        total_revenue = revenue - commission - stamp_tax

        # 计算收益率
        cost_basis = shares * pos["cost_price"]
        return_pct = (total_revenue - cost_basis) / cost_basis if cost_basis > 0 else 0.0

        # 计算持仓天数
        hold_days = self._count_trading_days(pos["entry_date"], signal.date)

        # 记录交易
        record = TradeRecord(
            entry_date=pos["entry_date"],
            exit_date=signal.date,
            code=code,
            entry_price=round(pos["cost_price"], 4),
            exit_price=round(actual_price, 4),
            return_pct=round(return_pct, 6),
            hold_days=hold_days,
            reason=signal.reason or pos.get("entry_reason", ""),
        )
        self._trade_records.append(record)

        # 更新状态
        self._cash += total_revenue
        del self._positions[code]

    def _calculate_equity(self, stocks: Dict) -> float:
        """计算当前总权益（现金 + 持仓市值）"""
        equity = self._cash
        for code, pos in self._positions.items():
            price = stocks.get(code, {}).get("close", pos["cost_price"])
            equity += pos["shares"] * price
        return equity

    def _count_trading_days(self, start_date: str, end_date: str) -> int:
        """
        计算两个日期之间的交易日天数（简化版）

        简化处理：假设每周5个交易日，按自然日/7*5估算
        """
        if not start_date or not end_date:
            return 0
        try:
            y1, m1, d1 = int(start_date[:4]), int(start_date[5:7]), int(start_date[8:10])
            y2, m2, d2 = int(end_date[:4]), int(end_date[5:7]), int(end_date[8:10])

            # 简化的Julian Day计算
            def julian(y, m, d):
                return y * 365 + y // 4 - y // 100 + y // 400 + (m * 306 + 5) // 10 + d

            days = julian(y2, m2, d2) - julian(y1, m1, d1)
            # 大约5/7是交易日
            return max(0, int(days * 5 / 7))
        except (ValueError, IndexError):
            return 0

    def _build_result(self, start_date: str = "", end_date: str = "") -> BacktestResult:
        """构建回测结果"""
        # 最终权益
        final_equity = self._equity_curve[-1]["equity"] if self._equity_curve else self.initial_capital

        # 总收益率
        total_return = (final_equity - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0.0

        # 年化收益率
        trading_days = len(self._equity_curve)
        annual_return = self._annualize_return(total_return, trading_days)

        # 最大回撤
        max_drawdown = self._calc_max_drawdown()

        # 夏普比率
        sharpe_ratio = self._calc_sharpe_ratio()

        # 胜率
        win_rate = self._calc_win_rate()

        # 盈亏比
        profit_loss_ratio = self._calc_profit_loss_ratio()

        # 卡尔马比率
        calmar_ratio = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0.0

        return BacktestResult(
            total_return=round(total_return, 6),
            annual_return=round(annual_return, 6),
            max_drawdown=round(max_drawdown, 6),
            sharpe_ratio=round(sharpe_ratio, 4),
            win_rate=round(win_rate, 4),
            profit_loss_ratio=round(profit_loss_ratio, 4),
            calmar_ratio=round(calmar_ratio, 4),
            total_trades=len(self._trade_records),
            trade_records=self._trade_records,
            equity_curve=self._equity_curve,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=round(final_equity, 2),
        )

    def _annualize_return(self, total_return: float, trading_days: int) -> float:
        """
        年化收益率计算

        公式：(1 + R)^(252/N) - 1
        其中 R = 总收益率，N = 交易日数，252 = 年交易日数
        """
        if trading_days <= 0:
            return 0.0
        try:
            annual = (1.0 + total_return) ** (252.0 / trading_days) - 1.0
            return annual
        except (ValueError, OverflowError):
            return 0.0

    def _calc_max_drawdown(self) -> float:
        """
        计算最大回撤

        遍历净值曲线，记录峰值，计算 (当前值 - 峰值) / 峰值 的最小值
        """
        if not self._equity_curve:
            return 0.0

        max_dd = 0.0
        peak = self._equity_curve[0]["equity"]

        for point in self._equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

        return max_dd

    def _calc_sharpe_ratio(self) -> float:
        """
        计算夏普比率

        公式：(R_p - R_f) / sigma_p
        其中 R_p = 组合日均收益率，R_f = 无风险日收益率，sigma_p = 日收益率标准差
        年化夏普 = 日夏普 * sqrt(252)
        """
        if not self._daily_returns or len(self._daily_returns) < 2:
            return 0.0

        n = len(self._daily_returns)
        mean_r = sum(self._daily_returns) / n

        # 无风险日收益率
        rf_daily = self.risk_free_rate / 252.0

        # 标准差
        variance = sum((r - mean_r) ** 2 for r in self._daily_returns) / n
        std_r = math.sqrt(variance)

        if std_r == 0:
            return 0.0

        # 日夏普
        daily_sharpe = (mean_r - rf_daily) / std_r

        # 年化夏普
        annual_sharpe = daily_sharpe * math.sqrt(252)

        return annual_sharpe

    def _calc_win_rate(self) -> float:
        """计算胜率（盈利交易数 / 总交易数）"""
        if not self._trade_records:
            return 0.0
        wins = sum(1 for t in self._trade_records if t.return_pct > 0)
        return wins / len(self._trade_records)

    def _calc_profit_loss_ratio(self) -> float:
        """
        计算盈亏比（平均盈利 / 平均亏损绝对值）

        盈利交易的平均收益率 / 亏损交易的平均亏损率绝对值
        """
        if not self._trade_records:
            return 0.0

        wins = [t.return_pct for t in self._trade_records if t.return_pct > 0]
        losses = [abs(t.return_pct) for t in self._trade_records if t.return_pct < 0]

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        if avg_loss == 0:
            return float("inf") if avg_win > 0 else 0.0

        return avg_win / avg_loss


# ============================================================
#  内置演示策略 — X大神策略（简化版）
# ============================================================

def x_god_strategy(date: str, market_data: Dict) -> List[StrategySignal]:
    """
    X大神策略 — 简化版回测演示策略

    策略逻辑（简化）：
    1. 寻找近5日涨幅超过3%且当日收红的股票买入
    2. 持仓期间若累计跌幅超过8%则卖出止损
    3. 持仓超过15天且收益未达5%则卖出
    4. 持仓收益超过15%则止盈卖出

    注意：这是简化演示策略，实际X大神策略远比此复杂。
    """
    signals = []
    stocks = market_data.get("stocks", {})
    holdings = market_data.get("holdings", {})

    for code, info in stocks.items():
        close = info.get("close", 0)
        pct_change = info.get("pct_change", 0)
        ma5 = info.get("ma5", 0)

        # ---- 买入逻辑 ----
        if code not in holdings:
            # 条件：近5日涨幅>3%，当日收红（涨幅>0），价格在MA5上方
            if (pct_change > 0 and ma5 > 0 and close > ma5):
                # 计算近5日涨幅
                price_5d_ago = info.get("close_5d_ago", 0)
                if price_5d_ago > 0:
                    gain_5d = (close - price_5d_ago) / price_5d_ago
                    if gain_5d > 0.03:
                        signals.append(StrategySignal(
                            date=date,
                            code=code,
                            signal="buy",
                            weight=1.0,
                            reason=f"X大神策略买入：5日涨幅{gain_5d:.2%}，当日涨幅{pct_change:.2%}，站上MA5",
                        ))

        # ---- 卖出逻辑 ----
        elif code in holdings:
            pos = holdings[code]
            entry_price = pos.get("cost_price", 0)
            hold_days = pos.get("hold_days", 0)

            if entry_price > 0:
                pnl = (close - entry_price) / entry_price

                # 止损：跌幅超过8%
                if pnl <= -0.08:
                    signals.append(StrategySignal(
                        date=date,
                        code=code,
                        signal="sell",
                        weight=1.0,
                        reason=f"X大神策略止损：亏损{pnl:.2%}，触发8%止损线",
                    ))
                # 止盈：收益超过15%
                elif pnl >= 0.15:
                    signals.append(StrategySignal(
                        date=date,
                        code=code,
                        signal="sell",
                        weight=1.0,
                        reason=f"X大神策略止盈：盈利{pnl:.2%}，触发15%止盈线",
                    ))
                # 时间止损：持仓超15天且收益未达5%
                elif hold_days >= 15 and pnl < 0.05:
                    signals.append(StrategySignal(
                        date=date,
                        code=code,
                        signal="sell",
                        weight=1.0,
                        reason=f"X大神策略时间止损：持仓{hold_days}天，收益{pnl:.2%}未达标",
                    ))

    return signals


# ============================================================
#  模拟数据生成器
# ============================================================

def generate_mock_market_data(trading_days: int = 120,
                               stock_pool: Optional[List[Dict]] = None) -> List[Dict]:
    """
    生成模拟A股日线数据

    Args:
        trading_days: 交易日天数
        stock_pool: 股票池配置，默认使用5只模拟股票

    Returns:
        List[Dict] 每日市场数据，格式：
        [{"date": "2026-01-02", "stocks": {"600519": {"close": 1800, ...}}, ...}, ...]
    """
    if stock_pool is None:
        stock_pool = [
            {"code": "600519", "name": "贵州茅台", "base_price": 1800.0, "volatility": 0.025, "trend": 0.0003},
            {"code": "000858", "name": "五粮液", "base_price": 160.0, "volatility": 0.030, "trend": 0.0002},
            {"code": "300750", "name": "宁德时代", "base_price": 220.0, "volatility": 0.035, "trend": 0.0004},
            {"code": "601318", "name": "中国平安", "base_price": 50.0, "volatility": 0.020, "trend": 0.0001},
            {"code": "002594", "name": "比亚迪", "base_price": 280.0, "volatility": 0.032, "trend": 0.0005},
        ]

    random.seed(42)  # 固定随机种子，保证可复现

    # 初始化每只股票的价格序列
    price_series: Dict[str, List[float]] = {}
    for stock in stock_pool:
        price_series[stock["code"]] = [stock["base_price"]]

    market_data = []
    base_date = [2026, 1, 2]  # 起始日期

    for day_idx in range(trading_days):
        # 生成日期（跳过周末）
        date = _generate_date(base_date, day_idx)

        day_stocks = {}
        for stock in stock_pool:
            code = stock["code"]
            vol = stock["volatility"]
            trend = stock["trend"]

            # 前一日收盘价
            prev_close = price_series[code][-1]

            # 随机涨跌（几何布朗运动简化）
            daily_return = trend + vol * random.gauss(0, 1)
            new_close = prev_close * (1.0 + daily_return)
            new_close = max(new_close, prev_close * 0.7)  # 限制单日最大跌幅30%

            price_series[code].append(new_close)

            pct_change = (new_close - prev_close) / prev_close if prev_close > 0 else 0.0

            # 计算MA5
            history = price_series[code]
            ma5 = sum(history[-6:-1]) / 5 if len(history) >= 6 else new_close

            # 5天前价格
            close_5d_ago = history[-6] if len(history) >= 6 else history[0]

            day_stocks[code] = {
                "open": round(prev_close, 2),
                "high": round(max(prev_close, new_close) * (1.0 + abs(random.gauss(0, 0.005))), 2),
                "low": round(min(prev_close, new_close) * (1.0 - abs(random.gauss(0, 0.005))), 2),
                "close": round(new_close, 2),
                "pct_change": round(pct_change, 6),
                "volume": random.randint(10000, 100000),
                "ma5": round(ma5, 2),
                "close_5d_ago": round(close_5d_ago, 2),
            }

        market_data.append({
            "date": date,
            "stocks": day_stocks,
        })

    return market_data


def _generate_date(base_date: List[int], day_idx: int) -> str:
    """根据基准日期和偏移量生成交易日期（跳过周末）"""
    y, m, d = base_date[0], base_date[1], base_date[2]
    elapsed = 0
    while elapsed <= day_idx:
        # 简化的日期推进
        d += 1
        # 每月天数（简化）
        days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if d > days_in_month[m - 1]:
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1
        # 计算星期几（Zeller公式简化）
        # 2026-01-02 是周五
        total_days = (y - 2026) * 365 + (m - 1) * 30 + d
        weekday = (total_days + 4) % 7  # 0=周一, 5=周六, 6=周日
        if weekday < 5:  # 周一到周五
            elapsed += 1
    return f"{y:04d}-{m:02d}-{d:02d}"


# ============================================================
#  增强版回测引擎（支持持仓状态传递给策略）
# ============================================================

def run_x_god_backtest() -> BacktestResult:
    """
    运行X大神策略完整回测演示

    使用模拟数据展示完整的回测流程：
    1. 生成120个交易日的模拟行情
    2. 逐日运行X大神策略
    3. 计算完整回测指标
    4. 输出结果
    """
    print("正在生成模拟行情数据...")
    market_data = generate_mock_market_data(trading_days=120)

    # 创建增强策略（带持仓状态）
    def enhanced_strategy(date: str, day_data: Dict) -> List[StrategySignal]:
        """增强版策略：将当前持仓信息传递给策略函数"""
        stocks = day_data.get("stocks", {})
        # 构建持仓信息
        holdings = {}
        for code, pos in engine._positions.items():
            stock_info = stocks.get(code, {})
            current_price = stock_info.get("close", pos["cost_price"])
            hold_days = engine._count_trading_days(pos["entry_date"], date)
            holdings[code] = {
                "cost_price": pos["cost_price"],
                "current_price": current_price,
                "hold_days": hold_days,
            }
        # 将持仓信息注入market_data
        day_data["holdings"] = holdings
        return x_god_strategy(date, day_data)

    print("正在执行回测...")
    engine = BacktestEngine(
        strategy=enhanced_strategy,
        market_data=market_data,
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        slippage=0.002,
        max_position_count=5,
        single_position_limit=0.20,
    )

    result = engine.run()
    return result


# ============================================================
#  __main__ 入口 — X大神策略回测演示
# ============================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("  玄甲AGI 回测框架 — X大神策略回测演示")
    print("=" * 60)

    # 运行回测
    result = run_x_god_backtest()

    # 输出回测结果摘要
    print("\n" + "-" * 40)
    print("  回测结果摘要")
    print("-" * 40)
    summary = result.summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # 输出交易记录
    print("\n" + "-" * 40)
    print(f"  交易记录（共 {result.total_trades} 笔）")
    print("-" * 40)
    for i, trade in enumerate(result.trade_records, 1):
        print(f"  [{i}] {trade.code}: {trade.entry_date} → {trade.exit_date} | "
              f"买入 {trade.entry_price:.2f} → 卖出 {trade.exit_price:.2f} | "
              f"收益 {trade.return_pct:.2%} | 持仓 {trade.hold_days}天 | {trade.reason}")

    # 输出净值曲线（首尾和关键节点）
    print("\n" + "-" * 40)
    print("  净值曲线（关键节点）")
    print("-" * 40)
    curve = result.equity_curve
    if curve:
        # 显示每20个交易日一个节点
        step = max(1, len(curve) // 6)
        for i in range(0, len(curve), step):
            point = curve[i]
            print(f"  {point['date']}: 净值 {point['equity']:>12,.2f} | "
                  f"日收益 {point['daily_return']:>8.2%} | "
                  f"现金 {point['cash']:>12,.2f} | "
                  f"持仓 {point['position_count']}只")
        # 确保显示最后一个点
        if len(curve) > 1 and (len(curve) - 1) % step != 0:
            point = curve[-1]
            print(f"  {point['date']}: 净值 {point['equity']:>12,.2f} | "
                  f"日收益 {point['daily_return']:>8.2%} | "
                  f"现金 {point['cash']:>12,.2f} | "
                  f"持仓 {point['position_count']}只")

    # 输出完整结果JSON（前50行）
    print("\n" + "-" * 40)
    print("  完整回测结果（JSON格式）")
    print("-" * 40)
    result_dict = {
        "total_return": result.total_return,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "win_rate": result.win_rate,
        "profit_loss_ratio": result.profit_loss_ratio,
        "calmar_ratio": result.calmar_ratio,
        "total_trades": result.total_trades,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "final_capital": result.final_capital,
    }
    print(json.dumps(result_dict, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("  回测演示完毕")
    print("=" * 60)
