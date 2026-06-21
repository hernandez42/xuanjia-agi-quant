#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连板天梯 + 主线分化体系模块

功能:
    - 连板天梯跟踪（高标、梯队结构、断板判断）
    - 主线方向强度评级（5星制）
    - 主线分化判断（分离模式、载体分离）
    - 毕业照判断（龙头滞涨 + 补涨加速 + 三题材高潮）

使用:
    python limitup_tracker.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class LimitUpStock:
    """连板个股信息"""
    name: str
    consecutive_boards: int
    total_boards_in_period: int
    sector: str
    status: str  # 运行中 / 断板 / 停牌等
    period_days: int = 0  # 统计周期天数，如 16天10板

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SectorStrength:
    """主线方向强度评级"""
    sector: str
    stars: int  # 1-5星
    trend: str  # 主升 / 亢奋 / 启动 / 爆发 / 震荡 / 退潮
    leader: str
    leader_boards: int
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DivergenceResult:
    """载体分离结果"""
    sector: str
    leader: str
    status: str  # 分离确认中 / 龙头首次大回撤 / 补涨加速 / 补涨扩散
    action: str  # 五日线持有 / 观察30日线 / 不再新开仓 / 坚决不碰
    stage: str = ""  # 主升延续 / 二阶段末期 / 后排跟风

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GraduationPhotoSignal:
    """毕业照预警信号"""
    is_graduation: bool
    reasons: List[str]
    conclusion: str
    risk_level: str  # 高 / 中 / 低

    def to_dict(self) -> dict:
        return {
            "is_graduation": self.is_graduation,
            "reasons": self.reasons,
            "conclusion": self.conclusion,
            "risk_level": self.risk_level,
        }


# ---------------------------------------------------------------------------
# 核心类
# ---------------------------------------------------------------------------

class LimitUpTracker:
    """
    连板天梯 + 主线分化体系跟踪器

    基于图片3+4的交易体系逻辑实现:
        - 连板天梯跟踪与断板判断
        - 主线方向5星制强度评级
        - 主线分化/载体分离分析
        - 毕业照（顶部信号）判断
    """

    def __init__(self, date_str: Optional[str] = None) -> None:
        """
        初始化跟踪器

        Args:
            date_str: 日期字符串，默认使用当天日期
        """
        self.date = date_str or datetime.now().strftime("%Y-%m-%d")
        self.stocks: List[LimitUpStock] = []
        self.sectors: List[SectorStrength] = []
        self.divergence_results: List[DivergenceResult] = []
        self.graduation_signal: Optional[GraduationPhotoSignal] = None

    # ------------------------------------------------------------------
    # 1. 连板天梯跟踪
    # ------------------------------------------------------------------

    def track_limitup_stocks(self, stocks_data: Optional[List[dict]] = None) -> dict:
        """
        跟踪连板天梯结构

        逻辑:
            - 高标跟踪: 最高板股票、连板数、题材、状态
            - 梯队结构: 4板几只、3板几只、2板几只
            - 断板判断: 最高板断板 = 休息不操作

        Args:
            stocks_data: 连板股票原始数据，为None时使用内置mock数据

        Returns:
            dict: 包含高标信息、梯队结构、断板判断结果
        """
        raw = self._fetch_limitup_data(stocks_data)
        self.stocks = [LimitUpStock(**item) for item in raw]

        # 高标跟踪
        if self.stocks:
            highest = max(self.stocks, key=lambda s: s.consecutive_boards)
            highest_stock = {
                "name": highest.name,
                "consecutive_boards": highest.consecutive_boards,
                "sector": highest.sector,
                "status": highest.status,
            }
        else:
            highest_stock = {}

        # 梯队结构统计
        ladder = {"4板及以上": 0, "3板": 0, "2板": 0, "首板": 0}
        for s in self.stocks:
            if s.consecutive_boards >= 4:
                ladder["4板及以上"] += 1
            elif s.consecutive_boards == 3:
                ladder["3板"] += 1
            elif s.consecutive_boards == 2:
                ladder["2板"] += 1
            else:
                ladder["首板"] += 1

        # 断板判断
        broken = any(s.status == "断板" for s in self.stocks if s.consecutive_boards >= 4)
        broken_advice = "最高板断板，休息不操作" if broken else "高标运行中，可正常观察"

        result = {
            "date": self.date,
            "highest_stock": highest_stock,
            "ladder_structure": ladder,
            "broken_board": broken,
            "broken_advice": broken_advice,
            "stocks": [s.to_dict() for s in self.stocks],
        }
        return result

    def _fetch_limitup_data(self, stocks_data: Optional[List[dict]] = None) -> List[dict]:
        """
        获取连板数据，支持外部传入或mock fallback

        Args:
            stocks_data: 外部传入的数据

        Returns:
            List[dict]: 连板股票数据列表
        """
        if stocks_data is not None:
            return stocks_data

        # mock fallback: 5/29 案例数据
        mock = [
            {
                "name": "宝鼎科技",
                "consecutive_boards": 2,
                "total_boards_in_period": 10,
                "sector": "PCB/铜箔",
                "status": "运行中",
                "period_days": 16,
            },
            {
                "name": "华电能源",
                "consecutive_boards": 4,
                "total_boards_in_period": 4,
                "sector": "电力",
                "status": "运行中",
                "period_days": 4,
            },
            {
                "name": "香江控股",
                "consecutive_boards": 4,
                "total_boards_in_period": 4,
                "sector": "房地产",
                "status": "运行中",
                "period_days": 4,
            },
            {
                "name": "华塑控股",
                "consecutive_boards": 4,
                "total_boards_in_period": 4,
                "sector": "PCB设备",
                "status": "运行中",
                "period_days": 4,
            },
            {
                "name": "中京电子",
                "consecutive_boards": 3,
                "total_boards_in_period": 3,
                "sector": "PCB",
                "status": "运行中",
                "period_days": 3,
            },
        ]
        return mock

    # ------------------------------------------------------------------
    # 2. 主线方向强度评级
    # ------------------------------------------------------------------

    def rate_sector_strength(self, sectors_data: Optional[List[dict]] = None) -> dict:
        """
        主线方向强度评级（5星制）

        逻辑:
            - 5星: 主升+亢奋，龙头高度最高
            - 4星: 主升或亢奋，龙头有高度
            - 3星: 主升或启动+爆发，龙头中等高度
            - 2星: 震荡，龙头高度有限
            - 1星: 退潮，龙头断板或走弱

        Args:
            sectors_data: 主线数据，为None时使用内置mock数据

        Returns:
            dict: 包含各主线评级列表及最强主线
        """
        raw = self._fetch_sector_data(sectors_data)
        self.sectors = [SectorStrength(**item) for item in raw]

        # 按星级排序
        sorted_sectors = sorted(self.sectors, key=lambda x: x.stars, reverse=True)
        strongest = sorted_sectors[0] if sorted_sectors else None

        result = {
            "date": self.date,
            "sectors": [s.to_dict() for s in sorted_sectors],
            "strongest_sector": strongest.to_dict() if strongest else {},
            "total_sectors": len(self.sectors),
        }
        return result

    def _fetch_sector_data(self, sectors_data: Optional[List[dict]] = None) -> List[dict]:
        """
        获取主线数据，支持外部传入或mock fallback

        Args:
            sectors_data: 外部传入的数据

        Returns:
            List[dict]: 主线数据列表
        """
        if sectors_data is not None:
            return sectors_data

        # mock fallback: 5/29 主线强度数据
        mock = [
            {
                "sector": "PCB/铜箔",
                "stars": 5,
                "trend": "主升+亢奋",
                "leader": "宝鼎科技",
                "leader_boards": 10,
                "note": "宝鼎16天10板",
            },
            {
                "sector": "MLCC/被动元件",
                "stars": 4,
                "trend": "主升",
                "leader": "风华高科",
                "leader_boards": 4,
                "note": "风华8天4板",
            },
            {
                "sector": "超级电容",
                "stars": 4,
                "trend": "主升",
                "leader": "江海股份",
                "leader_boards": 2,
                "note": "江海2连板",
            },
            {
                "sector": "CPO/光通信",
                "stars": 4,
                "trend": "亢奋",
                "leader": "易中天",
                "leader_boards": 0,
                "note": "易中天创历史新高",
            },
            {
                "sector": "电力",
                "stars": 3,
                "trend": "主升",
                "leader": "华电能源",
                "leader_boards": 4,
                "note": "华电4连板",
            },
            {
                "sector": "金刚石散热",
                "stars": 3,
                "trend": "启动+爆发",
                "leader": "黄河旋风",
                "leader_boards": 7,
                "note": "黄河14天7板",
            },
        ]
        return mock

    # ------------------------------------------------------------------
    # 3. 主线分化判断
    # ------------------------------------------------------------------

    def analyze_divergence(self, divergence_data: Optional[List[dict]] = None) -> dict:
        """
        主线分化/载体分离分析

        逻辑:
            - 分离模式: 等指数大跌日 → 观察逆势走强板块 → 排除外切避险 → 锁定主线内部逆势品种
            - 载体分离结果:
                * 光模块(易中天): 分离确认中, 主升延续 → 五日线持有, 分歧低吸
                * 半导体(中芯/华虹): 龙头首次大回撤 → 观察30日线, 不急着抄
                * PCB/电容(宝鼎/艾华): 补涨加速=二阶段末期 → 不再新开仓
                * MLCC/钻石(风华/黄河): 补涨扩散=后排跟风 → 坚决不碰

        Args:
            divergence_data: 分化数据，为None时使用内置mock数据

        Returns:
            dict: 包含分离模式说明及各载体分离结果
        """
        raw = self._fetch_divergence_data(divergence_data)
        self.divergence_results = [DivergenceResult(**item) for item in raw]

        result = {
            "date": self.date,
            "mode": (
                "等指数大跌日 → 观察逆势走强板块 → "
                "排除外切避险 → 锁定主线内部逆势品种"
            ),
            "results": [r.to_dict() for r in self.divergence_results],
            "summary": self._summarize_divergence(),
        }
        return result

    def _fetch_divergence_data(self, divergence_data: Optional[List[dict]] = None) -> List[dict]:
        """
        获取分化数据，支持外部传入或mock fallback

        Args:
            divergence_data: 外部传入的数据

        Returns:
            List[dict]: 分化数据列表
        """
        if divergence_data is not None:
            return divergence_data

        # mock fallback: 5/29 载体分离结果
        mock = [
            {
                "sector": "光模块",
                "leader": "易中天",
                "status": "分离确认中",
                "action": "五日线持有，分歧低吸",
                "stage": "主升延续",
            },
            {
                "sector": "半导体",
                "leader": "中芯/华虹",
                "status": "龙头首次大回撤",
                "action": "观察30日线，不急着抄",
                "stage": "主升中段调整",
            },
            {
                "sector": "PCB/电容",
                "leader": "宝鼎/艾华",
                "status": "补涨加速",
                "action": "不再新开仓",
                "stage": "二阶段末期",
            },
            {
                "sector": "MLCC/钻石",
                "leader": "风华/黄河",
                "status": "补涨扩散",
                "action": "坚决不碰",
                "stage": "后排跟风",
            },
        ]
        return mock

    def _summarize_divergence(self) -> str:
        """
        生成分化分析总结

        Returns:
            str: 总结文本
        """
        hold = [r for r in self.divergence_results if "持有" in r.action]
        avoid = [r for r in self.divergence_results if "不碰" in r.action or "不再" in r.action]
        watch = [r for r in self.divergence_results if "观察" in r.action]

        parts = []
        if hold:
            parts.append(f"可持有/低吸: {', '.join(r.sector for r in hold)}")
        if watch:
            parts.append(f"观察等待: {', '.join(r.sector for r in watch)}")
        if avoid:
            parts.append(f"回避不碰: {', '.join(r.sector for r in avoid)}")

        return "; ".join(parts) if parts else "暂无分化信号"

    # ------------------------------------------------------------------
    # 4. 毕业照判断
    # ------------------------------------------------------------------

    def detect_graduation_photo(
        self,
        leader_stagnant: bool = False,
       补涨_accelerating: bool = True,
        three_sectors_euphoria: bool = False,
    ) -> dict:
        """
        毕业照（顶部信号）判断

        经典毕业照 = 龙头滞涨 + 补涨加速 + 三题材全部高潮

        当前案例判断逻辑:
            - 龙头还在主升新高 → 不是滞涨
            - 半导体龙头首次大回撤 → 不是滞涨
            - 补涨在加速 → 风险但≠毕业照
            - 结论: 不是毕业照，是主线内部"换载体"

        Args:
            leader_stagnant: 龙头是否滞涨
            补涨_accelerating: 补涨是否加速
            three_sectors_euphoria: 三题材是否全部高潮

        Returns:
            dict: 毕业照判断结果
        """
        reasons = []

        if leader_stagnant:
            reasons.append("龙头滞涨")
        else:
            reasons.append("龙头还在主升新高（不是滞涨）")

        if 补涨_accelerating:
            reasons.append("补涨在加速（风险信号）")
        else:
            reasons.append("补涨未加速")

        if three_sectors_euphoria:
            reasons.append("三题材全部高潮")
        else:
            reasons.append("三题材未全部高潮")

        # 经典毕业照条件
        is_graduation = leader_stagnant and 补涨_accelerating and three_sectors_euphoria

        if is_graduation:
            conclusion = "经典毕业照确认，全面减仓回避"
            risk_level = "高"
        elif 补涨_accelerating and not leader_stagnant:
            conclusion = "不是毕业照，是主线内部'换载体'，注意补涨风险"
            risk_level = "中"
        else:
            conclusion = "暂无毕业照信号，继续跟踪"
            risk_level = "低"

        self.graduation_signal = GraduationPhotoSignal(
            is_graduation=is_graduation,
            reasons=reasons,
            conclusion=conclusion,
            risk_level=risk_level,
        )

        return self.graduation_signal.to_dict()

    # ------------------------------------------------------------------
    # 综合输出
    # ------------------------------------------------------------------

    def full_report(self) -> dict:
        """
        生成完整报告

        Returns:
            dict: 包含连板天梯、主线强度、分化判断、毕业照预警
        """
        limitup = self.track_limitup_stocks()
        sectors = self.rate_sector_strength()
        divergence = self.analyze_divergence()
        graduation = self.detect_graduation_photo()

        return {
            "date": self.date,
            "limitup_tracker": limitup,
            "sector_strength": sectors,
            "divergence_analysis": divergence,
            "graduation_photo": graduation,
        }

    def print_report(self) -> None:
        """打印格式化报告到控制台"""
        report = self.full_report()

        print("=" * 60)
        print(f"连板天梯 + 主线分化体系报告 [{report['date']}]")
        print("=" * 60)

        # 连板天梯
        lu = report["limitup_tracker"]
        print("\n【连板天梯】")
        print(f"  高标: {lu['highest_stock'].get('name', 'N/A')} "
              f"({lu['highest_stock'].get('consecutive_boards', 0)}板) "
              f"- {lu['highest_stock'].get('sector', '')}")
        print(f"  梯队结构: {lu['ladder_structure']}")
        print(f"  断板判断: {lu['broken_advice']}")

        # 主线强度
        ss = report["sector_strength"]
        print("\n【主线方向强度评级】")
        for s in ss["sectors"]:
            print(f"  {'★' * s['stars']}{'☆' * (5 - s['stars'])}  "
                  f"{s['sector']:12s}  {s['trend']:10s}  龙头:{s['leader']}")

        # 分化判断
        div = report["divergence_analysis"]
        print("\n【主线分化/载体分离】")
        print(f"  分离模式: {div['mode']}")
        for r in div["results"]:
            print(f"  {r['sector']:10s} ({r['leader']:8s})  "
                  f"{r['status']:12s} → {r['action']}")
        print(f"  总结: {div['summary']}")

        # 毕业照
        gp = report["graduation_photo"]
        print("\n【毕业照预警】")
        print(f"  是否毕业照: {'是' if gp['is_graduation'] else '否'}")
        print(f"  判断依据:")
        for r in gp["reasons"]:
            print(f"    - {r}")
        print(f"  结论: {gp['conclusion']}")
        print(f"  风险等级: {gp['risk_level']}")

        print("\n" + "=" * 60)


def demo() -> None:
    """
    演示入口

    展示 LimitUpTracker 的核心功能:
        1. 连板天梯跟踪
        2. 主线强度评级
        3. 分化分析
        4. 毕业照判断
        5. 完整报告输出
    """
    print("LimitUpTracker 演示开始...\n")

    tracker = LimitUpTracker(date_str="2025-05-29")

    # 1. 连板天梯
    print("--- 1. 连板天梯跟踪 ---")
    lu = tracker.track_limitup_stocks()
    print(json.dumps(lu, ensure_ascii=False, indent=2))

    # 2. 主线强度
    print("\n--- 2. 主线方向强度评级 ---")
    ss = tracker.rate_sector_strength()
    print(json.dumps(ss, ensure_ascii=False, indent=2))

    # 3. 分化分析
    print("\n--- 3. 主线分化判断 ---")
    div = tracker.analyze_divergence()
    print(json.dumps(div, ensure_ascii=False, indent=2))

    # 4. 毕业照判断（不同场景）
    print("\n--- 4. 毕业照判断（当前场景） ---")
    gp = tracker.detect_graduation_photo(
        leader_stagnant=False,
        补涨_accelerating=True,
        three_sectors_euphoria=False,
    )
    print(json.dumps(gp, ensure_ascii=False, indent=2))

    print("\n--- 4b. 毕业照判断（经典毕业照场景） ---")
    gp2 = tracker.detect_graduation_photo(
        leader_stagnant=True,
        补涨_accelerating=True,
        three_sectors_euphoria=True,
    )
    print(json.dumps(gp2, ensure_ascii=False, indent=2))

    # 5. 完整报告
    print("\n--- 5. 完整格式化报告 ---")
    tracker.print_report()

    print("\n演示结束。")


if __name__ == "__main__":
    demo()
