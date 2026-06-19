#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — 玄甲AGI 统一入口
═══════════════════════════════════════════════════════════════════════════════
玄甲AGI量化投资系统的统一命令行入口，整合所有引擎模块：

  1. 日频扫描 (daily-scan)    — 运行完整策略流水线，输出买入/卖出信号
  2. 回测验证 (backtest)      — 对指定股票池进行历史回测
  3. 单股分析 (analyze)       — 对单只股票进行深度多因子分析
  4. 消息面监控 (news)        — 获取并分析快兰斯实时快讯
  5. 风控检查 (risk)          — 检查当前持仓的风险状态
  6. 调度器启动 (scheduler)   — 启动自动化任务调度器

使用方式:
  python main.py daily-scan --stocks 600519,300750,002594
  python main.py backtest --stocks 600519,300750 --days 120
  python main.py analyze --stock 600519
  python main.py news
  python main.py risk --positions 600519:0.12,300750:0.08
  python main.py scheduler --duration 300
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ═══════════════════════════════════════════════════════════════════════════
#  命令处理函数
# ═══════════════════════════════════════════════════════════════════════════

def cmd_daily_scan(args):
    """日频扫描命令"""
    print("=" * 70)
    print("  玄甲AGI — 日频策略扫描")
    print("=" * 70)

    stock_pool = args.stocks.split(",") if args.stocks else ["600519", "300750", "002594", "601318", "000858"]
    print(f"\n  股票池: {stock_pool}")
    print(f"  扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from strategy_pipeline import StrategyPipeline
        pipeline = StrategyPipeline(stock_pool=stock_pool)
        result = pipeline.run_daily_scan()

        print("\n" + "-" * 70)
        print("  扫描结果")
        print("-" * 70)

        signals = result.get("signals", [])
        if signals:
            print(f"\n  发现 {len(signals)} 个交易信号:")
            for sig in signals:
                action_emoji = {"buy": "📈", "sell": "📉", "hold": "➖"}.get(sig.get("signal"), "❓")
                print(f"    {action_emoji} {sig.get('code', '')} {sig.get('name', '')}: "
                      f"{sig.get('signal', '').upper()} (置信度: {sig.get('confidence', 0):.1%})")
                print(f"       融合评分: {sig.get('fusion_score', 0):+.4f} | {sig.get('reasoning', '')}")
        else:
            print("  今日无明确交易信号")

        # 保存结果
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n  结果已保存: {args.output}")

    except Exception as e:
        print(f"\n  [错误] 日频扫描失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_backtest(args):
    """回测验证命令"""
    print("=" * 70)
    print("  玄甲AGI — 策略回测")
    print("=" * 70)

    stock_pool = args.stocks.split(",") if args.stocks else ["600519", "300750", "002594"]
    days = args.days or 120
    print(f"\n  股票池: {stock_pool}")
    print(f"  回测天数: {days}")

    try:
        from strategy_pipeline import StrategyPipeline
        pipeline = StrategyPipeline(stock_pool=stock_pool)
        result = pipeline.run_backtest(days=days)

        print("\n" + "-" * 70)
        print("  回测结果")
        print("-" * 70)
        for key, value in result.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n  结果已保存: {args.output}")

    except Exception as e:
        print(f"\n  [错误] 回测失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_analyze(args):
    """单股深度分析命令"""
    print("=" * 70)
    print("  玄甲AGI — 单股深度分析")
    print("=" * 70)

    stock_code = args.stock or "600519"
    print(f"\n  分析股票: {stock_code}")

    try:
        from data_fetcher import DataFetcher
        from unified_fusion import UnifiedFusionEngine

        fetcher = DataFetcher()
        engine = UnifiedFusionEngine()

        # 获取数据
        print("  正在获取行情数据...")
        quote = fetcher.fetch_quote(stock_code)
        kline = fetcher.fetch_kline(stock_code, days=60)

        if quote is None:
            print(f"  [错误] 无法获取 {stock_code} 的行情数据")
            return

        # 转换为因子输入
        factor_input = fetcher.quote_to_factor_input(quote, kline)

        # 执行融合分析
        print("  正在执行多因子融合分析...")
        result = engine.fuse(stock_code, quote.get("name", stock_code), factor_input)

        print("\n" + "-" * 70)
        print(f"  分析结果 — {result.stock_code} {result.stock_name}")
        print("-" * 70)
        print(f"  96因子评分:     {result.multi_factor_score:+.4f}")
        print(f"  三引擎评分:     {result.triple_engine_score:+.4f}")
        print(f"  消息面评分:     {result.news_sentiment_score:+.4f}")
        print(f"  融合评分:       {result.fusion_score:+.4f}")
        print(f"  交易信号:       {result.signal.upper()}")
        print(f"  置信度:         {result.confidence:.2%}")
        print(f"  因子共振:       {result.factor_resonance:.2%}")
        print(f"  风险等级:       {result.risk_level}")
        print(f"  推理:           {result.reasoning}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"\n  结果已保存: {args.output}")

    except Exception as e:
        print(f"\n  [错误] 分析失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_news(args):
    """消息面监控命令"""
    print("=" * 70)
    print("  玄甲AGI — 消息面监控")
    print("=" * 70)

    try:
        from news_sentiment_engine import NewsSentimentEngine
        engine = NewsSentimentEngine()

        print("\n  正在获取快兰斯实时快讯...")
        news = engine.fetch_news()
        print(f"  获取到 {len(news)} 条快讯")

        if news:
            engine.analyze_news(news)
            report = engine.generate_report()

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"\n  报告已保存: {args.output}")
        else:
            print("  未获取到快讯数据")

    except Exception as e:
        print(f"\n  [错误] 消息面获取失败: {e}")


def cmd_risk(args):
    """风控检查命令"""
    print("=" * 70)
    print("  玄甲AGI — 风控检查")
    print("=" * 70)

    try:
        from risk_engine import PortfolioRiskManager, Position

        rm = PortfolioRiskManager(initial_capital=1_000_000.0)

        # 解析持仓
        positions = []
        if args.positions:
            for pos_str in args.positions.split(","):
                code, weight = pos_str.split(":")
                positions.append(Position(
                    code=code, name=code, sector="未知", weight=float(weight),
                    cost_price=100.0, current_price=95.0, atr=5.0, hold_days=10, target_price=120.0
                ))
        rm.set_positions(positions)

        print(f"\n  持仓数量: {len(positions)}")
        for p in positions:
            print(f"    {p.code}: 权重 {p.weight:.2%}")

        # 回撤检查
        dd = rm.check_drawdown_action()
        print(f"\n  回撤控制:")
        print(f"    当前回撤: {dd['current_drawdown']:.2%}")
        print(f"    建议操作: {dd['action']}")
        print(f"    提示: {dd['message']}")

        # 压力测试
        stress = rm.stress_test()
        print(f"\n  压力测试:")
        print(f"    风险等级: {stress['risk_level']}")
        for scenario, detail in stress.get("scenarios", {}).items():
            print(f"    {scenario} 下跌: 预估损失 {detail['loss_pct']:.2%}")

    except Exception as e:
        print(f"\n  [错误] 风控检查失败: {e}")


def cmd_scheduler(args):
    """启动调度器命令"""
    print("=" * 70)
    print("  玄甲AGI — 自动化调度器")
    print("=" * 70)

    try:
        from auto_scheduler import TaskScheduler, register_preset_tasks

        scheduler = TaskScheduler()
        register_preset_tasks(scheduler)
        scheduler.print_tasks()

        duration = args.duration or 300
        print(f"\n  启动后台调度器（运行 {duration} 秒）...")
        scheduler.start(check_interval=1)

        # 倒计时
        for remaining in range(duration, 0, -1):
            print(f"\r  调度器运行中... 剩余 {remaining:3d} 秒", end="", flush=True)
            time.sleep(1)

        print("\n")
        scheduler.stop()
        scheduler.print_execution_logs()

    except Exception as e:
        print(f"\n  [错误] 调度器启动失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  命令行参数解析
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="玄甲AGI",
        description="玄甲AGI量化投资系统 — 统一命令行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py daily-scan --stocks 600519,300750,002594
  python main.py backtest --stocks 600519 --days 120 --output result.json
  python main.py analyze --stock 600519
  python main.py news --output news.json
  python main.py scheduler --duration 60
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # daily-scan
    p_scan = subparsers.add_parser("daily-scan", help="日频策略扫描")
    p_scan.add_argument("--stocks", type=str, help="股票代码列表，逗号分隔，如: 600519,300750")
    p_scan.add_argument("--output", type=str, help="结果输出文件路径")

    # backtest
    p_bt = subparsers.add_parser("backtest", help="策略回测验证")
    p_bt.add_argument("--stocks", type=str, help="股票代码列表，逗号分隔")
    p_bt.add_argument("--days", type=int, default=120, help="回测天数（默认120）")
    p_bt.add_argument("--output", type=str, help="结果输出文件路径")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="单股深度分析")
    p_analyze.add_argument("--stock", type=str, required=True, help="股票代码，如: 600519")
    p_analyze.add_argument("--output", type=str, help="结果输出文件路径")

    # news
    p_news = subparsers.add_parser("news", help="消息面监控")
    p_news.add_argument("--output", type=str, help="报告输出文件路径")

    # risk
    p_risk = subparsers.add_parser("risk", help="风控检查")
    p_risk.add_argument("--positions", type=str, help="持仓列表，格式: 代码:权重,如: 600519:0.12,300750:0.08")

    # scheduler
    p_sched = subparsers.add_parser("scheduler", help="启动自动化调度器")
    p_sched.add_argument("--duration", type=int, default=300, help="运行时长（秒，默认300）")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # 路由到对应命令
    commands = {
        "daily-scan": cmd_daily_scan,
        "backtest": cmd_backtest,
        "analyze": cmd_analyze,
        "news": cmd_news,
        "risk": cmd_risk,
        "scheduler": cmd_scheduler,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
