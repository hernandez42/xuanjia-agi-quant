#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场情绪 / 冰点引擎模块 (Market Sentiment Engine)

基于玄甲APEX-AGI交易体系的A股市场情绪与冰点判断逻辑：
- 冰点级别判断：下跌家数、连续冰点天数
- 关键点位监控：4068(箱体底) vs 4060(操作锚点)
- 30日线状态：首次跌破 vs 二次跌破
- 北向资金：逆势净流入 = 聪明钱信号
- 成交额：流动性充裕度判断

纯标准库实现，无第三方依赖。
"""

import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any


class MarketSentimentEngine:
    """
    A股市场情绪与冰点分析引擎。

    用于判断市场恐慌程度、关键点位状态、资金动向，
    并输出可操作的交易建议（尾盘低吸、停止买入、降仓等）。

    Attributes:
        history (List[Dict]): 历史冰点记录（用于连续天数判断）
        key_level_top (float): 箱体底关键点位
        key_level_anchor (float): 操作锚点
        mock_mode (bool): 是否使用模拟数据
    """

    # 关键点位常量
    KEY_LEVEL_TOP = 4068.0      # 箱体底
    KEY_LEVEL_ANCHOR = 4060.0   # 操作锚点

    # 冰点阈值
    ICE_GENERAL_THRESHOLD = 4200   # 一般冰点：下跌家数 > 4200
    ICE_NEAR_THRESHOLD = 4000      # 近4000只下跌观察阈值

    # 流动性阈值
    VOLUME_LIQUID_THRESHOLD = 20000  # 单位：亿，2万亿

    # 北向资金阈值
    NORTHBOUND_SMART_MONEY = 100   # 单位：亿，逆势净流入 > 100亿视为聪明钱

    def __init__(self):
        """初始化市场情绪引擎。"""
        self.history: List[Dict[str, Any]] = []
        self.mock_mode: bool = False
        self._cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 数据获取层 (Data Fetching)
    # ------------------------------------------------------------------

    def _fetch_mock_market_data(self) -> Dict[str, Any]:
        """
        返回预设的A股市场模拟数据。

        模拟场景设计（基于图片中的典型数据）：
        - 下跌家数 4500+（一般冰点）
        - 连续冰点天数 2 天
        - 指数点位 4055（跌破 4060 锚点）
        - 30日线状态：首次跌破
        - 北向资金逆势净流入 140 亿
        - 成交额 3.34 万亿

        Returns:
            模拟市场数据字典
        """
        return {
            "index_code": "SH000001",          # 上证指数
            "index_name": "上证指数",
            "index_price": 4055.32,
            "index_change_pct": -1.25,
            "prev_close": 4106.8,
            "ma30": 4072.5,
            "ma30_first_broken": True,         # 是否首次跌破
            "ma30_broken_count": 1,            # 跌破次数计数
            "declining_count": 4520,           # 下跌家数
            "rising_count": 650,               # 上涨家数
            "flat_count": 130,                 # 平盘家数
            "total_stocks": 5300,              # 总交易家数
            "northbound_net_inflow": 140.5,    # 北向资金净流入（亿）
            "turnover_volume": 33400.0,        # 成交额（亿）
            "timestamp": datetime.now().isoformat(),
            "mock": True,
        }

    def _fetch_market_data(self) -> Dict[str, Any]:
        """
        获取A股市场核心数据。

        当前版本以模拟数据为主（A股实时数据需专用API/数据源），
        预留了网络请求接口，失败时自动回退到 mock。

        Returns:
            市场数据字典
        """
        # 实际生产环境中可接入东方财富、同花顺等API
        # 此处统一使用 mock 数据以确保模块可独立运行
        try:
            # 预留：尝试从本地缓存或简易API获取
            # 若未来接入真实数据源，替换此处逻辑即可
            raise NotImplementedError("Real-time A-share API not configured")
        except Exception:
            self.mock_mode = True
            return self._fetch_mock_market_data()

    # ------------------------------------------------------------------
    # 冰点级别判断 (Ice Level)
    # ------------------------------------------------------------------

    def calculate_ice_level(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        计算当前市场的冰点级别。

        冰点分级：
        - 一般冰点：单天下跌家数 > 4200
        - 连续冰点：连续 3-4 天出现一般冰点
        - 观察期：连续 2 天近 4000 只下跌，需观察第三天

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            冰点分析结果字典，包含：
            - ice_level: 冰点级别 (none / general / consecutive / watch)
            - ice_name: 冰点中文名称
            - declining_count: 下跌家数
            - consecutive_days: 连续冰点天数
            - advice: 基于冰点级别的初步操作建议
        """
        if data is None:
            data = self._fetch_market_data()

        declining = data.get("declining_count", 0)
        total = data.get("total_stocks", 5300)

        result: Dict[str, Any] = {
            "ice_level": "none",
            "ice_name": "无冰点",
            "declining_count": declining,
            "total_stocks": total,
            "consecutive_days": 0,
            "advice": "正常交易",
            "analysis_time": datetime.now().isoformat(),
        }

        # 单天判断
        is_general_ice = declining > self.ICE_GENERAL_THRESHOLD
        is_near_ice = declining >= self.ICE_NEAR_THRESHOLD

        if not is_general_ice and not is_near_ice:
            result["advice"] = "市场情绪正常，按常规策略操作"
            return result

        # 计算连续冰点天数（基于历史记录）
        consecutive_days = self._count_consecutive_ice_days()
        result["consecutive_days"] = consecutive_days

        if is_general_ice:
            result["ice_level"] = "general"
            result["ice_name"] = "一般冰点"
            result["advice"] = "市场出现一般冰点，谨慎操作，控制仓位"

            if consecutive_days >= 3:
                result["ice_level"] = "consecutive"
                result["ice_name"] = "连续冰点"
                result["advice"] = (
                    f"连续 {consecutive_days} 天冰点，恐慌情绪充分释放，"
                    f"尾盘可低吸先手，博弈次日修复"
                )
            elif consecutive_days == 2:
                result["ice_level"] = "watch"
                result["ice_name"] = "观察期"
                result["advice"] = (
                    "连续 2 天近冰点，观察第三天走势，"
                    "若继续冰点则尾盘可尝试低吸"
                )

        elif is_near_ice and not is_general_ice:
            # 近 4000 只下跌但未达 4200
            if consecutive_days >= 2:
                result["ice_level"] = "watch"
                result["ice_name"] = "观察期"
                result["advice"] = (
                    "连续 2 天近 4000 只下跌，第三天若继续冰点可低吸，"
                    "否则等待明确信号"
                )
            else:
                result["ice_level"] = "mild"
                result["ice_name"] = "轻度恐慌"
                result["advice"] = "下跌家数较多，但未达冰点阈值，保持警惕"

        # 记录本次冰点状态到历史
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "declining_count": declining,
            "ice_level": result["ice_level"],
        })

        return result

    def _count_consecutive_ice_days(self) -> int:
        """
        统计最近连续出现冰点的天数。

        从 history 末尾向前遍历，直到遇到非冰点记录或日期不连续。

        Returns:
            连续冰点天数
        """
        if not self.history:
            # 模拟：假设今天是第 2 天连续冰点（用于演示）
            return 2

        count = 0
        today = datetime.now().date()
        for record in reversed(self.history):
            record_date = datetime.fromisoformat(record["timestamp"]).date()
            expected_date = today - timedelta(days=count)
            if record_date == expected_date and record.get("ice_level") != "none":
                count += 1
            else:
                break
        return count

    # ------------------------------------------------------------------
    # 关键点位判断 (Key Level)
    # ------------------------------------------------------------------

    def check_key_level(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        检查关键点位状态：4068(箱体底) vs 4060(操作锚点)。

        规则：
        - 点位在 4068 之上 = 越跌越买（箱体底部支撑有效）
        - 点位跌破 4060 且收不回来 = 停止一切买入
        - 介于 4060-4068 之间 = 谨慎观望，等待方向选择

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            点位判断结果字典，包含：
            - level_status: 点位状态 (above_box / in_zone / below_anchor)
            - level_name: 状态中文名称
            - index_price: 当前指数点位
            - key_level_top: 箱体底 4068
            - key_level_anchor: 操作锚点 4060
            - action: 点位对应的操作建议
        """
        if data is None:
            data = self._fetch_market_data()

        price = data.get("index_price", 0.0)
        top = self.KEY_LEVEL_TOP
        anchor = self.KEY_LEVEL_ANCHOR

        result: Dict[str, Any] = {
            "index_price": price,
            "key_level_top": top,
            "key_level_anchor": anchor,
            "level_status": "unknown",
            "level_name": "未知",
            "action": "观望",
            "analysis_time": datetime.now().isoformat(),
        }

        if price >= top:
            result["level_status"] = "above_box"
            result["level_name"] = "箱体底之上"
            result["action"] = "越跌越买（箱体支撑有效）"
        elif anchor <= price < top:
            result["level_status"] = "in_zone"
            result["level_name"] = "关键区间内"
            result["action"] = "谨慎观望，等待方向选择，控制仓位"
        else:
            result["level_status"] = "below_anchor"
            result["level_name"] = "跌破操作锚点"
            result["action"] = "停止一切买入，防范破位风险"

        return result

    # ------------------------------------------------------------------
    # 30日线状态分析 (MA30 Analysis)
    # ------------------------------------------------------------------

    def analyze_ma30_status(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析 30 日均线状态及其交易含义。

        规则：
        - 首次跌破 = 短期进入修复周期（2-3 天），可观察反弹力度
        - 二次跌破 = 趋势确认走坏，无条件降仓至 1-2 成
        - 未跌破 = 中期趋势完好

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            30日线分析结果字典，包含：
            - ma30_status: 状态 (intact / first_break / second_break)
            - ma30_name: 状态中文名称
            - index_price: 当前点位
            - ma30_value: 30 日均线值
            - broken_count: 跌破次数
            - action: 对应的操作建议
        """
        if data is None:
            data = self._fetch_market_data()

        price = data.get("index_price", 0.0)
        ma30 = data.get("ma30", price)
        first_broken = data.get("ma30_first_broken", False)
        broken_count = data.get("ma30_broken_count", 0)

        result: Dict[str, Any] = {
            "index_price": price,
            "ma30_value": ma30,
            "broken_count": broken_count,
            "ma30_status": "intact",
            "ma30_name": "趋势完好",
            "action": "中期趋势支撑有效，正常操作",
            "analysis_time": datetime.now().isoformat(),
        }

        if price >= ma30:
            return result

        # 已跌破
        if broken_count >= 2 or not first_broken:
            result["ma30_status"] = "second_break"
            result["ma30_name"] = "二次跌破"
            result["action"] = "30日线二次跌破，趋势确认走坏，无条件降仓至 1-2 成"
        else:
            result["ma30_status"] = "first_break"
            result["ma30_name"] = "首次跌破"
            result["action"] = "30日线首次跌破，进入短期修复周期（2-3天），观察反弹力度"

        return result

    # ------------------------------------------------------------------
    # 北向资金分析 (Northbound Capital)
    # ------------------------------------------------------------------

    def analyze_northbound(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析北向资金（沪深港通）流向及其信号含义。

        规则：
        - 逆势净流入 > 100 亿 = 聪明钱在买，市场可能接近底部
        - 大幅净流出 = 外资撤离，需警惕
        - 小幅波动 = 正常调仓，信号意义不大

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            北向资金分析结果字典，包含：
            - net_inflow: 净流入金额（亿）
            - signal: 信号类型 (smart_money / outflow / neutral)
            - signal_name: 信号中文名称
            - action: 操作建议
        """
        if data is None:
            data = self._fetch_market_data()

        inflow = data.get("northbound_net_inflow", 0.0)
        index_change = data.get("index_change_pct", 0.0)

        result: Dict[str, Any] = {
            "net_inflow": inflow,
            "index_change_pct": index_change,
            "signal": "neutral",
            "signal_name": "中性",
            "action": "北向资金波动不大，不作为主要决策依据",
            "analysis_time": datetime.now().isoformat(),
        }

        # 逆势净流入判定：指数下跌但北向大幅流入
        is_counter_trend = index_change < 0 and inflow > 0
        is_smart_money = inflow >= self.NORTHBOUND_SMART_MONEY

        if is_counter_trend and is_smart_money:
            result["signal"] = "smart_money"
            result["signal_name"] = "聪明钱买入"
            result["action"] = (
                f"指数下跌但北向逆势净流入 {inflow:.1f} 亿，"
                f"聪明钱正在抄底，可跟随布局"
            )
        elif inflow <= -50:
            result["signal"] = "outflow"
            result["signal_name"] = "外资撤离"
            result["action"] = (
                f"北向净流出 {abs(inflow):.1f} 亿，外资撤离明显，"
                f"需降低仓位应对"
            )
        elif inflow >= 50:
            result["signal"] = "inflow"
            result["signal_name"] = "资金流入"
            result["action"] = (
                f"北向净流入 {inflow:.1f} 亿，资金态度积极，"
                f"可作为加分项"
            )

        return result

    # ------------------------------------------------------------------
    # 成交额 / 流动性分析 (Volume & Liquidity)
    # ------------------------------------------------------------------

    def analyze_liquidity(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析市场成交额与流动性状态。

        规则：
        - 成交额 > 2 万亿 = 流动性充裕，市场有承接力
        - 成交额 < 1.5 万亿 = 流动性萎缩，需警惕
        - 介于之间 = 流动性中性

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            流动性分析结果字典
        """
        if data is None:
            data = self._fetch_market_data()

        volume = data.get("turnover_volume", 0.0)

        result: Dict[str, Any] = {
            "turnover_volume": volume,
            "liquidity_status": "neutral",
            "liquidity_name": "流动性中性",
            "action": "成交额一般，按常规策略操作",
            "analysis_time": datetime.now().isoformat(),
        }

        if volume >= self.VOLUME_LIQUID_THRESHOLD:
            result["liquidity_status"] = "abundant"
            result["liquidity_name"] = "流动性充裕"
            result["action"] = (
                f"成交额 {volume/10000:.2f} 万亿，未缩至 2 万亿以下，"
                f"市场流动性充裕，有承接力"
            )
        elif volume <= 15000:
            result["liquidity_status"] = "tight"
            result["liquidity_name"] = "流动性紧张"
            result["action"] = (
                f"成交额仅 {volume/10000:.2f} 万亿，流动性明显萎缩，"
                f"市场承接力不足，需降低仓位"
            )
        else:
            result["action"] = (
                f"成交额 {volume/10000:.2f} 万亿，流动性中等，"
                f"保持谨慎"
            )

        return result

    # ------------------------------------------------------------------
    # 综合交易建议 (Trading Advice)
    # ------------------------------------------------------------------

    def get_trading_advice(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        综合所有维度（冰点、点位、30日线、北向、流动性），输出最终交易建议。

        决策优先级：
        1. 清仓/极端风险信号（30日线二次跌破 + 跌破锚点）
        2. 红色信号（连续冰点 + 跌破锚点）
        3. 黄色信号（一般冰点 + 关键区间内）
        4. 机会信号（聪明钱 + 流动性充裕 + 首次跌破修复期）
        5. 正常观望

        Args:
            data: 可选，传入市场数据；为空时自动获取

        Returns:
            综合交易建议字典，包含：
            - overall_signal: 综合信号 (extreme_risk / caution / opportunity / neutral)
            - overall_name: 信号中文名称
            - position_pct: 建议仓位百分比
            - position_desc: 仓位描述
            - action: 核心操作建议
            - sub_analysis: 各子模块分析结果汇总
            - rationale: 完整决策理由列表
        """
        if data is None:
            data = self._fetch_market_data()

        # 并行执行各维度分析
        ice = self.calculate_ice_level(data)
        level = self.check_key_level(data)
        ma30 = self.analyze_ma30_status(data)
        north = self.analyze_northbound(data)
        liquidity = self.analyze_liquidity(data)

        sub_analysis = {
            "ice_level": ice,
            "key_level": level,
            "ma30_status": ma30,
            "northbound": north,
            "liquidity": liquidity,
        }

        # 综合决策逻辑
        advice: Dict[str, Any] = {
            "overall_signal": "neutral",
            "overall_name": "中性观望",
            "position_pct": 50,
            "position_desc": "5 成仓位",
            "action": "保持中性仓位，等待明确信号",
            "sub_analysis": sub_analysis,
            "rationale": [],
            "advice_time": datetime.now().isoformat(),
        }

        # 极端风险判定
        is_extreme_risk = (
            ma30["ma30_status"] == "second_break"
            or level["level_status"] == "below_anchor"
        )

        # 机会判定
        is_opportunity = (
            north["signal"] == "smart_money"
            and liquidity["liquidity_status"] == "abundant"
            and ice["ice_level"] in ("general", "consecutive", "watch")
        )

        # 谨慎判定
        is_caution = (
            ice["ice_level"] in ("general", "consecutive")
            or ma30["ma30_status"] == "first_break"
            or level["level_status"] == "in_zone"
        )

        if is_extreme_risk:
            advice["overall_signal"] = "extreme_risk"
            advice["overall_name"] = "极端风险"
            advice["position_pct"] = 15
            advice["position_desc"] = "1-2 成"
            advice["action"] = "无条件大幅降仓，停止买入"
            advice["rationale"] = [
                "【极端风险】多项关键指标同时恶化：",
            ]
            if ma30["ma30_status"] == "second_break":
                advice["rationale"].append(
                    f"- 30日线二次跌破({ma30['ma30_value']})，趋势确认走坏"
                )
            if level["level_status"] == "below_anchor":
                advice["rationale"].append(
                    f"- 指数跌破操作锚点 {self.KEY_LEVEL_ANCHOR}，"
                    f"当前 {level['index_price']}，支撑失效"
                )
            advice["rationale"].append(
                "操作：无条件降仓至 1-2 成，空仓观望亦可，等待趋势修复。"
            )

        elif is_opportunity:
            advice["overall_signal"] = "opportunity"
            advice["overall_name"] = "低吸机会"
            advice["position_pct"] = 60
            advice["position_desc"] = "6 成左右"
            advice["action"] = "尾盘可低吸先手，博弈次日修复"
            advice["rationale"] = [
                "【低吸机会】多项积极信号共振：",
                f"- 北向资金逆势净流入 {north['net_inflow']:.1f} 亿，聪明钱在买",
                f"- 成交额 {liquidity['turnover_volume']/10000:.2f} 万亿，流动性充裕",
                f"- 冰点级别：{ice['ice_name']}，恐慌情绪可能已充分释放",
                "操作：尾盘可分批低吸优质标的，仓位控制在 6 成左右，",
                "次日若反弹可获利了结，若继续下跌则止损。",
            ]

        elif is_caution:
            advice["overall_signal"] = "caution"
            advice["overall_name"] = "谨慎防御"
            advice["position_pct"] = 40
            advice["position_desc"] = "4 成以下"
            advice["action"] = "控制仓位，谨慎操作"
            advice["rationale"] = [
                "【谨慎防御】市场出现风险信号，需控制仓位：",
            ]
            if ice["ice_level"] != "none":
                advice["rationale"].append(
                    f"- 冰点状态：{ice['ice_name']}，"
                    f"下跌家数 {ice['declining_count']} 只"
                )
            if ma30["ma30_status"] == "first_break":
                advice["rationale"].append(
                    f"- 30日线首次跌破，进入 2-3 天修复周期，"
                    f"观察反弹力度再决定加仓"
                )
            if level["level_status"] == "in_zone":
                advice["rationale"].append(
                    f"- 指数处于 {self.KEY_LEVEL_ANCHOR}-{self.KEY_LEVEL_TOP} 关键区间，"
                    f"方向不明，等待突破"
                )
            advice["rationale"].append(
                "操作：仓位降至 4 成以下，停止追涨，只低吸不追高。"
            )

        else:
            advice["rationale"] = [
                "【中性观望】各维度指标均未出现极端信号：",
                f"- 冰点：{ice['ice_name']}",
                f"- 点位：{level['level_name']} ({level['index_price']})",
                f"- 30日线：{ma30['ma30_name']}",
                f"- 北向：{north['signal_name']}",
                f"- 流动性：{liquidity['liquidity_name']}",
                "操作：维持 5 成左右中性仓位，按常规策略执行。",
            ]

        return advice

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def to_json(self, obj: Dict[str, Any], indent: int = 2) -> str:
        """将结果对象序列化为 JSON 字符串。"""
        return json.dumps(obj, ensure_ascii=False, indent=indent)

    def get_history(self) -> List[Dict[str, Any]]:
        """获取历史分析记录。"""
        return self.history

    def reset_history(self) -> None:
        """清空历史记录。"""
        self.history.clear()


def main():
    """
    市场情绪 / 冰点引擎演示入口。

    演示流程：
    1. 初始化 MarketSentimentEngine
    2. 获取A股市场数据（含 mock fallback）
    3. 执行冰点级别计算
    4. 检查关键点位
    5. 分析30日线状态
    6. 分析北向资金
    7. 分析流动性
    8. 输出综合交易建议
    9. 打印完整 JSON 报告
    """
    print("=" * 60)
    print("玄甲 APEX-AGI | 市场情绪 / 冰点引擎 (Market Sentiment Engine)")
    print("=" * 60)

    engine = MarketSentimentEngine()

    # Step 1: 获取数据
    print("\n[1/8] 正在获取A股市场数据...")
    data = engine._fetch_market_data()
    if data.get("mock"):
        print("    已使用模拟数据（A股实时数据需专用API接入）")
    print(f"    数据时间: {data.get('timestamp')}")
    print(f"    上证指数: {data.get('index_price')} ({data.get('index_change_pct')}%)")

    # Step 2: 冰点级别
    print("\n[2/8] 计算冰点级别...")
    ice = engine.calculate_ice_level(data)
    print(f"    冰点级别: {ice['ice_name']} ({ice['ice_level']})")
    print(f"    下跌家数: {ice['declining_count']} / {ice['total_stocks']}")
    print(f"    连续天数: {ice['consecutive_days']}")
    print(f"    初步建议: {ice['advice']}")

    # Step 3: 关键点位
    print("\n[3/8] 检查关键点位...")
    level = engine.check_key_level(data)
    print(f"    当前点位: {level['index_price']}")
    print(f"    箱体底:   {level['key_level_top']}")
    print(f"    操作锚点: {level['key_level_anchor']}")
    print(f"    点位状态: {level['level_name']} ({level['level_status']})")
    print(f"    操作建议: {level['action']}")

    # Step 4: 30日线
    print("\n[4/8] 分析30日线状态...")
    ma30 = engine.analyze_ma30_status(data)
    print(f"    当前点位: {ma30['index_price']}")
    print(f"    MA30数值: {ma30['ma30_value']}")
    print(f"    跌破次数: {ma30['broken_count']}")
    print(f"    趋势状态: {ma30['ma30_name']} ({ma30['ma30_status']})")
    print(f"    操作建议: {ma30['action']}")

    # Step 5: 北向资金
    print("\n[5/8] 分析北向资金...")
    north = engine.analyze_northbound(data)
    print(f"    净流入:   {north['net_inflow']:.1f} 亿")
    print(f"    信号类型: {north['signal_name']} ({north['signal']})")
    print(f"    操作建议: {north['action']}")

    # Step 6: 流动性
    print("\n[6/8] 分析流动性...")
    liquidity = engine.analyze_liquidity(data)
    print(f"    成交额:   {liquidity['turnover_volume']/10000:.2f} 万亿")
    print(f"    流动性:   {liquidity['liquidity_name']} ({liquidity['liquidity_status']})")
    print(f"    操作建议: {liquidity['action']}")

    # Step 7: 综合建议
    print("\n[7/8] 生成综合交易建议...")
    advice = engine.get_trading_advice(data)
    print(f"    综合信号: {advice['overall_name']} ({advice['overall_signal']})")
    print(f"    建议仓位: {advice['position_desc']} ({advice['position_pct']}%)")
    print(f"    核心操作: {advice['action']}")
    print("    决策理由:")
    for line in advice.get("rationale", []):
        print(f"      {line}")

    # Step 8: 完整 JSON 报告
    print("\n[8/8] 完整 JSON 报告")
    print("-" * 60)
    full_report = {
        "market_data": data,
        "ice_level_analysis": ice,
        "key_level_analysis": level,
        "ma30_analysis": ma30,
        "northbound_analysis": north,
        "liquidity_analysis": liquidity,
        "trading_advice": advice,
    }
    print(engine.to_json(full_report))
    print("=" * 60)


if __name__ == "__main__":
    main()
