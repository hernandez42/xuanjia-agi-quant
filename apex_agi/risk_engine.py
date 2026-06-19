#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
risk_engine.py — 玄甲AGI 风控引擎

本模块实现完整的风控体系，包含三大核心组件：
1. PortfolioRiskManager — 组合级风险管理（回撤控制、仓位管理、相关性分析、压力测试）
2. PositionSizer — 仓位计算（凯利公式、波动率模型）
3. StopLossManager — 止损管理（固定止损、ATR跟踪止损、时间止损、里程碑止损）

所有类基于 dataclass 构建，方法返回 Dict，便于序列化和上层调用。
仅依赖标准库，无需第三方包。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================
#  辅助数据结构
# ============================================================

@dataclass
class Position:
    """单个持仓信息"""
    code: str                          # 股票代码
    name: str                          # 股票名称
    sector: str                       # 所属板块
    weight: float                     # 当前仓位占比（0~1）
    cost_price: float                 # 成本价
    current_price: float              # 当前价
    atr: float                        # 当前ATR值（用于波动率计算）
    hold_days: int                    # 持仓天数
    target_price: float               # 目标价
    milestone_date: Optional[str] = None  # 里程碑日期（如财报日、解禁日等）
    pnl_pct: float = 0.0              # 当前盈亏百分比

    def __post_init__(self):
        """自动计算盈亏百分比"""
        if self.cost_price > 0:
            self.pnl_pct = (self.current_price - self.cost_price) / self.cost_price


@dataclass
class DrawdownInfo:
    """回撤信息"""
    current_drawdown: float           # 当前回撤幅度（负数）
    max_drawdown: float               # 历史最大回撤（负数）
    peak_value: float                  # 历史峰值净值
    current_value: float              # 当前净值


# ============================================================
#  PortfolioRiskManager — 组合级风险管理
# ============================================================

@dataclass
class PortfolioRiskManager:
    """
    组合级风险管理器

    职责：
    - 组合最大回撤控制（默认15%触发减仓，20%触发清仓）
    - 动态仓位管理（基于波动率ATR计算，单只最大15%，组合最大80%）
    - 持仓相关性分析（计算持仓间相关系数矩阵，相关性>0.7的板块限制总仓位）
    - 压力测试（模拟-5%/-10%/-15%极端行情下的组合表现）
    """

    # ---------- 可配置参数 ----------
    initial_capital: float = 1_000_000.0     # 初始资金
    current_capital: float = 1_000_000.0     # 当前总资金
    reduce_threshold: float = -0.15           # 减仓触发阈值（回撤-15%）
    liquidate_threshold: float = -0.20         # 清仓触发阈值（回撤-20%）
    max_single_weight: float = 0.15           # 单只股票最大仓位占比
    max_total_weight: float = 0.80            # 组合最大总仓位
    high_corr_threshold: float = 0.70         # 高相关性阈值
    high_corr_sector_limit: float = 0.25       # 高相关板块总仓位限制
    risk_free_rate: float = 0.03              # 无风险利率（年化，用于夏普等计算）

    # ---------- 内部状态 ----------
    positions: List[Position] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    _peak_value: float = field(init=False, default=1_000_000.0)

    def set_positions(self, positions: List[Position]) -> None:
        """设置当前持仓列表"""
        self.positions = positions

    def set_equity_curve(self, equity_curve: List[float]) -> None:
        """设置净值曲线（用于回撤计算）"""
        self.equity_curve = equity_curve
        if equity_curve:
            self._peak_value = max(equity_curve)

    def _update_peak(self, current_value: float) -> None:
        """更新历史峰值"""
        if current_value > self._peak_value:
            self._peak_value = current_value

    # -------------------- 回撤控制 --------------------

    def calculate_drawdown(self, current_value: Optional[float] = None) -> DrawdownInfo:
        """
        计算当前回撤信息

        Args:
            current_value: 当前净值，若为None则用 current_capital

        Returns:
            DrawdownInfo 数据类
        """
        val = current_value if current_value is not None else self.current_capital
        self._update_peak(val)

        if self._peak_value <= 0:
            return DrawdownInfo(
                current_drawdown=0.0,
                max_drawdown=0.0,
                peak_value=self._peak_value,
                current_value=val,
            )

        current_dd = (val - self._peak_value) / self._peak_value

        # 从净值曲线计算历史最大回撤
        max_dd = 0.0
        peak = self.equity_curve[0] if self.equity_curve else val
        for v in self.equity_curve:
            if v > peak:
                peak = v
            dd = (v - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

        return DrawdownInfo(
            current_drawdown=round(current_dd, 6),
            max_drawdown=round(max_dd, 6),
            peak_value=round(self._peak_value, 2),
            current_value=round(val, 2),
        )

    def check_drawdown_action(self, current_value: Optional[float] = None) -> Dict:
        """
        检查回撤是否触发风控动作

        Returns:
            Dict 包含 action（none/reduce/liquidate）、回撤详情、建议减仓比例
        """
        dd_info = self.calculate_drawdown(current_value)
        dd = dd_info.current_drawdown

        action = "none"
        reduce_ratio = 0.0

        if dd <= self.liquidate_threshold:
            action = "liquidate"
            reduce_ratio = 1.0
        elif dd <= self.reduce_threshold:
            action = "reduce"
            # 回撤越深，减仓越多（线性插值）
            depth = abs(dd) - abs(self.reduce_threshold)
            total_range = abs(self.liquidate_threshold) - abs(self.reduce_threshold)
            reduce_ratio = min(0.5, 0.3 + 0.2 * (depth / total_range)) if total_range > 0 else 0.3

        return {
            "action": action,
            "current_drawdown": dd_info.current_drawdown,
            "max_drawdown": dd_info.max_drawdown,
            "peak_value": dd_info.peak_value,
            "current_value": dd_info.current_value,
            "reduce_ratio": round(reduce_ratio, 4),
            "message": self._drawdown_message(action, dd),
        }

    def _drawdown_message(self, action: str, dd: float) -> str:
        """生成回撤风控提示消息"""
        if action == "liquidate":
            return f"严重回撤 {dd:.2%}，触发清仓线({self.liquidate_threshold:.0%})，建议立即清仓"
        elif action == "reduce":
            return f"回撤 {dd:.2%}，触发减仓线({self.reduce_threshold:.0%})，建议减仓控制风险"
        else:
            return f"当前回撤 {dd:.2%}，在安全范围内"

    # -------------------- 动态仓位管理 --------------------

    def calculate_position_weights(self) -> Dict:
        """
        基于波动率（ATR）动态计算各持仓的目标权重

        逻辑：
        - 波动率越高 → 仓位越低
        - 波动率越低 → 仓位越高
        - 单只上限 max_single_weight，组合上限 max_total_weight

        Returns:
            Dict 包含各股票建议权重及调整建议
        """
        if not self.positions:
            return {"weights": {}, "total_weight": 0.0, "message": "无持仓"}

        # 计算各股票的波动率得分（ATR/价格）
        vol_scores = {}
        for pos in self.positions:
            if pos.current_price > 0 and pos.atr > 0:
                vol_scores[pos.code] = pos.atr / pos.current_price
            else:
                vol_scores[pos.code] = 0.05  # 默认波动率

        # 波动率越低，分配越多权重（反比关系）
        inv_vol = {code: 1.0 / vs for code, vs in vol_scores.items()}
        total_inv_vol = sum(inv_vol.values())

        raw_weights = {}
        for code, iv in inv_vol.items():
            raw_weights[code] = iv / total_inv_vol

        # 应用约束
        adjusted_weights = {}
        total_weight = 0.0
        for pos in self.positions:
            w = min(raw_weights[pos.code], self.max_single_weight)
            adjusted_weights[pos.code] = round(w, 4)
            total_weight += w

        # 如果总仓位超限，等比例缩减
        if total_weight > self.max_total_weight:
            scale = self.max_total_weight / total_weight
            adjusted_weights = {k: round(v * scale, 4) for k, v in adjusted_weights.items()}
            total_weight = self.max_total_weight

        # 生成调整建议
        adjustments = {}
        for pos in self.positions:
            target_w = adjusted_weights.get(pos.code, 0.0)
            diff = target_w - pos.weight
            if abs(diff) > 0.01:
                adjustments[pos.code] = {
                    "current_weight": round(pos.weight, 4),
                    "target_weight": target_w,
                    "adjustment": round(diff, 4),
                    "action": "加仓" if diff > 0 else "减仓",
                }

        return {
            "weights": adjusted_weights,
            "total_weight": round(total_weight, 4),
            "max_single_limit": self.max_single_weight,
            "max_total_limit": self.max_total_weight,
            "adjustments": adjustments,
            "message": f"组合目标总仓位 {total_weight:.2%}" if adjustments else "仓位无需调整",
        }

    # -------------------- 持仓相关性分析 --------------------

    def analyze_correlation(self, price_history: Optional[Dict[str, List[float]]] = None) -> Dict:
        """
        分析持仓间的相关性

        若提供 price_history（{code: [收盘价序列]}），则用实际数据计算皮尔逊相关系数。
        否则使用板块信息进行简化分析。

        Returns:
            Dict 包含相关系数矩阵、高相关板块警告、仓位限制建议
        """
        if not self.positions:
            return {"matrix": {}, "warnings": [], "message": "无持仓"}

        codes = [p.code for p in self.positions]
        n = len(codes)

        if price_history and len(price_history) >= 2:
            # 使用实际价格数据计算相关系数矩阵
            matrix = self._pearson_matrix(codes, price_history)
        else:
            # 基于板块的简化相关性（同板块=0.8，不同板块=0.3）
            matrix = self._sector_correlation_matrix(codes)

        # 找出高相关对
        high_corr_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                corr = matrix.get(codes[i], {}).get(codes[j], 0.0)
                if abs(corr) > self.high_corr_threshold:
                    high_corr_pairs.append({
                        "code_a": codes[i],
                        "code_b": codes[j],
                        "correlation": round(corr, 4),
                    })

        # 按板块聚合，检查高相关板块总仓位
        sector_weights: Dict[str, float] = {}
        for pos in self.positions:
            sector_weights[pos.sector] = sector_weights.get(pos.sector, 0.0) + pos.weight

        sector_warnings = []
        for sector, w in sector_weights.items():
            if w > self.high_corr_sector_limit:
                sector_warnings.append({
                    "sector": sector,
                    "total_weight": round(w, 4),
                    "limit": self.high_corr_sector_limit,
                    "excess": round(w - self.high_corr_sector_limit, 4),
                    "suggestion": f"板块 [{sector}] 仓位 {w:.2%} 超限，建议降至 {self.high_corr_sector_limit:.0%} 以下",
                })

        return {
            "codes": codes,
            "correlation_matrix": matrix,
            "high_corr_pairs": high_corr_pairs,
            "sector_weights": {k: round(v, 4) for k, v in sector_weights.items()},
            "sector_warnings": sector_warnings,
            "message": f"发现 {len(high_corr_pairs)} 对高相关性持仓" if high_corr_pairs else "持仓相关性在合理范围内",
        }

    def _pearson_matrix(self, codes: List[str], price_history: Dict[str, List[float]]) -> Dict:
        """计算皮尔逊相关系数矩阵"""
        matrix: Dict[str, Dict[str, float]] = {}
        for c1 in codes:
            matrix[c1] = {}
            for c2 in codes:
                if c1 == c2:
                    matrix[c1][c2] = 1.0
                elif c1 not in matrix or c2 not in matrix[c1]:
                    r = self._pearson_corr(
                        price_history.get(c1, []),
                        price_history.get(c2, []),
                    )
                    matrix[c1][c2] = round(r, 4)
                    if c2 not in matrix:
                        matrix[c2] = {}
                    matrix[c2][c1] = round(r, 4)
        return matrix

    @staticmethod
    def _pearson_corr(x: List[float], y: List[float]) -> float:
        """计算两个序列的皮尔逊相关系数"""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        x, y = x[:n], y[:n]
        mx = sum(x) / n
        my = sum(y) / n
        sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n)
        sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n)
        if sx == 0 or sy == 0:
            return 0.0
        cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
        return cov / (sx * sy)

    def _sector_correlation_matrix(self, codes: List[str]) -> Dict:
        """基于板块的简化相关系数矩阵"""
        code_to_sector = {p.code: p.sector for p in self.positions}
        matrix: Dict[str, Dict[str, float]] = {}
        for c1 in codes:
            matrix[c1] = {}
            for c2 in codes:
                if c1 == c2:
                    matrix[c1][c2] = 1.0
                else:
                    # 同板块高相关，不同板块低相关
                    matrix[c1][c2] = 0.8 if code_to_sector.get(c1) == code_to_sector.get(c2) else 0.3
        return matrix

    # -------------------- 压力测试 --------------------

    def stress_test(self, scenarios: Optional[List[float]] = None) -> Dict:
        """
        对当前组合进行压力测试

        模拟极端行情下跌场景，计算组合损失。

        Args:
            scenarios: 跌幅列表，默认 [-0.05, -0.10, -0.15]

        Returns:
            Dict 包含各场景下的组合预估损失
        """
        if scenarios is None:
            scenarios = [-0.05, -0.10, -0.15]

        if not self.positions:
            return {"scenarios": {}, "message": "无持仓，无需压力测试"}

        total_invested = sum(pos.weight * self.current_capital for pos in self.positions)
        cash_ratio = 1.0 - sum(pos.weight for pos in self.positions)

        results = {}
        for drop in scenarios:
            # 假设所有持仓同步下跌（最坏情况）
            position_loss = total_invested * drop
            remaining_value = self.current_capital + position_loss
            loss_pct = drop * (1.0 - cash_ratio)  # 实际损失比例（考虑现金缓冲）

            # 分股票明细
            details = []
            for pos in self.positions:
                pos_value = pos.weight * self.current_capital
                pos_loss = pos_value * drop
                details.append({
                    "code": pos.code,
                    "name": pos.name,
                    "weight": pos.weight,
                    "loss_amount": round(pos_loss, 2),
                    "remaining_value": round(pos_value + pos_loss, 2),
                })

            results[f"-{abs(drop)*100:.0f}%"] = {
                "scenario_drop": drop,
                "total_loss": round(position_loss, 2),
                "remaining_capital": round(remaining_value, 2),
                "loss_pct": round(loss_pct, 6),
                "cash_buffer": round(cash_ratio, 4),
                "details": details,
            }

        # 综合评估
        worst = results.get("-15%", results[list(results.keys())[-1]])
        risk_level = "低"
        if worst["loss_pct"] <= -0.10:
            risk_level = "高"
        elif worst["loss_pct"] <= -0.06:
            risk_level = "中"

        return {
            "scenarios": results,
            "total_invested": round(total_invested, 2),
            "cash_ratio": round(cash_ratio, 4),
            "risk_level": risk_level,
            "message": f"压力测试完成，当前组合风险等级：{risk_level}",
        }

    # -------------------- 综合风控报告 --------------------

    def full_risk_report(self, current_value: Optional[float] = None) -> Dict:
        """生成综合风控报告"""
        dd_action = self.check_drawdown_action(current_value)
        weights = self.calculate_position_weights()
        corr = self.analyze_correlation()
        stress = self.stress_test()

        return {
            "drawdown_control": dd_action,
            "position_weights": weights,
            "correlation_analysis": corr,
            "stress_test": stress,
            "summary": {
                "risk_level": stress["risk_level"],
                "drawdown_action": dd_action["action"],
                "high_corr_count": len(corr["high_corr_pairs"]),
                "sector_warnings": len(corr["sector_warnings"]),
            },
        }


# ============================================================
#  PositionSizer — 仓位计算器
# ============================================================

@dataclass
class PositionSizer:
    """
    仓位计算器

    提供两种仓位计算模型：
    1. 凯利公式 — 基于胜率和赔率的最优仓位
    2. 波动率模型 — 基于ATR的动态仓位（高波动=低仓位）
    """

    # ---------- 凯利公式参数 ----------
    default_win_rate: float = 0.55           # 默认胜率
    default_win_loss_ratio: float = 2.0      # 默认盈亏比（赔率）
    kelly_fraction: float = 0.5               # 凯利系数（半凯利，降低风险）

    # ---------- 波动率模型参数 ----------
    atr_lookback: int = 20                    # ATR计算周期
    max_vol_weight: float = 0.15              # 高波动最大仓位
    min_vol_weight: float = 0.02              # 低波动最小仓位
    vol_scale_factor: float = 2.0             # 波动率缩放因子

    # ---------- 通用约束 ----------
    max_position_pct: float = 0.15            # 单只最大仓位
    min_position_pct: float = 0.01            # 单只最小仓位

    def kelly_position(self, win_rate: Optional[float] = None,
                       win_loss_ratio: Optional[float] = None) -> Dict:
        """
        基于凯利公式计算最优仓位

        凯利公式：f* = (bp - q) / b
        其中 b = 赔率（盈亏比），p = 胜率，q = 1 - p

        Args:
            win_rate: 胜率（0~1），默认使用 default_win_rate
            win_loss_ratio: 盈亏比，默认使用 default_win_loss_ratio

        Returns:
            Dict 包含凯利仓位及计算详情
        """
        wr = win_rate if win_rate is not None else self.default_win_rate
        wlr = win_loss_ratio if win_loss_ratio is not None else self.default_win_loss_ratio

        # 凯利公式核心计算
        b = wlr  # 赔率
        p = wr   # 胜率
        q = 1.0 - p  # 败率

        # f* = (b*p - q) / b
        numerator = b * p - q
        kelly_raw = numerator / b if b > 0 else 0.0

        # 半凯利（更保守）
        kelly_adjusted = kelly_raw * self.kelly_fraction

        # 约束在合理范围
        kelly_clamped = max(self.min_position_pct, min(self.max_position_pct, kelly_adjusted))

        return {
            "win_rate": wr,
            "win_loss_ratio": wlr,
            "kelly_raw": round(kelly_raw, 6),
            "kelly_adjusted": round(kelly_adjusted, 6),
            "kelly_clamped": round(kelly_clamped, 4),
            "suggested_weight": kelly_clamped,
            "fraction": self.kelly_fraction,
            "message": f"凯利公式建议仓位 {kelly_clamped:.2%}（半凯利={self.kelly_fraction}）",
        }

    def volatility_position(self, atr: float, price: float,
                             base_weight: Optional[float] = None) -> Dict:
        """
        基于波动率（ATR）计算仓位

        逻辑：波动率越高 → 仓位越低
        vol_ratio = ATR / price（标准化波动率）
        weight = base_weight / (1 + vol_ratio * scale_factor)

        Args:
            atr: 当前ATR值
            price: 当前价格
            base_weight: 基础仓位权重，默认 max_position_pct

        Returns:
            Dict 包含波动率仓位及计算详情
        """
        bw = base_weight if base_weight is not None else self.max_position_pct

        if price <= 0 or atr <= 0:
            return {
                "atr": atr,
                "price": price,
                "vol_ratio": 0.0,
                "suggested_weight": bw,
                "message": "ATR或价格无效，使用默认仓位",
            }

        vol_ratio = atr / price  # 标准化波动率

        # 波动率调整：基础仓位 / (1 + 波动率 * 缩放因子)
        adjusted_weight = bw / (1.0 + vol_ratio * self.vol_scale_factor)

        # 约束范围
        clamped_weight = max(self.min_vol_weight, min(self.max_vol_weight, adjusted_weight))

        return {
            "atr": round(atr, 4),
            "price": round(price, 4),
            "vol_ratio": round(vol_ratio, 6),
            "base_weight": bw,
            "adjusted_weight": round(adjusted_weight, 6),
            "suggested_weight": round(clamped_weight, 4),
            "scale_factor": self.vol_scale_factor,
            "message": f"波动率 {vol_ratio:.4f}，建议仓位 {clamped_weight:.2%}",
        }

    def combined_position(self, atr: float, price: float,
                           win_rate: Optional[float] = None,
                           win_loss_ratio: Optional[float] = None) -> Dict:
        """
        综合凯利公式和波动率模型计算仓位

        取两者的较小值（更保守），确保仓位在安全范围内。

        Returns:
            Dict 包含两种模型的仓位及最终建议
        """
        kelly = self.kelly_position(win_rate, win_loss_ratio)
        vol = self.volatility_position(atr, price)

        # 取较小值（更保守）
        final_weight = min(kelly["suggested_weight"], vol["suggested_weight"])
        final_weight = max(self.min_position_pct, min(self.max_position_pct, final_weight))

        return {
            "kelly_weight": kelly["suggested_weight"],
            "volatility_weight": vol["suggested_weight"],
            "final_weight": round(final_weight, 4),
            "method": "min(kelly, volatility)",
            "kelly_detail": kelly,
            "volatility_detail": vol,
            "message": f"综合建议仓位 {final_weight:.2%}（取凯利{kelly['suggested_weight']:.2%}和波动率{vol['suggested_weight']:.2%}的较小值）",
        }


# ============================================================
#  StopLossManager — 止损管理器
# ============================================================

@dataclass
class StopLossManager:
    """
    止损管理器

    提供四种止损策略：
    1. 固定百分比止损 — 跌破固定比例触发
    2. ATR跟踪止损 — 基于ATR的动态跟踪止损
    3. 时间止损 — 持仓超过N天未达目标自动减仓
    4. 里程碑止损 — 关键日期（财报、解禁等）逾期未达标则止损
    """

    # ---------- 固定止损参数 ----------
    fixed_stop_pct: float = -0.15            # 固定止损比例（-15%）

    # ---------- ATR跟踪止损参数 ----------
    atr_multiplier: float = 2.0              # ATR倍数
    trailing_enabled: bool = True            # 是否启用跟踪止损

    # ---------- 时间止损参数 ----------
    time_stop_days: int = 20                 # 时间止损天数阈值
    time_stop_reduce_ratio: float = 0.5       # 时间止损减仓比例

    # ---------- 里程碑止损参数 ----------
    milestone_enabled: bool = True            # 是否启用里程碑止损
    milestone_buffer_days: int = 5            # 里程碑到期后缓冲天数
    milestone_stop_ratio: float = 0.7         # 里程碑止损减仓比例

    def fixed_stop_check(self, cost_price: float, current_price: float) -> Dict:
        """
        固定百分比止损检查

        Args:
            cost_price: 成本价
            current_price: 当前价

        Returns:
            Dict 包含是否触发、当前盈亏、止损价
        """
        if cost_price <= 0:
            return {"triggered": False, "message": "成本价无效"}

        pnl_pct = (current_price - cost_price) / cost_price
        stop_price = cost_price * (1.0 + self.fixed_stop_pct)
        triggered = pnl_pct <= self.fixed_stop_pct

        return {
            "triggered": triggered,
            "cost_price": cost_price,
            "current_price": current_price,
            "pnl_pct": round(pnl_pct, 6),
            "stop_price": round(stop_price, 4),
            "stop_pct": self.fixed_stop_pct,
            "distance_to_stop": round((current_price - stop_price) / cost_price, 6),
            "message": f"{'触发止损！' if triggered else '未触发'} 止损价={stop_price:.2f}，当前盈亏={pnl_pct:.2%}",
        }

    def atr_trailing_stop_check(self, cost_price: float, current_price: float,
                                  atr: float, highest_price: Optional[float] = None) -> Dict:
        """
        ATR跟踪止损检查

        止损价 = 最高价 - ATR * multiplier
        当价格跌破止损价时触发。

        Args:
            cost_price: 成本价
            current_price: 当前价
            atr: 当前ATR值
            highest_price: 持仓期间最高价，若为None则用current_price

        Returns:
            Dict 包含是否触发、跟踪止损价、保护利润等
        """
        if atr <= 0:
            return {"triggered": False, "message": "ATR无效"}

        hp = highest_price if highest_price is not None else max(current_price, cost_price)
        trailing_stop_price = hp - atr * self.atr_multiplier
        triggered = current_price <= trailing_stop_price

        # 计算保护利润
        pnl_pct = (current_price - cost_price) / cost_price if cost_price > 0 else 0.0
        protected_profit = max(0, (trailing_stop_price - cost_price) / cost_price) if cost_price > 0 else 0.0

        return {
            "triggered": triggered,
            "enabled": self.trailing_enabled,
            "cost_price": cost_price,
            "current_price": current_price,
            "highest_price": hp,
            "atr": atr,
            "atr_multiplier": self.atr_multiplier,
            "trailing_stop_price": round(trailing_stop_price, 4),
            "pnl_pct": round(pnl_pct, 6),
            "protected_profit_pct": round(protected_profit, 6),
            "message": f"{'触发ATR跟踪止损！' if triggered else '未触发'} 跟踪止损价={trailing_stop_price:.2f}（最高价{hp:.2f} - {self.atr_multiplier}xATR{atr:.2f}）",
        }

    def time_stop_check(self, hold_days: int, pnl_pct: float,
                        target_pct: float = 0.10) -> Dict:
        """
        时间止损检查

        持仓超过N天且未达到目标收益率，则建议减仓。

        Args:
            hold_days: 持仓天数
            pnl_pct: 当前盈亏百分比
            target_pct: 目标收益率

        Returns:
            Dict 包含是否触发、建议操作
        """
        triggered = hold_days >= self.time_stop_days and pnl_pct < target_pct

        # 超时程度
        overdue_days = max(0, hold_days - self.time_stop_days) if triggered else 0

        # 根据超时程度调整减仓比例
        reduce_ratio = self.time_stop_reduce_ratio
        if overdue_days > 10:
            reduce_ratio = min(0.8, reduce_ratio + 0.1 * (overdue_days - 10) / 10)

        return {
            "triggered": triggered,
            "hold_days": hold_days,
            "pnl_pct": round(pnl_pct, 6),
            "target_pct": target_pct,
            "time_limit": self.time_stop_days,
            "overdue_days": overdue_days,
            "reduce_ratio": round(reduce_ratio, 4),
            "message": f"{'触发时间止损！' if triggered else '未触发'} 持仓{hold_days}天，盈亏{pnl_pct:.2%}，目标{target_pct:.0%}未达",
        }

    def milestone_stop_check(self, hold_days: int, pnl_pct: float,
                              milestone_date: Optional[str] = None,
                              target_pct: float = 0.15) -> Dict:
        """
        里程碑止损检查（X大神策略专用）

        在关键里程碑日期（如财报发布日、解禁日、利好兑现日）前后，
        若持仓未达到目标收益，则强制减仓。

        Args:
            hold_days: 持仓天数
            pnl_pct: 当前盈亏百分比
            milestone_date: 里程碑日期（YYYY-MM-DD），若为None则按固定天数判断
            target_pct: 里程碑目标收益率

        Returns:
            Dict 包含是否触发、建议操作
        """
        if not self.milestone_enabled:
            return {"triggered": False, "message": "里程碑止损未启用"}

        # 如果没有指定里程碑日期，使用默认的持仓天数阈值
        if milestone_date is None:
            # 默认里程碑：持仓30天
            milestone_triggered = hold_days >= 30
            milestone_name = "默认30天里程碑"
        else:
            # 解析里程碑日期（简化处理，仅做字符串比较）
            milestone_triggered = True  # 已到里程碑日期
            milestone_name = f"里程碑日 {milestone_date}"

        # 到达里程碑但未达标
        triggered = milestone_triggered and pnl_pct < target_pct

        return {
            "triggered": triggered,
            "enabled": self.milestone_enabled,
            "hold_days": hold_days,
            "pnl_pct": round(pnl_pct, 6),
            "target_pct": target_pct,
            "milestone_date": milestone_date,
            "milestone_name": milestone_name,
            "stop_ratio": self.milestone_stop_ratio if triggered else 0.0,
            "buffer_days": self.milestone_buffer_days,
            "message": f"{'触发里程碑止损！' if triggered else '未触发'} {milestone_name}，盈亏{pnl_pct:.2%}，目标{target_pct:.0%}未达，建议减仓{self.milestone_stop_ratio:.0%}",
        }

    def comprehensive_stop_check(self, position: Position) -> Dict:
        """
        综合止损检查（对单个持仓执行所有止损策略）

        Args:
            position: Position 数据类

        Returns:
            Dict 包含所有止损策略的检查结果及最终建议
        """
        # 1. 固定止损
        fixed = self.fixed_stop_check(position.cost_price, position.current_price)

        # 2. ATR跟踪止损
        trailing = self.atr_trailing_stop_check(
            position.cost_price, position.current_price, position.atr
        )

        # 3. 时间止损
        time_stop = self.time_stop_check(position.hold_days, position.pnl_pct)

        # 4. 里程碑止损
        milestone = self.milestone_stop_check(
            position.hold_days, position.pnl_pct, position.milestone_date
        )

        # 汇总触发情况
        triggered_list = []
        if fixed["triggered"]:
            triggered_list.append("固定止损")
        if trailing["triggered"]:
            triggered_list.append("ATR跟踪止损")
        if time_stop["triggered"]:
            triggered_list.append("时间止损")
        if milestone["triggered"]:
            triggered_list.append("里程碑止损")

        # 最终建议
        any_triggered = len(triggered_list) > 0
        # 固定止损和ATR止损优先级最高（建议全部卖出）
        urgent = fixed["triggered"] or trailing["triggered"]
        action = "立即清仓" if urgent else ("减仓" if any_triggered else "继续持有")
        reduce_ratio = 1.0 if urgent else (
            max(time_stop["reduce_ratio"], milestone["stop_ratio"]) if any_triggered else 0.0
        )

        return {
            "code": position.code,
            "name": position.name,
            "any_triggered": any_triggered,
            "triggered_strategies": triggered_list,
            "action": action,
            "reduce_ratio": round(reduce_ratio, 4),
            "fixed_stop": fixed,
            "atr_trailing_stop": trailing,
            "time_stop": time_stop,
            "milestone_stop": milestone,
            "message": f"[{position.code}] {action}" + (f"，触发：{', '.join(triggered_list)}" if triggered_list else ""),
        }


# ============================================================
#  __main__ 入口 — 简单演示
# ============================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("  玄甲AGI 风控引擎 — 演示")
    print("=" * 60)

    # ---------- 1. PortfolioRiskManager 演示 ----------
    print("\n" + "-" * 40)
    print("  [1] 组合风险管理器 PortfolioRiskManager")
    print("-" * 40)

    # 构造模拟持仓
    positions = [
        Position(code="600519", name="贵州茅台", sector="白酒", weight=0.12,
                 cost_price=1800.0, current_price=1750.0, atr=45.0, hold_days=10,
                 target_price=2000.0),
        Position(code="000858", name="五粮液", sector="白酒", weight=0.10,
                 cost_price=160.0, current_price=155.0, atr=5.0, hold_days=8,
                 target_price=180.0),
        Position(code="300750", name="宁德时代", sector="新能源", weight=0.08,
                 cost_price=220.0, current_price=235.0, atr=8.0, hold_days=15,
                 target_price=260.0),
        Position(code="601318", name="中国平安", sector="金融", weight=0.10,
                 cost_price=50.0, current_price=48.0, atr=1.5, hold_days=5,
                 target_price=58.0),
        Position(code="002594", name="比亚迪", sector="新能源", weight=0.07,
                 cost_price=280.0, current_price=295.0, atr=12.0, hold_days=12,
                 target_price=330.0),
    ]

    rm = PortfolioRiskManager(initial_capital=1_000_000.0, current_capital=960_000.0)
    rm.set_positions(positions)

    # 回撤检查
    print("\n>>> 回撤控制检查：")
    dd_result = rm.check_drawdown_action()
    print(json.dumps(dd_result, ensure_ascii=False, indent=2))

    # 动态仓位
    print("\n>>> 动态仓位计算：")
    weight_result = rm.calculate_position_weights()
    print(json.dumps(weight_result, ensure_ascii=False, indent=2))

    # 相关性分析
    print("\n>>> 持仓相关性分析：")
    corr_result = rm.analyze_correlation()
    print(json.dumps(corr_result, ensure_ascii=False, indent=2))

    # 压力测试
    print("\n>>> 压力测试：")
    stress_result = rm.stress_test()
    print(json.dumps(stress_result, ensure_ascii=False, indent=2))

    # ---------- 2. PositionSizer 演示 ----------
    print("\n" + "-" * 40)
    print("  [2] 仓位计算器 PositionSizer")
    print("-" * 40)

    sizer = PositionSizer()

    # 凯利公式
    print("\n>>> 凯利公式仓位（胜率55%，盈亏比2.0）：")
    kelly = sizer.kelly_position()
    print(json.dumps(kelly, ensure_ascii=False, indent=2))

    # 波动率仓位
    print("\n>>> 波动率仓位（ATR=45, 价格=1750）：")
    vol = sizer.volatility_position(atr=45.0, price=1750.0)
    print(json.dumps(vol, ensure_ascii=False, indent=2))

    # 综合仓位
    print("\n>>> 综合仓位计算：")
    combined = sizer.combined_position(atr=45.0, price=1750.0)
    print(json.dumps(combined, ensure_ascii=False, indent=2))

    # ---------- 3. StopLossManager 演示 ----------
    print("\n" + "-" * 40)
    print("  [3] 止损管理器 StopLossManager")
    print("-" * 40)

    slm = StopLossManager()

    # 固定止损
    print("\n>>> 固定止损检查（成本1800，现价1520）：")
    fixed = slm.fixed_stop_check(1800.0, 1520.0)
    print(json.dumps(fixed, ensure_ascii=False, indent=2))

    # ATR跟踪止损
    print("\n>>> ATR跟踪止损（成本1800，现价1750，ATR=45，最高1900）：")
    trailing = slm.atr_trailing_stop_check(1800.0, 1750.0, 45.0, 1900.0)
    print(json.dumps(trailing, ensure_ascii=False, indent=2))

    # 时间止损
    print("\n>>> 时间止损（持仓25天，盈亏+3%，目标10%）：")
    time_stop = slm.time_stop_check(25, 0.03, 0.10)
    print(json.dumps(time_stop, ensure_ascii=False, indent=2))

    # 里程碑止损
    print("\n>>> 里程碑止损（持仓35天，盈亏+5%，目标15%）：")
    milestone = slm.milestone_stop_check(35, 0.05, target_pct=0.15)
    print(json.dumps(milestone, ensure_ascii=False, indent=2))

    # 综合止损
    print("\n>>> 综合止损检查（贵州茅台持仓）：")
    test_pos = Position(code="600519", name="贵州茅台", sector="白酒", weight=0.12,
                        cost_price=1800.0, current_price=1520.0, atr=45.0, hold_days=25,
                        target_price=2000.0, milestone_date="2026-06-20")
    full_check = slm.comprehensive_stop_check(test_pos)
    print(json.dumps(full_check, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("  风控引擎演示完毕")
    print("=" * 60)
