#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股跟踪体系模块 (US Market Tracker)

基于玄甲APEX-AGI交易体系的美股跟踪逻辑：
- 跟踪三大指数: 道指(DJI)/纳指(IXIC)/标普(GSPC)
- 跟踪三巨头: NVDA / MSFT / AAPL
- 三级信号体系（黄色/红色/清仓）
- 辅助判断因子：戴尔AI服务器需求、英伟达龙头轮跌、黄金避险、席勒PE

纯标准库实现，无第三方依赖。
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any


class USMarketTracker:
    """
    美股跟踪器，用于监控美股核心指数与龙头个股，
    并基于三级信号体系输出仓位建议。

    Attributes:
        indices (List[str]): 跟踪的三大指数代码列表
        giants (List[str]): 跟踪的科技三巨头代码列表
        signals (List[Dict]): 历史信号记录
        mock_mode (bool): 是否使用模拟数据（当网络请求失败时自动启用）
    """

    # 三大指数代码（Yahoo Finance 格式）
    INDICES = {
        "DJI": "^DJI",      # 道琼斯工业指数
        "IXIC": "^IXIC",    # 纳斯达克综合指数
        "GSPC": "^GSPC",    # 标普500指数
    }

    # 科技三巨头
    GIANTS = {
        "NVDA": "NVDA",     # 英伟达
        "MSFT": "MSFT",     # 微软
        "AAPL": "AAPL",     # 苹果
    }

    # 辅助参考标的
    AUXILIARY = {
        "DELL": "DELL",     # 戴尔（AI服务器需求风向标）
        "GOLD": "GC=F",     # 黄金期货（避险资产）
        "SOX": "^SOX",      # 费城半导体指数
    }

    # 席勒PE历史参考值
    SHILLER_PE_HISTORICAL = {
        "current": 42.32,
        "2000_bubble_peak": 44.19,
        "long_term_average": 17.0,
    }

    def __init__(self):
        """初始化美股跟踪器。"""
        self.signals: List[Dict[str, Any]] = []
        self.mock_mode: bool = False
        self._cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 数据获取层 (Data Fetching)
    # ------------------------------------------------------------------

    def _fetch_yahoo_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        通过 Yahoo Finance API 获取单只标的的实时行情。

        Args:
            symbol: Yahoo Finance 代码，如 "^IXIC"、"NVDA"

        Returns:
            包含最新价格、涨跌幅、成交量等字段的字典；失败时返回 None
        """
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?interval=1d&range=5d"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            timestamps = result.get("timestamp", [])
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])

            if not timestamps or not closes or len(closes) < 2:
                return None

            latest_close = closes[-1]
            prev_close = closes[-2] if len(closes) >= 2 else meta.get("previousClose")
            change_pct = (
                round((latest_close - prev_close) / prev_close * 100, 2)
                if prev_close and prev_close != 0
                else 0.0
            )

            # 计算简单 20 日/30 日均线（基于返回的 5 日数据做近似）
            ma20 = sum(closes) / len(closes) if closes else latest_close
            ma30 = ma20  # 数据不足时近似

            return {
                "symbol": symbol,
                "price": round(latest_close, 2),
                "prev_close": round(prev_close, 2) if prev_close else None,
                "change_pct": change_pct,
                "volume": meta.get("regularMarketVolume"),
                "ma20": round(ma20, 2),
                "ma30": round(ma30, 2),
                "timestamp": datetime.fromtimestamp(timestamps[-1]).isoformat(),
            }
        except Exception:
            return None

    def _mock_quote(self, symbol: str) -> Dict[str, Any]:
        """
        当网络请求失败时，返回预设的模拟行情数据。

        Args:
            symbol: 标的代码

        Returns:
            模拟行情字典
        """
        mock_data = {
            "^DJI": {
                "price": 42150.0,
                "prev_close": 42300.0,
                "change_pct": -0.35,
                "volume": 320000000,
                "ma20": 42350.0,
                "ma30": 42200.0,
            },
            "^IXIC": {
                "price": 17820.0,
                "prev_close": 18200.0,
                "change_pct": -2.09,
                "volume": 5800000000,
                "ma20": 18100.0,
                "ma30": 17950.0,
            },
            "^GSPC": {
                "price": 5450.0,
                "prev_close": 5480.0,
                "change_pct": -0.55,
                "volume": 2100000000,
                "ma20": 5490.0,
                "ma30": 5470.0,
            },
            "NVDA": {
                "price": 128.5,
                "prev_close": 130.3,
                "change_pct": -1.38,
                "volume": 45000000,
                "ma20": 131.0,
                "ma30": 129.5,
            },
            "MSFT": {
                "price": 445.2,
                "prev_close": 446.0,
                "change_pct": -0.18,
                "volume": 22000000,
                "ma20": 448.0,
                "ma30": 446.5,
            },
            "AAPL": {
                "price": 212.3,
                "prev_close": 214.0,
                "change_pct": -0.79,
                "volume": 55000000,
                "ma20": 215.0,
                "ma30": 213.5,
            },
            "DELL": {
                "price": 145.8,
                "prev_close": 109.8,
                "change_pct": 32.8,
                "volume": 35000000,
                "ma20": 112.0,
                "ma30": 111.0,
            },
            "GC=F": {
                "price": 2365.0,
                "prev_close": 2314.0,
                "change_pct": 2.2,
                "volume": 180000,
                "ma20": 2320.0,
                "ma30": 2310.0,
            },
            "^SOX": {
                "price": 4850.0,
                "prev_close": 4950.0,
                "change_pct": -2.02,
                "volume": 120000000,
                "ma20": 4980.0,
                "ma30": 4920.0,
            },
        }
        base = mock_data.get(symbol, {
            "price": 100.0,
            "prev_close": 100.0,
            "change_pct": 0.0,
            "volume": 1000000,
            "ma20": 100.0,
            "ma30": 100.0,
        })
        base["symbol"] = symbol
        base["timestamp"] = datetime.now().isoformat()
        return base

    def fetch_us_data(self) -> Dict[str, Any]:
        """
        获取美股核心数据，包括三大指数、三巨头及辅助参考标的。

        网络请求失败时自动回退到模拟数据，并标记 mock_mode。

        Returns:
            结构化数据字典，包含 indices、giants、auxiliary 三个分组
        """
        result: Dict[str, Any] = {
            "indices": {},
            "giants": {},
            "auxiliary": {},
            "fetch_time": datetime.now().isoformat(),
            "mock": False,
        }

        all_symbols = {
            **self.INDICES,
            **self.GIANTS,
            **self.AUXILIARY,
        }

        any_mock = False
        for name, symbol in all_symbols.items():
            data = self._fetch_yahoo_quote(symbol)
            if data is None:
                data = self._mock_quote(symbol)
                any_mock = True

            if name in self.INDICES:
                result["indices"][name] = data
            elif name in self.GIANTS:
                result["giants"][name] = data
            else:
                result["auxiliary"][name] = data

        if any_mock:
            self.mock_mode = True
            result["mock"] = True

        self._cache = result
        return result

    # ------------------------------------------------------------------
    # 信号分析层 (Signal Analysis)
    # ------------------------------------------------------------------

    def _check_yellow_signal(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        黄色信号判断：纳指上涨，但三巨头中有两个开始做顶。

        做顶判定：价格低于 20 日均线且当日收跌。

        Args:
            data: fetch_us_data 返回的结构化数据

        Returns:
            (是否触发, 理由描述)
        """
        ixic = data.get("indices", {}).get("IXIC", {})
        giants = data.get("giants", {})

        # 纳指需上涨
        if ixic.get("change_pct", 0) <= 0:
            return False, "纳指未上涨，黄色信号不触发"

        topping_count = 0
        topping_names = []
        for code, info in giants.items():
            price = info.get("price", 0)
            ma20 = info.get("ma20", price)
            change_pct = info.get("change_pct", 0)
            if price < ma20 and change_pct < 0:
                topping_count += 1
                topping_names.append(code)

        if topping_count >= 2:
            return True, (
                f"纳指上涨({ixic.get('change_pct', 0):.2f}%)，"
                f"但三巨头中 {', '.join(topping_names)} 共{topping_count}只开始做顶"
            )
        return False, "三巨头做顶数量不足，黄色信号不触发"

    def _check_red_signal(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        红色信号判断：纳指单日跌幅 >= 2% 且跌破 20 日均线。

        Args:
            data: fetch_us_data 返回的结构化数据

        Returns:
            (是否触发, 理由描述)
        """
        ixic = data.get("indices", {}).get("IXIC", {})
        change_pct = ixic.get("change_pct", 0)
        price = ixic.get("price", 0)
        ma20 = ixic.get("ma20", price)

        if change_pct <= -2.0 and price < ma20:
            return True, (
                f"纳指单日大跌 {change_pct:.2f}% 且跌破 20 日均线"
                f"(价格 {price} < MA20 {ma20})"
            )
        return False, "红色信号条件未满足"

    def _check_clearance_signal(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        清仓信号判断：纳指有效跌破 30 日均线 + 费城半导体指数领跌。

        领跌判定：费城半导体指数跌幅 >= 2% 且跌幅大于纳指。

        Args:
            data: fetch_us_data 返回的结构化数据

        Returns:
            (是否触发, 理由描述)
        """
        ixic = data.get("indices", {}).get("IXIC", {})
        sox = data.get("auxiliary", {}).get("SOX", {})

        price = ixic.get("price", 0)
        ma30 = ixic.get("ma30", price)
        ixic_change = ixic.get("change_pct", 0)
        sox_change = sox.get("change_pct", 0)

        nasdaq_broken = price < ma30
        sox_leading = sox_change <= -2.0 and sox_change < ixic_change

        if nasdaq_broken and sox_leading:
            return True, (
                f"纳指有效跌破 30 日均线(价格 {price} < MA30 {ma30})，"
                f"且费城半导体指数领跌 {sox_change:.2f}%"
            )
        return False, "清仓信号条件未满足"

    def _auxiliary_analysis(self, data: Dict[str, Any]) -> List[str]:
        """
        辅助因子分析，用于补充信号判断的上下文。

        当前包含：
        - 戴尔涨幅（AI 服务器需求热度）
        - 英伟达跌幅（龙头内部轮跌）
        - 黄金涨幅（避险情绪）
        - 席勒 PE（估值泡沫程度）

        Args:
            data: fetch_us_data 返回的结构化数据

        Returns:
            辅助判断理由列表
        """
        reasons: List[str] = []
        aux = data.get("auxiliary", {})
        giants = data.get("giants", {})

        # 戴尔 AI 服务器需求
        dell = aux.get("DELL", {})
        dell_change = dell.get("change_pct", 0)
        if dell_change >= 20:
            reasons.append(
                f"戴尔暴涨 {dell_change:.2f}%，AI 服务器需求极度旺盛，"
                f"需警惕短期情绪过热"
            )
        elif dell_change >= 5:
            reasons.append(
                f"戴尔上涨 {dell_change:.2f}%，AI 服务器需求持续强劲"
            )
        elif dell_change <= -5:
            reasons.append(
                f"戴尔下跌 {dell_change:.2f}%，AI 服务器需求可能降温"
            )

        # 英伟达龙头轮跌
        nvda = giants.get("NVDA", {})
        nvda_change = nvda.get("change_pct", 0)
        if nvda_change < -1.0:
            reasons.append(
                f"英伟达下跌 {nvda_change:.2f}%，龙头内部出现轮跌迹象，"
                f"资金可能正在切换"
            )
        elif nvda_change > 3.0:
            reasons.append(
                f"英伟达上涨 {nvda_change:.2f}%，龙头资金回流"
            )

        # 黄金避险
        gold = aux.get("GOLD", {})
        gold_change = gold.get("change_pct", 0)
        if gold_change >= 2.0:
            reasons.append(
                f"黄金大涨 {gold_change:.2f}%，市场避险情绪升温，"
                f"需关注风险资产承压"
            )
        elif gold_change <= -1.5:
            reasons.append(
                f"黄金下跌 {gold_change:.2f}%，避险情绪回落，风险偏好回升"
            )

        # 席勒 PE
        shiller = self.SHILLER_PE_HISTORICAL
        current_pe = shiller["current"]
        bubble_peak = shiller["2000_bubble_peak"]
        gap = bubble_peak - current_pe
        if gap <= 3:
            reasons.append(
                f"席勒 PE 为 {current_pe}，距 2000 年互联网泡沫顶 "
                f"({bubble_peak}) 仅 {gap:.2f} 点，估值处于历史极端高位"
            )
        elif current_pe > 30:
            reasons.append(
                f"席勒 PE 为 {current_pe}，显著高于长期均值 "
                f"({shiller['long_term_average']})，估值偏高"
            )

        return reasons

    def analyze_signals(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行三级信号分析，输出当前信号级别与详细理由。

        信号优先级（从高到低）：
        1. 清仓信号（红色最高级）
        2. 红色信号
        3. 黄色信号
        4. 无信号 / 正常

        Args:
            data: 可选，传入已获取的数据；为空时自动调用 fetch_us_data()

        Returns:
            信号分析结果字典，包含：
            - signal_level: 信号级别 (clearance / red / yellow / none)
            - signal_name: 信号中文名称
            - reasons: 主信号触发理由列表
            - auxiliary_reasons: 辅助分析理由列表
            - raw_data: 底层行情数据快照
        """
        if data is None:
            data = self.fetch_us_data()

        result: Dict[str, Any] = {
            "signal_level": "none",
            "signal_name": "无信号",
            "reasons": [],
            "auxiliary_reasons": [],
            "raw_data": data,
            "analysis_time": datetime.now().isoformat(),
        }

        # 按优先级依次检测
        clearance_triggered, clearance_reason = self._check_clearance_signal(data)
        if clearance_triggered:
            result["signal_level"] = "clearance"
            result["signal_name"] = "清仓信号"
            result["reasons"].append(clearance_reason)
            result["auxiliary_reasons"] = self._auxiliary_analysis(data)
            self.signals.append(result)
            return result

        red_triggered, red_reason = self._check_red_signal(data)
        if red_triggered:
            result["signal_level"] = "red"
            result["signal_name"] = "红色信号"
            result["reasons"].append(red_reason)
            result["auxiliary_reasons"] = self._auxiliary_analysis(data)
            self.signals.append(result)
            return result

        yellow_triggered, yellow_reason = self._check_yellow_signal(data)
        if yellow_triggered:
            result["signal_level"] = "yellow"
            result["signal_name"] = "黄色信号"
            result["reasons"].append(yellow_reason)
            result["auxiliary_reasons"] = self._auxiliary_analysis(data)
            self.signals.append(result)
            return result

        # 无信号时仍输出辅助分析
        result["reasons"].append("三级信号均未触发，市场处于正常波动区间")
        result["auxiliary_reasons"] = self._auxiliary_analysis(data)
        self.signals.append(result)
        return result

    # ------------------------------------------------------------------
    # 仓位建议层 (Position Advice)
    # ------------------------------------------------------------------

    def get_position_advice(self, signal_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        基于信号分析结果，输出 A 股仓位建议。

        仓位映射规则：
        - 清仓信号 -> 无条件空仓 (0%)
        - 红色信号 -> 大幅降仓至 1-2 成 (10%-20%)
        - 黄色信号 -> 仓位降至 5 成以下 (<50%)
        - 无信号   -> 维持现有仓位，结合辅助因子微调

        Args:
            signal_result: 可选，传入 analyze_signals() 的结果；
                           为空时自动执行信号分析

        Returns:
            仓位建议字典，包含：
            - position_pct: 建议仓位百分比（如 0、10、30）
            - position_desc: 仓位描述（如"空仓"、"1-2成"）
            - action: 操作建议（如"无条件清仓"、"大幅减仓"）
            - rationale: 完整决策理由
        """
        if signal_result is None:
            signal_result = self.analyze_signals()

        level = signal_result.get("signal_level", "none")
        reasons = signal_result.get("reasons", [])
        aux_reasons = signal_result.get("auxiliary_reasons", [])

        advice: Dict[str, Any] = {
            "signal_level": level,
            "position_pct": 100,
            "position_desc": "满仓",
            "action": "持仓观望",
            "rationale": [],
            "advice_time": datetime.now().isoformat(),
        }

        if level == "clearance":
            advice["position_pct"] = 0
            advice["position_desc"] = "空仓 (0%)"
            advice["action"] = "无条件清仓"
            advice["rationale"] = [
                "【清仓信号】纳指有效跌破 30 日均线，且费城半导体指数领跌，",
                "意味着美股科技板块进入系统性调整，A 股相关映射板块风险极高。",
                "操作：无条件空仓，等待趋势修复。",
            ]

        elif level == "red":
            advice["position_pct"] = 15
            advice["position_desc"] = "1-2 成 (10%-20%)"
            advice["action"] = "大幅降仓"
            advice["rationale"] = [
                "【红色信号】纳指单日暴跌且跌破 20 日均线，短期趋势恶化。",
                "操作：将 A 股仓位大幅降至 1-2 成，保留核心底仓。",
                "后续观察：若 3 日内无法收复 20 日线，考虑进一步降至空仓。",
            ]

        elif level == "yellow":
            advice["position_pct"] = 40
            advice["position_desc"] = "4 成以下 (<50%)"
            advice["action"] = "减仓至半仓以下"
            advice["rationale"] = [
                "【黄色信号】纳指虽上涨，但三巨头中两只开始做顶，",
                "表明科技龙头内部分化，资金开始撤离高估值标的。",
                "操作：将 A 股仓位降至 5 成以下，规避高位科技股映射风险。",
            ]

        else:
            # 无信号时，结合辅助因子给出微调建议
            advice["position_pct"] = 80
            advice["position_desc"] = "8 成左右"
            advice["action"] = "维持高仓位，但保持警惕"
            advice["rationale"] = [
                "【无信号】美股三级信号均未触发，大趋势未破坏。",
            ]
            # 根据辅助因子微调
            for r in aux_reasons:
                if "席勒 PE" in r and "极端高位" in r:
                    advice["position_pct"] = 60
                    advice["position_desc"] = "6 成左右"
                    advice["action"] = "适度降仓，防范估值风险"
                    advice["rationale"].append(
                        f"辅助判断：{r}，建议提前降低仓位以应对潜在回调。"
                    )
                    break
            else:
                advice["rationale"].append("辅助因子未提示重大风险，维持正常仓位。")

        # 追加主信号理由与辅助理由
        advice["rationale"].extend([f"主因：{r}" for r in reasons])
        if aux_reasons:
            advice["rationale"].append("--- 辅助判断 ---")
            advice["rationale"].extend(aux_reasons)

        return advice

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def to_json(self, obj: Dict[str, Any], indent: int = 2) -> str:
        """将结果对象序列化为 JSON 字符串。"""
        return json.dumps(obj, ensure_ascii=False, indent=indent)

    def get_signal_history(self) -> List[Dict[str, Any]]:
        """获取历史信号记录。"""
        return self.signals


def main():
    """
    美股跟踪器演示入口。

    演示流程：
    1. 初始化 USMarketTracker
    2. 获取美股实时数据（含 mock fallback）
    3. 执行三级信号分析
    4. 输出仓位建议
    5. 打印完整 JSON 报告
    """
    print("=" * 60)
    print("玄甲 APEX-AGI | 美股跟踪体系 (US Market Tracker)")
    print("=" * 60)

    tracker = USMarketTracker()

    # Step 1: 获取数据
    print("\n[1/4] 正在获取美股数据...")
    data = tracker.fetch_us_data()
    if data.get("mock"):
        print("    ⚠ 网络请求失败，已切换至模拟数据模式")
    print(f"    数据时间: {data.get('fetch_time')}")
    print(f"    三大指数: {list(data.get('indices', {}).keys())}")
    print(f"    三巨头:   {list(data.get('giants', {}).keys())}")

    # Step 2: 信号分析
    print("\n[2/4] 执行三级信号分析...")
    signal_result = tracker.analyze_signals(data)
    print(f"    当前信号: {signal_result['signal_name']} ({signal_result['signal_level']})")
    for r in signal_result.get("reasons", []):
        print(f"    - {r}")

    # Step 3: 仓位建议
    print("\n[3/4] 生成 A 股仓位建议...")
    advice = tracker.get_position_advice(signal_result)
    print(f"    建议仓位: {advice['position_desc']}")
    print(f"    操作建议: {advice['action']}")
    print("    决策理由:")
    for line in advice.get("rationale", []):
        print(f"      {line}")

    # Step 4: 输出完整报告
    print("\n[4/4] 完整 JSON 报告")
    print("-" * 60)
    full_report = {
        "us_market_data": data,
        "signal_analysis": signal_result,
        "position_advice": advice,
    }
    print(tracker.to_json(full_report))
    print("=" * 60)


if __name__ == "__main__":
    main()
