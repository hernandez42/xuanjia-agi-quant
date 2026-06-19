#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子选股模型 — A股多因子量化选股系统

本模块实现了一个完整的A股多因子选股模型，包含：
- FactorLibrary: 因子库，提供量价、基本面、资金、情绪、技术形态、
  背离与预警、筹码分布、事件驱动、宏观、机构暗盘追踪、舆情NLP、
  分域适配、微观结构、杠杆资金、龙虎榜聪明钱、集合竞价与尾盘、
  专利与创新、微观结构深度、MCTS公式、波动率择时、因子质量诊断
  二十二大类因子（共88个因子）
- FactorScorer: 因子评分器，负责因子标准化、加权合成与综合评分
- MultiFactorSelector: 多因子选股器，批量处理多只股票并输出TOP N推荐

仅使用Python标准库，不依赖任何第三方库。
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
    ema_val = sum(values[:period]) / period  # 初始SMA
    for price in values[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


# ==============================================================================
# FactorLibrary — 因子库
# ==============================================================================

class FactorLibrary:
    """
    因子库：提供A股多因子选股所需的各类因子计算方法。

    因子分类：
    - 量价因子：均线偏离度、MACD、RSI、KDJ、布林带、成交量比率
    - 基本面因子：PE/PB/PS估值、ROE、营收增速、毛利率、资产负债率
    - 资金因子：主力净流入比率、北向资金净买入、换手率异动
    - 情绪因子：涨跌停比率、融资余额变化、搜索热度
    - 技术形态因子：突破关键位、趋势强度、波动率变化

    每个因子方法接收 ohlcv_data (Dict) 参数，返回 float 因子值。
    ohlcv_data 的结构：
    {
        "dates":    [str, ...],           # 日期列表
        "open":     [float, ...],         # 开盘价
        "high":     [float, ...],         # 最高价
        "low":      [float, ...],         # 最低价
        "close":    [float, ...],         # 收盘价
        "volume":   [float, ...],         # 成交量
        "amount":   [float, ...],         # 成交额
        # 以下为基本面数据（可选，默认值用于演示）
        "pe":       float,                # 市盈率
        "pb":       float,                # 市净率
        "ps":       float,                # 市销率
        "roe":      float,                # 净资产收益率 (%)
        "revenue_growth": float,          # 营收增速 (%)
        "gross_margin":   float,          # 毛利率 (%)
        "debt_ratio":     float,          # 资产负债率 (%)
        "main_net_inflow": float,         # 主力净流入比率 (%)
        "north_net_buy":   float,         # 北向资金净买入 (万元)
        "turnover_rate":   float,         # 换手率 (%)
        "limit_up_count":  int,           # 涨停家数
        "limit_down_count": int,          # 跌停家数
        "margin_balance_change": float,   # 融资余额变化 (%)
        "search_heat":     float,         # 搜索热度 (0-100)
    }
    """

    def __init__(self):
        """初始化因子库"""
        pass

    # ==========================================================================
    # 量价因子
    # ==========================================================================

    def ma5_deviation(self, ohlcv_data: Dict) -> float:
        """MA5均线偏离度 = (收盘价 - MA5) / MA5 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 5:
            return 0.0
        ma5 = _rolling_mean(closes, 5)
        return _safe_divide(closes[-1] - ma5, ma5, 0.0) * 100

    def ma10_deviation(self, ohlcv_data: Dict) -> float:
        """MA10均线偏离度 = (收盘价 - MA10) / MA10 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 10:
            return 0.0
        ma10 = _rolling_mean(closes, 10)
        return _safe_divide(closes[-1] - ma10, ma10, 0.0) * 100

    def ma20_deviation(self, ohlcv_data: Dict) -> float:
        """MA20均线偏离度 = (收盘价 - MA20) / MA20 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        ma20 = _rolling_mean(closes, 20)
        return _safe_divide(closes[-1] - ma20, ma20, 0.0) * 100

    def ma60_deviation(self, ohlcv_data: Dict) -> float:
        """MA60均线偏离度 = (收盘价 - MA60) / MA60 * 100"""
        closes = ohlcv_data.get("close", [])
        if len(closes) < 60:
            return 0.0
        ma60 = _rolling_mean(closes, 60)
        return _safe_divide(closes[-1] - ma60, ma60, 0.0) * 100

    def macd_dif(self, ohlcv_data: Dict) -> float:
        """
        MACD DIF线（快线）= EMA12 - EMA26
        返回DIF值
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 26:
            return 0.0
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        return ema12 - ema26

    def macd_dea(self, ohlcv_data: Dict) -> float:
        """
        MACD DEA线（慢线）= DIF的EMA9
        需要先计算历史DIF序列，再对DIF序列求EMA9
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 35:  # 至少需要26+9=35个数据点
            return 0.0
        # 计算完整DIF序列
        dif_series = []
        multiplier = 2.0 / (13.0)  # EMA12的平滑因子
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
        # 对DIF序列求EMA9
        if len(dif_series) < 9:
            return 0.0
        dea = _ema(dif_series, 9)
        return dea

    def macd_histogram(self, ohlcv_data: Dict) -> float:
        """
        MACD柱状图 = (DIF - DEA) * 2
        正值表示多头动能，负值表示空头动能
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 35:
            return 0.0
        dif = self.macd_dif(ohlcv_data)
        dea = self.macd_dea(ohlcv_data)
        return (dif - dea) * 2

    def rsi14(self, ohlcv_data: Dict) -> float:
        """
        RSI(14) 相对强弱指标
        RSI = 100 - 100 / (1 + RS)
        RS = 平均涨幅 / 平均跌幅（14日）
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 15:
            return 50.0  # 数据不足时返回中性值
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

    def kdj_k(self, ohlcv_data: Dict) -> float:
        """
        KDJ指标 — K值
        RSV = (收盘价 - N日最低价) / (N日最高价 - N日最低价) * 100
        K = 2/3 * 前K + 1/3 * RSV（使用9日周期）
        """
        closes = ohlcv_data.get("close", [])
        highs = ohlcv_data.get("high", [])
        lows = ohlcv_data.get("low", [])
        n = 9
        if len(closes) < n:
            return 50.0
        # 取最近9日数据
        recent_highs = highs[-n:]
        recent_lows = lows[-n:]
        highest = max(recent_highs)
        lowest = min(recent_lows)
        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (closes[-1] - lowest) / (highest - lowest) * 100.0
        # 简化：用最近9日的平均RSV作为K值（完整实现需要递推）
        # 这里做完整递推
        k_val = 50.0  # 初始K值
        for i in range(n):
            h = max(highs[-(n - i):])
            l = min(lows[-(n - i):])
            if h == l:
                rsv_i = 50.0
            else:
                rsv_i = (closes[-(n - i)] - l) / (h - l) * 100.0
            k_val = 2.0 / 3.0 * k_val + 1.0 / 3.0 * rsv_i
        return k_val

    def kdj_d(self, ohlcv_data: Dict) -> float:
        """
        KDJ指标 — D值
        D = 2/3 * 前D + 1/3 * K
        """
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

    def kdj_j(self, ohlcv_data: Dict) -> float:
        """
        KDJ指标 — J值
        J = 3 * K - 2 * D
        """
        k = self.kdj_k(ohlcv_data)
        d = self.kdj_d(ohlcv_data)
        return 3.0 * k - 2.0 * d

    def bollinger_position(self, ohlcv_data: Dict) -> float:
        """
        布林带位置 = (收盘价 - MA20) / (2 * 20日标准差)
        返回值在 -1 到 1 之间，>1为突破上轨，<-1为跌破下轨
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        ma20 = _rolling_mean(closes, 20)
        std20 = _rolling_std(closes, 20)
        if std20 == 0:
            return 0.0
        return (closes[-1] - ma20) / (2.0 * std20)

    def volume_ratio(self, ohlcv_data: Dict) -> float:
        """
        成交量比率 = 当日成交量 / 5日平均成交量
        大于1表示放量，小于1表示缩量
        """
        volumes = ohlcv_data.get("volume", [])
        if len(volumes) < 6:
            return 1.0
        avg_vol = _rolling_mean(volumes[:-1], 5)
        if avg_vol == 0:
            return 1.0
        return volumes[-1] / avg_vol

    # ==========================================================================
    # 基本面因子
    # ==========================================================================

    def pe_factor(self, ohlcv_data: Dict) -> float:
        """
        PE估值因子
        返回市盈率的倒数（1/PE），值越大表示估值越低
        """
        pe = ohlcv_data.get("pe", 0.0)
        if pe is None or pe <= 0:
            return 0.0
        return 1.0 / pe

    def pb_factor(self, ohlcv_data: Dict) -> float:
        """
        PB估值因子
        返回市净率的倒数（1/PB），值越大表示估值越低
        """
        pb = ohlcv_data.get("pb", 0.0)
        if pb is None or pb <= 0:
            return 0.0
        return 1.0 / pb

    def ps_factor(self, ohlcv_data: Dict) -> float:
        """
        PS估值因子
        返回市销率的倒数（1/PS），值越大表示估值越低
        """
        ps = ohlcv_data.get("ps", 0.0)
        if ps is None or ps <= 0:
            return 0.0
        return 1.0 / ps

    def roe_factor(self, ohlcv_data: Dict) -> float:
        """
        ROE净资产收益率因子
        直接返回ROE百分比数值，越高越好
        """
        return ohlcv_data.get("roe", 0.0)

    def revenue_growth_factor(self, ohlcv_data: Dict) -> float:
        """
        营收增速因子
        直接返回营收增速百分比，越高越好
        """
        return ohlcv_data.get("revenue_growth", 0.0)

    def gross_margin_factor(self, ohlcv_data: Dict) -> float:
        """
        毛利率因子
        直接返回毛利率百分比，越高越好
        """
        return ohlcv_data.get("gross_margin", 0.0)

    def debt_ratio_factor(self, ohlcv_data: Dict) -> float:
        """
        资产负债率因子
        返回负值（取反），因为负债率越低越好
        """
        return -ohlcv_data.get("debt_ratio", 0.0)

    # ==========================================================================
    # 资金因子
    # ==========================================================================

    def main_net_inflow_ratio(self, ohlcv_data: Dict) -> float:
        """
        主力净流入比率
        正值表示主力净流入，负值表示净流出
        """
        return ohlcv_data.get("main_net_inflow", 0.0)

    def north_net_buy(self, ohlcv_data: Dict) -> float:
        """
        北向资金净买入
        正值表示净买入，负值表示净卖出
        单位：万元
        """
        return ohlcv_data.get("north_net_buy", 0.0)

    def turnover_rate_anomaly(self, ohlcv_data: Dict) -> float:
        """
        换手率异动
        计算当日换手率与20日平均换手率的偏离度
        """
        volumes = ohlcv_data.get("volume", [])
        amounts = ohlcv_data.get("amount", [])
        closes = ohlcv_data.get("close", [])
        current_turnover = ohlcv_data.get("turnover_rate", 0.0)

        if len(volumes) < 20 or len(closes) < 20:
            return 0.0

        # 用成交量/收盘价近似计算历史换手率
        avg_volume = _rolling_mean(volumes[:-1], 20)
        if avg_volume == 0:
            return 0.0

        # 换手率异动 = 当日换手率 / 20日平均换手率 - 1
        # 简化：用成交量比率近似
        vol_ratio = volumes[-1] / avg_volume
        return (vol_ratio - 1.0) * 100.0

    # ==========================================================================
    # 情绪因子
    # ==========================================================================

    def limit_ratio(self, ohlcv_data: Dict) -> float:
        """
        涨跌停比率 = 涨停家数 / (涨停家数 + 跌停家数)
        值在0到1之间，越高表示市场情绪越好
        """
        up = ohlcv_data.get("limit_up_count", 0)
        down = ohlcv_data.get("limit_down_count", 0)
        total = up + down
        if total == 0:
            return 0.5  # 无涨跌停时返回中性值
        return up / total

    def margin_balance_change(self, ohlcv_data: Dict) -> float:
        """
        融资余额变化
        正值表示融资余额增加（杠杆做多意愿增强）
        """
        return ohlcv_data.get("margin_balance_change", 0.0)

    def search_heat(self, ohlcv_data: Dict) -> float:
        """
        搜索热度（模拟）
        返回0-100的热度值，越高表示关注度越高
        """
        return ohlcv_data.get("search_heat", 0.0)

    # ==========================================================================
    # 技术形态因子
    # ==========================================================================

    def breakout_signal(self, ohlcv_data: Dict) -> float:
        """
        突破/跌破关键位信号
        比较当日收盘价与20日最高价/最低价的关系
        返回值：>0 突破，<0 跌破，0 震荡
        """
        closes = ohlcv_data.get("close", [])
        highs = ohlcv_data.get("high", [])
        lows = ohlcv_data.get("low", [])
        if len(closes) < 21:
            return 0.0
        # 20日最高价和最低价（不含当日）
        high_20 = max(highs[-21:-1])
        low_20 = min(lows[-21:-1]) if len(lows) >= 21 else min(closes[-21:-1])
        current = closes[-1]
        range_val = high_20 - low_20
        if range_val == 0:
            return 0.0
        # 返回突破强度
        if current > high_20:
            return (current - high_20) / range_val * 100.0
        elif current < low_20:
            return (current - low_20) / range_val * 100.0
        else:
            return 0.0

    def trend_strength(self, ohlcv_data: Dict) -> float:
        """
        趋势强度
        使用20日线性回归斜率标准化来衡量趋势强度
        正值表示上升趋势，负值表示下降趋势
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        recent = closes[-20:]
        n = len(recent)
        # 计算线性回归斜率
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent) / n
        numerator = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return 0.0
        slope = numerator / denominator
        # 标准化：斜率 / 均值 * 100
        return _safe_divide(slope, y_mean, 0.0) * 100.0

    def volatility_change(self, ohlcv_data: Dict) -> float:
        """
        波动率变化
        比较近5日波动率与20日波动率的变化
        正值表示波动率上升（风险增加），负值表示波动率下降（趋于稳定）
        """
        closes = ohlcv_data.get("close", [])
        if len(closes) < 20:
            return 0.0
        # 计算日收益率
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        if len(returns) < 20:
            return 0.0
        # 近5日波动率 vs 近20日波动率
        vol_5 = _rolling_std(returns, 5)
        vol_20 = _rolling_std(returns, 20)
        if vol_20 == 0:
            return 0.0
        return (vol_5 - vol_20) / vol_20 * 100.0

    # ==========================================================================
    # 背离与预警因子（6/18验证发现的新因子）
    # ==========================================================================

    def sector_stock_divergence(self, ohlcv_data: Dict) -> float:
        """板块-个股背离因子
        当板块涨幅>2%但个股逆势下跌时，返回负值（背离预警）
        正值=个股跑赢板块，负值=个股弱于板块
        """
        stock_change = ohlcv_data.get("stock_change_pct", 0)
        sector_change = ohlcv_data.get("sector_change_pct", 0)
        return stock_change - sector_change

    def main_capital_flow_warning(self, ohlcv_data: Dict) -> float:
        """主力资金流向预警因子
        主力净流入>0为正，净流出>3亿为强负信号
        返回值：正=资金流入，负=资金流出，绝对值越大信号越强
        """
        net_inflow = ohlcv_data.get("main_net_inflow", 0)  # 亿
        if net_inflow > 0:
            return min(net_inflow / 5.0, 1.0)  # 上限1.0
        elif net_inflow < -3:
            return max(net_inflow / 5.0, -1.0)  # 下限-1.0
        return net_inflow / 5.0

    def turnover_divergence_warning(self, ohlcv_data: Dict) -> float:
        """换手率分歧预警因子
        换手率>9%为高位分歧信号，返回负值
        换手率3-7%为健康区间，返回正值
        换手率<3%为低迷信号，返回0
        """
        turnover = ohlcv_data.get("turnover_rate", 0)
        if turnover > 9:
            return -(turnover - 9) / 10.0  # 越高越负
        elif 3 <= turnover <= 7:
            return 0.5  # 健康区间
        elif turnover > 0:
            return turnover / 6.0  # 低换手
        return 0.0

    def limit_up_pressure(self, ohlcv_data: Dict) -> float:
        """涨停板压力因子
        涨停=1.0(强势)，接近涨停(>7%)=0.5，跌停=-1.0(弱势)
        """
        change_pct = ohlcv_data.get("stock_change_pct", 0)
        if change_pct >= 9.9:
            return 1.0
        elif change_pct >= 7:
            return 0.5
        elif change_pct <= -9.9:
            return -1.0
        elif change_pct <= -7:
            return -0.5
        return change_pct / 10.0

    # ==========================================================================
    # 筹码分布因子
    # ==========================================================================

    def chip_concentration(self, ohlcv_data: Dict) -> float:
        """筹码集中度因子
        获利比例>70%为高位集中（负信号），30-70%为健康（正信号），<30%为低位集中（强正信号）
        """
        profit_ratio = ohlcv_data.get("profit_ratio", 50)
        if profit_ratio > 70:
            return -(profit_ratio - 70) / 30.0  # 高位套牢风险
        elif 30 <= profit_ratio <= 70:
            return 0.5
        else:
            return 1.0  # 低位筹码集中，上涨空间大

    def holder_count_change(self, ohlcv_data: Dict) -> float:
        """股东人数变化因子
        股东减少=筹码集中(正信号)，股东增加=筹码分散(负信号)
        """
        change_pct = ohlcv_data.get("holder_count_change_pct", 0)
        if change_pct < -5:
            return 1.0  # 大幅减少，筹码高度集中
        elif change_pct < 0:
            return 0.5
        elif change_pct > 5:
            return -1.0  # 大幅增加，筹码分散
        elif change_pct > 0:
            return -0.5
        return 0.0

    # ==========================================================================
    # 事件驱动因子
    # ==========================================================================

    def earnings_surprise(self, ohlcv_data: Dict) -> float:
        """业绩超预期因子
        实际净利润 > 预期 = 正信号
        """
        actual_eps = ohlcv_data.get("actual_eps", 0)
        expected_eps = ohlcv_data.get("expected_eps", 0)
        if expected_eps == 0:
            return 0.0
        surprise = (actual_eps - expected_eps) / abs(expected_eps)
        return max(-1.0, min(1.0, surprise))

    def institutional_position_change(self, ohlcv_data: Dict) -> float:
        """机构持仓变化因子
        机构增持=正信号，减持=负信号
        """
        change = ohlcv_data.get("inst_position_change_pct", 0)
        if change > 2:
            return 1.0
        elif change > 0:
            return 0.5
        elif change < -2:
            return -1.0
        elif change < 0:
            return -0.5
        return 0.0

    def major_contract_event(self, ohlcv_data: Dict) -> float:
        """重大合同/订单事件因子
        有重大合同=1.0，无=0
        """
        has_major_contract = ohlcv_data.get("has_major_contract", False)
        return 1.0 if has_major_contract else 0.0

    def insider_trading_signal(self, ohlcv_data: Dict) -> float:
        """高管增减持信号因子
        高管增持=正信号，减持=负信号
        """
        signal = ohlcv_data.get("insider_trading_signal", 0)
        return max(-1.0, min(1.0, signal))

    # ==========================================================================
    # 宏观因子
    # ==========================================================================

    def liquidity_environment(self, ohlcv_data: Dict) -> float:
        """流动性环境因子
        两市成交额>3万亿=宽松(正)，<2万亿=收紧(负)
        """
        total_volume = ohlcv_data.get("market_total_volume", 25000)
        if total_volume > 30000:
            return 1.0
        elif total_volume > 25000:
            return 0.5
        elif total_volume < 20000:
            return -1.0
        elif total_volume < 25000:
            return -0.5
        return 0.0

    def policy_tailwind(self, ohlcv_data: Dict) -> float:
        """政策顺风因子
        有政策利好=1.0，中性=0，有利空=-1.0
        """
        policy_signal = ohlcv_data.get("policy_signal", 0)
        return max(-1.0, min(1.0, policy_signal))

    def external_market_impact(self, ohlcv_data: Dict) -> float:
        """外盘影响因子
        美股涨=正，跌=负
        """
        us_change = ohlcv_data.get("us_market_change_pct", 0)
        return max(-1.0, min(1.0, us_change / 3.0))

    def industry_rotation_strength(self, ohlcv_data: Dict) -> float:
        """行业轮动强度因子
        行业相对大盘超额收益>2%=强正信号
        """
        industry_change = ohlcv_data.get("industry_change_pct", 0)
        market_change = ohlcv_data.get("market_change_pct", 0)
        excess = industry_change - market_change
        if excess > 2:
            return 1.0
        elif excess > 0:
            return 0.5
        elif excess < -2:
            return -1.0
        elif excess < 0:
            return -0.5
        return 0.0

    # ==========================================================================
    # 机构行为因子（暗盘追踪）
    # ==========================================================================

    def institutional_dark_pool(self, ohlcv_data: Dict) -> float:
        """机构暗盘资金因子
        检测隐藏在中小单中的主力动向。
        暗盘资金 = 总成交额 - 大单成交额 - 散户典型成交额
        暗盘占比>30%为强信号（主力隐蔽建仓/出货）
        """
        total_amount = ohlcv_data.get("total_amount", 0)
        large_order_amount = ohlcv_data.get("large_order_amount", 0)
        if total_amount == 0:
            return 0.0
        dark_pool_ratio = 1.0 - (large_order_amount / total_amount) - 0.3  # 减去散户典型占比
        if dark_pool_ratio > 0.3:
            return 1.0  # 大量暗盘活动
        elif dark_pool_ratio > 0.1:
            return 0.5
        elif dark_pool_ratio < -0.1:
            return -0.5  # 暗盘流出
        return 0.0

    def order_imbalance(self, ohlcv_data: Dict) -> float:
        """订单失衡因子
        主动买入量 vs 主动卖出量的失衡程度
        >0.3 = 买方主导，<-0.3 = 卖方主导
        """
        buy_volume = ohlcv_data.get("active_buy_volume", 0)
        sell_volume = ohlcv_data.get("active_sell_volume", 0)
        total = buy_volume + sell_volume
        if total == 0:
            return 0.0
        imbalance = (buy_volume - sell_volume) / total
        return max(-1.0, min(1.0, imbalance * 3))  # 放大3倍

    def vwap_deviation(self, ohlcv_data: Dict) -> float:
        """VWAP偏离因子
        收盘价高于VWAP = 买方优势（正信号）
        收盘价低于VWAP = 卖方优势（负信号）
        """
        close = ohlcv_data.get("close", 0)
        vwap = ohlcv_data.get("vwap", 0)
        if vwap == 0:
            return 0.0
        deviation = (close - vwap) / vwap * 100
        return max(-1.0, min(1.0, deviation / 3.0))  # ±3%为满值

    def large_order_density(self, ohlcv_data: Dict) -> float:
        """大单密度因子
        大单成交金额占总成交额的比例
        >40% = 机构积极参与，<15% = 散户主导
        """
        large_amount = ohlcv_data.get("large_order_amount", 0)
        total_amount = ohlcv_data.get("total_amount", 0)
        if total_amount == 0:
            return 0.0
        density = large_amount / total_amount
        if density > 0.4:
            return 1.0
        elif density > 0.25:
            return 0.5
        elif density < 0.15:
            return -0.5
        return 0.0

    # ==========================================================================
    # 舆情NLP因子
    # ==========================================================================

    def news_sentiment(self, ohlcv_data: Dict) -> float:
        """新闻情感因子
        基于NLP分析的舆情情感得分 [-1, 1]
        >0.3 = 正面舆情，<-0.3 = 负面舆情

        V6.3 增强：自动从 NewsSentimentEngine 获取实时快兰斯快讯情绪
        如果 ohlcv_data 中已提供 news_sentiment_score，则直接使用；
        否则尝试自动获取最新消息面情绪。
        """
        # 优先使用输入数据中的情绪值
        sentiment = ohlcv_data.get("news_sentiment_score", None)
        if sentiment is not None:
            return max(-1.0, min(1.0, float(sentiment)))

        # 尝试自动获取实时消息面情绪
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
                # 获取宏观情绪作为默认
                macro = engine.get_macro_sentiment()
                return max(-1.0, min(1.0, macro))
        except Exception:
            pass

        return 0.0

    def social_heat_anomaly(self, ohlcv_data: Dict) -> float:
        """社交热度异常因子
        搜索热度/讨论量相对均值的偏离度
        热度暴增可能预示短期方向性选择
        """
        current_heat = ohlcv_data.get("social_heat", 0)
        avg_heat = ohlcv_data.get("avg_social_heat", 0)
        if avg_heat == 0:
            return 0.0
        anomaly = (current_heat - avg_heat) / avg_heat
        if anomaly > 2.0:
            return 1.0  # 热度暴增
        elif anomaly > 1.0:
            return 0.5
        elif anomaly < -0.5:
            return -0.5  # 热度骤降
        return 0.0

    def analyst_consensus_breakout(self, ohlcv_data: Dict) -> float:
        """分析师共识突破因子
        当实际业绩大幅超出/低于分析师一致预期时
        往往引发机构调仓，产生趋势性机会
        """
        actual_growth = ohlcv_data.get("actual_revenue_growth", 0)
        consensus_growth = ohlcv_data.get("consensus_revenue_growth", 0)
        if consensus_growth == 0:
            return 0.0
        surprise = (actual_growth - consensus_growth) / abs(consensus_growth)
        return max(-1.0, min(1.0, surprise))

    # ==========================================================================
    # 分域适配因子（不同市场环境使用不同因子权重）
    # ==========================================================================

    def market_regime_detector(self, ohlcv_data: Dict) -> float:
        """市场体制检测因子
        返回当前市场环境类型编码：
        >0.5 = 趋势市（动量因子有效）
        0 ~ 0.5 = 震荡市（均值回归因子有效）
        <0 = 衰退市（防御因子有效）
        """
        # 简化判断：用20日均线斜率 + 波动率
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 20:
            return 0.0
        ma20 = sum(closes[-20:]) / 20
        ma5 = sum(closes[-5:]) / 5
        slope = (ma5 - ma20) / ma20 * 100  # 均线斜率

        # 波动率
        returns = []
        for i in range(1, min(20, len(closes))):
            if closes[-i-1] != 0:
                returns.append((closes[-i] - closes[-i-1]) / closes[-i-1])
        if not returns:
            return 0.0
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5 * 100

        if slope > 2 and volatility < 3:
            return 1.0  # 稳定趋势市
        elif slope > 0:
            return 0.5  # 弱趋势
        elif slope < -2 and volatility > 4:
            return -1.0  # 恐慌市
        elif slope < 0:
            return -0.5  # 弱震荡偏空
        return 0.0  # 震荡市

    def factor_momentum(self, ohlcv_data: Dict) -> float:
        """因子动量因子
        某个因子近期的表现趋势
        因子动量>0表示该因子近期在增强
        """
        factor_recent = ohlcv_data.get("factor_score_5d", 0)
        factor_20d = ohlcv_data.get("factor_score_20d", 0)
        if factor_20d == 0:
            return 0.0
        momentum = (factor_recent - factor_20d) / abs(factor_20d)
        return max(-1.0, min(1.0, momentum))

    def cross_section_momentum(self, ohlcv_data: Dict) -> float:
        """截面动量因子
        个股相对于行业/板块的超额收益动量
        近20日超额收益为正=动量延续
        """
        stock_return_20d = ohlcv_data.get("stock_return_20d", 0)
        industry_return_20d = ohlcv_data.get("industry_return_20d", 0)
        excess = stock_return_20d - industry_return_20d
        if excess > 10:
            return 1.0
        elif excess > 3:
            return 0.5
        elif excess < -10:
            return -1.0
        elif excess < -3:
            return -0.5
        return 0.0

    # ==========================================================================
    # 微观结构因子
    # ==========================================================================

    def bid_ask_spread_pressure(self, ohlcv_data: Dict) -> float:
        """买卖价差压力因子
        价差扩大 = 流动性下降 = 卖压
        价差收窄 = 流动性充裕 = 买方积极
        """
        spread = ohlcv_data.get("bid_ask_spread_pct", 0)
        if spread > 3:
            return -1.0  # 大价差，流动性差
        elif spread > 1.5:
            return -0.5
        elif spread < 0.5:
            return 1.0  # 极窄价差，流动性极好
        elif spread < 1:
            return 0.5
        return 0.0

    def limit_order_book_depth(self, ohlcv_data: Dict) -> float:
        """限价订单簿深度因子
        买盘深度/卖盘深度 > 1.2 = 买方力量强
        < 0.8 = 卖方力量强
        """
        buy_depth = ohlcv_data.get("buy_depth_5", 0)
        sell_depth = ohlcv_data.get("sell_depth_5", 0)
        if sell_depth == 0:
            return 0.0
        ratio = buy_depth / sell_depth
        if ratio > 1.5:
            return 1.0
        elif ratio > 1.2:
            return 0.5
        elif ratio < 0.67:
            return -1.0
        elif ratio < 0.83:
            return -0.5
        return 0.0

    def tick_frequency_anomaly(self, ohlcv_data: Dict) -> float:
        """成交频率异常因子
        成交笔数异常增加 = 机构算法交易活跃
        """
        current_ticks = ohlcv_data.get("tick_count", 0)
        avg_ticks = ohlcv_data.get("avg_tick_count", 0)
        if avg_ticks == 0:
            return 0.0
        ratio = current_ticks / avg_ticks
        if ratio > 2.0:
            return 1.0  # 成交频率翻倍，机构活跃
        elif ratio > 1.5:
            return 0.5
        elif ratio < 0.5:
            return -0.5  # 成交萎缩
        return 0.0

    # ==========================================================================
    # 杠杆资金因子（第四波突破性因子 — 2025-2026学术前沿）
    # ==========================================================================

    def margin_financing_intensity(self, ohlcv_data: Dict) -> float:
        """融资买入强度因子
        融资净买入额占成交额比例，反映杠杆资金看多意愿
        >5%返回1.0, 2-5%返回0.5, <-2%返回-0.5, <-5%返回-1.0
        """
        margin_net_buy = ohlcv_data.get("margin_net_buy", 0)
        amount = ohlcv_data.get("amount", 0)
        if isinstance(amount, list):
            amount = amount[-1] if amount else 0
        if amount == 0:
            return 0.0
        ratio = _safe_divide(margin_net_buy, amount, 0.0) * 100
        if ratio > 5:
            return 1.0
        elif ratio > 2:
            return 0.5
        elif ratio < -5:
            return -1.0
        elif ratio < -2:
            return -0.5
        return 0.0

    def margin_concentration_risk(self, ohlcv_data: Dict) -> float:
        """融资盘集中度风险因子
        融资余额占流通市值比例，过高有强平风险
        >10%返回-1.0(高风险), 5-10%返回-0.5, <3%返回0.5(安全)
        """
        margin_balance = ohlcv_data.get("margin_balance", 0)
        float_market_cap = ohlcv_data.get("float_market_cap", 0)
        if float_market_cap == 0:
            return 0.0
        ratio = _safe_divide(margin_balance, float_market_cap, 0.0) * 100
        if ratio > 10:
            return -1.0
        elif ratio > 5:
            return -0.5
        elif ratio < 3:
            return 0.5
        return 0.0

    def short_squeeze_potential(self, ohlcv_data: Dict) -> float:
        """融券做空挤压因子
        融券余额/融资余额比率异常低+股价上涨=逼空潜力
        ratio<0.05且涨幅>3%返回1.0, ratio<0.1且涨幅>0%返回0.5
        """
        short_balance = ohlcv_data.get("short_balance", 0)
        margin_balance = ohlcv_data.get("margin_balance", 0)
        stock_change_pct = ohlcv_data.get("stock_change_pct", 0)
        if margin_balance == 0:
            return 0.0
        ratio = _safe_divide(short_balance, margin_balance, 0.0)
        if ratio < 0.05 and stock_change_pct > 3:
            return 1.0
        elif ratio < 0.1 and stock_change_pct > 0:
            return 0.5
        return 0.0

    def leveraged_fund_flow_divergence(self, ohlcv_data: Dict) -> float:
        """杠杆资金流向背离因子
        融资净买入与股价走势背离（融资在买但股价跌=底部吸筹）
        margin增加但股价跌返回0.5(吸筹), margin减少但股价涨返回-0.5(派发)
        """
        margin_net_buy = ohlcv_data.get("margin_net_buy", 0)
        margin_net_buy_5d_ago = ohlcv_data.get("margin_net_buy_5d_ago", 0)
        stock_change_pct_5d = ohlcv_data.get("stock_change_pct_5d", 0)
        margin_increasing = margin_net_buy > margin_net_buy_5d_ago
        price_falling = stock_change_pct_5d < 0
        margin_decreasing = margin_net_buy < margin_net_buy_5d_ago
        price_rising = stock_change_pct_5d > 0
        if margin_increasing and price_falling:
            return 0.5  # 底部吸筹信号
        elif margin_decreasing and price_rising:
            return -0.5  # 派发信号
        return 0.0

    # ==========================================================================
    # 龙虎榜聪明钱因子
    # ==========================================================================

    def dragon_tiger_institutional_net(self, ohlcv_data: Dict) -> float:
        """龙虎榜机构净买入因子
        机构席位净买入金额占当日成交额比例
        >3%返回1.0, 1-3%返回0.5, <-1%返回-0.5, <-3%返回-1.0
        """
        institution_net_buy = ohlcv_data.get("institution_net_buy", 0)
        amount = ohlcv_data.get("amount", 0)
        if isinstance(amount, list):
            amount = amount[-1] if amount else 0
        if amount == 0:
            return 0.0
        ratio = _safe_divide(institution_net_buy, amount, 0.0) * 100
        if ratio > 3:
            return 1.0
        elif ratio > 1:
            return 0.5
        elif ratio < -3:
            return -1.0
        elif ratio < -1:
            return -0.5
        return 0.0

    def dragon_tiger_hot_money_trace(self, ohlcv_data: Dict) -> float:
        """游资席位追踪因子
        知名游资席位出现次数占总席位数比例
        ratio>0.3返回1.0, 0.15-0.3返回0.5
        """
        hot_money_seats = ohlcv_data.get("hot_money_seats", 0)
        total_seats = ohlcv_data.get("total_seats", 0)
        if total_seats == 0:
            return 0.0
        ratio = _safe_divide(hot_money_seats, total_seats, 0.0)
        if ratio > 0.3:
            return 1.0
        elif ratio > 0.15:
            return 0.5
        return 0.0

    def dragon_tiger_buy_sell_ratio(self, ohlcv_data: Dict) -> float:
        """龙虎榜买卖比因子
        买入金额/卖出金额比率
        >2返回1.0, 1.5-2返回0.5, <0.5返回-1.0, 0.5-1返回-0.5
        """
        dragon_buy_amount = ohlcv_data.get("dragon_buy_amount", 0)
        dragon_sell_amount = ohlcv_data.get("dragon_sell_amount", 0)
        if dragon_sell_amount == 0:
            return 0.0
        ratio = _safe_divide(dragon_buy_amount, dragon_sell_amount, 0.0)
        if ratio > 2:
            return 1.0
        elif ratio > 1.5:
            return 0.5
        elif ratio < 0.5:
            return -1.0
        elif ratio < 1:
            return -0.5
        return 0.0

    def dragon_tiger_new_face_signal(self, ohlcv_data: Dict) -> float:
        """龙虎榜新面孔因子
        首次上龙虎榜或机构新进=增量资金信号
        首次上榜返回0.5, 机构新进返回1.0, 两者都有返回1.0
        """
        is_first_dragon_tiger = ohlcv_data.get("is_first_dragon_tiger", False)
        institution_new_entry = ohlcv_data.get("institution_new_entry", False)
        if institution_new_entry:
            return 1.0
        elif is_first_dragon_tiger:
            return 0.5
        return 0.0

    # ==========================================================================
    # 集合竞价与尾盘因子
    # ==========================================================================

    def call_auction_premium(self, ohlcv_data: Dict) -> float:
        """集合竞价溢价因子
        开盘价相对前收溢价率，高溢价=抢筹意愿强
        >3%返回1.0, 1-3%返回0.5, <-2%返回-0.5, <-3%返回-1.0
        """
        opens = ohlcv_data.get("open", [])
        prev_close = ohlcv_data.get("prev_close", 0)
        if not opens or prev_close == 0:
            return 0.0
        open_price = opens[-1] if isinstance(opens, list) else opens
        premium = _safe_divide(open_price - prev_close, prev_close, 0.0) * 100
        if premium > 3:
            return 1.0
        elif premium > 1:
            return 0.5
        elif premium < -3:
            return -1.0
        elif premium < -2:
            return -0.5
        return 0.0

    def call_auction_volume_ratio(self, ohlcv_data: Dict) -> float:
        """集合竞价量比因子
        竞价成交量占全天成交量比例
        >8%返回1.0, 5-8%返回0.5, <2%返回-0.5
        """
        auction_volume = ohlcv_data.get("auction_volume", 0)
        volume = ohlcv_data.get("volume", 0)
        if isinstance(volume, list):
            volume = volume[-1] if volume else 0
        if volume == 0:
            return 0.0
        ratio = _safe_divide(auction_volume, volume, 0.0) * 100
        if ratio > 8:
            return 1.0
        elif ratio > 5:
            return 0.5
        elif ratio < 2:
            return -0.5
        return 0.0

    def tail_momentum_acceleration(self, ohlcv_data: Dict) -> float:
        """尾盘动量加速因子
        最后30分钟涨幅 vs 全天涨幅，尾盘加速=资金抢筹
        尾盘涨幅占全天>50%返回1.0, 30-50%返回0.5, <-10%返回-0.5
        """
        closes = ohlcv_data.get("close", [])
        opens = ohlcv_data.get("open", [])
        price_30min_ago = ohlcv_data.get("price_30min_ago", 0)
        if not closes or not opens or price_30min_ago == 0:
            return 0.0
        close_price = closes[-1] if isinstance(closes, list) else closes
        open_price = opens[-1] if isinstance(opens, list) else opens
        # 全天涨幅
        daily_change = _safe_divide(close_price - open_price, open_price, 0.0)
        # 尾盘涨幅（14:30到收盘）
        tail_change = _safe_divide(close_price - price_30min_ago, price_30min_ago, 0.0)
        if daily_change == 0:
            return 0.0
        tail_ratio = _safe_divide(tail_change, daily_change, 0.0)
        if tail_ratio > 0.5:
            return 1.0
        elif tail_ratio > 0.3:
            return 0.5
        elif tail_ratio < -0.1:
            return -0.5
        return 0.0

    def tail_volume_concentration(self, ohlcv_data: Dict) -> float:
        """尾盘量能集中因子
        最后30分钟成交量占全天比例
        >25%返回1.0, 15-25%返回0.5, <8%返回-0.5
        """
        tail_volume = ohlcv_data.get("tail_volume", 0)
        volume = ohlcv_data.get("volume", 0)
        if isinstance(volume, list):
            volume = volume[-1] if volume else 0
        if volume == 0:
            return 0.0
        ratio = _safe_divide(tail_volume, volume, 0.0) * 100
        if ratio > 25:
            return 1.0
        elif ratio > 15:
            return 0.5
        elif ratio < 8:
            return -0.5
        return 0.0

    # ==========================================================================
    # 专利与创新因子
    # ==========================================================================

    def patent_value_density(self, ohlcv_data: Dict) -> float:
        """专利价值密度因子
        专利数量/市值，衡量创新效率
        >5专利/亿市值返回1.0, 2-5返回0.5, <0.5返回-0.5
        """
        patent_count = ohlcv_data.get("patent_count", 0)
        market_cap = ohlcv_data.get("market_cap", 0)
        if market_cap == 0:
            return 0.0
        density = _safe_divide(patent_count, market_cap, 0.0)
        if density > 5:
            return 1.0
        elif density > 2:
            return 0.5
        elif density < 0.5:
            return -0.5
        return 0.0

    def rd_intensity_momentum(self, ohlcv_data: Dict) -> float:
        """研发强度动量因子
        研发费用增长率变化趋势
        增速>2pct返回1.0, 0-2pct返回0.5, 下降>2pct返回-1.0
        """
        rd_ratio_current = ohlcv_data.get("rd_ratio_current", 0)
        rd_ratio_yoy = ohlcv_data.get("rd_ratio_yoy", 0)
        change = rd_ratio_current - rd_ratio_yoy
        if change > 2:
            return 1.0
        elif change > 0:
            return 0.5
        elif change < -2:
            return -1.0
        elif change < 0:
            return -0.5
        return 0.0

    def innovation_breakthrough_signal(self, ohlcv_data: Dict) -> float:
        """技术突破信号因子
        近期是否有重大技术突破/产品发布/专利授权
        有突破且影响>3返回1.0, 有突破且影响1-3返回0.5
        """
        has_tech_breakthrough = ohlcv_data.get("has_tech_breakthrough", False)
        breakthrough_impact = ohlcv_data.get("breakthrough_impact", 0)
        if has_tech_breakthrough and breakthrough_impact > 3:
            return 1.0
        elif has_tech_breakthrough and breakthrough_impact >= 1:
            return 0.5
        return 0.0

    def patent_citation_impact(self, ohlcv_data: Dict) -> float:
        """专利引用影响力因子
        专利被引用次数，反映技术领先性
        >3倍行业平均返回1.0, 1.5-3倍返回0.5, <0.5倍返回-0.5
        """
        patent_citations = ohlcv_data.get("patent_citations", 0)
        industry_avg_citations = ohlcv_data.get("industry_avg_citations", 0)
        if industry_avg_citations == 0:
            return 0.0
        ratio = _safe_divide(patent_citations, industry_avg_citations, 0.0)
        if ratio > 3:
            return 1.0
        elif ratio > 1.5:
            return 0.5
        elif ratio < 0.5:
            return -0.5
        return 0.0

    # ==========================================================================
    # 第19大类：微观结构深度因子 (4) — 第五波因子
    # 来自论文 "Explainable Patterns in Cryptocurrency Microstructure"
    # ==========================================================================

    def order_flow_imbalance_enhanced(self, ohlcv_data: Dict) -> float:
        """增强版订单流不平衡因子
        论文SHAP排名第一的因子，跨资产稳定
        计算逻辑: OFI = (buy - sell) / (buy + sell)，然后应用凹性变换
        sign(OFI) * |OFI|^0.5 捕捉边际递减效应
        """
        active_buy = ohlcv_data.get("active_buy_volume", 0)
        active_sell = ohlcv_data.get("active_sell_volume", 0)
        total = active_buy + active_sell
        if total == 0:
            return 0.0
        ofi = _safe_divide(active_buy - active_sell, total, 0.0)
        # 凹性变换：捕捉边际递减效应
        result = (1.0 if ofi >= 0 else -1.0) * math.pow(abs(ofi), 0.5)
        # 限制在 [-1.0, 1.0]
        return max(-1.0, min(1.0, result))

    def vwap_asymmetric_deviation(self, ohlcv_data: Dict) -> float:
        """非对称VWAP偏离因子
        论文发现买卖VWAP偏离具有非对称效应
        (close - vwap) / vwap，正值表示收盘高于VWAP（买方强势）
        """
        close = ohlcv_data.get("close", 0)
        vwap = ohlcv_data.get("vwap", 0)
        if vwap == 0 or close == 0:
            return 0.0
        deviation = _safe_divide(close - vwap, vwap, 0.0)
        if deviation > 0.02:
            return 1.0
        elif deviation > 0.01:
            return 0.5
        elif deviation < -0.02:
            return -1.0
        elif deviation < -0.01:
            return -0.5
        return 0.0

    def microprice_deviation(self, ohlcv_data: Dict) -> float:
        """Stoikov微观价格偏离因子
        论文验证微观价格与后续价格变动高度相关(c=0.94)
        Microprice = mid + (spread/2) * (buy_depth - sell_depth) / (buy_depth + sell_depth)
        """
        buy_depth = ohlcv_data.get("buy_depth_5", 0)
        sell_depth = ohlcv_data.get("sell_depth_5", 0)
        spread_pct = ohlcv_data.get("bid_ask_spread_pct", 0)
        close = ohlcv_data.get("close", 0)
        if close == 0:
            return 0.0
        total_depth = buy_depth + sell_depth
        if total_depth == 0:
            return 0.0
        mid = close  # 近似中间价
        microprice = mid + (spread_pct / 2.0) * _safe_divide(buy_depth - sell_depth, total_depth, 0.0)
        deviation = _safe_divide(microprice - close, close, 0.0)
        if deviation > 0.01:
            return 1.0
        elif deviation > 0.005:
            return 0.5
        elif deviation < -0.01:
            return -1.0
        elif deviation < -0.005:
            return -0.5
        return 0.0

    def spread_attenuated_signal(self, ohlcv_data: Dict) -> float:
        """价差调节信号强度因子
        论文发现价差越大预测能力越弱（逆向选择风险）
        base_signal = OFI, attenuation = exp(-3 * spread)
        最终 = sign(base_signal) * min(1.0, |base_signal| * attenuation)
        """
        active_buy = ohlcv_data.get("active_buy_volume", 0)
        active_sell = ohlcv_data.get("active_sell_volume", 0)
        spread_pct = ohlcv_data.get("bid_ask_spread_pct", 0)
        total = active_buy + active_sell
        if total == 0:
            return 0.0
        base_signal = _safe_divide(active_buy - active_sell, total, 0.0)
        attenuation = math.exp(-3.0 * spread_pct)
        result = (1.0 if base_signal >= 0 else -1.0) * min(1.0, abs(base_signal) * attenuation)
        return max(-1.0, min(1.0, result))

    # ==========================================================================
    # 第20大类：MCTS公式因子 (4) — 第五波因子
    # 来自论文 "Navigating the Alpha Jungle: LLM-Powered MCTS"
    # ==========================================================================

    def volume_price_divergence_trend(self, ohlcv_data: Dict) -> float:
        """量价背离趋势因子
        MCTS挖掘的高效因子: Rank(MA5/MA20) * Sign(成交量5日变化)
        """
        closes = ohlcv_data.get("closes", [])
        volumes = ohlcv_data.get("volumes", [])
        if len(closes) < 20 or len(volumes) < 20:
            return 0.0
        ma5 = _rolling_mean(closes, 5)
        ma20 = _rolling_mean(closes, 20)
        if ma20 == 0:
            return 0.0
        ratio = _safe_divide(ma5, ma20, 1.0)
        # 在历史窗口中排名
        ratios = []
        for i in range(10, len(closes)):
            window = closes[i - 10:i + 1]
            if len(window) >= 10:
                m5 = sum(window[-5:]) / 5
                m20_v = sum(window) / len(window)
                if m20_v > 0:
                    ratios.append(_safe_divide(m5, m20_v, 1.0))
        if not ratios:
            return 0.0
        rank = sum(1 for r in ratios if r <= ratio) / len(ratios)  # 0~1
        # 成交量5日变化方向
        vol_change = _safe_divide(volumes[-1] - volumes[-6], volumes[-6], 0.0) if len(volumes) >= 6 else 0.0
        vol_sign = 1.0 if vol_change >= 0 else -1.0
        result = (rank - 0.5) * 2.0 * vol_sign  # -1.0~1.0
        return max(-1.0, min(1.0, result))

    def volatility_adjusted_momentum(self, ohlcv_data: Dict) -> float:
        """波动率调节动量因子
        Sharpe-like动量: Delta(close,10) / (StdDev(close,20) + epsilon)
        """
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 20:
            return 0.0
        momentum = _safe_divide(closes[-1] - closes[-11], closes[-11], 0.0) if len(closes) >= 11 else 0.0
        std = _rolling_std(closes, 20)
        if std == 0:
            return 0.0
        sharpe_mom = _safe_divide(momentum, std, 0.0)
        if sharpe_mom > 0.5:
            return 1.0
        elif sharpe_mom > 0.2:
            return 0.5
        elif sharpe_mom < -0.5:
            return -1.0
        elif sharpe_mom < -0.2:
            return -0.5
        return 0.0

    def multi_scale_price_position(self, ohlcv_data: Dict) -> float:
        """多尺度价格位置因子
        MCTS挖掘: Rank(close/Max(high,20)) - Rank(close/Min(low,20))
        """
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 20:
            return 0.0
        high_20 = max(closes[-20:])  # 用close近似high
        low_20 = min(closes[-20:])   # 用close近似low
        if high_20 == 0 or low_20 == 0:
            return 0.0
        high_ratio = _safe_divide(closes[-1], high_20, 0.0)
        low_ratio = _safe_divide(closes[-1], low_20, 0.0)
        # 在历史中排名
        high_ratios = []
        low_ratios = []
        for i in range(10, len(closes)):
            window = closes[i - 10:i + 1]
            h = max(window)
            l = min(window)
            if h > 0:
                high_ratios.append(_safe_divide(closes[i], h, 0.0))
            if l > 0:
                low_ratios.append(_safe_divide(closes[i], l, 0.0))
        if not high_ratios or not low_ratios:
            return 0.0
        rank_high = sum(1 for r in high_ratios if r <= high_ratio) / len(high_ratios)
        rank_low = sum(1 for r in low_ratios if r <= low_ratio) / len(low_ratios)
        result = (rank_high - rank_low) * 2.0  # -1.0~1.0
        return max(-1.0, min(1.0, result))

    def volume_acceleration(self, ohlcv_data: Dict) -> float:
        """成交量加速度因子
        Delta(Delta(volume,5),5) / (MA(volume,20) + epsilon)
        二阶差分标准化，捕捉成交量变化的变化率
        """
        volumes = ohlcv_data.get("volumes", [])
        if len(volumes) < 20:
            return 0.0
        delta1 = volumes[-1] - volumes[-6] if len(volumes) >= 6 else 0.0
        delta2 = volumes[-6] - volumes[-11] if len(volumes) >= 11 else 0.0
        acceleration = delta1 - delta2
        ma20 = _rolling_mean(volumes, 20)
        if ma20 == 0:
            return 0.0
        norm_accel = _safe_divide(acceleration, ma20, 0.0)
        if norm_accel > 0.3:
            return 1.0
        elif norm_accel > 0.1:
            return 0.5
        elif norm_accel < -0.3:
            return -1.0
        elif norm_accel < -0.1:
            return -0.5
        return 0.0

    # ==========================================================================
    # 第21大类：波动率择时因子 (4) — 第五波因子
    # 来自论文 "Seemingly Virtuous Complexity" + FinRL-Meta Turbulence
    # ==========================================================================

    def volatility_timed_momentum(self, ohlcv_data: Dict) -> float:
        """逆向波动率加权动量因子
        论文证明RFF成功本质就是该策略
        近5日收益均值 / (近20日收益标准差 + epsilon)
        低波动环境下动量信号更强
        """
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 20:
            return 0.0
        # 计算日收益率
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                returns.append(_safe_divide(closes[i] - closes[i - 1], closes[i - 1], 0.0))
        if len(returns) < 20:
            return 0.0
        mean_5 = _rolling_mean(returns, 5)
        std_20 = _rolling_std(returns, 20)
        if std_20 == 0:
            return 0.0
        vtm = _safe_divide(mean_5, std_20, 0.0)
        if vtm > 0.3:
            return 1.0
        elif vtm > 0.1:
            return 0.5
        elif vtm < -0.3:
            return -1.0
        elif vtm < -0.1:
            return -0.5
        return 0.0

    def turbulence_regime_signal(self, ohlcv_data: Dict) -> float:
        """湍流体制信号因子
        来自FinRL-Meta的Turbulence Index（Mahalanobis距离）
        简化版: 用个股波动率与市场波动率的偏离度
        |stock_vol - market_vol| / market_vol
        """
        stock_change = ohlcv_data.get("stock_change_pct", 0)
        market_change = ohlcv_data.get("market_change_pct", 0)
        if market_change == 0:
            return 0.0
        deviation = abs(_safe_divide(stock_change - market_change, market_change, 0.0))
        if deviation < 0.3:
            return 0.5   # 低湍流
        elif deviation > 0.7:
            return -0.5  # 高湍流
        return 0.0       # 中等湍流

    def amihud_illiquidity(self, ohlcv_data: Dict) -> float:
        """Amihud非流动性因子
        论文3启示: 流动性差时降低信号暴露
        |stock_change_pct| / (amount + epsilon)
        非流动性越高，逆向选择风险越大
        """
        stock_change = ohlcv_data.get("stock_change_pct", 0)
        amount = ohlcv_data.get("amount", 0)
        # amount单位为亿元，避免过小
        if amount <= 0:
            return -1.0  # 无成交额视为极度非流动性
        illiquidity = _safe_divide(abs(stock_change), amount, 0.0)
        if illiquidity > 0.5:
            return -1.0   # 高非流动性
        elif illiquidity > 0.2:
            return -0.5
        elif illiquidity < 0.1:
            return 0.5    # 流动性好
        return 0.0

    def realized_volatility_regime(self, ohlcv_data: Dict) -> float:
        """实现波动率体制因子
        来自FinRL-Meta VIX + 论文3波动率择时
        近5日收益率标准差 / 近20日收益率标准差
        """
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 20:
            return 0.0
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                returns.append(_safe_divide(closes[i] - closes[i - 1], closes[i - 1], 0.0))
        if len(returns) < 20:
            return 0.0
        std_5 = _rolling_std(returns, 5)
        std_20 = _rolling_std(returns, 20)
        if std_20 == 0:
            return 0.0
        ratio = _safe_divide(std_5, std_20, 1.0)
        if ratio > 1.5:
            return -0.5  # 高波动体制
        elif ratio < 0.8:
            return 0.5   # 低波动体制
        return 0.0       # 正常

    # ==========================================================================
    # 第22大类：因子质量诊断因子 (4) — 第五波因子
    # 来自论文3过拟合检测 + MCTS多维评估
    # ==========================================================================

    def factor_complexity_penalty(self, ohlcv_data: Dict) -> float:
        """因子复杂度惩罚因子
        论文3: 参数数远超样本数的模型不可信
        简化版: 用因子信号的一致性（近5日vs近20日）作为复杂度代理
        一致性高=简单稳健，一致性低=过度拟合
        """
        score_5d = ohlcv_data.get("factor_score_5d", 0)
        score_20d = ohlcv_data.get("factor_score_20d", 0)
        if score_5d == 0 and score_20d == 0:
            return 0.0
        # 方向一致且5d>20d：信号增强中，简单稳健
        if score_5d * score_20d > 0 and abs(score_5d) > abs(score_20d):
            return 0.5
        # 方向一致但5d<20d：信号减弱但方向一致
        elif score_5d * score_20d > 0:
            return 0.0
        # 方向相反：信号不稳定，可能过拟合
        else:
            return -0.5

    def signal_decay_detector(self, ohlcv_data: Dict) -> float:
        """信号衰减检测因子
        来自MCTS的Alpha Decay处理 + 论文3
        近5日因子得分变化率 / (近20日因子得分变化率 + epsilon)
        衰减过快说明因子可能失效
        """
        score_5d = ohlcv_data.get("factor_score_5d", 0)
        score_20d = ohlcv_data.get("factor_score_20d", 0)
        if score_20d == 0:
            return 0.0
        decay_ratio = _safe_divide(score_5d, score_20d, 0.0)
        if decay_ratio > 2.0:
            return -1.0   # 快速衰减
        elif decay_ratio < 0.5:
            return 0.5    # 信号增强
        return 0.0

    def cross_sectional_momentum_rank(self, ohlcv_data: Dict) -> float:
        """截面动量排名因子
        来自MCTS的GroupRank算子
        个股20日涨幅在行业中的相对排名
        """
        stock_return = ohlcv_data.get("stock_return_20d", 0)
        industry_return = ohlcv_data.get("industry_return_20d", 0)
        excess = stock_return - industry_return
        if excess > 0 and stock_return > 0.2:
            return 1.0
        elif excess > 0:
            return 0.5
        elif excess < 0:
            return -0.5
        return 0.0

    def high_low_asymmetry_signal(self, ohlcv_data: Dict) -> float:
        """高低价不对称信号因子
        MCTS挖掘: Log((high-close)/(close-low)+1) * Sign(5日价格变化)
        反映日内多空博弈结果
        """
        closes = ohlcv_data.get("closes", [])
        if len(closes) < 6:
            return 0.0
        # 用近期close近似日内high/low
        high = max(closes[-5:]) if len(closes) >= 5 else closes[-1]
        low = min(closes[-5:]) if len(closes) >= 5 else closes[-1]
        close = closes[-1]
        if close == 0 or close == low:
            return 0.0
        upper_shadow = _safe_divide(high - close, close - low, 0.0)
        if upper_shadow < 0:
            upper_shadow = 0.0
        asymmetry = math.log(upper_shadow + 1.0)
        # 5日价格变化方向
        price_change = _safe_divide(closes[-1] - closes[-6], closes[-6], 0.0) if len(closes) >= 6 else 0.0
        direction = 1.0 if price_change >= 0 else -1.0
        result = asymmetry * direction
        # 归一化到 [-1.0, 1.0]
        return max(-1.0, min(1.0, result))

    # ==========================================================================
    # 因子列表管理
    # ==========================================================================

    # ==========================================================================
    # Wave 6: 周级别趋势持续性因子 (8) — 第六波优化新增
    # ==========================================================================

    def weekly_momentum_convergence(self, data):
        """周动量收敛：5日动量与20日动量的收敛程度"""
        closes = data.get("closes", [])
        if len(closes) < 21: return 0.0
        mom_5 = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] != 0 else 0
        mom_20 = (closes[-1] - closes[-21]) / closes[-21] if closes[-21] != 0 else 0
        convergence = 1.0 - abs(mom_5 - mom_20) / (abs(mom_20) + 0.001)
        direction = 1.0 if (mom_5 > 0 and mom_20 > 0) or (mom_5 < 0 and mom_20 < 0) else -0.5
        return max(-1.0, min(1.0, convergence * direction))

    def weekly_volume_trend_consistency(self, data):
        """周量能趋势一致性：价格上涨时成交量是否持续放大"""
        closes = data.get("closes", []); volumes = data.get("volumes", [])
        if len(closes) < 10 or len(volumes) < 10: return 0.0
        price_up = sum(1 for i in range(1, min(5, len(closes))) if closes[-i] > closes[-i-1])
        vol_inc = sum(1 for i in range(1, min(5, len(volumes))) if volumes[-i] > volumes[-i-1])
        r = vol_inc / 4.0 if price_up >= 3 else -vol_inc / 4.0
        return max(-1.0, min(1.0, r))

    def weekly_price_channel_position(self, data):
        """周价格通道位置：当前价在5日高低通道中的位置"""
        closes = data.get("closes", [])
        if len(closes) < 5: return 0.0
        h5 = max(closes[-5:]); l5 = min(closes[-5:])
        if h5 == l5: return 0.0
        return max(-1.0, min(1.0, (closes[-1] - l5) / (h5 - l5) * 2 - 1))

    def weekly_institutional_accumulation(self, data):
        """周机构累积信号：主力连续净流入天数"""
        s = 0.0
        mi = data.get("main_net_inflow", 0)
        ic = data.get("inst_position_change_pct", 0)
        ib = data.get("institution_net_buy", 0)
        if mi > 0: s += min(mi / 10.0, 0.5)
        if ic > 0: s += min(ic / 5.0, 0.3)
        if ib > 0: s += min(ib / 5000.0, 0.2)
        return max(-1.0, min(1.0, s))

    def weekly_sector_momentum_transfer(self, data):
        """周行业动量传递：个股动量是否与行业动量一致"""
        sc = data.get("stock_change_pct", 0); ic = data.get("industry_change_pct", 0)
        mc = data.get("market_change_pct", 0)
        alpha = sc - ic; ia = ic - mc
        if alpha > 0 and ia > 0: return min(0.5 + alpha / 10.0, 1.0)
        elif alpha < 0 and ia < 0: return max(-0.5 + alpha / 10.0, -1.0)
        return max(-1.0, min(1.0, alpha / 10.0))

    def weekly_mean_reversion_signal(self, data):
        """周均值回归信号：短期偏离均值的程度"""
        closes = data.get("closes", [])
        if len(closes) < 20: return 0.0
        ma20 = sum(closes[-20:]) / 20
        if ma20 == 0: return 0.0
        d = (closes[-1] - ma20) / ma20
        if abs(d) > 0.05: return max(-1.0, min(1.0, -d * 5))
        return 0.0

    def weekly_breakout_continuation(self, data):
        """周突破持续性：突破后是否持续（量价齐升）"""
        closes = data.get("closes", []); volumes = data.get("volumes", [])
        if len(closes) < 6 or len(volumes) < 5: return 0.0
        cur = closes[-1]; ph = max(closes[-6:-1]); av = sum(volumes[-5:]) / 5
        if cur > ph and volumes[-1] > av * 1.2:
            return min(1.0, 0.5 + (cur / ph - 1) * 10)
        pl = min(closes[-6:-1])
        if cur < pl and volumes[-1] > av * 1.2:
            return max(-1.0, -0.5 - (pl / cur - 1) * 10)
        return 0.0

    def weekly_risk_adjusted_momentum(self, data):
        """周风险调整动量：夏普比率风格的周动量"""
        closes = data.get("closes", [])
        if len(closes) < 10: return 0.0
        ret = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, min(10, len(closes)))]
        if not ret: return 0.0
        mr = sum(ret) / len(ret)
        va = sum((r - mr) ** 2 for r in ret) / len(ret)
        sd = math.sqrt(va) if va > 0 else 0.001
        return max(-1.0, min(1.0, mr / sd * 2))

    # ==========================================================================
    # 因子列表管理
    # ==========================================================================

    def get_all_factor_names(self) -> List[str]:
        """获取所有因子名称列表（共96个因子）"""
        return [
            # 量价因子 (13)
            "ma5_deviation", "ma10_deviation", "ma20_deviation", "ma60_deviation",
            "macd_dif", "macd_dea", "macd_histogram",
            "rsi14", "kdj_k", "kdj_d", "kdj_j",
            "bollinger_position", "volume_ratio",
            # 基本面因子 (7)
            "pe_factor", "pb_factor", "ps_factor",
            "roe_factor", "revenue_growth_factor", "gross_margin_factor", "debt_ratio_factor",
            # 资金因子 (3)
            "main_net_inflow_ratio", "north_net_buy", "turnover_rate_anomaly",
            # 情绪因子 (3)
            "limit_ratio", "margin_balance_change", "search_heat",
            # 技术形态因子 (3)
            "breakout_signal", "trend_strength", "volatility_change",
            # 背离与预警因子 (4)
            "sector_stock_divergence", "main_capital_flow_warning",
            "turnover_divergence_warning", "limit_up_pressure",
            # 筹码分布因子 (2)
            "chip_concentration", "holder_count_change",
            # 事件驱动因子 (4)
            "earnings_surprise", "institutional_position_change",
            "major_contract_event", "insider_trading_signal",
            # 宏观因子 (4)
            "liquidity_environment", "policy_tailwind",
            "external_market_impact", "industry_rotation_strength",
            # 机构行为因子 (4)
            "institutional_dark_pool", "order_imbalance",
            "vwap_deviation", "large_order_density",
            # 舆情NLP因子 (3)
            "news_sentiment", "social_heat_anomaly", "analyst_consensus_breakout",
            # 分域适配因子 (3)
            "market_regime_detector", "factor_momentum", "cross_section_momentum",
            # 微观结构因子 (3)
            "bid_ask_spread_pressure", "limit_order_book_depth", "tick_frequency_anomaly",
            # 杠杆资金因子 (4)
            "margin_financing_intensity", "margin_concentration_risk",
            "short_squeeze_potential", "leveraged_fund_flow_divergence",
            # 龙虎榜聪明钱因子 (4)
            "dragon_tiger_institutional_net", "dragon_tiger_hot_money_trace",
            "dragon_tiger_buy_sell_ratio", "dragon_tiger_new_face_signal",
            # 集合竞价与尾盘因子 (4)
            "call_auction_premium", "call_auction_volume_ratio",
            "tail_momentum_acceleration", "tail_volume_concentration",
            # 专利与创新因子 (4)
            "patent_value_density", "rd_intensity_momentum",
            "innovation_breakthrough_signal", "patent_citation_impact",
            # 微观结构深度因子 (4)
            "order_flow_imbalance_enhanced", "vwap_asymmetric_deviation",
            "microprice_deviation", "spread_attenuated_signal",
            # MCTS公式因子 (4)
            "volume_price_divergence_trend", "volatility_adjusted_momentum",
            "multi_scale_price_position", "volume_acceleration",
            # 波动率择时因子 (4)
            "volatility_timed_momentum", "turbulence_regime_signal",
            "amihud_illiquidity", "realized_volatility_regime",
            # 因子质量诊断因子 (4)
            "factor_complexity_penalty", "signal_decay_detector",
            "cross_sectional_momentum_rank", "high_low_asymmetry_signal",
            # 周级别趋势持续性因子 (8) — Wave 6
            "weekly_momentum_convergence", "weekly_volume_trend_consistency",
            "weekly_price_channel_position", "weekly_institutional_accumulation",
            "weekly_sector_momentum_transfer", "weekly_mean_reversion_signal",
            "weekly_breakout_continuation", "weekly_risk_adjusted_momentum",
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
# FactorScorer — 因子评分器
# ==============================================================================

class FactorScorer:
    """
    因子评分器：负责因子标准化、加权合成与综合评分。

    功能：
    - 对单只股票计算全部因子
    - 因子标准化（Z-Score）：基于多只股票的因子分布进行标准化
    - 因子加权合成：默认权重可配置
    - 输出综合评分和各因子贡献度
    """

    # V6.2 混合评分权重：核心29因子 + 增强67因子 = 96因子全覆盖
    DEFAULT_WEIGHTS: Dict[str, float] = {
        # ═══ Wave 1 核心：量价因子 (13) — 日级别核心 ═══
        "ma5_deviation": 0.030, "ma10_deviation": 0.030,
        "ma20_deviation": 0.040, "ma60_deviation": 0.040,
        "macd_dif": 0.030, "macd_dea": 0.020, "macd_histogram": 0.030,
        "rsi14": 0.020, "kdj_k": 0.020, "kdj_d": 0.010, "kdj_j": 0.010,
        "bollinger_position": 0.010, "volume_ratio": 0.010,
        # ═══ Wave 1 核心：基本面因子 (7) ═══
        "pe_factor": 0.050, "pb_factor": 0.050, "ps_factor": 0.030,
        "roe_factor": 0.040, "revenue_growth_factor": 0.040,
        "gross_margin_factor": 0.020, "debt_ratio_factor": 0.020,
        # ═══ Wave 1 核心：资金因子 (3) ═══
        "main_net_inflow_ratio": 0.080, "north_net_buy": 0.070, "turnover_rate_anomaly": 0.050,
        # ═══ Wave 1 核心：情绪因子 (3) ═══
        "limit_ratio": 0.050, "margin_balance_change": 0.050, "search_heat": 0.050,
        # ═══ Wave 1 核心：技术形态因子 (3) ═══
        "breakout_signal": 0.040, "trend_strength": 0.030, "volatility_change": 0.030,
        # ═══ Wave 2 增强：背离与预警 (4) ═══
        "sector_stock_divergence": 0.015, "main_capital_flow_warning": 0.015,
        "turnover_divergence_warning": 0.012, "limit_up_pressure": 0.010,
        # ═══ Wave 2 增强：筹码分布 (2) ═══
        "chip_concentration": 0.012, "holder_count_change": 0.010,
        # ═══ Wave 2 增强：事件驱动 (4) ═══
        "earnings_surprise": 0.015, "institutional_position_change": 0.012,
        "major_contract_event": 0.010, "insider_trading_signal": 0.008,
        # ═══ Wave 2 增强：宏观 (4) ═══
        "liquidity_environment": 0.010, "policy_tailwind": 0.010,
        "external_market_impact": 0.008, "industry_rotation_strength": 0.006,
        # ═══ Wave 3 增强：机构暗盘 (4) ═══
        "institutional_dark_pool": 0.015, "order_imbalance": 0.015,
        "vwap_deviation": 0.012, "large_order_density": 0.012,
        # ═══ Wave 3 增强：舆情NLP (3) ═══
        "news_sentiment": 0.012, "social_heat_anomaly": 0.010, "analyst_consensus_breakout": 0.008,
        # ═══ Wave 3 增强：分域适配 (3) ═══
        "market_regime_detector": 0.012, "factor_momentum": 0.010, "cross_section_momentum": 0.010,
        # ═══ Wave 3 增强：微观结构 (3) ═══
        "bid_ask_spread_pressure": 0.012, "limit_order_book_depth": 0.010, "tick_frequency_anomaly": 0.008,
        # ═══ Wave 4 增强：杠杆资金 (4) ═══
        "margin_financing_intensity": 0.012, "margin_concentration_risk": 0.010,
        "short_squeeze_potential": 0.012, "leveraged_fund_flow_divergence": 0.008,
        # ═══ Wave 4 增强：龙虎榜 (4) ═══
        "dragon_tiger_institutional_net": 0.015, "dragon_tiger_hot_money_trace": 0.015,
        "dragon_tiger_buy_sell_ratio": 0.012, "dragon_tiger_new_face_signal": 0.010,
        # ═══ Wave 4 增强：竞价尾盘 (4) ═══
        "call_auction_premium": 0.012, "call_auction_volume_ratio": 0.010,
        "tail_momentum_acceleration": 0.012, "tail_volume_concentration": 0.010,
        # ═══ Wave 4 增强：专利创新 (4) ═══
        "patent_value_density": 0.010, "rd_intensity_momentum": 0.008,
        "innovation_breakthrough_signal": 0.008, "patent_citation_impact": 0.006,
        # ═══ Wave 5 增强：微观深度 (4) — S级 ═══
        "order_flow_imbalance_enhanced": 0.025, "vwap_asymmetric_deviation": 0.020,
        "microprice_deviation": 0.018, "spread_attenuated_signal": 0.020,
        # ═══ Wave 5 增强：MCTS公式 (4) — A级 ═══
        "volume_price_divergence_trend": 0.020, "volatility_adjusted_momentum": 0.018,
        "multi_scale_price_position": 0.015, "volume_acceleration": 0.020,
        # ═══ Wave 5 增强：波动率择时 (4) ═══
        "volatility_timed_momentum": 0.015, "turbulence_regime_signal": 0.012,
        "amihud_illiquidity": 0.012, "realized_volatility_regime": 0.012,
        # ═══ Wave 5 增强：因子诊断 (4) ═══
        "factor_complexity_penalty": 0.012, "signal_decay_detector": 0.010,
        "cross_sectional_momentum_rank": 0.010, "high_low_asymmetry_signal": 0.008,
        # ═══ Wave 6：周级别趋势 (8) ═══
        "weekly_momentum_convergence": 0.020, "weekly_volume_trend_consistency": 0.018,
        "weekly_price_channel_position": 0.020, "weekly_institutional_accumulation": 0.018,
        "weekly_sector_momentum_transfer": 0.015, "weekly_mean_reversion_signal": 0.018,
        "weekly_breakout_continuation": 0.020, "weekly_risk_adjusted_momentum": 0.018,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化因子评分器

        Args:
            weights: 自定义因子权重字典，键为因子名，值为权重。
                     如不指定则使用默认权重。
        """
        self.factor_lib = FactorLibrary()
        self.weights = weights if weights is not None else dict(self.DEFAULT_WEIGHTS)

    def _z_score(self, value: float, mean: float, std: float) -> float:
        """
        计算Z-Score标准化值
        Z-Score = (x - mean) / std
        """
        if std == 0:
            return 0.0
        return (value - mean) / std

    def standardize_factors(
        self,
        all_stocks_factors: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """
        V6.2 截尾Z-Score标准化：将极端值截断到±3σ，防止小样本放大效应
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
        V6.2 混合评分：核心因子加权 + 增强因子方向一致性奖励
        """
        w = weights if weights is not None else self.weights
        total_score = 0.0
        contributions = {}

        # 核心因子集合（Wave 1的29个因子）
        CORE_FACTORS = {
            "ma5_deviation", "ma10_deviation", "ma20_deviation", "ma60_deviation",
            "macd_dif", "macd_dea", "macd_histogram", "rsi14", "kdj_k", "kdj_d",
            "kdj_j", "bollinger_position", "volume_ratio", "pe_factor", "pb_factor",
            "ps_factor", "roe_factor", "revenue_growth_factor", "gross_margin_factor",
            "debt_ratio_factor", "main_net_inflow_ratio", "north_net_buy",
            "turnover_rate_anomaly", "limit_ratio", "margin_balance_change",
            "search_heat", "breakout_signal", "trend_strength", "volatility_change",
        }

        enhance_score = 0.0
        for factor_name, z_value in standardized_factors.items():
            weight = w.get(factor_name, 0.0)
            contribution = z_value * weight
            contributions[factor_name] = contribution
            total_score += contribution
            if factor_name not in CORE_FACTORS:
                enhance_score += contribution

        # 方向一致性奖励：增强因子方向一致时给予小幅加成
        enhance_factors = {k: v for k, v in standardized_factors.items() if k not in CORE_FACTORS}
        if enhance_factors:
            pos_count = sum(1 for v in enhance_factors.values() if v > 0)
            neg_count = sum(1 for v in enhance_factors.values() if v < 0)
            total_ef = len(enhance_factors)
            if total_ef > 0:
                direction_agreement = abs(pos_count - neg_count) / total_ef
                if direction_agreement > 0.6:
                    bonus = 0.05 * (direction_agreement - 0.6) / 0.4
                    total_score += bonus * (1 if enhance_score > 0 else -1 if enhance_score < 0 else 0)

        return total_score, contributions

    def score_single_stock(
        self,
        stock_code: str,
        ohlcv_data: Dict,
        all_stocks_factors: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict:
        """
        对单只股票进行完整评分流程

        Args:
            stock_code: 股票代码
            ohlcv_data: 该股票的OHLCV数据
            all_stocks_factors: 所有股票的原始因子数据（用于标准化）

        Returns:
            包含综合评分、因子贡献度等信息的字典
        """
        # 计算该股票的所有因子
        raw_factors = self.factor_lib.compute_all_factors(ohlcv_data)

        # 如果提供了全市场因子数据，进行标准化
        if all_stocks_factors is not None:
            std_factors = self.standardize_factors(all_stocks_factors)
            stock_std = std_factors.get(stock_code, raw_factors)
        else:
            # 无对比数据时，直接使用原始值
            stock_std = raw_factors

        # 计算综合评分
        score, contributions = self.compute_score(stock_std)

        return {
            "stock_code": stock_code,
            "total_score": round(score, 4),
            "raw_factors": raw_factors,
            "standardized_factors": stock_std,
            "contributions": {k: round(v, 6) for k, v in contributions.items()},
        }


# ==============================================================================
# MultiFactorSelector — 多因子选股器
# ==============================================================================

class MultiFactorSelector:
    """
    多因子选股器：批量处理多只股票的因子数据，按综合评分排序，输出TOP N推荐。

    使用流程：
    1. 输入多只股票的OHLCV数据
    2. 自动计算所有因子
    3. 标准化处理
    4. 加权评分
    5. 排序输出TOP N
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化多因子选股器

        Args:
            weights: 自定义因子权重
        """
        self.scorer = FactorScorer(weights=weights)
        self.factor_lib = FactorLibrary()

    def select(
        self,
        stocks_data: Dict[str, Dict],
        top_n: int = 10
    ) -> List[Dict]:
        """
        执行多因子选股

        Args:
            stocks_data: {股票代码: ohlcv_data} 多只股票的数据
            top_n: 返回排名前N的股票

        Returns:
            按综合评分降序排列的推荐列表
        """
        if not stocks_data:
            return []

        # 第一步：计算所有股票的原始因子
        all_raw_factors = {}
        for code, data in stocks_data.items():
            all_raw_factors[code] = self.factor_lib.compute_all_factors(data)

        # 第二步：标准化因子
        standardized = self.scorer.standardize_factors(all_raw_factors)

        # 第三步：计算每只股票的综合评分
        results = []
        for code in stocks_data:
            score, contributions = self.scorer.compute_score(standardized[code])
            results.append({
                "stock_code": code,
                "total_score": round(score, 4),
                "contributions": {k: round(v, 6) for k, v in contributions.items()},
                "raw_factors": all_raw_factors[code],
            })

        # 第四步：按综合评分降序排序
        results.sort(key=lambda x: x["total_score"], reverse=True)

        # 第五步：返回TOP N
        return results[:top_n]

    def print_ranking(self, results: List[Dict], top_n: int = 5) -> None:
        """
        打印选股排名结果

        Args:
            results: select() 方法返回的结果列表
            top_n: 打印前N名的详细信息
        """
        print("=" * 70)
        print("  A股多因子选股模型 — 排名结果")
        print("=" * 70)
        print(f"{'排名':<6}{'股票代码':<12}{'综合评分':<12}{'评级'}")
        print("-" * 70)

        for i, item in enumerate(results[:top_n]):
            rank = i + 1
            score = item["total_score"]
            # 简单评级
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

        # 打印TOP1的因子贡献度
        if results:
            best = results[0]
            print(f"\n  TOP 1 [{best['stock_code']}] 因子贡献度分析：")
            print(f"  {'因子名称':<28}{'贡献值':<12}{'占比'}")
            print("  " + "-" * 55)

            # 按贡献度绝对值排序
            sorted_contrib = sorted(
                best["contributions"].items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )
            total_abs = sum(abs(v) for v in best["contributions"].values())
            for fname, contrib in sorted_contrib[:10]:
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
    """
    生成模拟OHLCV数据

    Args:
        days: 生成天数
        base_price: 基础价格
        volatility: 日波动率
        trend: 日趋势偏移
        seed: 随机种子

    Returns:
        符合 FactorLibrary 要求的 ohlcv_data 字典
    """
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
        # 生成日内波动
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

    # 生成基本面数据（随机但合理）
    pe = round(random.uniform(5, 80), 2)
    pb = round(random.uniform(0.5, 10), 2)
    ps = round(random.uniform(0.5, 15), 2)
    roe = round(random.uniform(5, 35), 2)
    revenue_growth = round(random.uniform(-10, 50), 2)
    gross_margin = round(random.uniform(15, 65), 2)
    debt_ratio = round(random.uniform(20, 70), 2)
    main_net_inflow = round(random.uniform(-5, 5), 2)
    north_net_buy = round(random.uniform(-5000, 5000), 2)
    turnover_rate = round(random.uniform(0.5, 8), 2)
    limit_up_count = random.randint(5, 50)
    limit_down_count = random.randint(2, 30)
    margin_balance_change = round(random.uniform(-3, 3), 2)
    search_heat = round(random.uniform(10, 90), 1)

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "amount": amounts,
        "pe": pe,
        "pb": pb,
        "ps": ps,
        "roe": roe,
        "revenue_growth": revenue_growth,
        "gross_margin": gross_margin,
        "debt_ratio": debt_ratio,
        "main_net_inflow": main_net_inflow,
        "north_net_buy": north_net_buy,
        "turnover_rate": turnover_rate,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "margin_balance_change": margin_balance_change,
        "search_heat": search_heat,
    }


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    print("A股多因子选股模型 — 完整演示")
    print("=" * 70)

    # 模拟5只股票的60天OHLCV数据
    stock_names = {
        "SH600000": {"base": 12.0, "vol": 0.02, "trend": 0.002, "seed": 42},
        "SZ000001": {"base": 15.0, "vol": 0.03, "trend": -0.001, "seed": 123},
        "SH600519": {"base": 1800.0, "vol": 0.015, "trend": 0.001, "seed": 456},
        "SZ300750": {"base": 200.0, "vol": 0.04, "trend": 0.003, "seed": 789},
        "SH601318": {"base": 50.0, "vol": 0.025, "trend": 0.0005, "seed": 101},
    }

    stocks_data = {}
    for code, params in stock_names.items():
        print(f"  生成 {code} 模拟数据（基础价格={params['base']}，"
              f"波动率={params['vol']}，趋势={params['trend']}）...")
        stocks_data[code] = generate_mock_ohlcv(
            days=60,
            base_price=params["base"],
            volatility=params["vol"],
            trend=params["trend"],
            seed=params["seed"],
        )

    print(f"\n  共生成 {len(stocks_data)} 只股票的模拟数据\n")

    # 创建多因子选股器
    selector = MultiFactorSelector()

    # 执行选股
    results = selector.select(stocks_data, top_n=5)

    # 打印排名
    selector.print_ranking(results, top_n=5)

    # 打印所有股票的原始因子概览
    print("\n各股票关键因子概览：")
    print("-" * 70)
    key_factors = [
        "ma20_deviation", "macd_histogram", "rsi14", "kdj_k",
        "bollinger_position", "volume_ratio",
        "pe_factor", "roe_factor", "revenue_growth_factor",
        "main_net_inflow_ratio", "trend_strength",
    ]
    header = f"{'股票代码':<12}" + "".join(f"{f:<16}" for f in key_factors[:6])
    print(header)
    print("-" * 70)
    for item in results:
        code = item["stock_code"]
        vals = item["raw_factors"]
        row = f"{code:<12}"
        for f in key_factors[:6]:
            row += f"{vals[f]:<16.4f}"
        print(row)
    print("-" * 70)

    header2 = f"{'股票代码':<12}" + "".join(f"{f:<16}" for f in key_factors[6:])
    print(header2)
    print("-" * 70)
    for item in results:
        code = item["stock_code"]
        vals = item["raw_factors"]
        row = f"{code:<12}"
        for f in key_factors[6:]:
            row += f"{vals[f]:<16.4f}"
        print(row)
    print("-" * 70)

    print("\n演示完成。")
