#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSA Strategy Adapter - 策略适配器
将 daily_stock_analysis 的15种策略映射到玄甲APEX_MAX因子体系

映射关系:
  DSA策略 → 玄甲因子 → 权重调整

Author: XuanJia ApexAGI
Version: 1.0.0
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DSAStrategyAdapter")


# ==================== 玄甲因子定义 ====================

class XuanJiaFactor(Enum):
    """玄甲APEX_MAX因子枚举"""
    OMEGA_A = "Ω_A"        # 基本面权重因子
    BETA_BG = "β_bg"       # 背景趋势因子
    ALPHA_ACK = "α_ack"    # 技术确认因子
    THETA_TRI = "Θ_TRI"    # 三角收敛因子
    NABLA_K = "∇_K"        # 动能梯度因子
    ZETA_SIGMA = "ζ_σ"     # 波动率因子
    ETA_LAMBDA = "η_λ"     # 热点映射因子
    EVM = "EVM"            # 事件驱动因子
    AB = "A·B"             # 筹码博弈因子
    TAO = "Tao"            # 资金流向因子
    DELTA_SIGMA = "Δ_Σ"    # 风险惩罚因子


# ==================== DSA策略定义 ====================

class DSAStrategy(Enum):
    """DSA内置策略枚举"""
    MA_CROSS = "均线金叉死叉"
    CHAN_LUN = "缠论"
    ELLIOTT_WAVE = "波浪理论"
    BULL_TREND = "多头趋势"
    HOT_TOPIC = "热点题材"
    EVENT_DRIVE = "事件驱动"
    GROWTH_QUALITY = "成长质量"
    EXPECTATION_REVAL = "预期重估"
    CHIP_DIST = "筹码分布"
    FUND_FLOW = "资金流向"
    MEAN_REVERSION = "均值回归"
    BREAKOUT = "突破策略"
    MOMENTUM = "动量策略"
    VALUE_INVEST = "价值投资"
    TECH_DIVERGENCE = "技术背离"


@dataclass
class StrategyMapping:
    """策略映射定义"""
    dsa_strategy: DSAStrategy
    xuanjia_factors: List[Tuple[XuanJiaFactor, float]]  # (因子, 权重调整)
    description: str
    activation_condition: str
    priority: int


@dataclass
class FactorAdjustment:
    """因子调整结果"""
    factor: XuanJiaFactor
    base_weight: float
    adjustment: float
    final_weight: float
    reason: str


class DSAStrategyAdapter:
    """
    DSA策略适配器

    核心功能:
    1. 15种DSA策略 → 玄甲11因子映射
    2. 动态权重调整
    3. 策略冲突检测与解决
    4. 多策略组合优化
    """

    # 策略映射表
    STRATEGY_MAPPINGS: List[StrategyMapping] = [
        # 1. 均线金叉死叉 → 技术确认因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.MA_CROSS,
            xuanjia_factors=[
                (XuanJiaFactor.ALPHA_ACK, 0.25),   # 技术确认 +25%
                (XuanJiaFactor.BETA_BG, 0.15),     # 背景趋势 +15%
            ],
            description="MA5/MA10/MA20金叉死叉信号",
            activation_condition="短期MA上穿长期MA",
            priority=1,
        ),

        # 2. 缠论 → 三角收敛因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.CHAN_LUN,
            xuanjia_factors=[
                (XuanJiaFactor.THETA_TRI, 0.30),   # 三角收敛 +30%
                (XuanJiaFactor.NABLA_K, 0.15),     # 动能梯度 +15%
                (XuanJiaFactor.ZETA_SIGMA, 0.10),  # 波动率 +10%
            ],
            description="中枢、背驰、分型识别",
            activation_condition="出现背驰或中枢突破",
            priority=2,
        ),

        # 3. 波浪理论 → 动能梯度因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.ELLIOTT_WAVE,
            xuanjia_factors=[
                (XuanJiaFactor.NABLA_K, 0.25),     # 动能梯度 +25%
                (XuanJiaFactor.BETA_BG, 0.20),     # 背景趋势 +20%
            ],
            description="浪型结构识别与计数",
            activation_condition="清晰浪型结构",
            priority=3,
        ),

        # 4. 多头趋势 → 背景趋势因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.BULL_TREND,
            xuanjia_factors=[
                (XuanJiaFactor.BETA_BG, 0.30),     # 背景趋势 +30%
                (XuanJiaFactor.ALPHA_ACK, 0.15),   # 技术确认 +15%
            ],
            description="趋势跟踪与确认",
            activation_condition="MA多头排列",
            priority=1,
        ),

        # 5. 热点题材 → 热点映射因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.HOT_TOPIC,
            xuanjia_factors=[
                (XuanJiaFactor.ETA_LAMBDA, 0.35),  # 热点映射 +35%
                (XuanJiaFactor.EVM, 0.10),         # 事件驱动 +10%
            ],
            description="题材热度与持续性分析",
            activation_condition="题材发酵初期",
            priority=2,
        ),

        # 6. 事件驱动 → 事件驱动因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.EVENT_DRIVE,
            xuanjia_factors=[
                (XuanJiaFactor.EVM, 0.40),         # 事件驱动 +40%
                (XuanJiaFactor.ZETA_SIGMA, 0.15),  # 波动率 +15%
            ],
            description="重大事件冲击分析",
            activation_condition="重大公告/政策/事件",
            priority=1,
        ),

        # 7. 成长质量 → 基本面权重因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.GROWTH_QUALITY,
            xuanjia_factors=[
                (XuanJiaFactor.OMEGA_A, 0.30),     # 基本面 +30%
                (XuanJiaFactor.ZETA_SIGMA, 0.15),  # 波动率 +15% (预期重估映射)
            ],
            description="业绩质量与成长性评估",
            activation_condition="财报季/业绩公告",
            priority=1,
        ),

        # 8. 预期重估 → 波动率因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.EXPECTATION_REVAL,
            xuanjia_factors=[
                (XuanJiaFactor.ZETA_SIGMA, 0.25),  # 波动率 +25%
                (XuanJiaFactor.OMEGA_A, 0.15),     # 基本面 +15%
            ],
            description="市场预期差分析",
            activation_condition="预期与现实的偏离",
            priority=3,
        ),

        # 9. 筹码分布 → 筹码博弈因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.CHIP_DIST,
            xuanjia_factors=[
                (XuanJiaFactor.AB, 0.30),          # 筹码博弈 +30%
                (XuanJiaFactor.TAO, 0.15),         # 资金流向 +15%
            ],
            description="筹码集中度与成本分析",
            activation_condition="筹码显著集中/分散",
            priority=2,
        ),

        # 10. 资金流向 → 资金流向因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.FUND_FLOW,
            xuanjia_factors=[
                (XuanJiaFactor.TAO, 0.35),         # 资金流向 +35%
                (XuanJiaFactor.AB, 0.10),          # 筹码博弈 +10%
            ],
            description="主力资金进出分析",
            activation_condition="主力资金异动",
            priority=1,
        ),

        # 11. 均值回归 → 波动率因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.MEAN_REVERSION,
            xuanjia_factors=[
                (XuanJiaFactor.ZETA_SIGMA, 0.25),  # 波动率 +25%
                (XuanJiaFactor.THETA_TRI, 0.15),   # 三角收敛 +15%
            ],
            description="偏离均值后的回归交易",
            activation_condition="价格偏离均值2σ以上",
            priority=3,
        ),

        # 12. 突破策略 → 技术确认因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.BREAKOUT,
            xuanjia_factors=[
                (XuanJiaFactor.ALPHA_ACK, 0.30),   # 技术确认 +30%
                (XuanJiaFactor.NABLA_K, 0.15),     # 动能梯度 +15%
            ],
            description="关键位突破交易",
            activation_condition="放量突破关键位",
            priority=1,
        ),

        # 13. 动量策略 → 动能梯度因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.MOMENTUM,
            xuanjia_factors=[
                (XuanJiaFactor.NABLA_K, 0.30),     # 动能梯度 +30%
                (XuanJiaFactor.BETA_BG, 0.10),     # 背景趋势 +10%
            ],
            description="价格动量跟踪",
            activation_condition="动量指标强势",
            priority=2,
        ),

        # 14. 价值投资 → 基本面权重因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.VALUE_INVEST,
            xuanjia_factors=[
                (XuanJiaFactor.OMEGA_A, 0.35),     # 基本面 +35%
                (XuanJiaFactor.DELTA_SIGMA, -0.10), # 风险惩罚 -10% (价值股风险低)
            ],
            description="估值与价值分析",
            activation_condition="低估值/高股息",
            priority=2,
        ),

        # 15. 技术背离 → 技术确认因子
        StrategyMapping(
            dsa_strategy=DSAStrategy.TECH_DIVERGENCE,
            xuanjia_factors=[
                (XuanJiaFactor.ALPHA_ACK, 0.25),   # 技术确认 +25%
                (XuanJiaFactor.NABLA_K, 0.15),     # 动能梯度 +15%
                (XuanJiaFactor.ZETA_SIGMA, 0.10),  # 波动率 +10%
            ],
            description="量价/指标背离识别",
            activation_condition="出现顶底背离",
            priority=1,
        ),
    ]

    # 因子基础权重 (来自APEX_MAX公式)
    BASE_FACTOR_WEIGHTS = {
        XuanJiaFactor.OMEGA_A: 0.10,
        XuanJiaFactor.BETA_BG: 0.15,
        XuanJiaFactor.ALPHA_ACK: 0.15,
        XuanJiaFactor.THETA_TRI: 0.10,
        XuanJiaFactor.NABLA_K: 0.10,
        XuanJiaFactor.ZETA_SIGMA: 0.10,
        XuanJiaFactor.ETA_LAMBDA: 0.10,
        XuanJiaFactor.EVM: 0.05,
        XuanJiaFactor.AB: 0.05,
        XuanJiaFactor.TAO: 0.05,
        XuanJiaFactor.DELTA_SIGMA: 0.05,
    }

    def __init__(self):
        self.active_strategies: List[DSAStrategy] = []
        self.factor_adjustments: Dict[XuanJiaFactor, FactorAdjustment] = {}

    def activate_strategy(self, strategy: DSAStrategy, confidence: float = 1.0):
        """
        激活一个DSA策略

        Args:
            strategy: 要激活的策略
            confidence: 策略置信度 (0-1)
        """
        if strategy not in self.active_strategies:
            self.active_strategies.append(strategy)
            logger.info(f"[Adapter] 激活策略: {strategy.value} (置信度={confidence})")
            self._apply_strategy(strategy, confidence)

    def deactivate_strategy(self, strategy: DSAStrategy):
        """停用策略"""
        if strategy in self.active_strategies:
            self.active_strategies.remove(strategy)
            logger.info(f"[Adapter] 停用策略: {strategy.value}")
            self._recalculate_all()

    def _apply_strategy(self, strategy: DSAStrategy, confidence: float):
        """应用策略的因子调整"""
        mapping = self._get_mapping(strategy)
        if not mapping:
            return

        for factor, adjustment in mapping.xuanjia_factors:
            # 根据置信度缩放调整幅度
            scaled_adjustment = adjustment * confidence

            if factor in self.factor_adjustments:
                existing = self.factor_adjustments[factor]
                # 累加调整 (但不超过上限)
                new_adjustment = min(existing.adjustment + scaled_adjustment, 0.5)
                final_weight = min(existing.base_weight + new_adjustment, 0.5)
                self.factor_adjustments[factor] = FactorAdjustment(
                    factor=factor,
                    base_weight=existing.base_weight,
                    adjustment=new_adjustment,
                    final_weight=final_weight,
                    reason=f"{existing.reason}; {mapping.dsa_strategy.value}",
                )
            else:
                base = self.BASE_FACTOR_WEIGHTS.get(factor, 0.1)
                final = min(base + scaled_adjustment, 0.5)
                self.factor_adjustments[factor] = FactorAdjustment(
                    factor=factor,
                    base_weight=base,
                    adjustment=scaled_adjustment,
                    final_weight=final,
                    reason=mapping.dsa_strategy.value,
                )

    def _recalculate_all(self):
        """重新计算所有调整"""
        self.factor_adjustments.clear()
        for strategy in self.active_strategies:
            self._apply_strategy(strategy, 1.0)

    def _get_mapping(self, strategy: DSAStrategy) -> Optional[StrategyMapping]:
        """获取策略映射"""
        for mapping in self.STRATEGY_MAPPINGS:
            if mapping.dsa_strategy == strategy:
                return mapping
        return None

    def get_adjusted_weights(self) -> Dict[XuanJiaFactor, float]:
        """
        获取调整后的因子权重

        Returns:
            Dict[XuanJiaFactor, float]: 调整后的权重表
        """
        weights = self.BASE_FACTOR_WEIGHTS.copy()

        for factor, adjustment in self.factor_adjustments.items():
            weights[factor] = adjustment.final_weight

        # 归一化 (确保总和为1)
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        return weights

    def detect_conflicts(self) -> List[Dict]:
        """
        检测策略冲突

        Returns:
            List[Dict]: 冲突列表
        """
        conflicts = []

        # 检查互斥策略
        mutex_pairs = [
            (DSAStrategy.BULL_TREND, DSAStrategy.MEAN_REVERSION),
            (DSAStrategy.BREAKOUT, DSAStrategy.MEAN_REVERSION),
            (DSAStrategy.MOMENTUM, DSAStrategy.VALUE_INVEST),
        ]

        for s1, s2 in mutex_pairs:
            if s1 in self.active_strategies and s2 in self.active_strategies:
                conflicts.append({
                    "type": "mutex",
                    "strategies": [s1.value, s2.value],
                    "description": f"{s1.value} 与 {s2.value} 逻辑互斥",
                    "resolution": "建议根据市场环境选择其一",
                })

        # 检查因子过载 (同一因子被多个策略过度加权)
        factor_counts: Dict[XuanJiaFactor, int] = {}
        for strategy in self.active_strategies:
            mapping = self._get_mapping(strategy)
            if mapping:
                for factor, _ in mapping.xuanjia_factors:
                    factor_counts[factor] = factor_counts.get(factor, 0) + 1

        for factor, count in factor_counts.items():
            if count >= 3:
                conflicts.append({
                    "type": "overload",
                    "factor": factor.value,
                    "strategy_count": count,
                    "description": f"{factor.value} 被 {count} 个策略同时加权",
                    "resolution": "建议降低该因子权重上限",
                })

        return conflicts

    def resolve_conflicts(self) -> Dict[XuanJiaFactor, float]:
        """
        解决冲突并返回最终权重

        Returns:
            Dict[XuanJiaFactor, float]: 冲突解决后的权重
        """
        conflicts = self.detect_conflicts()

        if conflicts:
            logger.warning(f"[Adapter] 检测到 {len(conflicts)} 个策略冲突:")
            for conflict in conflicts:
                logger.warning(f"  - {conflict['type']}: {conflict['description']}")

        weights = self.get_adjusted_weights()

        # 处理过载因子的权重上限
        for conflict in conflicts:
            if conflict["type"] == "overload":
                factor = next(
                    (f for f in XuanJiaFactor if f.value == conflict["factor"]), None
                )
                if factor and factor in weights:
                    weights[factor] = min(weights[factor], 0.35)  # 上限35%

        # 再次归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        return weights

    def get_strategy_summary(self) -> Dict:
        """获取当前策略配置摘要"""
        return {
            "active_strategies": [s.value for s in self.active_strategies],
            "active_count": len(self.active_strategies),
            "factor_adjustments": {
                adj.factor.value: {
                    "base": adj.base_weight,
                    "adjustment": adj.adjustment,
                    "final": adj.final_weight,
                    "reason": adj.reason,
                }
                for adj in self.factor_adjustments.values()
            },
            "conflicts": self.detect_conflicts(),
            "final_weights": {
                k.value: v for k, v in self.resolve_conflicts().items()
            },
        }

    def auto_select_strategies(self, market_condition: Dict) -> List[DSAStrategy]:
        """
        根据市场环境自动选择策略

        Args:
            market_condition: 市场环境描述
                {
                    "trend": "up/down/sideways",
                    "volatility": "high/medium/low",
                    "volume": "high/medium/low",
                    "sentiment": "bullish/bearish/neutral",
                }

        Returns:
            List[DSAStrategy]: 推荐的策略列表
        """
        recommended = []
        trend = market_condition.get("trend", "sideways")
        volatility = market_condition.get("volatility", "medium")
        volume = market_condition.get("volume", "medium")
        sentiment = market_condition.get("sentiment", "neutral")

        # 趋势市场
        if trend == "up":
            recommended.extend([
                DSAStrategy.BULL_TREND,
                DSAStrategy.MOMENTUM,
                DSAStrategy.BREAKOUT,
            ])
        elif trend == "down":
            recommended.extend([
                DSAStrategy.MEAN_REVERSION,
                DSAStrategy.TECH_DIVERGENCE,
                DSAStrategy.VALUE_INVEST,
            ])
        else:  # sideways
            recommended.extend([
                DSAStrategy.CHAN_LUN,
                DSAStrategy.MEAN_REVERSION,
                DSAStrategy.CHIP_DIST,
            ])

        # 高波动市场
        if volatility == "high":
            recommended.extend([
                DSAStrategy.EVENT_DRIVE,
                DSAStrategy.TECH_DIVERGENCE,
            ])

        # 高成交量
        if volume == "high":
            recommended.extend([
                DSAStrategy.FUND_FLOW,
                DSAStrategy.BREAKOUT,
            ])

        # 情绪极端
        if sentiment in ["bullish", "bearish"]:
            recommended.append(DSAStrategy.EXPECTATION_REVAL)

        # 去重并排序
        unique = list(dict.fromkeys(recommended))
        return unique[:5]  # 最多5个策略


# ==================== 便捷函数 ====================

def apply_dsa_strategies_to_apex(
    apex_factors: Dict[str, float],
    active_strategies: List[str],
    market_condition: Optional[Dict] = None,
) -> Dict[str, float]:
    """
    将DSA策略应用到玄甲因子

    Args:
        apex_factors: 当前玄甲因子值
        active_strategies: 激活的DSA策略名称列表
        market_condition: 市场环境 (可选)

    Returns:
        Dict[str, float]: 调整后的因子值
    """
    adapter = DSAStrategyAdapter()

    # 自动选择策略 (如果未指定)
    if not active_strategies and market_condition:
        selected = adapter.auto_select_strategies(market_condition)
        active_strategies = [s.value for s in selected]

    # 激活策略
    for strategy_name in active_strategies:
        try:
            strategy = DSAStrategy(strategy_name)
            adapter.activate_strategy(strategy)
        except ValueError:
            logger.warning(f"[Adapter] 未知策略: {strategy_name}")

    # 获取调整后的权重
    adjusted_weights = adapter.resolve_conflicts()

    # 应用到因子值
    result = apex_factors.copy()
    for factor, weight in adjusted_weights.items():
        factor_key = factor.value
        if factor_key in result:
            # 权重调整影响因子贡献度
            base_weight = DSAStrategyAdapter.BASE_FACTOR_WEIGHTS.get(factor, 0.1)
            if base_weight > 0:
                scale = weight / base_weight
                result[factor_key] = round(result[factor_key] * scale, 4)

    return result


# ==================== 测试 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("DSA Strategy Adapter - 策略适配器测试")
    print("=" * 60)

    adapter = DSAStrategyAdapter()

    # 测试1: 激活多个策略
    print("\n📊 测试1: 激活多头趋势+资金流向+突破策略")
    adapter.activate_strategy(DSAStrategy.BULL_TREND, confidence=0.9)
    adapter.activate_strategy(DSAStrategy.FUND_FLOW, confidence=0.8)
    adapter.activate_strategy(DSAStrategy.BREAKOUT, confidence=0.85)

    weights = adapter.get_adjusted_weights()
    print("\n调整后的因子权重:")
    for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"  {factor.value}: {weight:.4f}")

    # 测试2: 冲突检测
    print("\n📊 测试2: 冲突检测")
    adapter.activate_strategy(DSAStrategy.MEAN_REVERSION, confidence=0.7)
    conflicts = adapter.detect_conflicts()
    print(f"检测到 {len(conflicts)} 个冲突:")
    for conflict in conflicts:
        print(f"  - {conflict['type']}: {conflict['description']}")

    # 测试3: 冲突解决
    print("\n📊 测试3: 冲突解决后的权重")
    resolved = adapter.resolve_conflicts()
    print("解决后的因子权重:")
    for factor, weight in sorted(resolved.items(), key=lambda x: -x[1]):
        print(f"  {factor.value}: {weight:.4f}")

    # 测试4: 策略摘要
    print("\n📊 测试4: 策略配置摘要")
    summary = adapter.get_strategy_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    # 测试5: 自动策略选择
    print("\n📊 测试5: 自动策略选择")
    market_conditions = [
        {"trend": "up", "volatility": "medium", "volume": "high", "sentiment": "bullish"},
        {"trend": "down", "volatility": "high", "volume": "low", "sentiment": "bearish"},
        {"trend": "sideways", "volatility": "low", "volume": "medium", "sentiment": "neutral"},
    ]

    for condition in market_conditions:
        print(f"\n  市场环境: {condition}")
        recommended = adapter.auto_select_strategies(condition)
        print(f"  推荐策略: {[s.value for s in recommended]}")

    # 测试6: 应用到玄甲因子
    print("\n📊 测试6: 应用到玄甲因子")
    apex_factors = {
        "Ω_A": 0.85,
        "β_bg": 0.75,
        "α_ack": 0.80,
        "Θ_TRI": 0.60,
        "∇_K": 0.70,
        "ζ_σ": 0.55,
        "η_λ": 0.65,
        "EVM": 0.50,
        "A·B": 0.45,
        "Tao": 0.60,
        "Δ_Σ": 0.40,
    }

    adjusted = apply_dsa_strategies_to_apex(
        apex_factors,
        active_strategies=["均线金叉死叉", "资金流向", "热点题材"],
    )
    print("\n原始因子 vs 调整后因子:")
    for key in apex_factors:
        print(f"  {key}: {apex_factors[key]:.4f} -> {adjusted.get(key, 0):.4f}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
