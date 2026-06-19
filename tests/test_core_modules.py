#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_core_modules.py — 玄甲AGI 核心模块单元测试
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apex_agi"))


def test_multi_factor_model():
    """测试96因子模型"""
    from multi_factor_model import FactorLibrary, FactorScorer, MultiFactorSelector

    fl = FactorLibrary()
    fs = FactorScorer()
    mfs = MultiFactorSelector()

    # 测试因子数量
    all_factors = fl.get_all_factor_names()
    assert len(all_factors) == 96, f"Expected 96 factors, got {len(all_factors)}"

    # 测试因子计算
    demo = {
        "dates": ["2026-06-01", "2026-06-02", "2026-06-03"],
        "open": [100.0, 102.0, 101.0],
        "high": [103.0, 104.0, 106.0],
        "low": [99.0, 101.0, 100.0],
        "close": [102.0, 103.0, 105.0],
        "volume": [10000, 12000, 11000],
        "amount": [1020000, 1236000, 1155000],
        "pe": 25.0, "pb": 3.0, "roe": 15.0,
        "main_net_inflow": 500000, "turnover_rate": 2.5,
    }
    factors = fl.compute_all_factors(demo)
    assert isinstance(factors, dict), "compute_all_factors should return dict"
    assert len(factors) > 0, "Should compute at least some factors"

    # 测试评分
    score, details = fs.compute_score(factors)
    assert isinstance(score, (int, float)), "Score should be numeric"

    print(f"  [PASS] MultiFactorModel: {len(all_factors)} factors, score={score:.4f}")


def test_unified_fusion():
    """测试统一融合引擎"""
    from unified_fusion import UnifiedFusionEngine, batch_fuse

    engine = UnifiedFusionEngine()
    demo = {
        "dates": ["2026-06-01"],
        "open": [100], "high": [103], "low": [99],
        "close": [102, 103, 105, 108, 110],
        "volume": [10000], "amount": [1020000],
        "pe": 25, "pb": 3, "roe": 15,
        "main_net_inflow": 500000, "turnover_rate": 2.5,
    }

    r = engine.fuse("600519", "贵州茅台", demo)
    assert r.signal in ("buy", "sell", "hold"), f"Invalid signal: {r.signal}"
    assert -1 <= r.fusion_score <= 1, f"Invalid score: {r.fusion_score}"
    assert 0 <= r.confidence <= 1, f"Invalid confidence: {r.confidence}"

    # 测试带消息面参数
    r2 = engine.fuse_with_news("300750", "宁德时代", demo, 0.3, 0.5, 0.2)
    assert r2.signal in ("buy", "sell", "hold")

    # 测试批量融合
    batch_data = {
        "600519": {"name": "贵州茅台", "ohlcv": demo},
        "300750": {"name": "宁德时代", "ohlcv": demo},
    }
    results = batch_fuse(batch_data)
    assert len(results) == 2

    print(f"  [PASS] UnifiedFusion: score={r.fusion_score:+.4f}, signal={r.signal}")


def test_data_fetcher():
    """测试数据获取层"""
    from data_fetcher import DataFetcher, KuailansiFetcher, EastMoneyFetcher

    df = DataFetcher()
    kf = KuailansiFetcher()
    ef = EastMoneyFetcher()

    assert df is not None
    assert kf is not None
    assert ef is not None

    print("  [PASS] DataFetcher: all classes initialized")


def test_news_sentiment():
    """测试消息面引擎"""
    from news_sentiment_engine import NewsSentimentEngine

    engine = NewsSentimentEngine()
    assert engine is not None

    # 测试关键词映射
    assert len(engine.SECTOR_KEYWORDS) > 0
    assert len(engine.STOCK_KEYWORDS) > 0

    print(f"  [PASS] NewsSentimentEngine: {len(engine.SECTOR_KEYWORDS)} sectors, {len(engine.STOCK_KEYWORDS)} stocks")


def test_risk_engine():
    """测试风控引擎"""
    from risk_engine import PortfolioRiskManager, PositionSizer, StopLossManager, Position

    rm = PortfolioRiskManager(initial_capital=1_000_000)
    ps = PositionSizer()
    sm = StopLossManager()

    # 测试回撤计算
    dd = rm.check_drawdown_action()
    assert "action" in dd

    # 测试仓位计算
    pos_weight = ps.combined_position(atr=5.0, price=100.0, win_rate=0.55, win_loss_ratio=2.0)
    assert 0 <= pos_weight <= 1

    print(f"  [PASS] RiskEngine: drawdown={dd['current_drawdown']:.2%}, position={pos_weight:.2%}")


def test_backtest_engine():
    """测试回测引擎"""
    from backtest_engine import BacktestEngine, StrategySignal

    # 创建简单策略
    def simple_strategy(date, day_data):
        signals = []
        for code, data in day_data.get("stocks", {}).items():
            if data.get("close", 0) > data.get("open", 0):
                signals.append(StrategySignal(signal="buy", code=code, price=data["close"], weight=0.1))
        return signals

    # 创建模拟市场数据
    market_data = [
        {
            "date": f"2026-06-{i:02d}",
            "stocks": {
                "600519": {"open": 100 + i, "high": 105 + i, "low": 99 + i, "close": 103 + i, "volume": 10000},
                "300750": {"open": 200 + i, "high": 205 + i, "low": 198 + i, "close": 202 + i, "volume": 8000},
            }
        }
        for i in range(1, 11)
    ]

    engine = BacktestEngine(strategy=simple_strategy, market_data=market_data, initial_capital=100000)
    result = engine.run()

    assert result is not None
    summary = result.summary()
    assert "total_return" in summary

    print(f"  [PASS] BacktestEngine: return={summary['total_return']:.2%}")


def test_auto_scheduler():
    """测试调度器"""
    from auto_scheduler import TaskScheduler, register_preset_tasks

    sched = TaskScheduler()
    register_preset_tasks(sched)
    tasks = sched.list_tasks()
    assert len(tasks) == 4, f"Expected 4 tasks, got {len(tasks)}"

    print(f"  [PASS] AutoScheduler: {len(tasks)} tasks registered")


def test_strategy_pipeline():
    """测试策略流水线"""
    from strategy_pipeline import StrategyPipeline

    pipeline = StrategyPipeline(stock_pool=["600519"])
    assert pipeline is not None

    print("  [PASS] StrategyPipeline initialized")


def test_x_god_strategy():
    """测试X大神策略"""
    from x_god_strategy import XGodStrategyEngine

    engine = XGodStrategyEngine()
    assert engine is not None

    print("  [PASS] XGodStrategyEngine initialized")


def test_superpower_fusion():
    """测试超能力融合"""
    from superpower_fusion import SuperpowerFusionEngine

    engine = SuperpowerFusionEngine()
    assert engine is not None

    print("  [PASS] SuperpowerFusionEngine initialized")


def test_triple_engine_fusion():
    """测试三引擎融合"""
    from triple_engine_fusion import TripleEngineFusion

    engine = TripleEngineFusion()
    assert engine is not None

    print("  [PASS] TripleEngineFusion initialized")


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  玄甲AGI V6.3 — 核心模块单元测试")
    print("=" * 60)

    tests = [
        test_multi_factor_model,
        test_unified_fusion,
        test_data_fetcher,
        test_news_sentiment,
        test_risk_engine,
        test_backtest_engine,
        test_auto_scheduler,
        test_strategy_pipeline,
        test_x_god_strategy,
        test_superpower_fusion,
        test_triple_engine_fusion,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  结果: {passed} PASSED, {failed} FAILED (共 {len(tests)} 个测试)")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
