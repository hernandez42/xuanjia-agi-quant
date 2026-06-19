#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲精简版多因子模型 — 12维最强因子 Alpha 引擎
═══════════════════════════════════════════════════════════════════════════════
基于 N=29 V5 核心日级别因子中 IC 最强的 12 个因子构建。

设计原则：
- 只保留日级别因子（排除 weekly_ 因子和 NaN 因子）
- 保留 V6.2 混合权重逻辑：核心因子加权 + 增强方向一致性奖励
- 保留截尾 Z-Score 标准化（±3σ）
- 保留 news_sentiment 自动接入
- 权重总和 = 1.0（12 × 0.08 + news_sentiment 0.04 = 1.0）

12维最强因子（按 IC 从高到低）：
1. macd_dif          — MACD快线，趋势动量核心
2. macd_dea          — MACD慢线，趋势确认
3. bollinger_position — 布林带位置，超买超卖
4. trend_strength    — 趋势强度，线性回归斜率
5. ma20_deviation    — MA20偏离度，中期趋势
6. ma10_deviation    — MA10偏离度，短期趋势
7. breakout_signal   — 突破/跌破信号
8. ma5_deviation     — MA5偏离度，极短期趋势
9. kdj_d             — KDJ-D值，动量反转
10. rsi14            — RSI14，相对强弱
11. main_net_inflow_ratio — 主力净流入比率，资金流
12. order_imbalance  — 订单失衡，微观结构

+ news_sentiment（自动接入，权重0.04）
═══════════════════════════════════════════════════════════════════════════════
"""

import math
import random
import statistics
from typing import Dict, List, Optional, Tuple


# ==============================================================================
# 辅助函数
# ==============================================================================

def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法，避免除零错误"""
    if denominator == 0 or math.isnan(denominator):
        return default
    return numerator / denominator


def _rolling_mean(values: List[float], window: int) -> float:
    """计算滚动均值"""
    if len(values) < window:
        return 0.0
    return sum(values[-window:]) / window


def _rolling_std(values: List[float], window: int) -> float:
    """计算滚动标准差"""
    if len(values) < window:
        return 0.0
    subset = values[-window:]
    mean = sum(subset) / len(subset)
    variance = sum((x - mean) ** 2 for x in subset) / len(subset)
    return math.sqrt(variance)


def _ema(values: List[float], period: int) -> float:
    """计算指数移动平均线（EMA）"""
    if len(values) < period:
        return 0.0
    multiplier = 2.0 / (period + 1)
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


# ==============================================================================
# FactorLibraryLite — 精简版因子库（仅12维）
# ==============================================================================

class FactorLibraryLite:
    """
    玄甲精简版因子库：仅保留 IC 最强的 12 个日级别因子。
    """

    def __init__(self):
        pass

    # --------------------------------------------------------------------------
    # 12维最强因子
    # --------------------------------------------------------------------------

    def macd_dif(self, ohlcv_data: Dict) -> float:
        """MACD DIF线（快线）= EMA12 - EMA26"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 26:
            return 0.0
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        return ema12 - ema26

    def macd_dea(self, ohlcv_data: Dict) -> float:
        """MACD DEA线（慢线）= DIF的EMA9"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 35:
            return 0.0
        dif_series = []
        ema12 = sum(closes[:12]) / 12.0
        ema26 = sum(closes[:26]) / 26.0
        for i, price in enumerate(closes):
            if i < 12:
                continue
            if i == 12:
                ema12 = sum(closes[:12]) / 12.0
            else:
                ema12 = (price - ema12) * (2.0 / 13.0) + ema12
            if i < 26:
                dif_series.append(0.0)
                continue
            if i == 26:
                ema26 = sum(closes[:26]) / 26.0
            else:
                ema26 = (price - ema26) * (2.0 / 27.0) + ema26
            dif_series.append(ema12 - ema26)
        if len(dif_series) < 9:
            return 0.0
        dea = _ema(dif_series, 9)
        return dea

    def bollinger_position(self, ohlcv_data: Dict) -> float:
        """布林带位置 = (收盘价 - MA20) / (2 * 20日标准差)"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        ma20 = _rolling_mean(closes, 20)
        std20 = _rolling_std(closes, 20)
        if std20 == 0:
            return 0.0
        return (closes[-1] - ma20) / (2.0 * std20)

    def trend_strength(self, ohlcv_data: Dict) -> float:
        """趋势强度：20日线性回归斜率标准化"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        recent = closes[-20:]
        n = len(recent)
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent) / n
        numerator = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return 0.0
        slope = numerator / denominator
        return _safe_divide(slope, y_mean, 0.0) * 100.0

    def ma20_deviation(self, ohlcv_data: Dict) -> float:
        """MA20均线偏离度 = (收盘价 - MA20) / MA20 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        ma20 = _rolling_mean(closes, 20)
        return _safe_divide(closes[-1] - ma20, ma20, 0.0) * 100

    def ma10_deviation(self, ohlcv_data: Dict) -> float:
        """MA10均线偏离度 = (收盘价 - MA10) / MA10 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 10:
            return 0.0
        ma10 = _rolling_mean(closes, 10)
        return _safe_divide(closes[-1] - ma10, ma10, 0.0) * 100

    def breakout_signal(self, ohlcv_data: Dict) -> float:
        """突破/跌破关键位信号：比较当日收盘价与20日最高价/最低价"""
        closes = ohlcv_data.get("close", [])
        highs = ohlcv_data.get("high", [])
        lows = ohlcv_data.get("low", [])
        if len(closes) < 21:
            return 0.0
        high_20 = max(highs[-21:-1])
        low_20 = min(lows[-21:-1]) if len(lows) >= 21 else min(closes[-21:-1])
        current = closes[-1]
        range_val = high_20 - low_20
        if range_val == 0:
            return 0.0
        if current > high_20:
            return (current - high_20) / range_val * 100.0
        elif current < low_20:
            return (current - low_20) / range_val * 100.0
        else:
            return 0.0

    def ma5_deviation(self, ohlcv_data: Dict) -> float:
        """MA5均线偏离度 = (收盘价 - MA5) / MA5 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 5:
            return 0.0
        ma5 = _rolling_mean(closes, 5)
        return _safe_divide(closes[-1] - ma5, ma5, 0.0) * 100

    def kdj_d(self, ohlcv_data: Dict) -> float:
        """KDJ指标 — D值"""
        closes = ohlcv_data.get("close", [])
        highs = ohlcv_data.get("high", [])
        lows = ohlcv_data.get("low", [])
        n = 9
        if len(closes) < n:
            return 50.0
        k_val = 50.0
        d_val = 50.0
        for i in range(n):
            h = max(highs[-(n - i):])
            l = min(lows[-(n - i):])
            if h == l:
                rsv_i = 50.0
            else:
                rsv_i = (closes[-(n - i)] - l) / (h - l) * 100.0
            k_val = 2.0 / 3.0 * k_val + 1.0 / 3.0 * rsv_i
            d_val = 2.0 / 3.0 * d_val + 1.0 / 3.0 * k_val
        return d_val

    def rsi14(self, ohlcv_data: Dict) -> float:
        """RSI(14) 相对强弱指标"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 15:
            return 50.0
        gains = []
        losses = []
        for i in range(1, min(15, len(closes))):
            change = closes[-(i + 1)] - closes[-i]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))
        avg_gain = sum(gains) / 14.0
        avg_loss = sum(losses) / 14.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def main_net_inflow_ratio(self, ohlcv_data: Dict) -> float:
        """主力净流入比率"""
        return ohlcv_data.get("main_net_inflow", 0.0)

    def order_imbalance(self, ohlcv_data: Dict) -> float:
        """订单失衡因子：主动买入量 vs 主动卖出量的失衡程度"""
        buy_volume = ohlcv_data.get("active_buy_volume", 0)
        sell_volume = ohlcv_data.get("active_sell_volume", 0)
        total = buy_volume + sell_volume
        if total == 0:
            return 0.0
        imbalance = (buy_volume - sell_volume) / total
        return max(-1.0, min(1.0, imbalance * 3))

    # --------------------------------------------------------------------------
    # news_sentiment 自动接入
    # --------------------------------------------------------------------------

    def news_sentiment(self, ohlcv_data: Dict) -> float:
        """
        新闻情感因子
        V6.3 增强：自动从 NewsSentimentEngine 获取实时消息面情绪
        """
        sentiment = ohlcv_data.get("news_sentiment_score", None)
        if sentiment is not None:
            return max(-1.0, min(1.0, float(sentiment)))

        try:
            import os, sys
            _dir = os.path.dirname(os.path.abspath(__file__))
            if _dir not in sys.path:
                sys.path.insert(0, _dir)
            from news_sentiment_engine import NewsSentimentEngine
            engine = NewsSentimentEngine()
            news = engine.fetch_news()
            if news:
                engine.analyze_news(news)
                macro = engine.get_macro_sentiment()
                return max(-1.0, min(1.0, macro))
        except Exception:
            pass

        return 0.0

    # --------------------------------------------------------------------------
    # 因子列表管理
    # --------------------------------------------------------------------------

    def get_all_factor_names(self) -> List[str]:
        """获取12维最强因子名称列表"""
        return [
            "macd_dif", "macd_dea", "bollinger_position", "trend_strength",
            "ma20_deviation", "ma10_deviation", "breakout_signal", "ma5_deviation",
            "kdj_d", "rsi14", "main_net_inflow_ratio", "order_imbalance",
            "news_sentiment",
        ]

    def compute_factor(self, factor_name: str, ohlcv_data: Dict) -> float:
        """计算单个因子的值"""
        method = getattr(self, factor_name, None)
        if method is None:
            return 0.0
        try:
            return method(ohlcv_data)
        except Exception:
            return 0.0

    def compute_all_factors(self, ohlcv_data: Dict) -> Dict[str, float]:
        """计算所有因子，返回因子名到因子值的字典"""
        factors = {}
        for name in self.get_all_factor_names():
            factors[name] = self.compute_factor(name, ohlcv_data)
        return factors


# ==============================================================================
# FactorScorerLite — 精简版因子评分器
# ==============================================================================

class FactorScorerLite:
    """
    玄甲精简版因子评分器：12维最强因子 + V6.2 混合评分逻辑。

    权重分配（总和=1.0）：
    - 12维核心因子各 0.08 = 0.96
    - news_sentiment = 0.04
    """

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "macd_dif": 0.08,
        "macd_dea": 0.08,
        "bollinger_position": 0.08,
        "trend_strength": 0.08,
        "ma20_deviation": 0.08,
        "ma10_deviation": 0.08,
        "breakout_signal": 0.08,
        "ma5_deviation": 0.08,
        "kdj_d": 0.08,
        "rsi14": 0.08,
        "main_net_inflow_ratio": 0.08,
        "order_imbalance": 0.08,
        "news_sentiment": 0.04,
    }

    # 核心因子集合（12维日级别因子）
    CORE_FACTORS = {
        "macd_dif", "macd_dea", "bollinger_position", "trend_strength",
        "ma20_deviation", "ma10_deviation", "breakout_signal", "ma5_deviation",
        "kdj_d", "rsi14", "main_net_inflow_ratio", "order_imbalance",
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.factor_lib = FactorLibraryLite()
        self.weights = weights if weights is not None else dict(self.DEFAULT_WEIGHTS)

    def _z_score(self, value: float, mean: float, std: float) -> float:
        """计算Z-Score标准化值"""
        if std == 0:
            return 0.0
        return (value - mean) / std

    def standardize_factors(
        self,
        all_stocks_factors: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """
        V6.2 截尾Z-Score标准化：将极端值截断到±3σ
        """
        if not all_stocks_factors:
            return {}

        factor_names = list(next(iter(all_stocks_factors.values())).keys())

        factor_stats = {}
        for fname in factor_names:
            values = [all_stocks_factors[code][fname] for code in all_stocks_factors]
            mean_val = sum(values) / len(values)
            if len(values) > 1:
                std_val = math.sqrt(sum((v - mean_val) ** 2 for v in values) / len(values))
            else:
                std_val = 1.0
            factor_stats[fname] = (mean_val, max(std_val, 0.001))

        standardized = {}
        for code, factors in all_stocks_factors.items():
            standardized[code] = {}
            for fname in factor_names:
                mean_val, std_val = factor_stats[fname]
                z = (factors[fname] - mean_val) / std_val
                z = max(-3.0, min(3.0, z))  # 截尾到±3σ
                standardized[code][fname] = z

        return standardized

    def compute_score(
        self,
        standardized_factors: Dict[str, float],
        weights: Optional[Dict[str, float]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        V6.2 混合评分：核心因子加权 + 方向一致性奖励
        """
        w = weights if weights is not None else self.weights
        total_score = 0.0
        contributions = {}

        core_score = 0.0
        enhance_score = 0.0

        for factor_name, z_value in standardized_factors.items():
            weight = w.get(factor_name, 0.0)
            contribution = z_value * weight
            contributions[factor_name] = contribution
            total_score += contribution
            if factor_name in self.CORE_FACTORS:
                core_score += contribution
            else:
                enhance_score += contribution

        # 方向一致性奖励：所有因子方向一致时给予小幅加成
        all_factors = standardized_factors
        if all_factors:
            pos_count = sum(1 for v in all_factors.values() if v > 0)
            neg_count = sum(1 for v in all_factors.values() if v < 0)
            total_f = len(all_factors)
            if total_f > 0:
                direction_agreement = abs(pos_count - neg_count) / total_f
                if direction_agreement > 0.6:
                    bonus = 0.05 * (direction_agreement - 0.6) / 0.4
                    total_score += bonus * (1 if total_score > 0 else -1 if total_score < 0 else 0)

        # V6.3 修复：归一化评分到 [-1, +1]
        # 理论最大绝对值 = sum(weights) * 3 + 0.05 ≈ 3.05
        # 使用 tanh 压缩确保输出严格在 (-1, +1)
        if total_score != 0.0:
            total_score = math.tanh(total_score / 1.5)

        return total_score, contributions

    def score_single_stock(
        self,
        stock_code: str,
        ohlcv_data: Dict,
        all_stocks_factors: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict:
        """对单只股票进行完整评分流程"""
        raw_factors = self.factor_lib.compute_all_factors(ohlcv_data)

        if all_stocks_factors is not None:
            std_factors = self.standardize_factors(all_stocks_factors)
            stock_std = std_factors.get(stock_code, raw_factors)
        else:
            stock_std = raw_factors

        score, contributions = self.compute_score(stock_std)

        return {
            "stock_code": stock_code,
            "total_score": round(score, 4),
            "raw_factors": raw_factors,
            "standardized_factors": stock_std,
            "contributions": {k: round(v, 6) for k, v in contributions.items()},
        }


# ==============================================================================
# MultiFactorSelectorLite — 精简版多因子选股器
# ==============================================================================

class MultiFactorSelectorLite:
    """
    玄甲精简版多因子选股器：批量处理多只股票并输出 TOP N 推荐。
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.scorer = FactorScorerLite(weights=weights)
        self.factor_lib = FactorLibraryLite()

    def select(
        self,
        stocks_data: Dict[str, Dict],
        top_n: int = 10
    ) -> List[Dict]:
        """执行多因子选股"""
        if not stocks_data:
            return []

        all_raw_factors = {}
        for code, data in stocks_data.items():
            all_raw_factors[code] = self.factor_lib.compute_all_factors(data)

        standardized = self.scorer.standardize_factors(all_raw_factors)

        results = []
        for code in stocks_data:
            score, contributions = self.scorer.compute_score(standardized[code])
            results.append({
                "stock_code": code,
                "total_score": round(score, 4),
                "contributions": {k: round(v, 6) for k, v in contributions.items()},
                "raw_factors": all_raw_factors[code],
            })

        results.sort(key=lambda x: x["total_score"], reverse=True)
        return results[:top_n]

    def print_ranking(self, results: List[Dict], top_n: int = 5) -> None:
        """打印选股排名结果"""
        print("=" * 70)
        print("  玄甲精简版 — 12维最强因子选股模型 — 排名结果")
        print("=" * 70)
        print(f"{'排名':<6}{'股票代码':<12}{'综合评分':<12}{'评级'}")
        print("-" * 70)

        for i, item in enumerate(results[:top_n]):
            rank = i + 1
            score = item["total_score"]
            if score > 0.5:
                grade = "强烈推荐"
            elif score > 0.2:
                grade = "推荐"
            elif score > 0:
                grade = "中性偏多"
            elif score > -0.2:
                grade = "中性偏空"
            else:
                grade = "回避"
            print(f"{rank:<6}{item['stock_code']:<12}{score:<12.4f}{grade}")

        print("-" * 70)

        if results:
            best = results[0]
            print(f"\n  TOP 1 [{best['stock_code']}] 因子贡献度分析：")
            print(f"  {'因子名称':<28}{'贡献值':<12}{'占比'}")
            print("  " + "-" * 55)

            sorted_contrib = sorted(
                best["contributions"].items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )
            total_abs = sum(abs(v) for v in best["contributions"].values())
            for fname, contrib in sorted_contrib[:12]:
                pct = abs(contrib) / total_abs * 100 if total_abs > 0 else 0
                print(f"  {fname:<28}{contrib:<12.6f}{pct:.1f}%")

        print("=" * 70)


# ==============================================================================
# 模拟数据生成器
# ==============================================================================

def generate_mock_ohlcv(
    days: int = 60,
    base_price: float = 20.0,
    volatility: float = 0.03,
    trend: float = 0.001,
    seed: int = None
) -> Dict:
    """生成模拟OHLCV数据"""
    if seed is not None:
        random.seed(seed)

    closes = []
    opens = []
    highs = []
    lows = []
    volumes = []
    amounts = []

    price = base_price
    for i in range(days):
        daily_return = trend + random.gauss(0, volatility)
        open_price = price * (1 + random.gauss(0, volatility * 0.3))
        close_price = price * (1 + daily_return)
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.5)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.5)))
        volume = random.uniform(500000, 5000000) * (1 + abs(daily_return) * 10)
        amount = volume * (open_price + close_price) / 2

        opens.append(round(open_price, 2))
        closes.append(round(close_price, 2))
        highs.append(round(high_price, 2))
        lows.append(round(low_price, 2))
        volumes.append(int(volume))
        amounts.append(round(amount, 2))

        price = close_price

    main_net_inflow = round(random.uniform(-5, 5), 2)

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "amount": amounts,
        "main_net_inflow": main_net_inflow,
        "active_buy_volume": volumes[-1] * 0.55,
        "active_sell_volume": volumes[-1] * 0.45,
        "news_sentiment_score": round(random.uniform(-0.5, 0.8), 2),
    }


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    print("玄甲精简版 — 12维最强因子选股模型")
    print("=" * 70)

    stock_names = {
        "SH600000": {"base": 12.0, "vol": 0.02, "trend": 0.002, "seed": 42},
        "SZ000001": {"base": 15.0, "vol": 0.03, "trend": -0.001, "seed": 123},
        "SH600519": {"base": 1800.0, "vol": 0.015, "trend": 0.001, "seed": 456},
        "SZ300750": {"base": 200.0, "vol": 0.04, "trend": 0.003, "seed": 789},
        "SH601318": {"base": 50.0, "vol": 0.025, "trend": 0.0005, "seed": 101},
    }

    stocks_data = {}
    for code, params in stock_names.items():
        print(f"  生成 {code} 模拟数据...")
        stocks_data[code] = generate_mock_ohlcv(
            days=60,
            base_price=params["base"],
            volatility=params["vol"],
            trend=params["trend"],
            seed=params["seed"],
        )

    print(f"\n  共生成 {len(stocks_data)} 只股票的模拟数据\n")

    selector = MultiFactorSelectorLite()
    results = selector.select(stocks_data, top_n=5)
    selector.print_ranking(results, top_n=5)

    print("\n演示完成。")
