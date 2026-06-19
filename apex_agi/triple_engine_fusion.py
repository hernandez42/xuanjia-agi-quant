#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Triple Engine Fusion - 三引擎融合器
将 APEX_MAX 公式引擎 + DSA LLM决策引擎 + FinRL-Meta DRL引擎 三方融合

融合公式:
  Fused_Score = (APEX_Score * W_apex + DSA_Score * W_dsa + FinRL_Score * W_finrl) / (W_sum)
  Triple_Consistency = (C_ad + C_af + C_df) / 3

Author: XuanJia ApexAGI
Version: 1.0.0
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TripleEngineFusion")


# 复用双引擎融合器的枚举和基类
class SignalType(Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "观望"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"


@dataclass
class ApexResult:
    """APEX_MAX公式引擎输出"""
    score: float = 50.0
    signal: str = "观望"
    trend: str = "震荡"
    confidence: float = 0.5
    predicted_change: float = 0.0
    interval_68: Tuple[float, float] = (0.0, 0.0)
    interval_95: Tuple[float, float] = (0.0, 0.0)
    factors: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class DSAResult:
    """DSA LLM决策引擎输出"""
    score: float = 50.0
    signal: str = "观望"
    trend: str = "震荡"
    confidence: float = 0.5
    buy_point: Optional[float] = None
    sell_point: Optional[float] = None
    risks: List[str] = field(default_factory=list)
    catalysts: List[str] = field(default_factory=list)
    checklist: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class FinRLResult:
    """FinRL-Meta DRL引擎输出"""
    score: float = 50.0           # 基于DRL策略收益风险调整后的评分
    signal: str = "观望"           # 买入/观望/卖出
    trend: str = "震荡"            # DRL预测的趋势方向
    confidence: float = 0.5        # DRL策略的历史胜率
    predicted_return: float = 0.0  # DRL预测的期望收益率
    sharpe_ratio: float = 0.0      # DRL策略的夏普比率
    max_drawdown: float = 0.0      # DRL策略的最大回撤
    action_distribution: Dict[str, float] = field(default_factory=dict)  # 动作分布
    metadata: Dict = field(default_factory=dict)


@dataclass
class TripleFusedResult:
    """三引擎融合结果"""
    fused_score: float = 50.0
    signal: str = "观望"
    trend: str = "震荡"
    triple_consistency: float = 0.5   # 三引擎一致性 0-1
    apex_contribution: float = 0.33
    dsa_contribution: float = 0.33
    finrl_contribution: float = 0.34
    warning: Optional[str] = None
    apex_detail: ApexResult = field(default_factory=ApexResult)
    dsa_detail: DSAResult = field(default_factory=DSAResult)
    finrl_detail: FinRLResult = field(default_factory=FinRLResult)
    action_plan: List[str] = field(default_factory=list)
    risk_level: str = "中低风险"
    timestamp: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())


class TripleEngineFusion:
    """
    三引擎融合器

    核心算法:
    1. 三引擎一致性检查: 计算两两一致性的平均值
    2. 动态权重分配: 基于各自置信度和历史准确率
    3. 加权融合: 综合三引擎输出
    4. 多数投票: 信号采用多数意见
    5. 分歧处理: 严重分歧时标记人工复核
    """

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

    DEFAULT_WEIGHTS = {
        "apex_base": 0.35,       # APEX基础权重 (公式驱动，稳定性高)
        "dsa_base": 0.30,        # DSA基础权重 (LLM驱动，灵活性强)
        "finrl_base": 0.35,      # FinRL基础权重 (DRL驱动，自适应强)
        "consistency_boost": 0.1,   # 一致性奖励
        "divergence_penalty": 0.15, # 分歧惩罚
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.history: List[Dict] = []

    def fuse(self, apex_result: ApexResult, dsa_result: DSAResult, finrl_result: FinRLResult) -> TripleFusedResult:
        """
        融合三个引擎的输出

        Args:
            apex_result: APEX_MAX公式引擎结果
            dsa_result: DSA LLM决策引擎结果
            finrl_result: FinRL-Meta DRL引擎结果

        Returns:
            TripleFusedResult: 融合后的决策结果
        """
        logger.info("[TripleFusion] ===== 开始三引擎融合 =====")

        # 1. 三引擎一致性检查
        triple_consistency = self._check_triple_consistency(apex_result, dsa_result, finrl_result)
        logger.info(f"[TripleFusion] 三引擎一致性: {triple_consistency:.2f}")

        # 2. 动态权重计算
        w_apex, w_dsa, w_finrl = self._calculate_dynamic_weights(
            apex_result, dsa_result, finrl_result, triple_consistency
        )
        logger.info(f"[TripleFusion] 动态权重 - APEX: {w_apex:.2f}, DSA: {w_dsa:.2f}, FinRL: {w_finrl:.2f}")

        # 3. 加权融合评分
        fused_score = self._fuse_score(apex_result.score, dsa_result.score, finrl_result.score, w_apex, w_dsa, w_finrl)
        logger.info(f"[TripleFusion] 融合评分: {fused_score:.1f}")

        # 4. 信号融合 (多数投票)
        signal, trend = self._fuse_signal(apex_result, dsa_result, finrl_result, w_apex, w_dsa, w_finrl)

        # 5. 分歧处理
        warning = None
        if triple_consistency < 0.3:
            warning = f"⚠️ 三引擎严重分歧 (一致性={triple_consistency:.2f})，建议人工复核"
            logger.warning(f"[TripleFusion] {warning}")
        elif triple_consistency < 0.6:
            warning = f"⚡ 三引擎轻度分歧 (一致性={triple_consistency:.2f})，谨慎决策"

        # 6. 生成行动计划
        action_plan = self._generate_action_plan(fused_score, signal, triple_consistency, apex_result, dsa_result, finrl_result)

        # 7. 风险等级
        risk_level = self._calculate_risk_level(fused_score, triple_consistency, apex_result, dsa_result, finrl_result)

        result = TripleFusedResult(
            fused_score=round(fused_score, 1),
            signal=signal,
            trend=trend,
            triple_consistency=round(triple_consistency, 2),
            apex_contribution=round(w_apex / (w_apex + w_dsa + w_finrl), 2),
            dsa_contribution=round(w_dsa / (w_apex + w_dsa + w_finrl), 2),
            finrl_contribution=round(w_finrl / (w_apex + w_dsa + w_finrl), 2),
            warning=warning,
            apex_detail=apex_result,
            dsa_detail=dsa_result,
            finrl_detail=finrl_result,
            action_plan=action_plan,
            risk_level=risk_level,
        )

        self._record_history(result)
        logger.info("[TripleFusion] ===== 三引擎融合完成 =====")
        return result

    def _check_triple_consistency(self, apex: ApexResult, dsa: DSAResult, finrl: FinRLResult) -> float:
        """
        计算三引擎一致性 (0-1)

        算法: 两两一致性取平均
        """
        c_ad = self._pair_consistency(apex.score, dsa.score, apex.signal, dsa.signal)
        c_af = self._pair_consistency(apex.score, finrl.score, apex.signal, finrl.signal)
        c_df = self._pair_consistency(dsa.score, finrl.score, dsa.signal, finrl.signal)

        consistency = (c_ad + c_af + c_df) / 3.0
        logger.info(f"[TripleFusion] 两两一致性: A-D={c_ad:.2f}, A-F={c_af:.2f}, D-F={c_df:.2f}")
        return consistency

    def _pair_consistency(self, s1: float, s2: float, sig1: str, sig2: str) -> float:
        """计算两个引擎之间的一致性"""
        score_diff = abs(s1 - s2) / 100.0
        score_penalty = score_diff * 0.5

        sig1_mapped = self.SIGNAL_MAP.get(sig1, SignalType.HOLD)
        sig2_mapped = self.SIGNAL_MAP.get(sig2, SignalType.HOLD)
        signal_match = 0.5 if sig1_mapped == sig2_mapped else 0.0

        return max(0.0, min(1.0, 1.0 - score_penalty + signal_match))

    def _calculate_dynamic_weights(
        self, apex: ApexResult, dsa: DSAResult, finrl: FinRLResult, consistency: float
    ) -> Tuple[float, float, float]:
        """
        计算动态权重

        策略:
        - 基础权重: APEX 0.35, DSA 0.30, FinRL 0.35
        - 根据各自置信度微调
        - 一致性高时奖励，低时惩罚最低置信度引擎
        """
        w_apex = self.weights["apex_base"]
        w_dsa = self.weights["dsa_base"]
        w_finrl = self.weights["finrl_base"]

        # 根据置信度微调
        apex_conf = apex.confidence if apex.confidence else 0.5
        dsa_conf = dsa.confidence if dsa.confidence else 0.5
        finrl_conf = finrl.confidence if finrl.confidence else 0.5

        total_conf = apex_conf + dsa_conf + finrl_conf
        if total_conf > 0:
            w_apex = self.weights["apex_base"] * (apex_conf / total_conf) * 3
            w_dsa = self.weights["dsa_base"] * (dsa_conf / total_conf) * 3
            w_finrl = self.weights["finrl_base"] * (finrl_conf / total_conf) * 3

        # 一致性奖励/惩罚
        if consistency > 0.7:
            boost = self.weights["consistency_boost"]
            w_apex += boost * 0.33
            w_dsa += boost * 0.33
            w_finrl += boost * 0.34
        elif consistency < 0.3:
            penalty = self.weights["divergence_penalty"]
            confs = {"apex": apex_conf, "dsa": dsa_conf, "finrl": finrl_conf}
            lowest = min(confs, key=confs.get)
            if lowest == "apex":
                w_apex = max(0.1, w_apex - penalty)
                w_dsa += penalty * 0.5
                w_finrl += penalty * 0.5
            elif lowest == "dsa":
                w_dsa = max(0.1, w_dsa - penalty)
                w_apex += penalty * 0.5
                w_finrl += penalty * 0.5
            else:
                w_finrl = max(0.1, w_finrl - penalty)
                w_apex += penalty * 0.5
                w_dsa += penalty * 0.5

        return w_apex, w_dsa, w_finrl

    def _fuse_score(self, apex_score: float, dsa_score: float, finrl_score: float,
                    w_apex: float, w_dsa: float, w_finrl: float) -> float:
        """加权融合评分"""
        total_weight = w_apex + w_dsa + w_finrl
        if total_weight == 0:
            return (apex_score + dsa_score + finrl_score) / 3
        return (apex_score * w_apex + dsa_score * w_dsa + finrl_score * w_finrl) / total_weight

    def _fuse_signal(self, apex: ApexResult, dsa: DSAResult, finrl: FinRLResult,
                     w_apex: float, w_dsa: float, w_finrl: float) -> Tuple[str, str]:
        """
        信号融合 (多数投票)

        策略:
        - 三引擎一致: 直接采用
        - 两引擎一致: 采用多数意见，但降级处理
        - 三引擎分歧: 权重最高的主导，降级为观望
        """
        apex_sig = self.SIGNAL_MAP.get(apex.signal, SignalType.HOLD)
        dsa_sig = self.SIGNAL_MAP.get(dsa.signal, SignalType.HOLD)
        finrl_sig = self.SIGNAL_MAP.get(finrl.signal, SignalType.HOLD)

        signals = [apex_sig, dsa_sig, finrl_sig]

        # 统计各信号出现次数
        from collections import Counter
        sig_counts = Counter(signals)
        most_common = sig_counts.most_common(1)[0]

        if most_common[1] >= 2:
            # 多数一致
            signal = most_common[0].value
            trend = self._fuse_trend(apex.trend, dsa.trend, finrl.trend, w_apex, w_dsa, w_finrl)
        else:
            # 三引擎全分歧，取权重最高的
            weights = {"apex": w_apex, "dsa": w_dsa, "finrl": w_finrl}
            dominant = max(weights, key=weights.get)
            if dominant == "apex":
                signal = self._demote_signal(apex.signal)
                trend = apex.trend
            elif dominant == "dsa":
                signal = self._demote_signal(dsa.signal)
                trend = dsa.trend
            else:
                signal = self._demote_signal(finrl.signal)
                trend = finrl.trend

        return signal, trend

    def _fuse_trend(self, apex_trend: str, dsa_trend: str, finrl_trend: str,
                    w_apex: float, w_dsa: float, w_finrl: float) -> str:
        """融合趋势判断"""
        trends = [apex_trend, dsa_trend, finrl_trend]
        if trends[0] == trends[1] == trends[2]:
            return trends[0]

        # 权重最高的趋势
        weights = {"apex": w_apex, "dsa": w_dsa, "finrl": w_finrl}
        dominant = max(weights, key=weights.get)
        return {"apex": apex_trend, "dsa": dsa_trend, "finrl": finrl_trend}[dominant]

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

    def _generate_action_plan(self, fused_score: float, signal: str, consistency: float,
                              apex: ApexResult, dsa: DSAResult, finrl: FinRLResult) -> List[str]:
        """生成行动计划"""
        actions = []

        # 基于融合评分
        if fused_score >= 80:
            actions.append("🟢 三引擎共振，评分优秀，可考虑建仓")
        elif fused_score >= 65:
            actions.append("🟡 评分良好，维持现有仓位")
        elif fused_score >= 40:
            actions.append("🟠 评分一般，谨慎操作")
        else:
            actions.append("🔴 评分偏低，考虑减仓或观望")

        # 基于信号
        if "买入" in signal:
            if dsa.buy_point:
                actions.append(f"💰 建议买入价位: {dsa.buy_point}")
            actions.append("📈 关注放量突破确认")
        elif "卖出" in signal:
            if dsa.sell_point:
                actions.append(f"💰 建议卖出价位: {dsa.sell_point}")
            actions.append("📉 设置止损位")

        # 基于一致性
        if consistency < 0.5:
            actions.append("⚠️ 三引擎分歧较大，建议等待更明确信号")
        elif consistency > 0.8:
            actions.append("✅ 三引擎高度一致，信号可信度高")

        # DRL特有信息
        if finrl.sharpe_ratio > 1.5:
            actions.append(f"🤖 DRL策略夏普比率优秀({finrl.sharpe_ratio:.2f})")
        if finrl.max_drawdown > 0.15:
            actions.append(f"⚠️ DRL策略最大回撤较大({finrl.max_drawdown:.1%})")

        # 合并检查清单
        if dsa.checklist:
            actions.extend([f"☑️ {item}" for item in dsa.checklist[:2]])

        # 风险提示
        if apex.warnings:
            actions.extend([f"🚨 {w}" for w in apex.warnings[:2]])
        if dsa.risks:
            actions.extend([f"🚨 {r}" for r in dsa.risks[:2]])

        return actions

    def _calculate_risk_level(self, fused_score: float, consistency: float,
                              apex: ApexResult, dsa: DSAResult, finrl: FinRLResult) -> str:
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

        # DRL策略风险
        if finrl.max_drawdown > 0.2:
            risk_score += 2
        elif finrl.max_drawdown > 0.1:
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

    def _record_history(self, result: TripleFusedResult):
        """记录融合历史"""
        self.history.append({
            "timestamp": result.timestamp,
            "fused_score": result.fused_score,
            "signal": result.signal,
            "triple_consistency": result.triple_consistency,
            "apex_score": result.apex_detail.score,
            "dsa_score": result.dsa_detail.score,
            "finrl_score": result.finrl_detail.score,
        })
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def get_performance_stats(self) -> Dict:
        """获取融合器性能统计"""
        if not self.history:
            return {"message": "暂无历史记录"}

        consistencies = [h["triple_consistency"] for h in self.history]
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

    def format_report(self, result: TripleFusedResult) -> str:
        """格式化融合结果为可读报告"""
        lines = [
            "=" * 60,
            "🎯 玄甲三引擎融合决策报告",
            "=" * 60,
            f"",
            f"📊 融合评分: {result.fused_score}/100",
            f"📈 信号: {result.signal}",
            f"📉 趋势: {result.trend}",
            f"",
            f"🔍 三引擎一致性: {result.triple_consistency:.2f}",
            f"   APEX贡献: {result.apex_contribution * 100:.0f}%",
            f"   DSA贡献: {result.dsa_contribution * 100:.0f}%",
            f"   FinRL贡献: {result.finrl_contribution * 100:.0f}%",
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
            f"🔬 APEX引擎: 评分={result.apex_detail.score} 信号={result.apex_detail.signal} 预测={result.apex_detail.predicted_change:+.2f}%",
            f"🤖 DSA引擎:  评分={result.dsa_detail.score} 信号={result.dsa_detail.signal} 趋势={result.dsa_detail.trend}",
            f"🧠 FinRL引擎: 评分={result.finrl_detail.score} 信号={result.finrl_detail.signal} 夏普={result.finrl_detail.sharpe_ratio:.2f} 回撤={result.finrl_detail.max_drawdown:.1%}",
            f"",
            f"{'=' * 60}",
            f"生成时间: {result.timestamp}",
            f"{'=' * 60}",
        ])

        return "\n".join(lines)


# ==================== 便捷函数 ====================

def quick_triple_fuse(apex_dict: Dict, dsa_dict: Dict, finrl_dict: Dict) -> TripleFusedResult:
    """快速融合三个字典格式的结果"""
    apex = ApexResult(
        score=apex_dict.get("score", 50),
        signal=apex_dict.get("signal", "观望"),
        trend=apex_dict.get("trend", "震荡"),
        confidence=apex_dict.get("confidence", 0.5),
        predicted_change=apex_dict.get("predicted_change", 0),
        interval_68=apex_dict.get("interval_68", (0, 0)),
        interval_95=apex_dict.get("interval_95", (0, 0)),
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

    finrl = FinRLResult(
        score=finrl_dict.get("score", 50),
        signal=finrl_dict.get("signal", "观望"),
        trend=finrl_dict.get("trend", "震荡"),
        confidence=finrl_dict.get("confidence", 0.5),
        predicted_return=finrl_dict.get("predicted_return", 0),
        sharpe_ratio=finrl_dict.get("sharpe_ratio", 0),
        max_drawdown=finrl_dict.get("max_drawdown", 0),
        action_distribution=finrl_dict.get("action_distribution", {}),
    )

    fusion = TripleEngineFusion()
    return fusion.fuse(apex, dsa, finrl)


# ==================== 测试 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Triple Engine Fusion - 三引擎融合器测试")
    print("=" * 60)

    fusion = TripleEngineFusion()

    # 测试场景1: 三引擎一致 (高一致性)
    print("\n📊 测试场景1: 三引擎一致 (看多)")
    apex1 = ApexResult(score=75, signal="买入", trend="震·震荡上行", confidence=0.8, predicted_change=0.85)
    dsa1 = DSAResult(score=72, signal="买入", trend="看多", confidence=0.75, risks=["上方压力"])
    finrl1 = FinRLResult(score=78, signal="买入", trend="看多", confidence=0.82, predicted_return=0.92, sharpe_ratio=1.8, max_drawdown=0.08)

    result1 = fusion.fuse(apex1, dsa1, finrl1)
    print(fusion.format_report(result1))

    # 测试场景2: 三引擎分歧
    print("\n" + "=" * 60)
    print("📊 测试场景2: 三引擎分歧")
    apex2 = ApexResult(score=35, signal="卖出", trend="兑·震荡下行", confidence=0.7, predicted_change=-0.95)
    dsa2 = DSAResult(score=68, signal="买入", trend="看多", confidence=0.6, risks=["波动加大"])
    finrl2 = FinRLResult(score=55, signal="观望", trend="震荡", confidence=0.5, predicted_return=0.1, sharpe_ratio=0.8, max_drawdown=0.15)

    result2 = fusion.fuse(apex2, dsa2, finrl2)
    print(fusion.format_report(result2))

    # 测试场景3: 两引擎一致，一引擎分歧
    print("\n" + "=" * 60)
    print("📊 测试场景3: APEX+DSA一致，FinRL分歧")
    apex3 = ApexResult(score=70, signal="买入", trend="震·震荡上行", confidence=0.75, predicted_change=0.65)
    dsa3 = DSAResult(score=68, signal="买入", trend="看多", confidence=0.7, risks=[])
    finrl3 = FinRLResult(score=40, signal="卖出", trend="看空", confidence=0.4, predicted_return=-0.5, sharpe_ratio=0.5, max_drawdown=0.2)

    result3 = fusion.fuse(apex3, dsa3, finrl3)
    print(fusion.format_report(result3))

    # 性能统计
    print("\n" + "=" * 60)
    print("📈 融合器性能统计")
    print("=" * 60)
    stats = fusion.get_performance_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
