#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
strategy_pipeline.py — 玄甲AGI 统一策略管线
═══════════════════════════════════════════════════════════════════════════════
将6大独立引擎串联为一个完整的日频策略流水线：

  1. 数据采集 (DataFetcher)          → 新闻 + 行情 + K线
  2. 新闻情绪 (NewsSentimentEngine)   → 消息面情绪分析
  3. 多因子筛选 (MultiFactorSelector) → 96因子综合评分
  4. X大神策略 (XGodStrategyEngine)   → 4步闭环选股 + 超越融合
  5. 超能力融合 (SuperpowerFusionEngine) → 五维化学反应融合
  6. 风控引擎 (PortfolioRiskManager)  → 回撤/仓位/压力测试
  7. 仓位计算 (PositionSizer)         → 凯利 + 波动率综合仓位

设计原则：
  - 懒加载导入，避免循环依赖
  - 所有外部数据获取均 try/except 包裹，网络不可用时自动降级为模拟数据
  - 仅依赖标准库，无第三方包
  - 中文 docstring，PipelineResult 数据类承载全部输出
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
#  确保本模块所在目录在 sys.path 中（用于懒加载兄弟模块）
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ═══════════════════════════════════════════════════════════════════════════
#  PipelineResult — 管线输出数据类
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineResult:
    """
    策略管线完整输出

    承载管线7个阶段的全部中间结果与最终结论，便于上层调用方
    序列化存储或生成报告。
    """
    # ---------- 元信息 ----------
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    stock_pool: List[str] = field(default_factory=list)

    # ---------- 阶段1: 数据采集 ----------
    raw_news: List[Dict] = field(default_factory=list)
    quotes: Dict[str, Dict] = field(default_factory=dict)
    klines: Dict[str, List[Dict]] = field(default_factory=dict)
    factor_inputs: Dict[str, Dict] = field(default_factory=dict)

    # ---------- 阶段2: 新闻情绪 ----------
    macro_sentiment: float = 0.0
    sector_sentiments: Dict[str, float] = field(default_factory=dict)
    stock_sentiments: Dict[str, float] = field(default_factory=dict)

    # ---------- 阶段3: 多因子筛选 ----------
    multi_factor_top: List[Dict] = field(default_factory=list)

    # ---------- 阶段4: X大神策略 ----------
    xgod_step1: List[str] = field(default_factory=list)
    xgod_step2: List[str] = field(default_factory=list)
    xgod_red_team: Dict[str, Dict] = field(default_factory=dict)
    xgod_beyond_x: Dict[str, Dict] = field(default_factory=dict)

    # ---------- 阶段5: 超能力融合 ----------
    fusion_results: List[Dict] = field(default_factory=list)

    # ---------- 阶段6: 风控 ----------
    drawdown_action: Dict = field(default_factory=dict)
    position_weights: Dict = field(default_factory=dict)
    stress_test: Dict = field(default_factory=dict)

    # ---------- 阶段7: 仓位计算 ----------
    position_sizes: Dict[str, Dict] = field(default_factory=dict)

    # ---------- 最终结论 ----------
    final_recommendations: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """序列化为字典（递归处理 dataclass / list / dict）"""
        import json
        raw = json.dumps(self, default=str, ensure_ascii=False)
        return json.loads(raw)


# ═══════════════════════════════════════════════════════════════════════════
#  StrategyPipeline — 统一策略管线
# ═══════════════════════════════════════════════════════════════════════════

class StrategyPipeline:
    """
    统一策略管线 — 将6大引擎串联为一个完整的日频策略流水线

    使用方式::

        pipeline = StrategyPipeline(stock_pool=["600519", "300750", "002594"])
        result = pipeline.run_daily_scan()
        report = pipeline.generate_report(result)

    管线流程::

        数据采集 → 新闻情绪 → 多因子筛选 → X大神策略
        → 超能力融合 → 风控检查 → 仓位计算 → 最终推荐
    """

    # ------------------------------------------------------------------
    #  初始化
    # ------------------------------------------------------------------

    def __init__(self, stock_pool: List[str]):
        """
        初始化策略管线

        Args:
            stock_pool: 股票代码列表，如 ["600519", "300750", "002594"]
        """
        self.stock_pool = list(stock_pool)
        self._result: Optional[PipelineResult] = None

    # ------------------------------------------------------------------
    #  公开方法
    # ------------------------------------------------------------------

    def run_daily_scan(self) -> Dict:
        """
        执行完整日频扫描管线

        按照以下7个阶段依次执行：
          1. 数据采集 — 获取新闻、行情、K线
          2. 新闻情绪 — 分析消息面情绪
          3. 多因子筛选 — 96因子综合评分
          4. X大神策略 — 4步闭环 + 超越融合
          5. 超能力融合 — 五维化学反应融合
          6. 风控检查 — 回撤/仓位/压力测试
          7. 仓位计算 — 凯利 + 波动率综合仓位

        Returns:
            PipelineResult 转字典后的完整结果
        """
        result = PipelineResult(stock_pool=self.stock_pool)
        print("=" * 78)
        print("  玄甲AGI 统一策略管线 — 日频扫描")
        print(f"  时间: {result.timestamp}")
        print(f"  股票池: {self.stock_pool}")
        print("=" * 78)

        # ── 阶段1: 数据采集 ──
        print("\n[阶段1/7] 数据采集 ...")
        self._stage1_data_acquisition(result)

        # ── 阶段2: 新闻情绪 ──
        print("[阶段2/7] 新闻情绪分析 ...")
        self._stage2_news_sentiment(result)

        # ── 阶段3: 多因子筛选 ──
        print("[阶段3/7] 多因子筛选 (96因子) ...")
        self._stage3_multi_factor(result)

        # ── 阶段4: X大神策略 ──
        print("[阶段4/7] X大神4步闭环策略 ...")
        self._stage4_xgod_strategy(result)

        # ── 阶段5: 超能力融合 ──
        print("[阶段5/7] 超能力化学反应融合 ...")
        self._stage5_superpower_fusion(result)

        # ── 阶段6: 风控检查 ──
        print("[阶段6/7] 风控引擎检查 ...")
        self._stage6_risk_control(result)

        # ── 阶段7: 仓位计算 ──
        print("[阶段7/7] 仓位计算 ...")
        self._stage7_position_sizing(result)

        # ── 汇总最终推荐 ──
        self._assemble_final_recommendations(result)

        self._result = result
        print("\n" + "=" * 78)
        print("  日频扫描完成")
        print("=" * 78)
        return result.to_dict()

    def run_backtest(self, days: int = 120) -> Dict:
        """
        使用管线策略运行回测

        基于管线逻辑构造策略函数，接入 BacktestEngine 执行历史回测。

        Args:
            days: 回测交易日天数，默认120

        Returns:
            回测结果字典，包含关键指标与交易记录
        """
        from backtest_engine import (
            BacktestEngine,
            BacktestResult,
            generate_mock_market_data,
        )

        print("=" * 78)
        print(f"  玄甲AGI 统一策略管线 — 回测模式 ({days}个交易日)")
        print("=" * 78)

        # 构造模拟行情数据
        stock_pool_config = []
        for code in self.stock_pool[:5]:  # 最多5只，避免回测过慢
            base_price = random.uniform(20, 200)
            stock_pool_config.append({
                "code": code,
                "name": code,
                "base_price": base_price,
                "volatility": random.uniform(0.02, 0.04),
                "trend": random.uniform(0.0001, 0.0005),
            })

        market_data = generate_mock_market_data(
            trading_days=days,
            stock_pool=stock_pool_config if stock_pool_config else None,
        )

        # 创建策略函数
        strategy_func = self._create_backtest_strategy()

        # 执行回测
        engine = BacktestEngine(
            strategy=strategy_func,
            market_data=market_data,
            initial_capital=1_000_000.0,
        )
        bt_result: BacktestResult = engine.run()

        # 输出摘要
        summary = bt_result.summary()
        print("\n  回测结果摘要:")
        for k, v in summary.items():
            print(f"    {k}: {v}")

        return {
            "total_return": bt_result.total_return,
            "annual_return": bt_result.annual_return,
            "max_drawdown": bt_result.max_drawdown,
            "sharpe_ratio": bt_result.sharpe_ratio,
            "win_rate": bt_result.win_rate,
            "profit_loss_ratio": bt_result.profit_loss_ratio,
            "calmar_ratio": bt_result.calmar_ratio,
            "total_trades": bt_result.total_trades,
            "start_date": bt_result.start_date,
            "end_date": bt_result.end_date,
            "initial_capital": bt_result.initial_capital,
            "final_capital": bt_result.final_capital,
            "trade_records": [
                {
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                    "code": t.code,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "return_pct": t.return_pct,
                    "hold_days": t.hold_days,
                    "reason": t.reason,
                }
                for t in bt_result.trade_records
            ],
        }

    def _create_backtest_strategy(self) -> Callable:
        """
        创建回测策略函数

        将管线核心逻辑封装为 BacktestEngine 所需的签名：
            strategy(date: str, market_data: dict) -> list[StrategySignal]

        策略逻辑（简化版，适用于回测）：
          - 买入：当日涨幅 > 0 且近5日涨幅 > 3% 且站上MA5
          - 卖出：持仓亏损 > 8% 或 持仓盈利 > 15% 或 持仓 > 15天且收益 < 5%

        Returns:
            符合 BacktestEngine 签名的策略函数
        """
        from backtest_engine import StrategySignal

        # 用闭包捕获管线状态
        pipeline_self = self

        def strategy_func(date: str, market_data: Dict) -> List:
            """管线回测策略函数"""
            signals = []
            stocks = market_data.get("stocks", {})
            holdings = market_data.get("holdings", {})

            for code, info in stocks.items():
                close = info.get("close", 0)
                pct_change = info.get("pct_change", 0)
                ma5 = info.get("ma5", 0)

                # ---- 买入逻辑 ----
                if code not in holdings:
                    if pct_change > 0 and ma5 > 0 and close > ma5:
                        price_5d_ago = info.get("close_5d_ago", 0)
                        if price_5d_ago > 0:
                            gain_5d = (close - price_5d_ago) / price_5d_ago
                            if gain_5d > 0.03:
                                signals.append(StrategySignal(
                                    date=date,
                                    code=code,
                                    signal="buy",
                                    weight=1.0,
                                    reason=(
                                        f"管线策略买入: 5日涨幅{gain_5d:.2%}, "
                                        f"当日涨幅{pct_change:.2%}, 站上MA5"
                                    ),
                                ))

                # ---- 卖出逻辑 ----
                elif code in holdings:
                    pos = holdings[code]
                    entry_price = pos.get("cost_price", 0)
                    hold_days = pos.get("hold_days", 0)

                    if entry_price > 0:
                        pnl = (close - entry_price) / entry_price

                        if pnl <= -0.08:
                            signals.append(StrategySignal(
                                date=date, code=code, signal="sell",
                                weight=1.0,
                                reason=f"管线策略止损: 亏损{pnl:.2%}",
                            ))
                        elif pnl >= 0.15:
                            signals.append(StrategySignal(
                                date=date, code=code, signal="sell",
                                weight=1.0,
                                reason=f"管线策略止盈: 盈利{pnl:.2%}",
                            ))
                        elif hold_days >= 15 and pnl < 0.05:
                            signals.append(StrategySignal(
                                date=date, code=code, signal="sell",
                                weight=1.0,
                                reason=(
                                    f"管线策略时间止损: 持仓{hold_days}天, "
                                    f"收益{pnl:.2%}未达标"
                                ),
                            ))

            return signals

        return strategy_func

    def _inject_news_sentiment(self, factor_input: Dict) -> Dict:
        """
        将新闻情绪评分注入因子输入数据

        将宏观情绪、行业情绪、个股情绪写入 factor_input 中对应的字段，
        使得下游多因子模型和融合引擎可以利用消息面信号。

        Args:
            factor_input: 单只股票的因子输入字典（来自 DataFetcher.quote_to_factor_input）

        Returns:
            注入情绪评分后的因子输入字典（原地修改并返回）
        """
        if self._result is None:
            return factor_input

        # 宏观情绪 → news_sentiment_score
        factor_input["news_sentiment_score"] = self._result.macro_sentiment

        # 政策信号 → policy_signal（基于宏观情绪映射到 -1 ~ +1）
        factor_input["policy_signal"] = max(-1.0, min(1.0, self._result.macro_sentiment))

        # 个股情绪 → social_heat（用情绪绝对值作为热度代理）
        code = factor_input.get("code", "")
        stock_sent = self._result.stock_sentiments.get(code, 0.0)
        factor_input["social_heat"] = int(30000 + abs(stock_sent) * 20000)

        return factor_input

    def generate_report(self, result: Dict) -> str:
        """
        生成格式化的文本报告

        将 PipelineResult 的字典形式渲染为可读性强的中文报告。

        Args:
            result: run_daily_scan() 返回的结果字典

        Returns:
            多行文本报告字符串
        """
        lines: List[str] = []
        sep = "=" * 78
        thin = "-" * 78

        lines.append(sep)
        lines.append("  玄甲AGI 统一策略管线 — 日频扫描报告")
        lines.append(f"  生成时间: {result.get('timestamp', 'N/A')}")
        lines.append(f"  股票池: {result.get('stock_pool', [])}")
        lines.append(sep)

        # ── 1. 数据采集 ──
        lines.append("\n[1] 数据采集")
        lines.append(thin)
        news_count = len(result.get("raw_news", []))
        quote_count = len(result.get("quotes", {}))
        kline_count = len(result.get("klines", {}))
        lines.append(f"  新闻条数: {news_count}")
        lines.append(f"  行情获取: {quote_count} 只")
        lines.append(f"  K线获取: {kline_count} 只")

        # ── 2. 新闻情绪 ──
        lines.append("\n[2] 新闻情绪")
        lines.append(thin)
        macro = result.get("macro_sentiment", 0.0)
        label = "积极" if macro > 0.2 else ("谨慎" if macro < -0.2 else "中性")
        lines.append(f"  宏观情绪: {macro:+.2f} ({label})")
        sector_sents = result.get("sector_sentiments", {})
        if sector_sents:
            lines.append("  行业情绪:")
            for sector, score in sorted(sector_sents.items(), key=lambda x: x[1], reverse=True):
                bar = "+" * int(abs(score) * 10) if score > 0 else "-" * int(abs(score) * 10)
                lines.append(f"    {sector:<10} {score:+.2f} {bar}")

        # ── 3. 多因子筛选 ──
        lines.append("\n[3] 多因子筛选 (96因子)")
        lines.append(thin)
        mf_top = result.get("multi_factor_top", [])
        lines.append(f"  入选数量: {len(mf_top)}")
        for i, item in enumerate(mf_top[:10], 1):
            code = item.get("stock_code", "?")
            score = item.get("total_score", 0)
            lines.append(f"    {i:>2}. {code}  综合评分: {score:.4f}")

        # ── 4. X大神策略 ──
        lines.append("\n[4] X大神4步闭环策略")
        lines.append(thin)
        step1 = result.get("xgod_step1", [])
        step2 = result.get("xgod_step2", [])
        lines.append(f"  Step1 月度初筛通过: {len(step1)} 只")
        for code in step1[:5]:
            lines.append(f"    - {code}")
        lines.append(f"  Step2 季度复审通过: {len(step2)} 只")
        for code in step2[:5]:
            lines.append(f"    - {code}")

        red_team = result.get("xgod_red_team", {})
        if red_team:
            lines.append("  Step3 AI红队证伪:")
            for code, info in list(red_team.items())[:5]:
                risk_level = info.get("risk_level", "N/A")
                risk_score = info.get("risk_score", 0)
                lines.append(f"    {code}: 风险等级={risk_level}, 风险分={risk_score}")

        beyond_x = result.get("xgod_beyond_x", {})
        if beyond_x:
            lines.append("  Beyond-X 超越融合:")
            for code, info in sorted(
                beyond_x.items(),
                key=lambda x: x[1].get("beyond_x_score", 0),
                reverse=True,
            )[:5]:
                bx_score = info.get("beyond_x_score", 0)
                conf = info.get("confidence", 0)
                lines.append(f"    {code}: 超越得分={bx_score:.1f}, 置信度={conf:.0f}%")

        # ── 5. 超能力融合 ──
        lines.append("\n[5] 超能力化学反应融合")
        lines.append(thin)
        fusion = result.get("fusion_results", [])
        lines.append(f"  融合标的数: {len(fusion)}")
        for i, item in enumerate(fusion[:10], 1):
            code = item.get("stock_code", "?")
            name = item.get("stock_name", "?")
            score = item.get("fusion_score", 0)
            signal = item.get("signal", "?")
            reaction = item.get("reaction_type", "?")
            conf = item.get("confidence", 0)
            lines.append(
                f"    {i:>2}. {code} {name}  "
                f"融合分={score:.1f}  信号={signal}  "
                f"反应={reaction}  置信度={conf:.0f}%"
            )

        # ── 6. 风控 ──
        lines.append("\n[6] 风控引擎")
        lines.append(thin)
        dd = result.get("drawdown_action", {})
        if dd:
            lines.append(f"  回撤检查: {dd.get('message', 'N/A')}")
        pw = result.get("position_weights", {})
        if pw:
            lines.append(f"  仓位管理: {pw.get('message', 'N/A')}")
        st = result.get("stress_test", {})
        if st:
            lines.append(f"  压力测试: {st.get('message', 'N/A')}")

        # ── 7. 仓位计算 ──
        lines.append("\n[7] 仓位计算")
        lines.append(thin)
        sizes = result.get("position_sizes", {})
        if sizes:
            for code, info in sizes.items():
                lines.append(f"  {code}: {info.get('message', 'N/A')}")
        else:
            lines.append("  无仓位计算结果")

        # ── 最终推荐 ──
        lines.append("\n" + sep)
        lines.append("  最终推荐")
        lines.append(sep)
        final = result.get("final_recommendations", [])
        if not final:
            lines.append("  无推荐标的")
        for i, rec in enumerate(final, 1):
            code = rec.get("code", "?")
            name = rec.get("name", "?")
            score = rec.get("score", 0)
            signal = rec.get("signal", "?")
            weight = rec.get("weight", 0)
            reason = rec.get("reason", "")
            lines.append(
                f"  {i}. {code} {name}  "
                f"综合分={score:.1f}  信号={signal}  仓位={weight:.1%}"
            )
            if reason:
                lines.append(f"     理由: {reason}")

        lines.append("\n" + sep)
        lines.append("  报告结束")
        lines.append(sep)

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  私有方法 — 管线各阶段实现
# ═══════════════════════════════════════════════════════════════════════════

    # ------------------------------------------------------------------
    #  阶段1: 数据采集
    # ------------------------------------------------------------------

    def _stage1_data_acquisition(self, result: PipelineResult) -> None:
        """
        阶段1 — 数据采集

        使用 DataFetcher 获取新闻、行情、K线数据。
        获取失败时自动降级为模拟数据，确保管线可离线运行。
        """
        try:
            from data_fetcher import DataFetcher
        except ImportError:
            print("  [警告] 无法导入 DataFetcher，使用模拟数据")
            self._fill_mock_data(result)
            return

        fetcher = DataFetcher()

        # 1.1 获取新闻
        try:
            news = fetcher.fetch_news(limit=50)
            result.raw_news = news
            print(f"    新闻获取: {len(news)} 条")
        except Exception as e:
            print(f"    [警告] 新闻获取失败: {e}，使用空列表")
            result.raw_news = []

        # 1.2 获取行情 + K线 → 因子输入
        for code in self.stock_pool:
            # 行情
            try:
                quote = fetcher.fetch_quote(code)
                if quote is None:
                    quote = self._mock_quote(code)
                result.quotes[code] = quote
            except Exception as e:
                print(f"    [警告] 行情获取失败({code}): {e}，使用模拟数据")
                result.quotes[code] = self._mock_quote(code)

            # K线
            try:
                kline = fetcher.fetch_kline(code, days=60)
                if kline is None:
                    kline = self._mock_kline(code)
                result.klines[code] = kline
            except Exception as e:
                print(f"    [警告] K线获取失败({code}): {e}，使用模拟数据")
                result.klines[code] = self._mock_kline(code)

            # 转换为因子输入格式
            quote = result.quotes[code]
            kline = result.klines[code]
            try:
                factor_input = fetcher.quote_to_factor_input(quote, kline)
                factor_input["code"] = code
                result.factor_inputs[code] = factor_input
            except Exception as e:
                print(f"    [警告] 因子输入转换失败({code}): {e}")
                result.factor_inputs[code] = self._mock_factor_input(code)

        print(f"    行情获取: {len(result.quotes)} 只")
        print(f"    K线获取: {len(result.klines)} 只")
        print(f"    因子输入: {len(result.factor_inputs)} 只")

    # ------------------------------------------------------------------
    #  阶段2: 新闻情绪
    # ------------------------------------------------------------------

    def _stage2_news_sentiment(self, result: PipelineResult) -> None:
        """
        阶段2 — 新闻情绪分析

        使用 NewsSentimentEngine 分析快讯对行业/个股/宏观的影响。
        """
        try:
            from news_sentiment_engine import NewsSentimentEngine
        except ImportError:
            print("  [警告] 无法导入 NewsSentimentEngine，跳过")
            return

        engine = NewsSentimentEngine()

        # 获取新闻（使用阶段1已获取的新闻，或重新获取）
        try:
            news = engine.fetch_news()
            if not news and result.raw_news:
                # 如果阶段1已获取新闻，直接使用
                engine.news_cache = result.raw_news
                news = result.raw_news
        except Exception as e:
            print(f"    [警告] 新闻获取失败: {e}")
            news = []

        # 分析新闻
        try:
            engine.analyze_news(news)
        except Exception as e:
            print(f"    [警告] 新闻分析失败: {e}")
            return

        # 提取情绪评分
        result.macro_sentiment = engine.get_macro_sentiment()

        # 提取行业情绪
        from news_sentiment_engine import SECTOR_KEYWORDS
        for sector in SECTOR_KEYWORDS:
            score = engine.get_sector_sentiment(sector)
            if score != 0.0:
                result.sector_sentiments[sector] = score

        # 提取个股情绪
        from news_sentiment_engine import STOCK_KEYWORDS
        for stock_name in STOCK_KEYWORDS:
            score = engine.get_stock_sentiment(stock_name)
            if score != 0.0:
                result.stock_sentiments[stock_name] = score

        # 将情绪注入因子输入
        for code in result.factor_inputs:
            self._inject_news_sentiment(result.factor_inputs[code])

        print(f"    宏观情绪: {result.macro_sentiment:+.2f}")
        print(f"    行业情绪: {len(result.sector_sentiments)} 个行业有信号")
        print(f"    个股情绪: {len(result.stock_sentiments)} 只个股有信号")

    # ------------------------------------------------------------------
    #  阶段3: 多因子筛选
    # ------------------------------------------------------------------

    def _stage3_multi_factor(self, result: PipelineResult) -> None:
        """
        阶段3 — 多因子筛选

        使用 MultiFactorSelector 对所有股票进行96因子综合评分。
        """
        try:
            from multi_factor_model import MultiFactorSelector
        except ImportError:
            print("  [警告] 无法导入 MultiFactorSelector，跳过")
            return

        selector = MultiFactorSelector()

        # 构造 stocks_data: {code: factor_input}
        stocks_data = {}
        for code, fi in result.factor_inputs.items():
            stocks_data[code] = fi

        if not stocks_data:
            print("    无因子输入数据，跳过多因子筛选")
            return

        try:
            top_n = min(10, len(stocks_data))
            top_stocks = selector.select(stocks_data, top_n=top_n)
            result.multi_factor_top = top_stocks
            print(f"    多因子筛选完成: {len(top_stocks)} 只入选")
            for item in top_stocks[:5]:
                code = item.get("stock_code", "?")
                score = item.get("total_score", 0)
                print(f"      {code}: {score:.4f}")
        except Exception as e:
            print(f"    [警告] 多因子筛选失败: {e}")

    # ------------------------------------------------------------------
    #  阶段4: X大神策略
    # ------------------------------------------------------------------

    def _stage4_xgod_strategy(self, result: PipelineResult) -> None:
        """
        阶段4 — X大神4步闭环策略

        使用 XGodStrategyEngine 执行月度初筛 → 季度复审 → AI红队证伪 → 超越融合。
        """
        try:
            from x_god_strategy import XGodStrategyEngine, StockCandidate
        except ImportError:
            print("  [警告] 无法导入 XGodStrategyEngine，跳过")
            return

        engine = XGodStrategyEngine()

        # 构造 StockCandidate 列表
        universe = []
        for code in self.stock_pool:
            quote = result.quotes.get(code, {})
            fi = result.factor_inputs.get(code, {})

            # 从行情和因子数据中提取候选股信息
            name = quote.get("name", code)
            market_cap = quote.get("float_market_cap", 100000) / 10000  # 转亿元
            if market_cap < 1:
                market_cap = fi.get("market_cap", 100) / 10000
            if market_cap < 1:
                market_cap = 50.0  # 默认50亿

            # 模拟X大神策略所需的属性
            candidate = StockCandidate(
                code=code,
                name=name,
                market_cap=round(market_cap, 2),
                sector=self._guess_sector(code, quote),
                localization_rate=15.0,  # 默认值
                expansion_cycle_months=20,  # 默认值
                gross_margin_history=[30, 32, 35, 38],  # 默认毛利率
                analyst_reports_count=5,
                monopoly_score=6,
            )
            universe.append(candidate)

        # Step 1: 月度初筛
        try:
            step1 = engine.step1_screen(universe)
            result.xgod_step1 = [s.code for s in step1]
            print(f"    Step1 月度初筛: {len(step1)} 只通过")
        except Exception as e:
            print(f"    [警告] Step1失败: {e}")
            step1 = []

        # Step 2: 季度复审
        try:
            step2 = engine.step2_review(step1)
            result.xgod_step2 = [s.code for s in step2]
            print(f"    Step2 季度复审: {len(step2)} 只通过")
        except Exception as e:
            print(f"    [警告] Step2失败: {e}")
            step2 = []

        # Step 3: AI红队证伪
        try:
            for stock in step2:
                report = engine.step3_red_team(stock)
                result.xgod_red_team[stock.code] = {
                    "risk_level": report.risk_level,
                    "risk_score": report.overall_risk_score,
                    "recommendation": report.recommendation,
                }
            print(f"    Step3 AI红队: {len(result.xgod_red_team)} 只完成证伪")
        except Exception as e:
            print(f"    [警告] Step3失败: {e}")

        # Beyond-X 超越融合
        try:
            for stock in step2:
                bx = engine.beyond_x_fusion(stock)
                result.xgod_beyond_x[stock.code] = bx
            print(f"    Beyond-X: {len(result.xgod_beyond_x)} 只完成超越融合")
        except Exception as e:
            print(f"    [警告] Beyond-X失败: {e}")

    # ------------------------------------------------------------------
    #  阶段5: 超能力融合
    # ------------------------------------------------------------------

    def _stage5_superpower_fusion(self, result: PipelineResult) -> None:
        """
        阶段5 — 超能力化学反应融合

        使用 SuperpowerFusionEngine 对X大神策略选出的标的进行五维化学反应融合。
        """
        try:
            from superpower_fusion import SuperpowerFusionEngine
            from x_god_strategy import StockCandidate
        except ImportError:
            print("  [警告] 无法导入 SuperpowerFusionEngine，跳过")
            return

        try:
            engine = SuperpowerFusionEngine()
        except Exception as e:
            print(f"    [警告] SuperpowerFusionEngine 初始化失败: {e}")
            return

        # 获取X大神策略选出的标的
        xgod_codes = set(result.xgod_step2) if result.xgod_step2 else set(self.stock_pool)

        for code in self.stock_pool:
            if code not in xgod_codes:
                continue

            quote = result.quotes.get(code, {})
            fi = result.factor_inputs.get(code, {})
            name = quote.get("name", code)
            market_cap = quote.get("float_market_cap", 100000) / 10000
            if market_cap < 1:
                market_cap = 50.0

            # 构造 StockCandidate
            candidate = StockCandidate(
                code=code,
                name=name,
                market_cap=round(market_cap, 2),
                sector=self._guess_sector(code, quote),
                localization_rate=15.0,
                expansion_cycle_months=20,
                gross_margin_history=[30, 32, 35, 38],
                analyst_reports_count=5,
                monopoly_score=6,
            )

            # 先运行X大神红队（SuperpowerFusionEngine 内部依赖）
            try:
                engine.x_god.step3_red_team(candidate)
            except Exception:
                pass

            # 执行融合
            try:
                fusion = engine.fuse(candidate)
                result.fusion_results.append({
                    "stock_code": fusion.stock_code,
                    "stock_name": fusion.stock_name,
                    "x_god_score": fusion.x_god_score,
                    "superpower_score": fusion.superpower_score,
                    "triple_engine_score": fusion.triple_engine_score,
                    "multi_factor_score": fusion.multi_factor_score,
                    "fusion_score": fusion.fusion_score,
                    "four_way_consistency": fusion.four_way_consistency,
                    "five_way_consistency": fusion.five_way_consistency,
                    "signal": fusion.signal,
                    "trend": fusion.trend,
                    "confidence": fusion.confidence,
                    "reaction_type": fusion.reaction_type,
                    "catalyst_boost": fusion.catalyst_boost,
                    "factor_resonance_count": fusion.factor_resonance_count,
                    "factor_positive_ratio": fusion.factor_positive_ratio,
                    "action_plan": fusion.action_plan,
                    "risk_level": fusion.risk_level,
                })
            except Exception as e:
                print(f"    [警告] 融合失败({code}): {e}")

        # 按融合分排序
        result.fusion_results.sort(
            key=lambda x: x.get("fusion_score", 0), reverse=True
        )
        print(f"    融合完成: {len(result.fusion_results)} 只标的")

    # ------------------------------------------------------------------
    #  阶段6: 风控检查
    # ------------------------------------------------------------------

    def _stage6_risk_control(self, result: PipelineResult) -> None:
        """
        阶段6 — 风控引擎检查

        使用 PortfolioRiskManager 执行回撤控制、仓位管理、压力测试。
        """
        try:
            from risk_engine import PortfolioRiskManager, Position
        except ImportError:
            print("  [警告] 无法导入 PortfolioRiskManager，跳过")
            return

        # 构造模拟持仓（基于融合结果）
        positions = []
        for item in result.fusion_results[:5]:
            code = item.get("stock_code", "")
            name = item.get("stock_name", "")
            quote = result.quotes.get(code, {})
            price = quote.get("close", 50.0)
            if price <= 0:
                price = 50.0

            positions.append(Position(
                code=code,
                name=name,
                sector=self._guess_sector(code, quote),
                weight=0.10,  # 默认10%
                cost_price=price * 0.95,
                current_price=price,
                atr=price * 0.03,  # 默认ATR为价格的3%
                hold_days=10,
                target_price=price * 1.15,
            ))

        rm = PortfolioRiskManager(
            initial_capital=1_000_000.0,
            current_capital=1_000_000.0,
        )
        rm.set_positions(positions)

        # 6.1 回撤检查
        try:
            dd_action = rm.check_drawdown_action()
            result.drawdown_action = dd_action
            print(f"    回撤检查: {dd_action.get('message', 'N/A')}")
        except Exception as e:
            print(f"    [警告] 回撤检查失败: {e}")

        # 6.2 仓位管理
        try:
            weights = rm.calculate_position_weights()
            result.position_weights = weights
            print(f"    仓位管理: {weights.get('message', 'N/A')}")
        except Exception as e:
            print(f"    [警告] 仓位管理失败: {e}")

        # 6.3 压力测试
        try:
            stress = rm.stress_test()
            result.stress_test = stress
            print(f"    压力测试: {stress.get('message', 'N/A')}")
        except Exception as e:
            print(f"    [警告] 压力测试失败: {e}")

    # ------------------------------------------------------------------
    #  阶段7: 仓位计算
    # ------------------------------------------------------------------

    def _stage7_position_sizing(self, result: PipelineResult) -> None:
        """
        阶段7 — 仓位计算

        使用 PositionSizer 为每只推荐标的计算凯利+波动率综合仓位。
        """
        try:
            from risk_engine import PositionSizer
        except ImportError:
            print("  [警告] 无法导入 PositionSizer，跳过")
            return

        sizer = PositionSizer()

        for item in result.fusion_results[:10]:
            code = item.get("stock_code", "")
            quote = result.quotes.get(code, {})
            price = quote.get("close", 50.0)
            if price <= 0:
                price = 50.0

            # 估算ATR
            kline = result.klines.get(code, [])
            atr = self._estimate_atr(kline, price)

            # 基于融合置信度估算胜率
            confidence = item.get("confidence", 70.0)
            win_rate = min(0.70, max(0.40, confidence / 100.0))

            try:
                pos = sizer.combined_position(
                    atr=atr,
                    price=price,
                    win_rate=win_rate,
                    win_loss_ratio=2.0,
                )
                result.position_sizes[code] = pos
            except Exception as e:
                print(f"    [警告] 仓位计算失败({code}): {e}")

        print(f"    仓位计算完成: {len(result.position_sizes)} 只")

    # ------------------------------------------------------------------
    #  汇总最终推荐
    # ------------------------------------------------------------------

    def _assemble_final_recommendations(self, result: PipelineResult) -> None:
        """
        汇总各阶段结果，生成最终推荐列表

        综合融合得分、风控结论、仓位建议，输出最终推荐。
        """
        recommendations = []

        for item in result.fusion_results:
            code = item.get("stock_code", "")
            name = item.get("stock_name", "")
            fusion_score = item.get("fusion_score", 0)
            signal = item.get("signal", "观望")
            confidence = item.get("confidence", 0)
            risk_level = item.get("risk_level", "中低风险")
            reaction_type = item.get("reaction_type", "")

            # 跳过回避信号
            if signal == "回避":
                continue

            # 获取仓位建议
            pos_info = result.position_sizes.get(code, {})
            weight = pos_info.get("final_weight", 0.05)

            # 构造推荐理由
            reasons = []
            if reaction_type == "因子共振":
                reasons.append("72因子强信号共振")
            elif reaction_type == "催化反应":
                reasons.append("验证通过+三引擎一致")
            elif reaction_type == "共振效应":
                reasons.append("四引擎高度一致")
            elif reaction_type == "链式反应":
                reasons.append("多条件连续满足")
            reasons.append(f"融合分={fusion_score:.1f}")
            reasons.append(f"置信度={confidence:.0f}%")
            reasons.append(f"风险={risk_level}")

            recommendations.append({
                "code": code,
                "name": name,
                "score": fusion_score,
                "signal": signal,
                "confidence": confidence,
                "weight": weight,
                "risk_level": risk_level,
                "reaction_type": reaction_type,
                "reason": ", ".join(reasons),
            })

        # 按综合分排序
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        result.final_recommendations = recommendations[:10]

        print(f"\n  最终推荐: {len(result.final_recommendations)} 只标的")
        for i, rec in enumerate(result.final_recommendations, 1):
            print(
                f"    {i}. {rec['code']} {rec['name']}  "
                f"分={rec['score']:.1f}  信号={rec['signal']}  "
                f"仓位={rec['weight']:.1%}"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  辅助方法 — 模拟数据 / 工具函数
# ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _mock_quote(code: str) -> Dict:
        """生成模拟行情数据"""
        base_price = 50.0 + hash(code) % 200
        return {
            "code": code,
            "name": code,
            "close": base_price,
            "open": base_price * 0.99,
            "high": base_price * 1.02,
            "low": base_price * 0.97,
            "volume": 50000,
            "amount": base_price * 50000,
            "change_pct": 1.5,
            "change_amount": base_price * 0.015,
            "turnover_rate": 3.5,
            "pe_ttm": 30.0,
            "pb": 3.0,
            "total_market_cap": base_price * 100000,
            "float_market_cap": base_price * 50000,
            "main_net_inflow": 0.5,
            "amplitude": 2.0,
        }

    @staticmethod
    def _mock_kline(code: str, days: int = 60) -> List[Dict]:
        """生成模拟K线数据"""
        base_price = 50.0 + hash(code) % 200
        klines = []
        price = base_price * 0.85
        random.seed(hash(code) % 10000)

        for i in range(days):
            change = random.gauss(0.001, 0.02)
            price *= (1 + change)
            klines.append({
                "date": f"2026-{(i // 30 + 1):02d}-{(i % 30 + 1):02d}",
                "open": round(price * 0.998, 2),
                "close": round(price, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "volume": random.randint(30000, 80000),
                "amount": round(price * random.randint(30000, 80000), 2),
                "change_pct": round(change * 100, 2),
            })

        return klines

    @staticmethod
    def _mock_factor_input(code: str) -> Dict:
        """生成模拟因子输入数据"""
        base_price = 50.0 + hash(code) % 200
        closes = [base_price * (1 - 0.01 * i) for i in range(20, 0, -1)] + [base_price]
        volumes = [50000] * 21
        return {
            "code": code,
            "close": base_price,
            "open": base_price * 0.99,
            "high": base_price * 1.02,
            "low": base_price * 0.97,
            "volume": 50000,
            "amount": base_price * 50000,
            "closes": closes,
            "volumes": volumes,
            "stock_change_pct": 1.5,
            "sector_change_pct": 0.8,
            "market_change_pct": 0.3,
            "main_net_inflow": 0.5,
            "turnover_rate": 3.5,
            "news_sentiment_score": 0.3,
            "policy_signal": 1.0,
            "pe_factor": 30.0,
            "pb_factor": 3.0,
            "market_cap": base_price * 100000,
            "float_market_cap": base_price * 50000,
        }

    def _fill_mock_data(self, result: PipelineResult) -> None:
        """填充全部模拟数据（网络完全不可用时）"""
        result.raw_news = []
        for code in self.stock_pool:
            result.quotes[code] = self._mock_quote(code)
            result.klines[code] = self._mock_kline(code)
            result.factor_inputs[code] = self._mock_factor_input(code)

    @staticmethod
    def _guess_sector(code: str, quote: Dict) -> str:
        """
        根据股票代码和行情信息猜测所属板块

        简化规则：
          - 688xxx → 科创板（半导体/科技）
          - 300xxx → 创业板（新能源/医药/科技）
          - 60xxxx → 上证主板
          - 00xxxx → 深证主板
        """
        if code.startswith("688"):
            return "半导体/科技"
        elif code.startswith("300"):
            return "创业板"
        elif code.startswith("60"):
            return "上证主板"
        elif code.startswith("00"):
            return "深证主板"
        else:
            return "其他"

    @staticmethod
    def _estimate_atr(kline: List[Dict], current_price: float) -> float:
        """
        从K线数据估算ATR（平均真实波幅）

        使用最近20日的 True Range 均值。

        Args:
            kline: K线数据列表
            current_price: 当前价格

        Returns:
            估算的ATR值
        """
        if not kline or current_price <= 0:
            return current_price * 0.03  # 默认3%

        lookback = min(20, len(kline))
        recent = kline[-lookback:]

        true_ranges = []
        for i, bar in enumerate(recent):
            high = bar.get("high", current_price)
            low = bar.get("low", current_price)
            prev_close = recent[i - 1].get("close", current_price) if i > 0 else current_price
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if not true_ranges:
            return current_price * 0.03

        return sum(true_ranges) / len(true_ranges)


# ═══════════════════════════════════════════════════════════════════════════
#  __main__ 入口 — 演示
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 默认股票池
    default_pool = [
        "600519",  # 贵州茅台
        "300750",  # 宁德时代
        "002594",  # 比亚迪
        "601318",  # 中国平安
        "000858",  # 五粮液
    ]

    pipeline = StrategyPipeline(stock_pool=default_pool)

    # 运行日频扫描
    result = pipeline.run_daily_scan()

    # 生成报告
    report = pipeline.generate_report(result)
    print("\n" + report)
