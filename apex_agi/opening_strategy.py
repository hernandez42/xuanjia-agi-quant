#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
低开应对策略模块

功能:
    - 周一四种走法分类（A/B/C/D）
    - 各走法具体操作计划生成
    - 仓位建议与操作锚点判断

使用:
    python opening_strategy.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class MarketSnapshot:
    """开盘前市场快照"""
    index_level: float
    prev_close: float
    northbound_flow: float  # 北向资金流入(亿)
    volume_estimate: str  # 缩量 / 放量 / 平量
    sentiment: str  # 恐慌 / 中性 / 乐观

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionPlan:
    """具体操作计划"""
    plan_id: str  # A/B/C/D
    name: str
    condition: str
    timing: str
    direction: List[str]
    position: str
    notes: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 核心类
# ---------------------------------------------------------------------------

class OpeningStrategy:
    """
    低开应对策略器

    基于图片5的交易体系逻辑实现:
        - 周一四种走法分类（A/B/C/D）
        - 各走法具体操作计划
        - 操作锚点: 4060之上越跌越买，之下收不回来停止买入
        - 北向资金参考
    """

    ANCHOR_LEVEL: float = 4060.0

    def __init__(self, date_str: Optional[str] = None) -> None:
        """
        初始化策略器

        Args:
            date_str: 日期字符串，默认使用当天日期
        """
        self.date = date_str or datetime.now().strftime("%Y-%m-%d")
        self.snapshot: Optional[MarketSnapshot] = None
        self.classified_plan: Optional[str] = None

    # ------------------------------------------------------------------
    # 0. 数据获取（try/except + mock fallback）
    # ------------------------------------------------------------------

    def _fetch_market_snapshot(self, snapshot_data: Optional[dict] = None) -> MarketSnapshot:
        """
        获取开盘前市场快照，支持外部传入或mock fallback

        Args:
            snapshot_data: 外部传入的快照数据

        Returns:
            MarketSnapshot: 市场快照对象
        """
        if snapshot_data is not None:
            return MarketSnapshot(**snapshot_data)

        # mock fallback: 模拟周一低开场景
        mock = {
            "index_level": 4055.0,
            "prev_close": 4080.0,
            "northbound_flow": 140.0,
            "volume_estimate": "缩量",
            "sentiment": "恐慌",
        }
        return MarketSnapshot(**mock)

    # ------------------------------------------------------------------
    # 1. 走法分类
    # ------------------------------------------------------------------

    def classify_opening(
        self,
        open_level: float,
        prev_close: float,
        volume_trend: str,
        recovery_speed: str,
        snapshot_data: Optional[dict] = None,
    ) -> dict:
        """
        根据开盘数据分类周一走法

        四种走法:
            A: 低开低走, 缩量 → 第三个冰点日确认, 尾盘低吸
            B: 低开后快速修复, 放量 → 竞价延续恐慌=加仓时机, 开盘30分钟内确认
            C: 平开/高开, 缩量震荡 → 需次日确认, 当天不出手
            D: 低开放量暴跌, 破4060 → 箱体底被有效击穿, 不买

        Args:
            open_level: 开盘点位
            prev_close: 昨日收盘点位
            volume_trend: 量能趋势 ('缩量' / '放量' / '平量')
            recovery_speed: 修复速度 ('快速修复' / '低走' / '震荡' / '暴跌')
            snapshot_data: 可选的市场快照数据

        Returns:
            dict: 走法分类结果
        """
        self.snapshot = self._fetch_market_snapshot(snapshot_data)
        gap = open_level - prev_close
        gap_pct = gap / prev_close * 100

        # 判断逻辑
        is_low_open = gap < 0
        is_below_anchor = open_level < self.ANCHOR_LEVEL
        is_volume_shrink = volume_trend == "缩量"
        is_volume_expand = volume_trend == "放量"
        is_crash = recovery_speed == "暴跌"
        is_fast_recovery = recovery_speed == "快速修复"
        is_flat_high_open = not is_low_open

        # 走法D: 低开放量暴跌, 破4060
        if is_low_open and is_volume_expand and is_crash and is_below_anchor:
            plan = "D"
            name = "低开放量暴跌（破锚点）"
            desc = "箱体底被有效击穿，不买"
        # 走法B: 低开后快速修复, 放量
        elif is_low_open and is_fast_recovery and is_volume_expand:
            plan = "B"
            name = "低开后快速修复（放量）"
            desc = "竞价延续恐慌=加仓时机，开盘30分钟内确认"
        # 走法A: 低开低走, 缩量
        elif is_low_open and not is_fast_recovery and is_volume_shrink:
            plan = "A"
            name = "低开低走（缩量）"
            desc = "第三个冰点日确认，尾盘低吸"
        # 走法C: 平开/高开, 缩量震荡
        elif is_flat_high_open and is_volume_shrink:
            plan = "C"
            name = "平开/高开（缩量震荡）"
            desc = "缩量修复=需次日确认，当天不出手"
        # 默认兜底
        else:
            plan = "C"
            name = "其他情况（偏观望）"
            desc = "信号不明确，按走法C处理，等待确认"

        self.classified_plan = plan

        return {
            "date": self.date,
            "open_level": open_level,
            "prev_close": prev_close,
            "gap": round(gap, 2),
            "gap_pct": round(gap_pct, 3),
            "volume_trend": volume_trend,
            "recovery_speed": recovery_speed,
            "below_anchor": is_below_anchor,
            "classified_plan": plan,
            "plan_name": name,
            "description": desc,
            "snapshot": self.snapshot.to_dict(),
        }

    # ------------------------------------------------------------------
    # 2. 各走法计划生成
    # ------------------------------------------------------------------

    def generate_plan_a(self) -> dict:
        """
        生成走法A操作计划

        走法A: 低开低走, 缩量
            - 第三个冰点日确认, 尾盘低吸
            - 方向: 光模块龙头(五日线附近的)
            - 仓位: 加至5成

        Returns:
            dict: 走法A计划详情
        """
        plan = ActionPlan(
            plan_id="A",
            name="低开低走（缩量）",
            condition="低开 + 低走 + 缩量",
            timing="尾盘低吸（第三个冰点日确认后）",
            direction=["光模块龙头（五日线附近的）"],
            position="加至5成",
            notes=[
                "确认是第三个冰点日再出手",
                "选择五日线附近的光模块龙头",
                "不追高，等尾盘确认",
            ],
        )
        return plan.to_dict()

    def generate_plan_b(self) -> dict:
        """
        生成走法B操作计划

        走法B: 低开后快速修复, 放量
            - 竞价延续恐慌 = 加仓时机(体系原话)
            - 开盘30分钟内确认, 直接上
            - 方向: 光模块 + 北向流入共振的

        Returns:
            dict: 走法B计划详情
        """
        plan = ActionPlan(
            plan_id="B",
            name="低开后快速修复（放量）",
            condition="低开 + 快速修复 + 放量",
            timing="开盘30分钟内确认，直接上",
            direction=["光模块", "北向流入共振方向"],
            position="积极加仓",
            notes=[
                "竞价延续恐慌=加仓时机",
                "开盘30分钟内确认修复力度",
                "优先光模块+北向共振品种",
            ],
        )
        return plan.to_dict()

    def generate_plan_c(self) -> dict:
        """
        生成走法C操作计划

        走法C: 平开/高开, 缩量震荡
            - 需要等次日确认, 当天不出手
            - 缩量修复 = 体系说的"需次日确认"

        Returns:
            dict: 走法C计划详情
        """
        plan = ActionPlan(
            plan_id="C",
            name="平开/高开（缩量震荡）",
            condition="平开/高开 + 缩量 + 震荡",
            timing="当天不出手，等次日确认",
            direction=[],
            position="维持原仓位，不操作",
            notes=[
                "缩量修复=需次日确认",
                "当天不出手，避免假修复",
                "观察次日量能是否配合",
            ],
        )
        return plan.to_dict()

    def generate_plan_d(self) -> dict:
        """
        生成走法D操作计划

        走法D: 低开放量暴跌, 破4060
            - 箱体底被有效击穿, 不买
            - 等三天确认是否二次跌破30日线
            - 如果确认 = 降仓至1-2成防守

        Returns:
            dict: 走法D计划详情
        """
        plan = ActionPlan(
            plan_id="D",
            name="低开放量暴跌（破锚点）",
            condition="低开 + 放量暴跌 + 破4060",
            timing="等三天确认是否二次跌破30日线",
            direction=[],
            position="降仓至1-2成防守",
            notes=[
                "箱体底被有效击穿，不买",
                "等三天确认是否二次跌破30日线",
                "如果确认=全面降仓防守",
            ],
        )
        return plan.to_dict()

    # ------------------------------------------------------------------
    # 3. 操作锚点判断
    # ------------------------------------------------------------------

    def check_anchor(self, current_level: float) -> dict:
        """
        检查操作锚点

        锚点逻辑:
            - 4060之上 = 越跌越买
            - 之下收不回来 = 停止一切买入

        Args:
            current_level: 当前指数点位

        Returns:
            dict: 锚点判断结果
        """
        above = current_level >= self.ANCHOR_LEVEL
        distance = current_level - self.ANCHOR_LEVEL
        distance_pct = distance / self.ANCHOR_LEVEL * 100

        if above:
            advice = "4060之上，越跌越买"
            action = "可以逢低买入"
        else:
            advice = "4060之下，若收不回来则停止一切买入"
            action = "停止买入，观望或减仓"

        return {
            "anchor_level": self.ANCHOR_LEVEL,
            "current_level": current_level,
            "distance": round(distance, 2),
            "distance_pct": round(distance_pct, 3),
            "above_anchor": above,
            "advice": advice,
            "action": action,
        }

    # ------------------------------------------------------------------
    # 4. 北向资金参考
    # ------------------------------------------------------------------

    def northbound_reference(self, flow: Optional[float] = None) -> dict:
        """
        北向资金参考判断

        逻辑:
            - 周五逆势140亿流入是重要参考
            - 大幅流入 = 支撑力度强
            - 大幅流出 = 需要谨慎

        Args:
            flow: 北向资金流入金额（亿），None时使用快照数据

        Returns:
            dict: 北向资金参考结论
        """
        if flow is None:
            if self.snapshot is not None:
                flow = self.snapshot.northbound_flow
            else:
                flow = 0.0

        if flow >= 100:
            level = "极强"
            note = "北向大幅流入，提供强支撑"
        elif flow >= 50:
            level = "较强"
            note = "北向流入积极，偏多"
        elif flow >= 0:
            level = "中性"
            note = "北向小幅流入或持平"
        elif flow >= -50:
            level = "偏弱"
            note = "北向小幅流出，注意风险"
        else:
            level = "极弱"
            note = "北向大幅流出，需高度谨慎"

        return {
            "northbound_flow": flow,
            "reference_level": level,
            "note": note,
            "friday_reference": "周五逆势140亿流入是重要参考",
        }

    # ------------------------------------------------------------------
    # 5. 综合策略生成
    # ------------------------------------------------------------------

    def generate_strategy(
        self,
        open_level: float,
        prev_close: float,
        volume_trend: str,
        recovery_speed: str,
        snapshot_data: Optional[dict] = None,
    ) -> dict:
        """
        生成完整低开应对策略

        Args:
            open_level: 开盘点位
            prev_close: 昨日收盘点位
            volume_trend: 量能趋势
            recovery_speed: 修复速度
            snapshot_data: 可选市场快照

        Returns:
            dict: 包含走法分类、具体计划、锚点判断、北向参考
        """
        # 1. 分类
        classification = self.classify_opening(
            open_level, prev_close, volume_trend, recovery_speed, snapshot_data
        )
        plan_id = classification["classified_plan"]

        # 2. 生成对应计划
        plan_generators = {
            "A": self.generate_plan_a,
            "B": self.generate_plan_b,
            "C": self.generate_plan_c,
            "D": self.generate_plan_d,
        }
        plan = plan_generators.get(plan_id, self.generate_plan_c)()

        # 3. 锚点判断
        anchor = self.check_anchor(open_level)

        # 4. 北向参考
        north = self.northbound_reference()

        return {
            "date": self.date,
            "classification": classification,
            "plan": plan,
            "anchor_check": anchor,
            "northbound_reference": north,
            "final_advice": self._final_advice(plan_id, anchor, north),
        }

    def _final_advice(self, plan_id: str, anchor: dict, north: dict) -> str:
        """
        生成最终操作建议

        Args:
            plan_id: 走法ID
            anchor: 锚点判断结果
            north: 北向参考结果

        Returns:
            str: 最终建议文本
        """
        parts = []

        if plan_id == "D":
            parts.append("走法D确认，全面防守")
        elif plan_id == "B":
            parts.append("走法B确认，积极加仓")
        elif plan_id == "A":
            parts.append("走法A确认，尾盘择机低吸")
        else:
            parts.append("走法C确认，观望等待")

        parts.append(anchor["advice"])
        parts.append(north["note"])

        return "; ".join(parts)

    def print_strategy(self, strategy: Optional[dict] = None) -> None:
        """
        打印格式化策略报告

        Args:
            strategy: 策略字典，None时重新生成
        """
        if strategy is None:
            strategy = self.generate_strategy(
                open_level=4055.0,
                prev_close=4080.0,
                volume_trend="缩量",
                recovery_speed="低走",
            )

        print("=" * 60)
        print(f"低开应对策略报告 [{strategy['date']}]")
        print("=" * 60)

        cls = strategy["classification"]
        print(f"\n【走法分类】{cls['classified_plan']} - {cls['plan_name']}")
        print(f"  开盘: {cls['open_level']} (昨收 {cls['prev_close']}, 缺口 {cls['gap']})")
        print(f"  量能: {cls['volume_trend']}, 修复: {cls['recovery_speed']}")
        print(f"  描述: {cls['description']}")

        plan = strategy["plan"]
        print(f"\n【操作计划】{plan['plan_id']} - {plan['name']}")
        print(f"  条件: {plan['condition']}")
        print(f"  时机: {plan['timing']}")
        if plan["direction"]:
            print(f"  方向: {', '.join(plan['direction'])}")
        print(f"  仓位: {plan['position']}")
        print("  注意:")
        for note in plan["notes"]:
            print(f"    - {note}")

        anc = strategy["anchor_check"]
        print(f"\n【操作锚点】")
        print(f"  锚点: {anc['anchor_level']}, 当前: {anc['current_level']}")
        print(f"  判断: {anc['advice']}")

        nth = strategy["northbound_reference"]
        print(f"\n【北向参考】")
        print(f"  流入: {nth['northbound_flow']}亿, 级别: {nth['reference_level']}")
        print(f"  结论: {nth['note']}")

        print(f"\n【最终建议】")
        print(f"  {strategy['final_advice']}")

        print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# 演示
# ---------------------------------------------------------------------------

def demo() -> None:
    """
    演示入口

    展示 OpeningStrategy 的核心功能:
        1. 走法分类（A/B/C/D）
        2. 各走法计划生成
        3. 操作锚点判断
        4. 北向资金参考
        5. 完整策略生成与报告
    """
    print("OpeningStrategy 演示开始...\n")

    strategy = OpeningStrategy(date_str="2025-05-29")

    # 1. 走法分类 - 四种场景
    scenarios = [
        (4050.0, 4080.0, "缩量", "低走", "走法A: 低开低走缩量"),
        (4055.0, 4080.0, "放量", "快速修复", "走法B: 低开快速修复放量"),
        (4085.0, 4080.0, "缩量", "震荡", "走法C: 平开高开缩量震荡"),
        (4030.0, 4080.0, "放量", "暴跌", "走法D: 低开放量暴跌破锚点"),
    ]

    for open_lv, prev, vol, rec, label in scenarios:
        print(f"\n--- {label} ---")
        cls = strategy.classify_opening(open_lv, prev, vol, rec)
        print(json.dumps(cls, ensure_ascii=False, indent=2))

    # 2. 各计划生成
    print("\n--- 各走法详细计划 ---")
    for gen in [strategy.generate_plan_a, strategy.generate_plan_b,
                strategy.generate_plan_c, strategy.generate_plan_d]:
        plan = gen()
        print(f"\n计划 {plan['plan_id']}: {plan['name']}")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    # 3. 锚点判断
    print("\n--- 操作锚点判断 ---")
    for level in [4070.0, 4060.0, 4050.0, 4030.0]:
        anc = strategy.check_anchor(level)
        print(f"  当前{level}: {anc['advice']}")

    # 4. 北向参考
    print("\n--- 北向资金参考 ---")
    for flow in [150.0, 80.0, 20.0, -30.0, -80.0]:
        ref = strategy.northbound_reference(flow)
        print(f"  流入{flow}亿: {ref['reference_level']} - {ref['note']}")

    # 5. 完整策略报告
    print("\n--- 完整策略报告（走法A示例） ---")
    full = strategy.generate_strategy(
        open_level=4050.0,
        prev_close=4080.0,
        volume_trend="缩量",
        recovery_speed="低走",
        snapshot_data={
            "index_level": 4050.0,
            "prev_close": 4080.0,
            "northbound_flow": 140.0,
            "volume_estimate": "缩量",
            "sentiment": "恐慌",
        },
    )
    strategy.print_strategy(full)

    print("\n演示结束。")


if __name__ == "__main__":
    demo()
