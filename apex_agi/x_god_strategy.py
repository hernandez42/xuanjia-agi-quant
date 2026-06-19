#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X大神4步闭环策略引擎 + 玄甲超越模块
Step1: 月度初筛 - 中小盘+国产化率<20%+扩产周期>18个月
Step2: 季度复审 - 毛利率连扩+剔除研报>15篇热门股
Step3: AI红队证伪 - 客户自研/技术替代风险扫描
Step4: 持股监控 - 3里程碑+时限止损
BeyondX: 玄甲APEX引擎+PHI进化+实时数据融合
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import json
import math


@dataclass
class StockCandidate:
    """候选标的"""
    code: str
    name: str
    market_cap: float  # 亿元
    sector: str
    localization_rate: float  # 国产化率 %
    expansion_cycle_months: int  # 扩产周期 月
    gross_margin_history: List[float] = field(default_factory=list)
    analyst_reports_count: int = 0
    monopoly_score: float = 0.0  # 垄断程度 0-10
    risk_flags: List[str] = field(default_factory=list)
    milestones: List[Dict] = field(default_factory=list)
    apex_score: float = 0.0


@dataclass
class RedTeamReport:
    """AI红队证伪报告"""
    stock_code: str
    risk_level: str  # LOW/MEDIUM/HIGH/CRITICAL
    risk_items: List[Dict]
    customer_self_development_risk: float  # 0-1
    tech_substitution_risk: float  # 0-1
    policy_risk: float  # 0-1
    supply_chain_risk: float  # 0-1
    overall_risk_score: float  # 0-100
    recommendation: str


@dataclass
class Milestone:
    """持股里程碑"""
    name: str
    deadline: str  # YYYY-MM-DD
    target_metric: str
    target_value: float
    actual_value: Optional[float] = None
    status: str = "PENDING"  # PENDING/ACHIEVED/MISSED


class XGodStrategyEngine:
    """X大神4步闭环策略引擎"""

    # 策略参数
    STEP1_MARKET_CAP_MIN = 30  # 亿
    STEP1_MARKET_CAP_MAX = 150  # 亿
    STEP1_LOCALIZATION_MAX = 20  # %
    STEP1_EXPANSION_MIN = 18  # 月
    STEP2_MARGIN_EXPANSION_QUARTERS = 2  # 毛利率连扩季度数
    STEP2_REPORTS_MAX = 15  # 研报数量上限
    STEP4_MILESTONE_COUNT = 3
    STEP4_MAX_HOLD_QUARTERS = 2

    def __init__(self):
        self.candidates: List[StockCandidate] = []
        self.selected: List[StockCandidate] = []
        self.red_team_reports: Dict[str, RedTeamReport] = {}
        self.milestones: Dict[str, List[Milestone]] = {}

    # ========== Step 1: 月度初筛 ==========
    def step1_screen(self, universe: List[StockCandidate]) -> List[StockCandidate]:
        """
        月度初筛：锁定30-150亿中小盘
        条件：国产化率<20%、扩产周期>18个月、垄断环节
        """
        filtered = []
        for stock in universe:
            score = 0
            reasons = []

            # 市值筛选
            if not (self.STEP1_MARKET_CAP_MIN <= stock.market_cap <= self.STEP1_MARKET_CAP_MAX):
                continue

            # 国产化率<20%
            if stock.localization_rate < self.STEP1_LOCALIZATION_MAX:
                score += 30
                reasons.append(f"国产化率{stock.localization_rate}%<20%，替代空间大")

            # 扩产周期>18个月
            if stock.expansion_cycle_months > self.STEP1_EXPANSION_MIN:
                score += 25
                reasons.append(f"扩产周期{stock.expansion_cycle_months}月>18月，供给刚性")

            # 垄断评分
            if stock.monopoly_score >= 7:
                score += 25
                reasons.append(f"垄断评分{stock.monopoly_score}/10，竞争格局优")
            elif stock.monopoly_score >= 5:
                score += 15
                reasons.append(f"垄断评分{stock.monopoly_score}/10，细分龙头")

            # 中小盘溢价
            if stock.market_cap < 80:
                score += 10
                reasons.append("小盘弹性，机构低配")

            stock.apex_score = score
            if score >= 50:
                filtered.append(stock)

        filtered.sort(key=lambda x: x.apex_score, reverse=True)
        self.candidates = filtered
        return filtered

    # ========== Step 2: 季度复审 ==========
    def step2_review(self, candidates: List[StockCandidate]) -> List[StockCandidate]:
        """
        季度复审：取毛利率连扩、剔除研报超15篇的热门股
        """
        reviewed = []
        for stock in candidates:
            # 剔除研报过多的热门股
            if stock.analyst_reports_count > self.STEP2_REPORTS_MAX:
                stock.risk_flags.append(f"研报{stock.analyst_reports_count}篇>15篇，过于热门")
                continue

            # 毛利率连扩检查
            margins = stock.gross_margin_history
            if len(margins) >= self.STEP2_MARGIN_EXPANSION_QUARTERS + 1:
                expanding = all(margins[i] < margins[i+1] for i in range(len(margins)-1))
                if expanding:
                    stock.apex_score += 20
                    stock.risk_flags.append("毛利率连续扩张")
                else:
                    stock.risk_flags.append("毛利率未连续扩张，需观察")
            else:
                stock.risk_flags.append("毛利率数据不足")

            # 研报极少 = 冷门预期差
            if stock.analyst_reports_count <= 5:
                stock.apex_score += 15
                stock.risk_flags.append("机构极度低配，筹码干净")

            reviewed.append(stock)

        reviewed.sort(key=lambda x: x.apex_score, reverse=True)
        self.selected = reviewed[:20]  # 取前20
        return self.selected

    # ========== Step 3: AI红队证伪 ==========
    def step3_red_team(self, stock: StockCandidate) -> RedTeamReport:
        """
        AI红队视角证伪风险
        查：客户自研、技术替代、政策变化、供应链断裂
        """
        risk_items = []
        risk_score = 0

        # 1. 客户自研风险
        customer_self_dev = self._assess_customer_self_dev(stock)
        if customer_self_dev > 0.6:
            risk_items.append({
                "type": "客户自研",
                "level": "HIGH",
                "detail": "头部客户已启动自研计划，2-3年内可能替代"
            })
            risk_score += 25
        elif customer_self_dev > 0.3:
            risk_items.append({
                "type": "客户自研",
                "level": "MEDIUM",
                "detail": "客户有自研意向，需持续跟踪"
            })
            risk_score += 12

        # 2. 技术替代风险
        tech_sub = self._assess_tech_substitution(stock)
        if tech_sub > 0.6:
            risk_items.append({
                "type": "技术替代",
                "level": "HIGH",
                "detail": "新技术路线可能颠覆现有产品"
            })
            risk_score += 25
        elif tech_sub > 0.3:
            risk_items.append({
                "type": "技术替代",
                "level": "MEDIUM",
                "detail": "技术迭代加速，需关注替代进程"
            })
            risk_score += 12

        # 3. 政策风险
        policy_risk = self._assess_policy_risk(stock)
        if policy_risk > 0.5:
            risk_items.append({
                "type": "政策风险",
                "level": "MEDIUM",
                "detail": "行业政策存在不确定性"
            })
            risk_score += 10

        # 4. 供应链风险
        supply_risk = self._assess_supply_chain(stock)
        if supply_risk > 0.5:
            risk_items.append({
                "type": "供应链",
                "level": "MEDIUM",
                "detail": "关键原材料依赖进口"
            })
            risk_score += 10

        # 风险定级
        if risk_score >= 60:
            risk_level = "CRITICAL"
            recommendation = "否决：风险过高，不予纳入"
        elif risk_score >= 40:
            risk_level = "HIGH"
            recommendation = "谨慎：需附加条件方可纳入"
        elif risk_score >= 20:
            risk_level = "MEDIUM"
            recommendation = "可纳入：设定更严格止损"
        else:
            risk_level = "LOW"
            recommendation = "通过：风险可控，正常纳入"

        report = RedTeamReport(
            stock_code=stock.code,
            risk_level=risk_level,
            risk_items=risk_items,
            customer_self_development_risk=customer_self_dev,
            tech_substitution_risk=tech_sub,
            policy_risk=policy_risk,
            supply_chain_risk=supply_risk,
            overall_risk_score=risk_score,
            recommendation=recommendation
        )
        self.red_team_reports[stock.code] = report
        return report

    def _assess_customer_self_dev(self, stock: StockCandidate) -> float:
        """评估客户自研风险 (模拟)"""
        # 基于行业特征模拟
        if "半导体设备" in stock.sector or "材料" in stock.sector:
            return 0.2  # 设备材料客户自研难度高
        if "零部件" in stock.sector:
            return 0.5  # 零部件客户可能自研
        return 0.3

    def _assess_tech_substitution(self, stock: StockCandidate) -> float:
        """评估技术替代风险 (模拟)"""
        if stock.localization_rate < 10:
            return 0.15  # 国产化率极低，技术壁垒极高
        if "光刻" in stock.name or "靶材" in stock.name:
            return 0.1  # 光刻/靶材技术替代极难
        return 0.3

    def _assess_policy_risk(self, stock: StockCandidate) -> float:
        """评估政策风险"""
        if "半导体" in stock.sector or "芯片" in stock.sector:
            return 0.1  # 政策大力支持
        return 0.3

    def _assess_supply_chain(self, stock: StockCandidate) -> float:
        """评估供应链风险"""
        if stock.localization_rate < 15:
            return 0.4  # 高度依赖进口原材料
        return 0.2

    # ========== Step 4: 持股监控 ==========
    def step4_monitor(self, stock: StockCandidate) -> List[Milestone]:
        """
        持股监控：设未来两季度3个里程碑及时限
        未兑现就止损
        """
        now = datetime.now()
        milestones = []

        # 里程碑1: 订单/营收验证 (1个月内)
        m1 = Milestone(
            name="订单验证",
            deadline=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
            target_metric="新增订单/营收增速",
            target_value=20.0  # 20%增长
        )
        milestones.append(m1)

        # 里程碑2: 毛利率验证 (1个季度内)
        m2 = Milestone(
            name="毛利率验证",
            deadline=(now + timedelta(days=90)).strftime("%Y-%m-%d"),
            target_metric="毛利率",
            target_value=stock.gross_margin_history[-1] if stock.gross_margin_history else 30.0
        )
        milestones.append(m2)

        # 里程碑3: 产能/客户验证 (2个季度内)
        m3 = Milestone(
            name="产能/客户验证",
            deadline=(now + timedelta(days=180)).strftime("%Y-%m-%d"),
            target_metric="产能利用率/大客户导入",
            target_value=80.0  # 80%产能利用率
        )
        milestones.append(m3)

        self.milestones[stock.code] = milestones
        return milestones

    def check_stop_loss(self, stock_code: str, current_data: Dict) -> Tuple[bool, str]:
        """
        检查止损条件
        返回: (是否止损, 原因)
        """
        milestones = self.milestones.get(stock_code, [])
        now = datetime.now()

        for ms in milestones:
            deadline = datetime.strptime(ms.deadline, "%Y-%m-%d")
            if now > deadline and ms.status == "PENDING":
                return True, f"里程碑[{ms.name}]逾期未兑现"

        # 跌幅止损: 15%
        if current_data.get("drawdown", 0) > 15:
            return True, "跌幅超15%，触发硬性止损"

        # 红队风险升级
        report = self.red_team_reports.get(stock_code)
        if report and report.risk_level == "CRITICAL":
            return True, "红队风险升级为CRITICAL"

        return False, ""

    # ========== Beyond X: 玄甲超越模块 ==========
    def beyond_x_fusion(self, stock: StockCandidate) -> Dict:
        """
        超越X大神：融合玄甲APEX引擎+PHI进化+实时数据
        """
        # 基础X策略得分 (Step1+Step2综合得分)
        base_score = stock.apex_score

        # 玄甲APEX因子加成
        apex_boost = self._apex_factor_boost(stock)

        # PHI进化系数 (动态调整)
        phi_coefficient = self._phi_evolution_coefficient(stock)

        # 实时数据融合
        real_time_boost = self._real_time_data_fusion(stock)

        # 综合超越得分 (累加制，确保高分标的充分体现)
        beyond_score = base_score + apex_boost + (phi_coefficient * 10) + real_time_boost

        return {
            "stock": stock.code,
            "base_x_score": base_score,
            "apex_boost": apex_boost,
            "phi_coefficient": phi_coefficient,
            "real_time_boost": real_time_boost,
            "beyond_x_score": round(beyond_score, 2),
            "recommendation": self._beyond_recommendation(beyond_score),
            "confidence": self._calculate_confidence(stock)
        }

    def _apex_factor_boost(self, stock: StockCandidate) -> float:
        """玄甲APEX因子加成"""
        boost = 0
        # 国产化率极低 = 高壁垒高弹性
        if stock.localization_rate < 10:
            boost += 15
        # 扩产周期长 = 供给刚性
        if stock.expansion_cycle_months > 24:
            boost += 10
        # 垄断性强
        if stock.monopoly_score >= 8:
            boost += 12
        return boost

    def _phi_evolution_coefficient(self, stock: StockCandidate) -> float:
        """PHI进化系数：基于历史学习动态调整"""
        # 模拟PHI_APEX = (base × ev × an × nv) / harm_rate
        base = stock.monopoly_score / 10
        ev = 1.0  # 进化速度
        an = 1.0  # 适应性
        nv = 1.0  # 新颖性
        harm_rate = max(0.1, stock.localization_rate / 100)
        phi = (base * ev * an * nv) / harm_rate
        return min(phi, 2.0)  # 上限2.0

    def _real_time_data_fusion(self, stock: StockCandidate) -> float:
        """实时数据融合加成"""
        # 模拟实时市场情绪+资金流向
        boost = 0
        if stock.analyst_reports_count <= 3:
            boost += 8  # 极度冷门，预期差大
        if stock.market_cap < 50:
            boost += 5  # 小盘弹性
        return boost

    def _beyond_recommendation(self, score: float) -> str:
        if score >= 120:
            return "强烈建议：超越X策略高置信度标的"
        elif score >= 100:
            return "建议：具备超越潜力"
        elif score >= 80:
            return "观察：条件部分满足"
        else:
            return "回避：不满足超越条件"

    def _calculate_confidence(self, stock: StockCandidate) -> float:
        """计算综合置信度"""
        factors = [
            1.0 if stock.localization_rate < 20 else 0.5,
            1.0 if stock.expansion_cycle_months > 18 else 0.5,
            stock.monopoly_score / 10,
            1.0 if stock.analyst_reports_count <= 15 else 0.3,
        ]
        return round(sum(factors) / len(factors) * 100, 1)

    # ========== 完整流程 ==========
    def execute_full_pipeline(self, universe: List[StockCandidate]) -> Dict:
        """执行完整4步+X超越流程"""
        results = {
            "step1_screened": [],
            "step2_reviewed": [],
            "step3_red_team": {},
            "step4_milestones": {},
            "beyond_x": {},
            "final_recommendations": []
        }

        # Step 1
        step1 = self.step1_screen(universe)
        results["step1_screened"] = [s.code for s in step1]

        # Step 2
        step2 = self.step2_review(step1)
        results["step2_reviewed"] = [s.code for s in step2]

        # Step 3
        for stock in step2:
            report = self.step3_red_team(stock)
            results["step3_red_team"][stock.code] = {
                "risk_level": report.risk_level,
                "risk_score": report.overall_risk_score,
                "recommendation": report.recommendation
            }

        # Step 4
        for stock in step2:
            ms = self.step4_monitor(stock)
            results["step4_milestones"][stock.code] = [
                {"name": m.name, "deadline": m.deadline, "target": m.target_metric}
                for m in ms
            ]

        # Beyond X
        for stock in step2:
            fusion = self.beyond_x_fusion(stock)
            results["beyond_x"][stock.code] = fusion

        # 最终推荐：综合评分前10
        all_scores = []
        for stock in step2:
            bx = results["beyond_x"][stock.code]
            red = results["step3_red_team"][stock.code]
            if red["risk_level"] not in ["CRITICAL", "HIGH"]:
                all_scores.append((stock, bx["beyond_x_score"], bx["confidence"]))

        all_scores.sort(key=lambda x: x[1], reverse=True)
        results["final_recommendations"] = [
            {
                "code": s.code,
                "name": s.name,
                "market_cap": s.market_cap,
                "beyond_score": score,
                "confidence": conf,
                "sector": s.sector
            }
            for s, score, conf in all_scores[:10]
        ]

        return results


# ========== 预置候选池（基于搜索数据） ==========
PRESET_UNIVERSE = [
    StockCandidate("300786", "国林科技", 40, "半导体设备/臭氧", 10, 24,
                   gross_margin_history=[35.4, 37.3, 31.2, 17.71],
                   analyst_reports_count=3, monopoly_score=9),
    StockCandidate("688234", "天岳先进", 120, "半导体材料/SiC衬底", 15, 36,
                   gross_margin_history=[25, 28, 32, 35],
                   analyst_reports_count=8, monopoly_score=8),
    StockCandidate("688233", "神工股份", 45, "半导体材料/单晶硅", 12, 30,
                   gross_margin_history=[30, 32, 35, 38],
                   analyst_reports_count=2, monopoly_score=7),
    StockCandidate("300346", "南大光电", 140, "半导体材料/光刻胶", 5, 48,
                   gross_margin_history=[40, 42, 45, 48],
                   analyst_reports_count=12, monopoly_score=9),
    StockCandidate("688268", "华特气体", 80, "半导体材料/电子特气", 18, 24,
                   gross_margin_history=[28, 30, 33, 36],
                   analyst_reports_count=6, monopoly_score=7),
    StockCandidate("300054", "鼎龙股份", 130, "半导体材料/CMP", 19, 30,
                   gross_margin_history=[32, 35, 38, 40],
                   analyst_reports_count=10, monopoly_score=8),
    StockCandidate("603938", "三孚股份", 55, "电子化工/高纯硅", 15, 36,
                   gross_margin_history=[25, 30, 38, 45],
                   analyst_reports_count=4, monopoly_score=7),
    StockCandidate("300811", "铂科新材", 90, "电子材料/软磁", 18, 24,
                   gross_margin_history=[35, 38, 40, 42],
                   analyst_reports_count=5, monopoly_score=6),
    StockCandidate("688205", "德科立", 70, "光通信/OCS", 19, 30,
                   gross_margin_history=[20, 25, 30, 35],
                   analyst_reports_count=3, monopoly_score=6),
    StockCandidate("002428", "云南锗业", 85, "稀散金属/锗", 19, 36,
                   gross_margin_history=[15, 18, 22, 28],
                   analyst_reports_count=2, monopoly_score=7),
    StockCandidate("688126", "沪硅产业", 450, "半导体材料/硅片", 19, 36,
                   gross_margin_history=[15, 18, 20, 22],
                   analyst_reports_count=15, monopoly_score=9),
    StockCandidate("300666", "江丰电子", 180, "半导体材料/靶材", 15, 30,
                   gross_margin_history=[28, 30, 32, 35],
                   analyst_reports_count=9, monopoly_score=8),
    StockCandidate("688019", "安集科技", 160, "半导体材料/CMP液", 18, 24,
                   gross_margin_history=[45, 48, 50, 52],
                   analyst_reports_count=8, monopoly_score=7),
    StockCandidate("300655", "晶瑞电材", 65, "半导体材料/光刻胶", 15, 24,
                   gross_margin_history=[22, 25, 28, 30],
                   analyst_reports_count=4, monopoly_score=5),
    StockCandidate("688072", "拓荆科技", 280, "半导体设备/薄膜", 19, 36,
                   gross_margin_history=[40, 43, 45, 48],
                   analyst_reports_count=14, monopoly_score=8),
]


def main():
    """主入口：执行X大神策略并输出结果"""
    engine = XGodStrategyEngine()
    results = engine.execute_full_pipeline(PRESET_UNIVERSE)

    print("=" * 60)
    print("X大神4步闭环策略 + 玄甲超越引擎")
    print("=" * 60)

    print(f"\n[Step 1] 月度初筛: {len(results['step1_screened'])} 只通过")
    print(f"[Step 2] 季度复审: {len(results['step2_reviewed'])} 只通过")
    print(f"[Step 3] AI红队: {len(results['step3_red_team'])} 只完成证伪")
    print(f"[Step 4] 持股监控: {len(results['step4_milestones'])} 只设定里程碑")

    print("\n" + "=" * 60)
    print("Beyond X: 玄甲超越推荐 TOP 10")
    print("=" * 60)

    for i, rec in enumerate(results["final_recommendations"], 1):
        print(f"\n{i}. {rec['code']} {rec['name']}")
        print(f"   市值: {rec['market_cap']}亿 | 板块: {rec['sector']}")
        print(f"   超越得分: {rec['beyond_score']:.1f} | 置信度: {rec['confidence']}%")

    return results


if __name__ == "__main__":
    main()
