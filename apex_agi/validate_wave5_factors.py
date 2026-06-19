#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第五波因子(72→88) 一周验证
基于FinRL-Meta + 三篇顶会论文的16个新因子
用6/12-6/18真实数据验证增量贡献
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from multi_factor_model import FactorLibrary, MultiFactorSelector

# 复用一周数据（从validate_weekly_0612_0618.py导入）
from validate_weekly_0612_0618 import WEEKLY_DATA, WEEKLY_ACTUAL

WAVE5_FACTORS = {
    # 微观结构深度
    "增强OFI": "order_flow_imbalance_enhanced",
    "非对称VWAP": "vwap_asymmetric_deviation",
    "微观价格": "microprice_deviation",
    "价差调节": "spread_attenuated_signal",
    # MCTS公式
    "量价背离": "volume_price_divergence_trend",
    "波动率动量": "volatility_adjusted_momentum",
    "多尺度位置": "multi_scale_price_position",
    "量加速度": "volume_acceleration",
    # 波动率择时
    "波动率择时": "volatility_timed_momentum",
    "湍流体制": "turbulence_regime_signal",
    "非流动性": "amihud_illiquidity",
    "波动率体制": "realized_volatility_regime",
    # 因子质量
    "复杂度惩罚": "factor_complexity_penalty",
    "信号衰减": "signal_decay_detector",
    "截面动量": "cross_sectional_momentum_rank",
    "高低不对称": "high_low_asymmetry_signal",
}


def validate_wave5():
    lib = FactorLibrary()
    selector = MultiFactorSelector()

    print("=" * 80)
    print("第五波因子(72→88) 一周验证")
    print("基于: FinRL-Meta + 微观结构论文 + MCTS因子挖掘 + 波动率择时论文")
    print("=" * 80)

    # 一、每日88因子排名 vs 72因子排名
    print("\n【一】72因子 vs 88因子 每日排名对比")
    print("-" * 80)

    for date_key in ["0612", "0616", "0617", "0618"]:
        date_label = {"0612": "6/12(周四)", "0616": "6/16(周一)",
                      "0617": "6/17(周二)", "0618": "6/18(周三)"}[date_key]
        stocks = WEEKLY_DATA[date_key]["stocks"]
        stock_dict = {name: data for name, data in stocks.items()}
        results = selector.select(stock_dict, top_n=5)

        print(f"\n  {date_label}:")
        print(f"  {'排名':<4} {'股票':<10} {'88因子评分':<12} {'实际涨幅':<10} {'验证'}")
        print(f"  {'-'*50}")

        for i, r in enumerate(results, 1):
            code = r["stock_code"]
            actual = stocks[code]["stock_change_pct"]
            match = "✓" if (
                (actual > 0 and r["total_score"] > 0) or
                (actual < 0 and r["total_score"] < 0) or
                (abs(actual) < 1 and abs(r["total_score"]) < 0.01)
            ) else "✗"
            print(f"  {i:<4} {code:<10} {r['total_score']:<12.4f} {actual:>+8.2f}%    {match}")

    # 二、第五波因子逐日信号矩阵
    print(f"\n{'='*80}")
    print("【二】第五波因子信号矩阵（16因子 × 4天 × 5股）")
    print("-" * 80)

    # 统计每个因子的预测准确率
    factor_stats = {label: {"correct": 0, "total": 0} for label in WAVE5_FACTORS}

    for date_key in ["0612", "0616", "0617", "0618"]:
        date_label = {"0612": "6/12", "0616": "6/16", "0617": "6/17", "0618": "6/18"}[date_key]
        stocks = WEEKLY_DATA[date_key]["stocks"]

        print(f"\n  {date_label}:")
        header = f"  {'因子':<10}"
        for name in stocks:
            short = name[:4]
            header += f" {short:>8}"
        header += f" {'准确'}"
        print(header)
        print(f"  {'-'*65}")

        for label, factor_name in WAVE5_FACTORS.items():
            row = f"  {label:<10}"
            for name, data in stocks.items():
                val = lib.compute_factor(factor_name, data)
                actual = data["stock_change_pct"]
                # 判断因子方向是否与实际一致
                correct = (val > 0.1 and actual > 0) or (val < -0.1 and actual < 0) or (abs(val) <= 0.1 and abs(actual) < 1)
                if correct:
                    factor_stats[label]["correct"] += 1
                factor_stats[label]["total"] += 1
                if val > 0.3:
                    row += f" {'▲▲':>8}"
                elif val > 0.1:
                    row += f" {'▲':>8}"
                elif val < -0.3:
                    row += f" {'▼▼':>8}"
                elif val < -0.1:
                    row += f" {'▼':>8}"
                else:
                    row += f" {'—':>8}"
            acc = factor_stats[label]["correct"] / factor_stats[label]["total"] * 100 if factor_stats[label]["total"] > 0 else 0
            row += f" {acc:>5.0f}%"
            print(row)

    # 三、第五波因子有效性排名
    print(f"\n{'='*80}")
    print("【三】第五波因子有效性排名（20次预测准确率）")
    print("-" * 80)

    sorted_factors = sorted(factor_stats.items(), key=lambda x: x[1]["correct"] / max(x[1]["total"], 1), reverse=True)
    for i, (label, stats) in enumerate(sorted_factors, 1):
        acc = stats["correct"] / stats["total"] * 100
        bar = "█" * int(acc / 5) + "░" * (20 - int(acc / 5))
        grade = "S" if acc >= 85 else ("A" if acc >= 75 else ("B" if acc >= 65 else ("C" if acc >= 55 else "D")))
        print(f"  {i:>2}. {label:<10} {stats['correct']:>2}/{stats['total']:<2} {acc:>5.1f}% {bar} {grade}")

    # 四、关键股票的第五波因子深度分析
    print(f"\n{'='*80}")
    print("【四】关键股票第五波因子深度分析")
    print("-" * 80)

    # 神工股份（本周+19.49%，最大赢家）
    print("\n  ▶ 神工股份（本周+19.49%，最大赢家）:")
    print("  第五波因子在6/12的信号（提前一天预测）:")
    data_0612 = WEEKLY_DATA["0612"]["stocks"]["神工股份"]
    for label, factor_name in WAVE5_FACTORS.items():
        val = lib.compute_factor(factor_name, data_0612)
        signal = "✓看多" if val > 0.3 else ("⚠中性" if val > -0.3 else "✗看空")
        print(f"    {label:<10} {val:>+6.3f}  {signal}")

    # 南大光电（6/12跌停-10.97%，应被预警）
    print("\n  ▶ 南大光电（6/12跌停-10.97%，应被预警）:")
    data_0612_nande = WEEKLY_DATA["0612"]["stocks"]["南大光电"]
    for label, factor_name in WAVE5_FACTORS.items():
        val = lib.compute_factor(factor_name, data_0612_nande)
        signal = "✓预警" if val < -0.3 else ("⚠中性" if val > -0.3 and val < 0.3 else "✗未预警")
        print(f"    {label:<10} {val:>+6.3f}  {signal}")

    # 三孚股份（6/12跌停-10.01%，应被预警）
    print("\n  ▶ 三孚股份（6/12跌停-10.01%，应被预警）:")
    data_0612_sanfu = WEEKLY_DATA["0612"]["stocks"]["三孚股份"]
    for label, factor_name in WAVE5_FACTORS.items():
        val = lib.compute_factor(factor_name, data_0612_sanfu)
        signal = "✓预警" if val < -0.3 else ("⚠中性" if val > -0.3 and val < 0.3 else "✗未预警")
        print(f"    {label:<10} {val:>+6.3f}  {signal}")

    # 五、综合评估
    print(f"\n{'='*80}")
    print("【五】综合评估：72→88因子增量贡献")
    print("-" * 80)

    # 计算第五波因子整体准确率
    total_correct = sum(s["correct"] for s in factor_stats.values())
    total_predictions = sum(s["total"] for s in factor_stats.values())
    wave5_accuracy = total_correct / total_predictions * 100

    # 计算S/A级因子数量
    s_count = sum(1 for _, s in sorted_factors if s["correct"]/s["total"]*100 >= 85)
    a_count = sum(1 for _, s in sorted_factors if 75 <= s["correct"]/s["total"]*100 < 85)
    b_count = sum(1 for _, s in sorted_factors if 65 <= s["correct"]/s["total"]*100 < 75)

    print(f"""
  第五波因子整体准确率: {total_correct}/{total_predictions} = {wave5_accuracy:.1f}%

  因子评级分布:
    S级(≥85%): {s_count}个
    A级(75-85%): {a_count}个
    B级(65-75%): {b_count}个

  与72因子对比（之前一周验证）:
    72因子每日准确率: 80.0% (16/20)
    88因子每日准确率: 需观察第五波因子对排名的影响

  关键改进:
    1. 微观结构深度因子(论文1): OFI增强+凹性变换，捕捉边际递减效应
    2. MCTS公式因子(论文2): 量价背离+波动率动量+多尺度位置
    3. 波动率择时因子(论文3+FinRL): 湍流体制+非流动性+波动率体制
    4. 因子质量诊断(论文3): 复杂度惩罚+信号衰减+截面动量

  FinRL-Meta架构对接点:
    - DataProcessor标准化 → 88因子可作为tech_indicator_list传入
    - StockTradingEnv状态空间 → tech_array自动扩展
    - Turbulence Index → 湍流体制因子直接复用
    - Almgren-Chriss执行优化 → 价差调节信号对接

  论文来源:
    [1] Explainable Patterns in Cryptocurrency Microstructure (arXiv:2602.00776)
    [2] Navigating the Alpha Jungle: LLM-Powered MCTS (arXiv:2505.11122v3)
    [3] Seemingly Virtuous Complexity in Return Prediction (BFI WP 2025-104)
    [4] FinRL-Meta (AI4Finance-Foundation, GitHub 1890★)
""")


if __name__ == "__main__":
    validate_wave5()
