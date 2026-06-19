#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Superpower × X-God Strategy 化学反应融合引擎
将 Superpowers 验证体系与 X大神4步策略引擎叠加，产生"1+1>2"的化学反应

化学反应方程式:
  X_God(4步闭环) + Superpowers(10维验证) + TripleEngine(三引擎融合)
  = Fusion_Engine(四维进化策略)

核心反应:
  1. 催化反应: Superpowers验证 → 自动修正策略参数
  2. 链式反应: X-God选股 → TripleEngine评分 → Superpowers验证 → 动态调参
  3. 共振效应: 四引擎一致性 > 三引擎一致性，置信度提升
  4. 负反馈: 验证失败 → 自动降级权重 → 触发红队重审
"""

import json
import sys
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x_god_strategy import XGodStrategyEngine, StockCandidate, PRESET_UNIVERSE
from triple_engine_fusion import TripleEngineFusion, ApexResult, DSAResult, FinRLResult, TripleFusedResult
from multi_factor_model import FactorLibrary, MultiFactorSelector


@dataclass
class SuperpowerFusionResult:
    """Superpower融合结果"""
    stock_code: str
    stock_name: str
    # 五维评分（新增多因子深度评分）
    x_god_score: float = 0.0           # X大神基础分
    superpower_score: float = 0.0      # Superpower验证分
    triple_engine_score: float = 0.0   # 三引擎融合分
    multi_factor_score: float = 0.0    # 72因子深度评分（第四波新增）
    fusion_score: float = 0.0          # 最终融合分
    # 一致性
    four_way_consistency: float = 0.0  # 四引擎一致性
    five_way_consistency: float = 0.0   # 五维一致性（新增）
    # 信号
    signal: str = "观望"
    trend: str = "震荡"
    confidence: float = 0.0
    # 化学反应标记
    reaction_type: str = ""            # 催化/链式/共振/负反馈/因子共振
    catalyst_boost: float = 0.0        # 催化加成
    # 因子共振标记（第四波新增）
    factor_resonance_count: int = 0    # 强信号因子数
    factor_positive_ratio: float = 0.0 # 正向因子占比
    # 行动建议
    action_plan: List[str] = field(default_factory=list)
    risk_level: str = "中低风险"
    # 元数据
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SuperpowerFusionEngine:
    """
    Superpower × X-God 化学反应融合引擎

    化学反应机制:
    1. 催化反应 (Catalysis): Superpowers验证通过 → 自动提升该标的权重
    2. 链式反应 (Chain): X-God选股 → 三引擎评分 → Superpowers验证 → 参数自动修正
    3. 共振效应 (Resonance): 四引擎一致时，置信度呈指数级提升
    4. 负反馈 (Negative Feedback): 验证失败 → 权重降级 → 红队重审
    """

    # 化学反应参数
    CATALYST_BOOST = 0.15              # 催化加成系数
    RESONANCE_MULTIPLIER = 1.25        # 共振乘数
    NEGATIVE_FEEDBACK_PENALTY = 0.20   # 负反馈惩罚
    CHAIN_REACTION_BONUS = 0.10        # 链式反应奖励

    def __init__(self):
        self.x_god = XGodStrategyEngine()
        self.triple = TripleEngineFusion()
        self.factor_lib = FactorLibrary()  # 72因子库（第四波新增）
        self.factor_selector = MultiFactorSelector()
        self.verification_cache: Dict[str, Dict] = {}
        self.reaction_history: List[Dict] = []

    def fuse(self, stock: StockCandidate) -> SuperpowerFusionResult:
        """
        执行Superpower × X-God化学反应融合

        流程:
        1. X-God 4步策略评分
        2. 模拟三引擎评分 (APEX + DSA + FinRL)
        3. Superpowers验证
        4. 化学反应融合
        """
        # Step 1: X-God评分
        x_god_result = self.x_god.beyond_x_fusion(stock)
        x_score = x_god_result["beyond_x_score"]

        # Step 2: 模拟三引擎结果
        apex_result = self._simulate_apex(stock, x_god_result)
        dsa_result = self._simulate_dsa(stock, x_god_result)
        finrl_result = self._simulate_finrl(stock, x_god_result)

        # Step 3: 三引擎融合 (直接计算，避免权重压缩)
        triple_result = self.triple.fuse(apex_result, dsa_result, finrl_result)
        # 直接使用三引擎原始评分均值，避免融合器权重压缩
        triple_score = (apex_result.score + dsa_result.score + finrl_result.score) / 3.0

        # Step 4: Superpowers验证
        sp_score = self._run_superpower_verification(stock, x_god_result, triple_result)

        # Step 5: 72因子深度评分（第四波新增）
        mf_score, factor_resonance, factor_positive = self._compute_multi_factor_deep_score(
            stock, x_god_result
        )

        # Step 6: 化学反应融合（五维）
        fusion = self._chemical_reaction(
            stock, x_score, triple_score, sp_score, mf_score,
            triple_result.triple_consistency, x_god_result["confidence"],
            factor_resonance, factor_positive
        )

        return fusion

    def _simulate_apex(self, stock: StockCandidate, x_result: Dict) -> ApexResult:
        """模拟APEX公式引擎结果 - 对齐X-God评分"""
        base = x_result["beyond_x_score"]
        return ApexResult(
            score=base,
            signal="买入" if base > 55 else "观望",
            trend="看多" if base > 50 else "震荡",
            confidence=x_result["confidence"] / 100,
            factors={
                "localization_rate": stock.localization_rate,
                "expansion_cycle": stock.expansion_cycle_months,
                "monopoly_score": stock.monopoly_score,
            }
        )

    def _simulate_dsa(self, stock: StockCandidate, x_result: Dict) -> DSAResult:
        """模拟DSA LLM引擎结果 - 对齐X-God评分"""
        base = x_result["beyond_x_score"]
        dsa_score = base
        if stock.analyst_reports_count <= 3:
            dsa_score += 3  # 冷门预期差微调
        return DSAResult(
            score=dsa_score,
            signal="买入" if dsa_score > 55 else "观望",
            trend="看多" if dsa_score > 50 else "震荡",
            confidence=0.75 if stock.analyst_reports_count <= 5 else 0.60,
            catalysts=["国产替代加速", "毛利率连续扩张"] if stock.gross_margin_history and stock.gross_margin_history[-1] > stock.gross_margin_history[0] else [],
            risks=["客户自研风险"] if stock.localization_rate > 15 else []
        )

    def _simulate_finrl(self, stock: StockCandidate, x_result: Dict) -> FinRLResult:
        """模拟FinRL DRL引擎结果 - 对齐X-God评分"""
        base = x_result["beyond_x_score"]
        finrl_score = base
        if stock.market_cap < 50:
            finrl_score += 2  # 小盘弹性微调
        return FinRLResult(
            score=finrl_score,
            signal="买入" if finrl_score > 55 else "观望",
            trend="看多" if finrl_score > 50 else "震荡",
            confidence=0.70,
            predicted_return=(finrl_score - 50) * 0.2,
            sharpe_ratio=1.2 if finrl_score > 55 else 0.8,
            max_drawdown=12.0 if finrl_score > 55 else 18.0,
        )

    def _run_superpower_verification(self, stock: StockCandidate,
                                     x_result: Dict, triple_result: TripleFusedResult) -> float:
        """
        运行Superpowers验证
        返回验证得分 (0-100)
        """
        score = 100.0
        checks_passed = 0
        total_checks = 6

        # Check 1: X-God基础分 > 50
        if x_result["beyond_x_score"] >= 50:
            checks_passed += 1
        else:
            score -= 15

        # Check 2: 三引擎一致性 > 0.5
        if triple_result.triple_consistency >= 0.5:
            checks_passed += 1
        else:
            score -= 10

        # Check 3: 置信度 > 80%
        if x_result["confidence"] >= 80:
            checks_passed += 1
        else:
            score -= 10

        # Check 4: 无CRITICAL风险
        red_team = self.x_god.red_team_reports.get(stock.code)
        if red_team and red_team.risk_level != "CRITICAL":
            checks_passed += 1
        else:
            score -= 20

        # Check 5: 市值在范围内
        if 30 <= stock.market_cap <= 150:
            checks_passed += 1
        else:
            score -= 10

        # Check 6: 国产化率 < 20%
        if stock.localization_rate < 20:
            checks_passed += 1
        else:
            score -= 10

        # 额外奖励
        if checks_passed == total_checks:
            score = min(100, score + 10)  # 全通过奖励

        self.verification_cache[stock.code] = {
            "checks_passed": checks_passed,
            "total_checks": total_checks,
            "score": max(0, score)
        }

        return max(0, score)

    def _compute_multi_factor_deep_score(self, stock: StockCandidate,
                                          x_result: Dict) -> Tuple[float, int, float]:
        """
        72因子深度评分（第四波新增）

        基于X-God策略的ohlc数据模拟72因子计算，返回:
        - 综合评分 (0-100)
        - 强信号因子数 (|factor| > 0.3)
        - 正向因子占比

        因子映射: 将StockCandidate属性映射到FactorLibrary所需的数据格式
        """
        # 构建因子计算所需的数据字典
        # StockCandidate属性: code, name, market_cap, sector, localization_rate,
        #   expansion_cycle_months, gross_margin_history, analyst_reports_count,
        #   monopoly_score, risk_flags, milestones, apex_score
        # 使用market_cap和sector模拟价格相关数据
        sim_price = 50.0 + stock.market_cap * 0.3  # 模拟股价
        sim_volume = int(stock.market_cap * 1000)  # 模拟成交量

        factor_data = {
            "close": sim_price,
            "open": sim_price * 0.98,
            "high": sim_price * 1.02,
            "low": sim_price * 0.96,
            "volume": sim_volume,
            "amount": sim_volume * sim_price / 10000,
            "closes": [sim_price * (1 - 0.01 * i) for i in range(20, 0, -1)] + [sim_price],
            "volumes": [sim_volume] * 20,
            # 基本面
            "pe": 30 + (100 - stock.localization_rate) * 0.5,
            "pb": 3.0,
            "ps": 5.0,
            "roe": 15 + stock.localization_rate * 0.3,
            "revenue_growth": 20 + stock.localization_rate * 0.5,
            "gross_margin": stock.gross_margin_history[-1] if stock.gross_margin_history else 40,
            "debt_ratio": 35,
            # 资金
            "main_net_inflow": 1.0 + stock.monopoly_score * 0.2,
            "turnover_rate": 5.0,
            # 情绪
            "limit_up_count": 5,
            "limit_down_count": 2,
            "search_heat": 60,
            # 技术形态
            "stock_change_pct": 2.5,
            "sector_change_pct": 1.5,
            "market_change_pct": 0.5,
            "industry_change_pct": 1.5,
            # 背离预警
            "profit_ratio": 70 + stock.localization_rate * 0.5,
            "holder_count_change_pct": -5,
            # 事件驱动
            "actual_eps": 1.0,
            "expected_eps": 0.8,
            "inst_position_change_pct": 2.0,
            "has_major_contract": stock.monopoly_score > 5,
            "insider_trading_signal": 0.3,
            "market_total_volume": 33101,
            # 宏观
            "policy_signal": 1.0,
            "us_market_change_pct": -0.3,
            # 机构暗盘
            "total_amount": sim_volume * sim_price / 10000,
            "large_order_amount": sim_volume * sim_price / 20000,
            "active_buy_volume": sim_volume * 0.55,
            "active_sell_volume": sim_volume * 0.45,
            "vwap": sim_price * 0.99,
            # 舆情NLP
            "news_sentiment_score": 0.5,
            "social_heat": 50000,
            "avg_social_heat": 30000,
            "actual_revenue_growth": 20,
            "consensus_revenue_growth": 15,
            # 分域适配
            "factor_score_5d": 0.1,
            "factor_score_20d": 0.05,
            "stock_return_20d": 15,
            "industry_return_20d": 10,
            # 微观结构
            "bid_ask_spread_pct": 1.0,
            "buy_depth_5": sim_volume * 0.3,
            "sell_depth_5": sim_volume * 0.25,
            "tick_count": 2000,
            "avg_tick_count": 1500,
            # 第四波 — 杠杆资金
            "margin_net_buy": 3000,
            "margin_balance": 30000,
            "float_market_cap": stock.market_cap * 10000,
            "short_balance": 1000,
            "margin_net_buy_5d_ago": 1500,
            "stock_change_pct_5d": 3.0,
            # 第四波 — 龙虎榜
            "institution_net_buy": 2000,
            "hot_money_seats": 1,
            "total_seats": 4,
            "dragon_buy_amount": 5000,
            "dragon_sell_amount": 3000,
            "is_first_dragon_tiger": False,
            "institution_new_entry": stock.localization_rate > 10,
            # 第四波 — 集合竞价与尾盘
            "prev_close": sim_price / 1.025,
            "auction_volume": sim_volume * 0.05,
            "price_30min_ago": sim_price * 0.98,
            "tail_volume": sim_volume * 0.2,
            # 第四波 — 专利与创新
            "patent_count": 30,
            "market_cap": stock.market_cap,
            "rd_ratio_current": 5.0,
            "rd_ratio_yoy": 4.5,
            "has_tech_breakthrough": stock.localization_rate > 10,
            "breakthrough_impact": 3 if stock.localization_rate > 10 else 0,
            "patent_citations": 100,
            "industry_avg_citations": 60,
        }

        # 计算全部72因子
        all_factors = self.factor_lib.compute_all_factors(factor_data)

        # 统计强信号和方向
        strong_count = 0
        positive_count = 0
        total_count = len(all_factors)

        for fname, fval in all_factors.items():
            if abs(fval) > 0.3:
                strong_count += 1
            if fval > 0.1:
                positive_count += 1

        positive_ratio = positive_count / total_count if total_count > 0 else 0

        # 综合评分: 基于强信号因子数和正向占比
        # 满分100 = 强信号因子数权重(50) + 正向占比权重(30) + X-God对齐权重(20)
        signal_score = min(50, strong_count * 2.5)  # 最多20个强信号=50分
        direction_score = positive_ratio * 30  # 正向占比映射到0-30分
        alignment_score = min(20, (x_result["beyond_x_score"] / 168) * 20)  # X-God对齐

        total_mf_score = signal_score + direction_score + alignment_score

        return total_mf_score, strong_count, positive_ratio

    def _chemical_reaction(self, stock: StockCandidate,
                           x_score: float, triple_score: float,
                           sp_score: float, mf_score: float,
                           triple_consistency: float,
                           x_confidence: float,
                           factor_resonance: int = 0,
                           factor_positive: float = 0.0) -> SuperpowerFusionResult:
        """
        化学反应融合核心算法（五维升级版）

        反应类型判定:
        - 因子共振: 72因子中>15个强信号 + 正向占比>60%（第四波新增）
        - 催化: Superpowers验证通过 + 三引擎一致
        - 链式: 多条件连续满足，产生连锁加成
        - 共振: 四引擎高度一致，置信度指数提升
        - 负反馈: 验证失败或分歧严重，触发降级
        """
        # 基础融合分 (五维加权，新增多因子深度评分)
        base_fusion = (
            x_score * 0.25 +
            triple_score * 0.20 +
            sp_score * 0.20 +
            mf_score * 0.25 +
            x_confidence * 0.10
        )

        # 四引擎一致性（保留兼容）
        four_way_consistency = self._calculate_four_way_consistency(
            x_score, triple_score, sp_score, x_confidence
        )

        # 五维一致性（新增）
        five_way_consistency = self._calculate_five_way_consistency(
            x_score, triple_score, sp_score, mf_score, x_confidence
        )

        # 判定化学反应类型（新增因子共振优先级）
        reaction_type = ""
        catalyst_boost = 0.0

        if factor_resonance >= 15 and factor_positive > 0.6:
            # 因子共振: 72因子中大量强信号一致看多（第四波新增）
            reaction_type = "因子共振"
            catalyst_boost = 0.20 * (factor_positive)
            base_fusion *= (1 + catalyst_boost)

        elif sp_score >= 90 and triple_consistency >= 0.7:
            # 催化反应: 验证通过 + 三引擎一致
            reaction_type = "催化反应"
            catalyst_boost = self.CATALYST_BOOST * (sp_score / 100)
            base_fusion *= (1 + catalyst_boost)

        elif four_way_consistency >= 0.8:
            # 共振效应: 四引擎高度一致
            reaction_type = "共振效应"
            base_fusion *= self.RESONANCE_MULTIPLIER

        elif sp_score < 60 or triple_consistency < 0.3:
            # 负反馈: 验证失败或严重分歧
            reaction_type = "负反馈"
            base_fusion *= (1 - self.NEGATIVE_FEEDBACK_PENALTY)

        elif x_score > 55 and triple_score > 55 and sp_score > 70:
            # 链式反应: 多条件连续满足
            reaction_type = "链式反应"
            base_fusion *= (1 + self.CHAIN_REACTION_BONUS)

        else:
            reaction_type = "常规融合"

        # 最终融合分
        fusion_score = min(100, base_fusion)

        # 信号判定
        signal = self._determine_signal(fusion_score, reaction_type)
        trend = self._determine_trend(fusion_score, reaction_type)

        # 置信度
        confidence = self._calculate_fusion_confidence(
            four_way_consistency, sp_score, reaction_type
        )

        # 行动建议
        action_plan = self._generate_action_plan(
            stock, fusion_score, signal, reaction_type, confidence
        )

        # 风险等级
        risk_level = self._determine_risk_level(
            fusion_score, reaction_type, sp_score
        )

        return SuperpowerFusionResult(
            stock_code=stock.code,
            stock_name=stock.name,
            x_god_score=round(x_score, 2),
            superpower_score=round(sp_score, 2),
            triple_engine_score=round(triple_score, 2),
            multi_factor_score=round(mf_score, 2),
            fusion_score=round(fusion_score, 2),
            four_way_consistency=round(four_way_consistency, 2),
            five_way_consistency=round(five_way_consistency, 2),
            signal=signal,
            trend=trend,
            confidence=round(confidence, 2),
            reaction_type=reaction_type,
            catalyst_boost=round(catalyst_boost, 3),
            factor_resonance_count=factor_resonance,
            factor_positive_ratio=round(factor_positive, 3),
            action_plan=action_plan,
            risk_level=risk_level,
        )

    def _calculate_four_way_consistency(self, x_score: float,
                                        triple_score: float,
                                        sp_score: float,
                                        x_confidence: float) -> float:
        """计算四引擎一致性"""
        scores = [x_score, triple_score, sp_score, x_confidence]
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        # 一致性 = 1 - 标准化标准差
        consistency = max(0, 1 - std_dev / 50)
        return consistency

    def _calculate_five_way_consistency(self, x_score: float,
                                         triple_score: float,
                                         sp_score: float,
                                         mf_score: float,
                                         x_confidence: float) -> float:
        """计算五维一致性（第四波新增）"""
        scores = [x_score, triple_score, sp_score, mf_score, x_confidence]
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        consistency = max(0, 1 - std_dev / 50)
        return consistency

    def _determine_signal(self, fusion_score: float, reaction_type: str) -> str:
        """判定交易信号"""
        if reaction_type == "负反馈":
            return "观望"
        if fusion_score >= 75:
            return "强烈买入"
        elif fusion_score >= 60:
            return "买入"
        elif fusion_score >= 45:
            return "观望"
        else:
            return "回避"

    def _determine_trend(self, fusion_score: float, reaction_type: str) -> str:
        """判定趋势"""
        if reaction_type in ["因子共振", "催化反应", "共振效应", "链式反应"]:
            return "强烈看多"
        elif fusion_score >= 60:
            return "看多"
        elif fusion_score >= 45:
            return "震荡偏多"
        else:
            return "震荡"

    def _calculate_fusion_confidence(self, four_way_consistency: float,
                                     sp_score: float, reaction_type: str) -> float:
        """计算融合置信度"""
        base_conf = four_way_consistency * 100
        if reaction_type == "共振效应":
            base_conf *= 1.2
        elif reaction_type == "因子共振":
            base_conf *= 1.25  # 因子共振置信度更高
        elif reaction_type == "催化反应":
            base_conf *= 1.15
        elif reaction_type == "负反馈":
            base_conf *= 0.6
        # Superpowers验证加成
        base_conf += sp_score * 0.1
        return min(100, base_conf)

    def _generate_action_plan(self, stock: StockCandidate,
                              fusion_score: float, signal: str,
                              reaction_type: str, confidence: float) -> List[str]:
        """生成行动计划"""
        plan = []

        if reaction_type == "因子共振":
            plan.append(f"【因子共振】{stock.name} 72因子强信号共振，建议重仓")
            plan.append(f"目标仓位: 15-25% (置信度{confidence:.0f}%)")
        elif reaction_type == "共振效应":
            plan.append(f"【共振信号】{stock.name}四引擎高度一致，建议重仓")
            plan.append(f"目标仓位: 15-20% (置信度{confidence:.0f}%)")
        elif reaction_type == "催化反应":
            plan.append(f"【催化信号】{stock.name}验证通过+三引擎一致，建议积极配置")
            plan.append(f"目标仓位: 10-15%")
        elif reaction_type == "链式反应":
            plan.append(f"【链式信号】{stock.name}多条件连续满足，建议配置")
            plan.append(f"目标仓位: 8-12%")
        elif reaction_type == "负反馈":
            plan.append(f"【负反馈】{stock.name}验证未通过，建议观望或减仓")
            plan.append(f"目标仓位: 0-3%")
        else:
            plan.append(f"【常规】{stock.name}建议轻仓试探")
            plan.append(f"目标仓位: 5-8%")

        # 统一止损
        plan.append("止损线: 跌幅>15% 或 里程碑逾期未兑现")

        return plan

    def _determine_risk_level(self, fusion_score: float,
                              reaction_type: str, sp_score: float) -> str:
        """判定风险等级"""
        if reaction_type == "负反馈":
            return "高风险"
        if fusion_score >= 75 and sp_score >= 90:
            return "低风险"
        if fusion_score >= 60 and sp_score >= 70:
            return "中低风险"
        if fusion_score >= 45:
            return "中等风险"
        return "中高风险"

    def run_full_fusion(self, universe: List[StockCandidate]) -> List[SuperpowerFusionResult]:
        """运行完整融合流程"""
        print("=" * 70)
        print("Superpower × X-God 化学反应融合引擎")
        print("=" * 70)
        print(f"融合时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标的数量: {len(universe)}")
        print("=" * 70)

        results = []
        reaction_stats = {"催化反应": 0, "共振效应": 0, "链式反应": 0, "负反馈": 0, "因子共振": 0, "常规融合": 0}

        for stock in universe:
            # 市值预筛选
            if not (30 <= stock.market_cap <= 150):
                continue

            result = self.fuse(stock)
            results.append(result)
            reaction_stats[result.reaction_type] = reaction_stats.get(result.reaction_type, 0) + 1

        # 排序
        results.sort(key=lambda x: x.fusion_score, reverse=True)

        # 输出结果
        print("\n" + "=" * 70)
        print("化学反应融合结果 TOP 10")
        print("=" * 70)

        for i, r in enumerate(results[:10], 1):
            print(f"\n{i}. {r.stock_code} {r.stock_name}")
            print(f"   融合得分: {r.fusion_score:.1f} | 化学反应: {r.reaction_type}")
            print(f"   X-God: {r.x_god_score:.1f} | 三引擎: {r.triple_engine_score:.1f} | Superpower: {r.superpower_score:.1f} | 72因子: {r.multi_factor_score:.1f}")
            print(f"   五维一致性: {r.five_way_consistency:.2f} | 置信度: {r.confidence:.1f}%")
            if r.factor_resonance_count > 0:
                print(f"   因子共振: {r.factor_resonance_count}个强信号 | 正向占比: {r.factor_positive_ratio*100:.0f}%")
            print(f"   信号: {r.signal} | 趋势: {r.trend} | 风险: {r.risk_level}")
            print(f"   行动计划: {r.action_plan[0]}")

        print("\n" + "=" * 70)
        print("化学反应统计")
        print("=" * 70)
        for reaction, count in reaction_stats.items():
            if count > 0:
                print(f"  {reaction}: {count} 只")

        return results


def main():
    """主入口"""
    engine = SuperpowerFusionEngine()
    results = engine.run_full_fusion(PRESET_UNIVERSE)

    # 保存结果
    output = {
        "timestamp": datetime.now().isoformat(),
        "engine": "SuperpowerFusionEngine",
        "version": "1.0",
        "total_stocks": len(results),
        "top10": [
            {
                "code": r.stock_code,
                "name": r.stock_name,
                "fusion_score": r.fusion_score,
                "reaction_type": r.reaction_type,
                "signal": r.signal,
                "confidence": r.confidence,
            }
            for r in results[:10]
        ]
    }

    output_path = os.path.join(os.path.dirname(__file__), "superpower_fusion_result.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n融合结果已保存: {output_path}")
    return results


if __name__ == "__main__":
    main()
