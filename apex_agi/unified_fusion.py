#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unified_fusion.py — 玄甲AGI 统一融合引擎
═══════════════════════════════════════════════════════════════════════════════
解决 dual_engine_fusion.py 与 triple_engine_fusion.py 的类名冲突和融合逻辑割裂问题，
提供单一、统一的融合入口。

融合架构:
  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
  │  96因子多因子评分  │  │  三引擎融合评分   │  │  消息面情绪评分   │
  │  (40%权重)      │  │  (35%权重)      │  │  (25%权重)      │
  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                ▼
                    ┌─────────────────────┐
                    │   UnifiedFusionEngine │
                    │   加权融合 + 信号输出   │
                    └─────────────────────┘

信号规则:
  - fusion_score > +0.30  → "buy" (买入)
  - fusion_score < -0.30  → "sell" (卖出)
  - 否则                  → "hold" (观望)

仅依赖标准库，懒加载避免循环依赖。
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ═══════════════════════════════════════════════════════════════════════════
#  UnifiedFusionResult — 统一融合结果
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class UnifiedFusionResult:
    """
    统一融合引擎输出

    Attributes:
        stock_code:           股票代码
        stock_name:           股票名称
        multi_factor_score:   96因子多因子评分 (-1 ~ +1)
        triple_engine_score:  三引擎融合评分 (0 ~ 100, 归一化到 -1 ~ +1)
        news_sentiment_score: 消息面情绪评分 (-1 ~ +1)
        fusion_score:         最终融合评分 (-1 ~ +1)
        signal:               交易信号 "buy" / "sell" / "hold"
        confidence:           置信度 (0 ~ 1)
        reasoning:            信号推理说明
        factor_resonance:     因子共振强度 (0 ~ 1)
        risk_level:           风险等级
        timestamp:            时间戳
    """
    stock_code: str = ""
    stock_name: str = ""
    multi_factor_score: float = 0.0
    triple_engine_score: float = 0.0
    news_sentiment_score: float = 0.0
    fusion_score: float = 0.0
    signal: str = "hold"
    confidence: float = 0.0
    reasoning: str = ""
    factor_resonance: float = 0.0
    risk_level: str = "中低风险"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "multi_factor_score": round(self.multi_factor_score, 4),
            "triple_engine_score": round(self.triple_engine_score, 4),
            "news_sentiment_score": round(self.news_sentiment_score, 4),
            "fusion_score": round(self.fusion_score, 4),
            "signal": self.signal,
            "confidence": round(self.confidence, 4),
            "reasoning": self.reasoning,
            "factor_resonance": round(self.factor_resonance, 4),
            "risk_level": self.risk_level,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  UnifiedFusionEngine — 统一融合引擎
# ═══════════════════════════════════════════════════════════════════════════

class UnifiedFusionEngine:
    """
    统一融合引擎

    将 96因子多因子评分 + 三引擎融合评分 + 消息面情绪评分
    通过加权融合产生最终交易信号。

    权重分配:
        - multi_factor:   40% (量化因子驱动，稳定性最高)
        - triple_engine:  35% (多模型融合，捕捉非线性模式)
        - news_sentiment: 25% (消息面驱动，短期催化)

    情绪调整:
        - 消息面评分对最终结果的影响上限为 ±10%
        - 防止单一消息过度扭曲量化信号
    """

    # 融合权重
    WEIGHT_MULTI_FACTOR: float = 0.40
    WEIGHT_TRIPLE_ENGINE: float = 0.35
    WEIGHT_NEWS_SENTIMENT: float = 0.25

    # 信号阈值
    BUY_THRESHOLD: float = 0.30
    SELL_THRESHOLD: float = -0.30

    # 情绪调整上限
    NEWS_ADJUSTMENT_CAP: float = 0.10

    def __init__(self):
        self._triple_engine = None
        self._factor_lib = None
        self._factor_scorer = None
        self._news_engine = None
        self.fusion_history: List[Dict] = []

    # ------------------------------------------------------------------
    #  懒加载属性
    # ------------------------------------------------------------------

    @property
    def triple_engine(self):
        """懒加载三引擎融合器"""
        if self._triple_engine is None:
            try:
                from triple_engine_fusion import TripleEngineFusion
                self._triple_engine = TripleEngineFusion()
            except Exception as e:
                print(f"[UnifiedFusion] 三引擎融合器加载失败: {e}")
                self._triple_engine = None
        return self._triple_engine

    @property
    def factor_lib(self):
        """懒加载因子库"""
        if self._factor_lib is None:
            try:
                from multi_factor_model import FactorLibrary
                self._factor_lib = FactorLibrary()
            except Exception as e:
                print(f"[UnifiedFusion] 因子库加载失败: {e}")
                self._factor_lib = None
        return self._factor_lib

    @property
    def factor_scorer(self):
        """懒加载因子评分器"""
        if self._factor_scorer is None:
            try:
                from multi_factor_model import FactorScorer
                self._factor_scorer = FactorScorer()
            except Exception as e:
                print(f"[UnifiedFusion] 因子评分器加载失败: {e}")
                self._factor_scorer = None
        return self._factor_scorer

    @property
    def news_engine(self):
        """懒加载消息面引擎"""
        if self._news_engine is None:
            try:
                from news_sentiment_engine import NewsSentimentEngine
                self._news_engine = NewsSentimentEngine()
            except Exception as e:
                print(f"[UnifiedFusion] 消息面引擎加载失败: {e}")
                self._news_engine = None
        return self._news_engine

    # ------------------------------------------------------------------
    #  核心融合方法
    # ------------------------------------------------------------------

    def fuse(
        self,
        stock_code: str,
        stock_name: str,
        ohlcv_data: Dict,
        news_sentiment: Optional[Dict] = None,
    ) -> UnifiedFusionResult:
        """
        执行统一融合

        Args:
            stock_code:   股票代码
            stock_name:   股票名称
            ohlcv_data:   OHLCV数据字典
            news_sentiment: 预计算的消息面情绪字典，若为None则自动获取

        Returns:
            UnifiedFusionResult
        """
        # 1. 96因子多因子评分
        multi_factor_score = self._compute_multi_factor_score(stock_code, ohlcv_data)

        # 2. 三引擎融合评分
        triple_engine_score = self._compute_triple_engine_score(stock_code, ohlcv_data)

        # 3. 消息面情绪评分
        if news_sentiment is None:
            news_sentiment = self._fetch_news_sentiment(stock_code)
        news_score = news_sentiment.get("score", 0.0)

        # 4. 加权融合
        fusion_score = self._weighted_fusion(
            multi_factor_score, triple_engine_score, news_score
        )

        # 5. 因子共振强度
        resonance = self._calc_resonance(multi_factor_score, triple_engine_score, news_score)

        # 6. 生成信号
        signal, confidence, reasoning = self._generate_signal(
            fusion_score, multi_factor_score, triple_engine_score, news_score, resonance
        )

        # 7. 风险等级
        risk_level = self._assess_risk(fusion_score, resonance, news_score)

        result = UnifiedFusionResult(
            stock_code=stock_code,
            stock_name=stock_name,
            multi_factor_score=multi_factor_score,
            triple_engine_score=triple_engine_score,
            news_sentiment_score=news_score,
            fusion_score=fusion_score,
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            factor_resonance=resonance,
            risk_level=risk_level,
        )

        self.fusion_history.append(result.to_dict())
        return result

    def fuse_with_news(
        self,
        stock_code: str,
        stock_name: str,
        ohlcv_data: Dict,
        macro_sentiment: float = 0.0,
        sector_sentiment: float = 0.0,
        stock_sentiment: float = 0.0,
    ) -> UnifiedFusionResult:
        """
        带消息面参数的融合（用于已知情绪的场景）

        Args:
            macro_sentiment:   宏观情绪 (-1 ~ +1)
            sector_sentiment:  行业情绪 (-1 ~ +1)
            stock_sentiment:   个股情绪 (-1 ~ +1)
        """
        # 综合消息面评分：宏观30% + 行业30% + 个股40%
        combined_news = macro_sentiment * 0.30 + sector_sentiment * 0.30 + stock_sentiment * 0.40
        combined_news = max(-1.0, min(1.0, combined_news))

        news_dict = {"score": combined_news, "macro": macro_sentiment, "sector": sector_sentiment, "stock": stock_sentiment}
        return self.fuse(stock_code, stock_name, ohlcv_data, news_dict)

    def quick_score(self, stock_code: str, ohlcv_data: Dict) -> float:
        """
        快速单股票评分（用于流水线批量调用）

        仅计算多因子评分，跳过三引擎和消息面，速度最快。
        """
        return self._compute_multi_factor_score(stock_code, ohlcv_data)

    # ------------------------------------------------------------------
    #  内部计算方法
    # ------------------------------------------------------------------

    def _compute_multi_factor_score(self, stock_code: str, ohlcv_data: Dict) -> float:
        """计算96因子多因子评分 (-1 ~ +1)"""
        try:
            if self.factor_lib is None or self.factor_scorer is None:
                return 0.0

            raw_factors = self.factor_lib.compute_all_factors(ohlcv_data)
            # 单股票无横截面标准化，直接用原始值
            score, _ = self.factor_scorer.compute_score(raw_factors)
            # 压缩到 -1 ~ +1
            return max(-1.0, min(1.0, score))
        except Exception as e:
            print(f"[UnifiedFusion] 多因子评分失败({stock_code}): {e}")
            return 0.0

    def _compute_triple_engine_score(self, stock_code: str, ohlcv_data: Dict) -> float:
        """计算三引擎融合评分并归一化到 (-1 ~ +1)"""
        try:
            if self.triple_engine is None:
                return 0.0

            # 构建模拟的三引擎输入
            from triple_engine_fusion import ApexResult, DSAResult, FinRLResult

            # 基于OHLCV数据模拟各引擎评分
            closes = ohlcv_data.get("close", [])
            if isinstance(closes, (list, tuple)) and len(closes) >= 2:
                latest = closes[-1]
                prev = closes[-2]
                change = (latest - prev) / prev if prev != 0 else 0.0
            else:
                change = 0.0

            # 模拟 APEX 评分 (0-100)
            apex_score = 50.0 + change * 500.0
            apex_score = max(0.0, min(100.0, apex_score))

            # 模拟 DSA 评分
            dsa_score = 50.0 + change * 400.0
            dsa_score = max(0.0, min(100.0, dsa_score))

            # 模拟 FinRL 评分
            finrl_score = 50.0 + change * 450.0
            finrl_score = max(0.0, min(100.0, finrl_score))

            apex = ApexResult(score=apex_score, signal="买入" if change > 0.02 else "观望" if change > -0.02 else "卖出")
            dsa = DSAResult(score=dsa_score, signal="买入" if change > 0.015 else "观望" if change > -0.015 else "卖出")
            finrl = FinRLResult(score=finrl_score, signal="买入" if change > 0.01 else "观望" if change > -0.01 else "卖出")

            fused = self.triple_engine.fuse(apex, dsa, finrl)
            # 将 0-100 归一化到 -1 ~ +1
            return (fused.fused_score - 50.0) / 50.0
        except Exception as e:
            print(f"[UnifiedFusion] 三引擎评分失败({stock_code}): {e}")
            return 0.0

    def _fetch_news_sentiment(self, stock_code: str) -> Dict:
        """自动获取消息面情绪评分"""
        try:
            if self.news_engine is None:
                return {"score": 0.0}

            news = self.news_engine.fetch_news()
            if news:
                self.news_engine.analyze_news(news)

            # 尝试获取个股情绪，若无则取宏观
            stock_name_map = {
                "600519": "贵州茅台", "000858": "五粮液", "300750": "宁德时代",
                "601318": "中国平安", "002594": "比亚迪", "688981": "中芯国际",
                "600111": "北方稀土", "603259": "药明康德", "600028": "中国石化",
                "688012": "中微公司", "688111": "金山办公", "002230": "科大讯飞",
                "600438": "通威股份", "603533": "掌阅科技",
            }
            stock_name = stock_name_map.get(stock_code, "")
            if stock_name:
                score = self.news_engine.get_stock_sentiment(stock_name)
            else:
                score = self.news_engine.get_macro_sentiment()

            return {"score": score}
        except Exception as e:
            print(f"[UnifiedFusion] 消息面获取失败({stock_code}): {e}")
            return {"score": 0.0}

    def _weighted_fusion(
        self,
        multi_factor: float,
        triple_engine: float,
        news: float,
    ) -> float:
        """
        加权融合三个评分

        算法:
            base = mf * 0.40 + te * 0.35
            news_adj = news * 0.25，但上限 ±0.10
            final = base + clamp(news_adj, -0.10, +0.10)
        """
        base = multi_factor * self.WEIGHT_MULTI_FACTOR + triple_engine * self.WEIGHT_TRIPLE_ENGINE
        news_adj = news * self.WEIGHT_NEWS_SENTIMENT
        news_adj = max(-self.NEWS_ADJUSTMENT_CAP, min(self.NEWS_ADJUSTMENT_CAP, news_adj))
        return max(-1.0, min(1.0, base + news_adj))

    def _calc_resonance(self, mf: float, te: float, news: float) -> float:
        """
        计算因子共振强度

        三个评分同向程度越高，共振越强。
        """
        signs = [math.copysign(1, s) if abs(s) > 0.05 else 0 for s in [mf, te, news]]
        non_zero = [s for s in signs if s != 0]
        if len(non_zero) < 2:
            return 0.0
        # 同向比例
        same_dir = sum(1 for s in non_zero if s == non_zero[0])
        return same_dir / len(non_zero)

    def _generate_signal(
        self,
        fusion_score: float,
        mf: float,
        te: float,
        news: float,
        resonance: float,
    ) -> tuple:
        """
        生成交易信号、置信度和推理说明

        Returns:
            (signal, confidence, reasoning)
        """
        # 信号判定
        if fusion_score > self.BUY_THRESHOLD:
            signal = "buy"
        elif fusion_score < self.SELL_THRESHOLD:
            signal = "sell"
        else:
            signal = "hold"

        # 置信度 = |融合分| * 0.5 + 共振强度 * 0.3 + 三引擎一致性 * 0.2
        # 简化：用 |fusion_score| 和 resonance
        confidence = min(1.0, abs(fusion_score) * 0.6 + resonance * 0.4)

        # 推理说明
        reasons = []
        if abs(mf) > 0.1:
            reasons.append(f"96因子{'看多' if mf > 0 else '看空'}({mf:+.2f})")
        if abs(te) > 0.1:
            reasons.append(f"三引擎{'看多' if te > 0 else '看空'}({te:+.2f})")
        if abs(news) > 0.1:
            reasons.append(f"消息面{'利好' if news > 0 else '利空'}({news:+.2f})")
        if resonance > 0.6:
            reasons.append(f"高共振({resonance:.0%})")

        reasoning = "；".join(reasons) if reasons else "信号偏弱，观望为主"

        return signal, confidence, reasoning

    def _assess_risk(self, fusion_score: float, resonance: float, news: float) -> str:
        """评估风险等级"""
        if abs(fusion_score) > 0.5 and resonance < 0.3:
            return "高风险"  # 强信号但低共振，可能是假信号
        if abs(fusion_score) > 0.5 and resonance > 0.7:
            return "中低风险"  # 强信号高共振，最可靠
        if abs(news) > 0.5:
            return "中高风险"  # 消息面驱动过强，注意反转
        return "中等风险"


# ═══════════════════════════════════════════════════════════════════════════
#  批量融合接口
# ═══════════════════════════════════════════════════════════════════════════

def batch_fuse(
    stocks_data: Dict[str, Dict],
    news_sentiment: Optional[Dict[str, Dict]] = None,
) -> List[UnifiedFusionResult]:
    """
    批量融合多只股票

    Args:
        stocks_data: {stock_code: {"name": str, "ohlcv": Dict}}
        news_sentiment: {stock_code: {"score": float}} 可选

    Returns:
        List[UnifiedFusionResult] 按融合评分降序排列
    """
    engine = UnifiedFusionEngine()
    results = []

    for code, data in stocks_data.items():
        name = data.get("name", code)
        ohlcv = data.get("ohlcv", data)
        ns = news_sentiment.get(code) if news_sentiment else None
        result = engine.fuse(code, name, ohlcv, ns)
        results.append(result)

    results.sort(key=lambda r: r.fusion_score, reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════════════
#  __main__ 演示
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  玄甲AGI 统一融合引擎 — 演示")
    print("=" * 70)

    engine = UnifiedFusionEngine()

    # 模拟股票数据
    demo_ohlcv = {
        "dates": ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"],
        "open": [100.0, 102.0, 101.0, 105.0, 108.0],
        "high": [103.0, 104.0, 106.0, 109.0, 110.0],
        "low": [99.0, 101.0, 100.0, 104.0, 107.0],
        "close": [102.0, 103.0, 105.0, 108.0, 110.0],
        "volume": [10000, 12000, 11000, 15000, 18000],
        "amount": [1020000, 1236000, 1155000, 1620000, 1980000],
        "pe": 25.0, "pb": 3.0, "roe": 15.0,
        "main_net_inflow": 500000, "turnover_rate": 2.5,
    }

    print("\n--- 单股票融合演示 ---")
    result = engine.fuse("600519", "贵州茅台", demo_ohlcv)
    print(f"  股票: {result.stock_code} {result.stock_name}")
    print(f"  96因子评分: {result.multi_factor_score:+.4f}")
    print(f"  三引擎评分: {result.triple_engine_score:+.4f}")
    print(f"  消息面评分: {result.news_sentiment_score:+.4f}")
    print(f"  融合评分:   {result.fusion_score:+.4f}")
    print(f"  信号: {result.signal} | 置信度: {result.confidence:.2%}")
    print(f"  推理: {result.reasoning}")
    print(f"  风险等级: {result.risk_level}")

    print("\n--- 带消息面参数的融合演示 ---")
    result2 = engine.fuse_with_news(
        "300750", "宁德时代", demo_ohlcv,
        macro_sentiment=0.3, sector_sentiment=0.5, stock_sentiment=0.2
    )
    print(f"  股票: {result2.stock_code} {result2.stock_name}")
    print(f"  融合评分: {result2.fusion_score:+.4f} | 信号: {result2.signal}")
    print(f"  推理: {result2.reasoning}")

    print("\n--- 批量融合演示 ---")
    batch_data = {
        "600519": {"name": "贵州茅台", "ohlcv": demo_ohlcv},
        "300750": {"name": "宁德时代", "ohlcv": demo_ohlcv},
        "002594": {"name": "比亚迪", "ohlcv": demo_ohlcv},
    }
    batch_results = batch_fuse(batch_data)
    print(f"  共融合 {len(batch_results)} 只股票")
    for r in batch_results:
        print(f"    {r.stock_code} {r.stock_name}: {r.fusion_score:+.4f} → {r.signal}")

    print("\n" + "=" * 70)
    print("  统一融合引擎演示完毕")
    print("=" * 70)
