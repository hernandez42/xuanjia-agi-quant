#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apex_agi — 玄甲AGI量化投资系统
═══════════════════════════════════════════════════════════════════════════════

玄甲AGI是一个完整的A股多因子量化投资系统，包含以下核心模块：

  - multi_factor_model:    96因子多因子选股模型（V6.3）
  - x_god_strategy:        X大神4步闭环策略引擎
  - superpower_fusion:     Superpower × X-God 化学反应融合引擎
  - triple_engine_fusion:  APEX + DSA + FinRL 三引擎融合器
  - unified_fusion:        统一融合引擎（解决dual/triple冲突）
  - risk_engine:           组合风控 + 仓位计算 + 止损管理
  - backtest_engine:       完整回测框架
  - data_fetcher:          统一数据获取层（快兰斯+东方财富）
  - news_sentiment_engine: 消息面情绪分析引擎
  - strategy_pipeline:     统一策略流水线（串联7大引擎）
  - auto_scheduler:        自动化任务调度器
  - us_market_tracker:     美股跟踪体系（三级信号+仓位建议）
  - market_sentiment_engine: 市场情绪/冰点分析引擎
  - limitup_tracker:       连板天梯 + 主线分化 + 毕业照判断
  - opening_strategy:      低开应对策略（四种走法）
  - main:                  统一命令行入口

版本: V6.4 小青龙体系融合版
═══════════════════════════════════════════════════════════════════════════════
"""

__version__ = "6.4.0"
__author__ = "玄甲AGI"

# 导出核心类（按需导入，避免循环依赖）
__all__ = [
    "__version__",
    # 数据层
    "DataFetcher",
    "KuailansiFetcher",
    "EastMoneyFetcher",
    # 因子层
    "FactorLibrary",
    "FactorScorer",
    "MultiFactorSelector",
    # 策略层
    "XGodStrategyEngine",
    "StockCandidate",
    # 融合层
    "SuperpowerFusionEngine",
    "SuperpowerFusionResult",
    "TripleEngineFusion",
    "TripleFusedResult",
    "UnifiedFusionEngine",
    "UnifiedFusionResult",
    "batch_fuse",
    # 风控层
    "PortfolioRiskManager",
    "PositionSizer",
    "StopLossManager",
    "Position",
    # 回测层
    "BacktestEngine",
    "BacktestResult",
    "StrategySignal",
    # 消息面
    "NewsSentimentEngine",
    # 流水线
    "StrategyPipeline",
    "PipelineResult",
    # 调度器
    "TaskScheduler",
    "CronParser",
    "register_preset_tasks",
    # 小青龙体系
    "USMarketTracker",
    "MarketSentimentEngine",
    "LimitUpTracker",
    "OpeningStrategy",
]


# 懒加载导出函数
def _lazy_import(name: str):
    """延迟导入模块，避免循环依赖和启动开销"""
    import importlib
    module_map = {
        # 数据层
        "DataFetcher": ("data_fetcher", "DataFetcher"),
        "KuailansiFetcher": ("data_fetcher", "KuailansiFetcher"),
        "EastMoneyFetcher": ("data_fetcher", "EastMoneyFetcher"),
        # 因子层
        "FactorLibrary": ("multi_factor_model", "FactorLibrary"),
        "FactorScorer": ("multi_factor_model", "FactorScorer"),
        "MultiFactorSelector": ("multi_factor_model", "MultiFactorSelector"),
        # 策略层
        "XGodStrategyEngine": ("x_god_strategy", "XGodStrategyEngine"),
        "StockCandidate": ("x_god_strategy", "StockCandidate"),
        # 融合层
        "SuperpowerFusionEngine": ("superpower_fusion", "SuperpowerFusionEngine"),
        "SuperpowerFusionResult": ("superpower_fusion", "SuperpowerFusionResult"),
        "TripleEngineFusion": ("triple_engine_fusion", "TripleEngineFusion"),
        "TripleFusedResult": ("triple_engine_fusion", "TripleFusedResult"),
        "UnifiedFusionEngine": ("unified_fusion", "UnifiedFusionEngine"),
        "UnifiedFusionResult": ("unified_fusion", "UnifiedFusionResult"),
        "batch_fuse": ("unified_fusion", "batch_fuse"),
        # 风控层
        "PortfolioRiskManager": ("risk_engine", "PortfolioRiskManager"),
        "PositionSizer": ("risk_engine", "PositionSizer"),
        "StopLossManager": ("risk_engine", "StopLossManager"),
        "Position": ("risk_engine", "Position"),
        # 回测层
        "BacktestEngine": ("backtest_engine", "BacktestEngine"),
        "BacktestResult": ("backtest_engine", "BacktestResult"),
        "StrategySignal": ("backtest_engine", "StrategySignal"),
        # 消息面
        "NewsSentimentEngine": ("news_sentiment_engine", "NewsSentimentEngine"),
        # 流水线
        "StrategyPipeline": ("strategy_pipeline", "StrategyPipeline"),
        "PipelineResult": ("strategy_pipeline", "PipelineResult"),
        # 调度器
        "TaskScheduler": ("auto_scheduler", "TaskScheduler"),
        "CronParser": ("auto_scheduler", "CronParser"),
        "register_preset_tasks": ("auto_scheduler", "register_preset_tasks"),
        # 小青龙体系
        "USMarketTracker": ("us_market_tracker", "USMarketTracker"),
        "MarketSentimentEngine": ("market_sentiment_engine", "MarketSentimentEngine"),
        "LimitUpTracker": ("limitup_tracker", "LimitUpTracker"),
        "OpeningStrategy": ("opening_strategy", "OpeningStrategy"),
    }
    module_name, attr_name = module_map.get(name, (None, None))
    if module_name is None:
        raise ImportError(f"无法找到 '{name}' 的导入映射")
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


# 使用 __getattr__ 实现真正的懒加载
__lazy_cache = {}

def __getattr__(name: str):
    if name in __lazy_cache:
        return __lazy_cache[name]
    if name in __all__:
        obj = _lazy_import(name)
        __lazy_cache[name] = obj
        return obj
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
