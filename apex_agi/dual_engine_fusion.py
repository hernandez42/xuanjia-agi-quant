#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual Engine Fusion - 双引擎融合器
将 APEX_MAX 公式引擎与 DSA LLM决策引擎结果融合

融合公式:
  Fused_Score = (APEX_Score * W_apex + DSA_Score * W_dsa) / (W_apex + W_dsa)
  Consistency = 1 - |Score_Diff|/100 * 0.5 + Signal_Match * 0.5

Author: XuanJia ApexAGI
Version: 1.0.0
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DualEngineFusion")


class SignalType(Enum):
    """信号类型"""
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "观望"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"


class TrendType(Enum):
    """趋势类型"""
    STRONG_UP = "强烈看多"
    UP = "看多"
    OSCILLATE = "震荡"
    DOWN = "看空"
    STRONG_DOWN = "强烈看空"


@dataclass
class ApexResult:
    """APEX_MAX公式引擎输出"""
    score: float                    # 0-100 综合评分
    signal: str                     # 买入/观望/卖出
    trend: str                      # 八卦分类
    confidence: float               # 0-1 置信度
    predicted_change: float         # 预测涨跌幅
    interval_68: Tuple[float, float]  # 68%置信区间
    interval_95: Tuple[float, float]  # 95%置信区间
    factors: Dict[str, float]       # 各因子得分
    warnings: List[str]             # 风险提示
    metadata: Dict = field(default_factory=dict)


@dataclass
class DSAResult:
    """DSA LLM决策引擎输出"""
    score: float = 50.0              # 0-100 综合评分
    signal: str = "观望"              # 买入/观望/卖出
    trend: str = "震荡"               # 强烈看多/看多/震荡/看空/强烈看空
    confidence: float = 0.5           # 0-1 置信度
    buy_point: Optional[float] = None      # 建议买入价位
    sell_point: Optional[float] = None     # 建议卖出价位
    risks: List[str] = field(default_factory=list)   # 风险警报
    catalysts: List[str] = field(default_factory=list)  # 利好催化
    checklist: List[str] = field(default_factory=list)  # 操作检查清单
    metadata: Dict = field(default_factory=dict)


@dataclass
class FusedResult:
    """融合结果"""
    fused_score: float              # 融合评分 0-100
    signal: str                     # 最终信号
    trend: str                      # 最终趋势判断
    consistency: float              # 引擎一致性 0-1
    apex_contribution: float        # APEX权重贡献
    dsa_contribution: float         # DSA权重贡献
    warning: Optional[str]          # 分歧警告
    apex_detail: ApexResult         # APEX详细结果
    dsa_detail: DSAResult           # DSA详细结果
    action_plan: List[str]          # 行动计划
    risk_level: str                 # 风险等级
    timestamp: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())


class DualEngineFusion:
    """
    双引擎融合器

    核心算法:
    1. 信号一致性检查: 计算两引擎结果的匹配度
    2. 动态权重分配: 基于历史准确率动态调整权重
    3. 加权融合: 综合两引擎输出
    4. 分歧处理: 严重分歧时标记人工复核
    """

    # 信号映射表 (统一两引擎的信号表述)
    SIGNAL_MAP = {
        "买入": SignalType.BUY,
        "强烈买入": SignalType.STRONG_BUY,
        "观望": SignalType.HOLD,
        "卖出": SignalType.SELL,
        "强烈卖出": SignalType.STRONG_SELL,
        "强烈看多": SignalType.STRONG_BUY,
        "看多": SignalType.BUY,
        "震荡": SignalType.HOLD,
        "看空": SignalType.SELL,
        "强烈看空": SignalType.STRONG_SELL,
    }

    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "apex_base": 0.55,      # APEX基础权重
        "dsa_base": 0.45,       # DSA基础权重
        "consistency_boost": 0.1,  # 一致性奖励
        "divergence_penalty": 0.2, # 分歧惩罚
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化融合器

        Args:
            weights: 自定义权重配置
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.history: List[Dict] = []  # 历史融合记录，用于动态调权

    def fuse(self, apex_result: ApexResult, dsa_result: DSAResult) -> FusedResult:
        """
        融合两个引擎的输出

        Args:
            apex_result: APEX_MAX公式引擎结果
            dsa_result: DSA LLM决策引擎结果

        Returns:
            FusedResult: 融合后的决策结果
        """
        logger.info("[Fusion] 开始双引擎融合...")

        # 1. 信号一致性检查
        consistency = self._check_consistency(apex_result, dsa_result)
        logger.info(f"[Fusion] 引擎一致性: {consistency:.2f}")

        # 2. 动态权重计算
        w_apex, w_dsa = self._calculate_dynamic_weights(apex_result, dsa_result, consistency)
        logger.info(f"[Fusion] 动态权重 - APEX: {w_apex:.2f}, DSA: {w_dsa:.2f}")

        # 3. 加权融合评分
        fused_score = self._fuse_score(apex_result.score, dsa_result.score, w_apex, w_dsa)
        logger.info(f"[Fusion] 融合评分: {fused_score:.1f}")

        # 4. 信号融合
        signal, trend = self._fuse_signal(apex_result, dsa_result, w_apex, w_dsa)

        # 5. 分歧处理
        warning = None
        if consistency < 0.3:
            warning = f"⚠️ 双引擎严重分歧 (一致性={consistency:.2f})，建议人工复核"
            logger.warning(f"[Fusion] {warning}")
        elif consistency < 0.6:
            warning = f"⚡ 双引擎轻度分歧 (一致性={consistency:.2f})，谨慎决策"

        # 6. 生成行动计划
        action_plan = self._generate_action_plan(fused_score, signal, consistency, apex_result, dsa_result)

        # 7. 风险等级
        risk_level = self._calculate_risk_level(fused_score, consistency, apex_result, dsa_result)

        result = FusedResult(
            fused_score=round(fused_score, 1),
            signal=signal,
            trend=trend,
            consistency=round(consistency, 2),
            apex_contribution=round(w_apex / (w_apex + w_dsa), 2),
            dsa_contribution=round(w_dsa / (w_apex + w_dsa), 2),
            warning=warning,
            apex_detail=apex_result,
            dsa_detail=dsa_result,
            action_plan=action_plan,
            risk_level=risk_level,
        )

        # 记录历史
        self._record_history(result)

        return result

    def _check_consistency(self, apex: ApexResult, dsa: DSAResult) -> float:
        """
        计算两引擎结果一致性 (0-1)

        算法:
          consistency = 1 - score_diff_penalty + signal_match_bonus
          score_diff_penalty = |apex_score - dsa_score| / 100 * 0.5
          signal_match_bonus = 0.5 if signals_match else 0
        """
        # 评分差异惩罚
        score_diff = abs(apex.score - dsa.score) / 100.0
        score_penalty = score_diff * 0.5

        # 信号匹配奖励
        apex_signal = self.SIGNAL_MAP.get(apex.signal, SignalType.HOLD)
        dsa_signal = self.SIGNAL_MAP.get(dsa.signal, SignalType.HOLD)
        signal_match = 0.5 if apex_signal == dsa_signal else 0.0

        # 趋势方向一致性 (加分项)
        trend_bonus = 0.0
        if hasattr(apex, 'predicted_change') and apex.predicted_change:
            apex_direction = 1 if apex.predicted_change > 0 else (-1 if apex.predicted_change < 0 else 0)
            dsa_direction = 1 if "多" in dsa.trend else (-1 if "空" in dsa.trend else 0)
            if apex_direction == dsa_direction and apex_direction != 0:
                trend_bonus = 0.1

        consistency = max(0.0, min(1.0, 1.0 - score_penalty + signal_match + trend_bonus))
        return consistency

    def _calculate_dynamic_weights(
        self, apex: ApexResult, dsa: DSAResult, consistency: float
    ) -> Tuple[float, float]:
        """
        计算动态权重

        策略:
        - 基础权重: APEX 0.55, DSA 0.45
        - 一致性高 (>0.7): 两引擎都可靠，保持基础权重
        - 一致性中 (0.3-0.7): 根据各自置信度调整
        - 一致性低 (<0.3): 降低不确定引擎的权重
        """
        w_apex = self.weights["apex_base"]
        w_dsa = self.weights["dsa_base"]

        # 根据各自置信度微调
        apex_conf = apex.confidence if apex.confidence else 0.5
        dsa_conf = dsa.confidence if dsa.confidence else 0.5

        # 置信度归一化
        total_conf = apex_conf + dsa_conf
        if total_conf > 0:
            w_apex = self.weights["apex_base"] * (apex_conf / total_conf) * 2
            w_dsa = self.weights["dsa_base"] * (dsa_conf / total_conf) * 2

        # 一致性奖励/惩罚
        if consistency > 0.7:
            # 高一致性，两引擎都可靠，稍微提升总置信度
            boost = self.weights["consistency_boost"]
            w_apex += boost * 0.5
            w_dsa += boost * 0.5
        elif consistency < 0.3:
            # 低一致性，惩罚置信度低的引擎
            penalty = self.weights["divergence_penalty"]
            if apex_conf < dsa_conf:
                w_apex = max(0.1, w_apex - penalty)
                w_dsa += penalty * 0.5
            else:
                w_dsa = max(0.1, w_dsa - penalty)
                w_apex += penalty * 0.5

        return w_apex, w_dsa

    def _fuse_score(self, apex_score: float, dsa_score: float, w_apex: float, w_dsa: float) -> float:
        """加权融合评分"""
        total_weight = w_apex + w_dsa
        if total_weight == 0:
            return (apex_score + dsa_score) / 2
        return (apex_score * w_apex + dsa_score * w_dsa) / total_weight

    def _fuse_signal(
        self, apex: ApexResult, dsa: DSAResult, w_apex: float, w_dsa: float
    ) -> Tuple[str, str]:
        """
        融合信号和趋势

        策略:
        - 信号一致: 直接采用
        - 信号分歧: 权重高的引擎主导，但降级处理
        """
        apex_signal = self.SIGNAL_MAP.get(apex.signal, SignalType.HOLD)
        dsa_signal = self.SIGNAL_MAP.get(dsa.signal, SignalType.HOLD)

        if apex_signal == dsa_signal:
            # 信号一致
            signal = apex.signal
            trend = self._fuse_trend(apex.trend, dsa.trend, w_apex, w_dsa)
        else:
            # 信号分歧，权重高的主导，但降级
            if w_apex > w_dsa:
                signal = self._demote_signal(apex.signal)
                trend = apex.trend
            else:
                signal = self._demote_signal(dsa.signal)
                trend = dsa.trend

        return signal, trend

    def _fuse_trend(self, apex_trend: str, dsa_trend: str, w_apex: float, w_dsa: float) -> str:
        """融合趋势判断"""
        # 如果趋势表述一致，直接采用
        if apex_trend == dsa_trend:
            return apex_trend

        # 否则采用权重高的
        return apex_trend if w_apex > w_dsa else dsa_trend

    def _demote_signal(self, signal: str) -> str:
        """信号降级 (分歧时保守处理)"""
        demotion_map = {
            "强烈买入": "买入",
            "买入": "观望",
            "观望": "观望",
            "卖出": "观望",
            "强烈卖出": "卖出",
            "强烈看多": "看多",
            "看多": "震荡",
            "震荡": "震荡",
            "看空": "震荡",
            "强烈看空": "看空",
        }
        return demotion_map.get(signal, "观望")

    def _generate_action_plan(
        self,
        fused_score: float,
        signal: str,
        consistency: float,
        apex: ApexResult,
        dsa: DSAResult,
    ) -> List[str]:
        """生成行动计划"""
        actions = []

        # 基于融合评分
        if fused_score >= 80:
            actions.append("🟢 评分优秀，可考虑建仓或加仓")
        elif fused_score >= 60:
            actions.append("🟡 评分良好，维持现有仓位")
        elif fused_score >= 40:
            actions.append("🟠 评分一般，谨慎操作")
        else:
            actions.append("🔴 评分偏低，考虑减仓或观望")

        # 基于信号
        if "买入" in signal:
            if dsa.buy_point:
                actions.append(f"💰 建议买入价位: {dsa.buy_point}")
            actions.append("📈 关注放量突破确认信号")
        elif "卖出" in signal:
            if dsa.sell_point:
                actions.append(f"💰 建议卖出价位: {dsa.sell_point}")
            actions.append("📉 设置止损位，控制回撤")

        # 基于一致性
        if consistency < 0.5:
            actions.append("⚠️ 双引擎分歧较大，建议等待更明确信号")

        # 合并检查清单
        if dsa.checklist:
            actions.extend([f"☑️ {item}" for item in dsa.checklist[:3]])

        # 风险提示
        if apex.warnings:
            actions.extend([f"🚨 {w}" for w in apex.warnings[:2]])
        if dsa.risks:
            actions.extend([f"🚨 {r}" for r in dsa.risks[:2]])

        return actions

    def _calculate_risk_level(
        self, fused_score: float, consistency: float, apex: ApexResult, dsa: DSAResult
    ) -> str:
        """计算风险等级"""
        risk_score = 0

        # 评分风险
        if fused_score < 30:
            risk_score += 3
        elif fused_score < 50:
            risk_score += 2
        elif fused_score < 70:
            risk_score += 1

        # 一致性风险
        if consistency < 0.3:
            risk_score += 2
        elif consistency < 0.6:
            risk_score += 1

        # 风险警报数量
        risk_count = len(apex.warnings or []) + len(dsa.risks or [])
        if risk_count >= 4:
            risk_score += 2
        elif risk_count >= 2:
            risk_score += 1

        if risk_score >= 5:
            return "🔴 高风险"
        elif risk_score >= 3:
            return "🟠 中高风险"
        elif risk_score >= 1:
            return "🟡 中低风险"
        else:
            return "🟢 低风险"

    def _record_history(self, result: FusedResult):
        """记录融合历史，用于后续动态调权"""
        self.history.append({
            "timestamp": result.timestamp,
            "fused_score": result.fused_score,
            "signal": result.signal,
            "consistency": result.consistency,
            "apex_score": result.apex_detail.score,
            "dsa_score": result.dsa_detail.score,
        })

        # 保持最近100条记录
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def get_performance_stats(self) -> Dict:
        """获取融合器性能统计"""
        if not self.history:
            return {"message": "暂无历史记录"}

        consistencies = [h["consistency"] for h in self.history]
        return {
            "total_fusions": len(self.history),
            "avg_consistency": round(sum(consistencies) / len(consistencies), 3),
            "high_consistency_rate": round(
                sum(1 for c in consistencies if c > 0.7) / len(consistencies) * 100, 1
            ),
            "low_consistency_rate": round(
                sum(1 for c in consistencies if c < 0.3) / len(consistencies) * 100, 1
            ),
        }

    def format_report(self, result: FusedResult) -> str:
        """格式化融合结果为可读报告"""
        lines = [
            "=" * 60,
            "🎯 玄甲双引擎融合决策报告",
            "=" * 60,
            f"",
            f"📊 融合评分: {result.fused_score}/100",
            f"📈 信号: {result.signal}",
            f"📉 趋势: {result.trend}",
            f"",
            f"🔍 引擎一致性: {result.consistency:.2f}",
            f"   APEX贡献: {result.apex_contribution * 100:.0f}%",
            f"   DSA贡献: {result.dsa_contribution * 100:.0f}%",
            f"",
            f"⚡ 风险等级: {result.risk_level}",
        ]

        if result.warning:
            lines.extend([f"", f"⚠️ 警告: {result.warning}"])

        lines.extend([
            f"",
            f"📋 行动计划:",
        ])
        for action in result.action_plan:
            lines.append(f"   {action}")

        lines.extend([
            f"",
            f"🔬 APEX引擎详情:",
            f"   评分: {result.apex_detail.score}",
            f"   信号: {result.apex_detail.signal}",
            f"   预测涨跌: {result.apex_detail.predicted_change:+.2f}%",
            f"   68%区间: [{result.apex_detail.interval_68[0]:+.2f}%, {result.apex_detail.interval_68[1]:+.2f}%]",
        ])

        lines.extend([
            f"",
            f"🤖 DSA引擎详情:",
            f"   评分: {result.dsa_detail.score}",
            f"   信号: {result.dsa_detail.signal}",
            f"   趋势: {result.dsa_detail.trend}",
        ])

        if result.dsa_detail.risks:
            lines.extend([f"   风险:", *[f"     - {r}" for r in result.dsa_detail.risks[:3]]])
        if result.dsa_detail.catalysts:
            lines.extend([f"   催化:", *[f"     + {c}" for c in result.dsa_detail.catalysts[:3]]])

        lines.extend([
            f"",
            f"{'=' * 60}",
            f"生成时间: {result.timestamp}",
            f"{'=' * 60}",
        ])

        return "\n".join(lines)


# ==================== 便捷函数 ====================

def quick_fuse(apex_dict: Dict, dsa_dict: Dict) -> FusedResult:
    """
    快速融合两个字典格式的结果

    Args:
        apex_dict: APEX引擎结果字典
        dsa_dict: DSA引擎结果字典

    Returns:
        FusedResult: 融合结果
    """
    apex = ApexResult(
        score=apex_dict.get("score", 50),
        signal=apex_dict.get("signal", "观望"),
        trend=apex_dict.get("trend", "震荡"),
        confidence=apex_dict.get("confidence", 0.5),
        predicted_change=apex_dict.get("predicted_change", 0),
        interval_68=apex_dict.get("interval_68", (-1, 1)),
        interval_95=apex_dict.get("interval_95", (-2, 2)),
        factors=apex_dict.get("factors", {}),
        warnings=apex_dict.get("warnings", []),
    )

    dsa = DSAResult(
        score=dsa_dict.get("score", 50),
        signal=dsa_dict.get("signal", "观望"),
        trend=dsa_dict.get("trend", "震荡"),
        confidence=dsa_dict.get("confidence", 0.5),
        buy_point=dsa_dict.get("buy_point"),
        sell_point=dsa_dict.get("sell_point"),
        risks=dsa_dict.get("risks", []),
        catalysts=dsa_dict.get("catalysts", []),
        checklist=dsa_dict.get("checklist", []),
    )

    fusion = DualEngineFusion()
    return fusion.fuse(apex, dsa)


# ==================== 测试 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Dual Engine Fusion - 双引擎融合器测试")
    print("=" * 60)

    # 测试场景1: 两引擎一致 (高一致性)
    print("\n📊 测试场景1: 两引擎一致")
    apex1 = ApexResult(
        score=75,
        signal="买入",
        trend="震·震荡上行",
        confidence=0.8,
        predicted_change=0.85,
        interval_68=(0.3, 1.4),
        interval_95=(-0.2, 1.9),
        factors={"inertia": 0.7, "volume": 0.8, "sentiment": 0.75},
        warnings=["量能未明显放大"],
    )
    dsa1 = DSAResult(
        score=72,
        signal="买入",
        trend="看多",
        confidence=0.75,
        buy_point=3380.0,
        sell_point=3450.0,
        risks=["上方3450压力"],
        catalysts=["政策利好", "资金流入"],
        checklist=["确认放量突破", "关注北向资金"],
    )

    fusion = DualEngineFusion()
    result1 = fusion.fuse(apex1, dsa1)
    print(fusion.format_report(result1))

    # 测试场景2: 两引擎分歧 (低一致性)
    print("\n" + "=" * 60)
    print("📊 测试场景2: 两引擎分歧")
    apex2 = ApexResult(
        score=35,
        signal="卖出",
        trend="兑·震荡下行",
        confidence=0.7,
        predicted_change=-0.95,
        interval_68=(-1.5, -0.4),
        interval_95=(-2.2, 0.3),
        factors={"inertia": 0.3, "volume": 0.2, "sentiment": 0.25},
        warnings=["缩量反弹", "顶背离"],
    )
    dsa2 = DSAResult(
        score=68,
        signal="买入",
        trend="看多",
        confidence=0.6,
        buy_point=3350.0,
        sell_point=3420.0,
        risks=["短期波动加大"],
        catalysts=["业绩超预期"],
        checklist=["等待回调企稳"],
    )

    result2 = fusion.fuse(apex2, dsa2)
    print(fusion.format_report(result2))

    # 性能统计
    print("\n" + "=" * 60)
    print("📈 融合器性能统计")
    print("=" * 60)
    stats = fusion.get_performance_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
