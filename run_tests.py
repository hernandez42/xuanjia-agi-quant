#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_tests.py — 玄甲AGI 快速测试入口
用于 CI/CD 和本地开发快速验证所有核心模块。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apex_agi"))


def main():
    """运行所有核心模块快速验证"""
    print("=" * 60)
    print("  玄甲AGI V6.3 — 快速验证")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    modules = [
        ("multi_factor_model", "FactorLibrary, FactorScorer, MultiFactorSelector"),
        ("unified_fusion", "UnifiedFusionEngine, UnifiedFusionResult"),
        ("data_fetcher", "DataFetcher, KuailansiFetcher, EastMoneyFetcher"),
        ("news_sentiment_engine", "NewsSentimentEngine"),
        ("risk_engine", "PortfolioRiskManager, PositionSizer, StopLossManager"),
        ("backtest_engine", "BacktestEngine, StrategySignal"),
        ("auto_scheduler", "TaskScheduler, register_preset_tasks"),
        ("strategy_pipeline", "StrategyPipeline, PipelineResult"),
        ("x_god_strategy", "XGodStrategyEngine"),
        ("superpower_fusion", "SuperpowerFusionEngine"),
        ("triple_engine_fusion", "TripleEngineFusion"),
    ]

    for module_name, classes in modules:
        try:
            __import__(module_name)
            print(f"  [PASS] {module_name}: {classes}")
            tests_passed += 1
        except Exception as e:
            print(f"  [FAIL] {module_name}: {e}")
            tests_failed += 1

    # 验证96因子数量
    try:
        from multi_factor_model import FactorLibrary
        fl = FactorLibrary()
        count = len(fl.get_all_factor_names())
        assert count == 96, f"Expected 96, got {count}"
        print(f"  [PASS] Factor count: {count}")
        tests_passed += 1
    except Exception as e:
        print(f"  [FAIL] Factor count: {e}")
        tests_failed += 1

    # 验证调度器任务数
    try:
        from auto_scheduler import TaskScheduler, register_preset_tasks
        sched = TaskScheduler()
        register_preset_tasks(sched)
        count = len(sched.list_tasks())
        assert count == 4, f"Expected 4, got {count}"
        print(f"  [PASS] Scheduler tasks: {count}")
        tests_passed += 1
    except Exception as e:
        print(f"  [FAIL] Scheduler tasks: {e}")
        tests_failed += 1

    print()
    print("=" * 60)
    print(f"  结果: {tests_passed} PASSED, {tests_failed} FAILED")
    print("=" * 60)

    return 0 if tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
