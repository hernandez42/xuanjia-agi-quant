#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daogi × 玄甲 18维融合模型
═══════════════════════════════════════════════════════════════════════════════
将 daogi 6维因子与玄甲精简版 12维因子合并为 18维统一评分体系。

权重分配（总和 = 1.0）：
- daogi 6维：各 0.08 = 0.48
  1. vol_ratio_5d        — 5日成交量比率
  2. momentum_5d         — 5日价格动量
  3. vcp_score           — 波动率收缩模式评分
  4. range_5d            — 5日价格区间
  5. paper_a_factor_1    — Paper A因子1（假设：换手率异动）
  6. paper_a_factor_2    — Paper A因子2（假设：振幅偏离）

- 玄甲12维：各 0.04 = 0.48
  1. macd_dif            — MACD快线
  2. macd_dea            — MACD慢线
  3. bollinger_position  — 布林带位置
  4. trend_strength      — 趋势强度
  5. ma20_deviation      — MA20偏离度
  6. ma10_deviation      — MA10偏离度
  7. breakout_signal     — 突破信号
  8. ma5_deviation       — MA5偏离度
  9. kdj_d               — KDJ-D值
  10. rsi14              — RSI14
  11. main_net_inflow_ratio — 主力净流入比率
  12. order_imbalance    — 订单失衡

- news_sentiment：0.04

融合逻辑：
1. 分别计算 daogi 6维和玄甲12维的原始因子值
2. 对18维因子进行截尾Z-Score标准化（±3σ）
3. 按上述权重加权合成综合评分
4. 保留方向一致性奖励机制（同向>60%时+5% bonus）
5. 输出排序后的TOP N推荐
═══════════════════════════════════════════════════════════════════════════════
"""

import math
import random
import sys
import os
from typing import Dict, List, Optional, Tuple

# 将项目根目录加入路径，以便导入玄甲精简版模型
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apex_agi"))
from multi_factor_model_lite import FactorLibraryLite, _safe_divide, _rolling_mean, _rolling_std, _ema


# ==============================================================================
# DaogiFactorLibrary — daogi 6维因子库
# ==============================================================================

class DaogiFactorLibrary:
    """
    daogi 6维因子库：基于量价行为的短周期因子。
    """

    def vol_ratio_5d(self, ohlcv_data: Dict) -> float:
        """5日成交量比率 = 当日成交量 / 5日均成交量"""
        volumes = ohlcv_data.get("volume", [])
        if len(volumes) < 6:
            return 1.0
        avg_vol = _rolling_mean(volumes[:-1], 5)
        if avg_vol == 0:
            return 1.0
        return volumes[-1] / avg_vol

    def momentum_5d(self, ohlcv_data: Dict) -> float:
        """5日价格动量 = (收盘价 - 5日前收盘价) / 5日前收盘价 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 6:
            return 0.0
        return _safe_divide(closes[-1] - closes[-6], closes[-6], 0.0) * 100.0

    def vcp_score(self, ohlcv_data: Dict) -> float:
        """
        波动率收缩模式(VCP)评分
        近5日波动率 < 近20日波动率 = 收缩（正信号）
        返回收缩程度标准化值
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 21:
            return 0.0
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                returns.append(_safe_divide(closes[i] - closes[i - 1], closes[i - 1], 0.0))
        if len(returns) < 20:
            return 0.0
        vol_5 = _rolling_std(returns, 5)
        vol_20 = _rolling_std(returns, 20)
        if vol_20 == 0:
            return 0.0
        # 收缩程度：vol_5/vol_20 越小越好
        ratio = vol_5 / vol_20
        return max(-1.0, min(1.0, (1.0 - ratio) * 2.0))

    def range_5d(self, ohlcv_data: Dict) -> float:
        """
        5日价格区间因子 = (5日最高 - 5日最低) / 5日最低
        区间收窄 = 蓄势（正信号），区间扩大 = 分歧（负信号）
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 5:
            return 0.0
        h5 = max(closes[-5:])
        l5 = min(closes[-5:])
        if l5 == 0:
            return 0.0
        range_pct = (h5 - l5) / l5 * 100.0
        # 归一化到 [-1, 1]：区间<3%视为强势蓄势
        if range_pct < 3.0:
            return 1.0
        elif range_pct < 5.0:
            return 0.5
        elif range_pct > 10.0:
            return -1.0
        elif range_pct > 7.0:
            return -0.5
        return 0.0

    def paper_a_factor_1(self, ohlcv_data: Dict) -> float:
        """
        Paper A 因子1：换手率异动
        当日换手率相对20日均值的偏离度
        """
        volumes = ohlcv_data.get("volume", [])
        closes = ohlcv_data.get("close", [])
        current_turnover = ohlcv_data.get("turnover_rate", 0.0)
        if len(volumes) < 20 or len(closes) < 20:
            return 0.0
        avg_volume = _rolling_mean(volumes[:-1], 20)
        if avg_volume == 0:
            return 0.0
        vol_ratio = volumes[-1] / avg_volume
        return (vol_ratio - 1.0) * 100.0

    def paper_a_factor_2(self, ohlcv_data: Dict) -> float:
        """
        Paper A 因子2：振幅偏离
        当日振幅相对5日平均振幅的偏离
        """
        highs = ohlcv_data.get("high", [])
        lows = ohlcv_data.get("low", [])
        closes = ohlcv_data.get("close", [])
        if len(highs) < 6 or len(lows) < 6 or len(closes) < 6:
            return 0.0
        # 计算每日振幅
        amplitudes = []
        for i in range(-5, 0):
            if closes[i] != 0:
                amp = (highs[i] - lows[i]) / closes[i] * 100.0
                amplitudes.append(amp)
        if not amplitudes:
            return 0.0
        avg_amp = sum(amplitudes[:-1]) / len(amplitudes[:-1]) if len(amplitudes) > 1 else amplitudes[0]
        today_amp = amplitudes[-1]
        if avg_amp == 0:
            return 0.0
        return _safe_divide(today_amp - avg_amp, avg_amp, 0.0) * 100.0

    def get_all_factor_names(self) -> List[str]:
        return [
            "vol_ratio_5d", "momentum_5d", "vcp_score", "range_5d",
            "paper_a_factor_1", "paper_a_factor_2",
        ]

    def compute_factor(self, factor_name: str, ohlcv_data: Dict) -> float:
        method = getattr(self, factor_name, None)
        if method is None:
            return 0.0
        try:
            return method(ohlcv_data)
        except Exception:
            return 0.0

    def compute_all_factors(self, ohlcv_data: Dict) -> Dict[str, float]:
        factors = {}
        for name in self.get_all_factor_names():
            factors[name] = self.compute_factor(name, ohlcv_data)
        return factors


# ==============================================================================
# UnifiedFactorLibrary — 18维统一因子库
# ==============================================================================

class UnifiedFactorLibrary:
    """
    18维统一因子库：daogi 6维 + 玄甲12维 + news_sentiment
    """

    def __init__(self):
        self.daogi_lib = DaogiFactorLibrary()
        self.xuanjia_lib = FactorLibraryLite()

    def compute_all_factors(self, ohlcv_data: Dict) -> Dict[str, float]:
        """计算全部18维因子"""
        daogi_factors = self.daogi_lib.compute_all_factors(ohlcv_data)
        xuanjia_factors = self.xuanjia_lib.compute_all_factors(ohlcv_data)
        # 合并（玄甲已包含 news_sentiment）
        return {**daogi_factors, **xuanjia_factors}

    def get_all_factor_names(self) -> List[str]:
        return (
            self.daogi_lib.get_all_factor_names()
            + self.xuanjia_lib.get_all_factor_names()
        )


# ==============================================================================
# UnifiedFactorScorer — 18维统一评分器
# ==============================================================================

class UnifiedFactorScorer:
    """
    18维统一评分器

    权重分配（总和 = 1.0）：
    - daogi 6维：各 0.08 = 0.48
    - 玄甲12维：各 0.04 = 0.48
    - news_sentiment：0.04
    """

    DEFAULT_WEIGHTS: Dict[str, float] = {
        # daogi 6维（各0.08）
        "vol_ratio_5d": 0.08,
        "momentum_5d": 0.08,
        "vcp_score": 0.08,
        "range_5d": 0.08,
        "paper_a_factor_1": 0.08,
        "paper_a_factor_2": 0.08,
        # 玄甲12维（各0.04）
        "macd_dif": 0.04,
        "macd_dea": 0.04,
        "bollinger_position": 0.04,
        "trend_strength": 0.04,
        "ma20_deviation": 0.04,
        "ma10_deviation": 0.04,
        "breakout_signal": 0.04,
        "ma5_deviation": 0.04,
        "kdj_d": 0.04,
        "rsi14": 0.04,
        "main_net_inflow_ratio": 0.04,
        "order_imbalance": 0.04,
        # news_sentiment
        "news_sentiment": 0.04,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.factor_lib = UnifiedFactorLibrary()
        self.weights = weights if weights is not None else dict(self.DEFAULT_WEIGHTS)

    def standardize_factors(
        self,
        all_stocks_factors: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """V6.2 截尾Z-Score标准化（±3σ）"""
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
                z = max(-3.0, min(3.0, z))
                standardized[code][fname] = z

        return standardized

    def compute_score(
        self,
        standardized_factors: Dict[str, float],
        weights: Optional[Dict[str, float]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """V6.2 混合评分 + 方向一致性奖励"""
        w = weights if weights is not None else self.weights
        total_score = 0.0
        contributions = {}

        for factor_name, z_value in standardized_factors.items():
            weight = w.get(factor_name, 0.0)
            contribution = z_value * weight
            contributions[factor_name] = contribution
            total_score += contribution

        # 方向一致性奖励
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
# UnifiedMultiFactorSelector — 18维统一选股器
# ==============================================================================

class UnifiedMultiFactorSelector:
    """
    Daogi × 玄甲 18维融合选股器
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.scorer = UnifiedFactorScorer(weights=weights)
        self.factor_lib = UnifiedFactorLibrary()

    def select(
        self,
        stocks_data: Dict[str, Dict],
        top_n: int = 10
    ) -> List[Dict]:
        """执行18维融合选股"""
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
        print("=" * 78)
        print("  Daogi × 玄甲 — 18维融合选股模型 — 排名结果")
        print("=" * 78)
        print(f"{'排名':<6}{'股票代码':<12}{'综合评分':<12}{'评级'}")
        print("-" * 78)

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

        print("-" * 78)

        if results:
            best = results[0]
            print(f"\n  TOP 1 [{best['stock_code']}] 18维因子贡献度分析：")
            print(f"  {'因子名称':<28}{'贡献值':<12}{'占比'}")
            print("  " + "-" * 55)

            sorted_contrib = sorted(
                best["contributions"].items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )
            total_abs = sum(abs(v) for v in best["contributions"].values())
            for fname, contrib in sorted_contrib[:18]:
                pct = abs(contrib) / total_abs * 100 if total_abs > 0 else 0
                print(f"  {fname:<28}{contrib:<12.6f}{pct:.1f}%")

        print("=" * 78)


# ==============================================================================
# 权重表输出工具
# ==============================================================================

def print_weight_table() -> None:
    """打印18维因子权重表"""
    weights = UnifiedFactorScorer.DEFAULT_WEIGHTS

    print("\n" + "=" * 78)
    print("  Daogi × 玄甲 18维融合模型 — 因子权重表")
    print("=" * 78)

    print("\n  【daogi 6维 — 权重各0.08，小计0.48】")
    print("  " + "-" * 60)
    daogi_factors = [
        ("vol_ratio_5d", "5日成交量比率"),
        ("momentum_5d", "5日价格动量"),
        ("vcp_score", "波动率收缩模式评分"),
        ("range_5d", "5日价格区间"),
        ("paper_a_factor_1", "Paper A 因子1（换手率异动）"),
        ("paper_a_factor_2", "Paper A 因子2（振幅偏离）"),
    ]
    for fn, desc in daogi_factors:
        print(f"  {fn:<24} {desc:<30} 权重: {weights[fn]:.2f}")

    print("\n  【玄甲12维 — 权重各0.04，小计0.48】")
    print("  " + "-" * 60)
    xuanjia_factors = [
        ("macd_dif", "MACD快线"),
        ("macd_dea", "MACD慢线"),
        ("bollinger_position", "布林带位置"),
        ("trend_strength", "趋势强度"),
        ("ma20_deviation", "MA20偏离度"),
        ("ma10_deviation", "MA10偏离度"),
        ("breakout_signal", "突破/跌破信号"),
        ("ma5_deviation", "MA5偏离度"),
        ("kdj_d", "KDJ-D值"),
        ("rsi14", "RSI14"),
        ("main_net_inflow_ratio", "主力净流入比率"),
        ("order_imbalance", "订单失衡"),
    ]
    for fn, desc in xuanjia_factors:
        print(f"  {fn:<24} {desc:<30} 权重: {weights[fn]:.2f}")

    print("\n  【情绪因子】")
    print("  " + "-" * 60)
    print(f"  {'news_sentiment':<24} {'新闻情感因子':<30} 权重: {weights['news_sentiment']:.2f}")

    print("\n  【权重校验】")
    print("  " + "-" * 60)
    daogi_sum = sum(weights[k] for k, _ in daogi_factors)
    xuanjia_sum = sum(weights[k] for k, _ in xuanjia_factors)
    total_sum = daogi_sum + xuanjia_sum + weights["news_sentiment"]
    print(f"  daogi 6维小计:  {daogi_sum:.2f}")
    print(f"  玄甲12维小计:  {xuanjia_sum:.2f}")
    print(f"  news_sentiment: {weights['news_sentiment']:.2f}")
    print(f"  总权重:         {total_sum:.2f} {'✓ 校验通过' if abs(total_sum - 1.0) < 0.001 else '✗ 校验失败'}")
    print("=" * 78)


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
        "turnover_rate": round(random.uniform(0.5, 8), 2),
        "news_sentiment_score": round(random.uniform(-0.5, 0.8), 2),
    }


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    print("Daogi × 玄甲 — 18维融合选股模型")
    print("=" * 78)

    # 打印权重表
    print_weight_table()

    # 模拟选股演示
    print("\n" + "=" * 78)
    print("  模拟选股演示")
    print("=" * 78)

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

    selector = UnifiedMultiFactorSelector()
    results = selector.select(stocks_data, top_n=5)
    selector.print_ranking(results, top_n=5)

    print("\n演示完成。")
