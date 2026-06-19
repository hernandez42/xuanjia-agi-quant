#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
6月18日收盘数据完整验证
用真实收盘数据验证X大神策略 + Superpower融合引擎
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x_god_strategy import XGodStrategyEngine, StockCandidate, PRESET_UNIVERSE
from superpower_fusion import SuperpowerFusionEngine

# ========== 6月18日真实收盘数据 ==========
MARKET_DATA_0618 = {
    "date": "2026-06-18",
    "indices": {
        "上证指数": {"close": 4090.48, "change_pct": -0.43, "volume": 15605},
        "深证成指": {"close": 16030.70, "change_pct": 0.94, "volume": 17496},
        "创业板指": {"close": 4252.39, "change_pct": 2.05, "volume": 4009},
        "科创50": {"close": 1911.51, "change_pct": 3.84, "volume": 2095},
        "沪深300": {"close": 4941.60, "change_pct": 0.21, "volume": 10217},
        "上证50": {"close": 2928.75, "change_pct": -0.19, "volume": 2897},
    },
    "market_breadth": {
        "up": 2023, "down": 3395, "flat": 113,
        "limit_up": 102, "limit_down": 34,
        "total_volume": 33101,  # 亿
        "volume_change": "+2183亿(较昨日放量)",
    },
    "sector_performance": {
        "半导体": {"change_pct": 4.15, "net_inflow": 31.9, "leader": "晶升股份"},
        "PCB": {"change_pct": 5.0, "leader": "宏昌电子(7天5板)"},
        "光刻胶": {"change_pct": 3.5, "leader": "广信材料"},
        "稀土": {"change_pct": 6.73, "leader": "盛和资源"},
        "保险": {"change_pct": -6.19, "leader": "—"},
        "火力发电": {"change_pct": -5.73, "leader": "—"},
    },
    "capital_flow": {
        "main_net_outflow": -177.87,  # 亿
        "northbound_net_inflow": 28.3,  # 亿
        "northbound_focus": ["算力", "光通信", "芯片龙头"],
        "outflow_sectors": ["大金融", "周期资源", "地产煤炭"],
    },
    "main_themes": [
        "AI算力硬件/CPO光模块(全场最强)",
        "人形机器人/具身智能",
        "PCB覆铜板+电子材料",
        "稀土战略小金属",
    ],
}

# X大神TOP10标的 6/18真实表现
STOCK_PERFORMANCE_0618 = {
    "688233": {"name": "神工股份", "close": 28.25, "change_pct": -0.25, "volume": 1.73, "turnover": "—", "main_flow": "—"},
    "603938": {"name": "三孚股份", "close": 53.82, "change_pct": 8.15, "volume": 17.11, "turnover": "—", "main_flow": "净流入"},
    "300346": {"name": "南大光电", "close": 64.90, "change_pct": -0.66, "volume": 39.24, "turnover": "9.3%", "main_flow": "净流出3.64亿"},
    "300786": {"name": "国林科技", "close": "—", "change_pct": "—", "volume": "—", "turnover": "—", "main_flow": "—"},
    "688234": {"name": "天岳先进", "close": "—", "change_pct": "—", "volume": "—", "turnover": "—", "main_flow": "—"},
    "300655": {"name": "晶瑞电材", "close": 16.41, "change_pct": -1.26, "volume": "—", "turnover": "—", "main_flow": "—"},
    "300811": {"name": "铂科新材", "close": "—", "change_pct": "—", "volume": "—", "turnover": "—", "main_flow": "—"},
    "688268": {"name": "华特气体", "close": 188.36, "change_pct": "—", "volume": "—", "turnover": "—", "main_flow": "—"},
    "688205": {"name": "德科立", "close": "—", "change_pct": "—", "volume": "—", "turnover": "—", "main_flow": "—"},
    "002428": {"name": "云南锗业", "close": "涨停", "change_pct": 10.0, "volume": "—", "turnover": "—", "main_flow": "稀土涨停"},
}


def validate_market_prediction():
    """验证市场预测"""
    print("=" * 70)
    print("6月18日收盘数据完整验证")
    print("=" * 70)

    # 市场概况
    data = MARKET_DATA_0618
    print(f"\n日期: {data['date']}")
    print(f"\n{'指数':<12} {'收盘':<12} {'涨跌幅':<10} {'成交额(亿)'}")
    print("-" * 50)
    for idx, val in data["indices"].items():
        arrow = "↑" if val["change_pct"] > 0 else "↓"
        print(f"{idx:<12} {val['close']:<12.2f} {arrow}{abs(val['change_pct']):.2f}%{'':<4} {val['volume']}")

    print(f"\n涨跌家数: 上涨{data['market_breadth']['up']} / 下跌{data['market_breadth']['down']} / 平盘{data['market_breadth']['flat']}")
    print(f"涨跌停: 涨停{data['market_breadth']['limit_up']} / 跌停{data['market_breadth']['limit_down']}")
    print(f"两市成交: {data['market_breadth']['total_volume']}亿 {data['market_breadth']['volume_change']}")

    # 市场特征分析
    print("\n" + "=" * 70)
    print("市场特征分析")
    print("=" * 70)
    print("1. 极致分化: 科创50+3.84%创新高 vs 沪指-0.43%，超七成个股下跌")
    print("2. 科技抱团: 资金全面涌向AI算力/半导体/PCB，传统权重被抛弃")
    print("3. 放量滞涨: 两市3.31万亿(+2183亿)，但沪指收阴十字星")
    print("4. 主线清晰: AI算力硬件>CPO光模块>PCB>稀土>机器人")
    print("5. 北向资金: 净流入28.3亿，加仓算力/光通信/芯片龙头")

    # X大神策略验证
    print("\n" + "=" * 70)
    print("X大神策略TOP10标的 6/18表现验证")
    print("=" * 70)
    print(f"{'代码':<8} {'名称':<10} {'收盘价':<10} {'涨跌幅':<10} {'成交额(亿)':<12} {'验证'}")
    print("-" * 70)

    hits = 0
    misses = 0
    for code, perf in STOCK_PERFORMANCE_0618.items():
        if perf["close"] == "—":
            status = "数据缺失"
            misses += 1
        elif isinstance(perf["change_pct"], (int, float)):
            if perf["change_pct"] > 0:
                status = "✓ 正收益"
                hits += 1
            else:
                status = "✗ 负收益"
                misses += 1
        else:
            status = perf["change_pct"]
            hits += 1

        close_str = str(perf["close"]) if perf["close"] != "—" else "N/A"
        chg_str = f"{perf['change_pct']}%" if isinstance(perf["change_pct"], (int, float)) else str(perf["change_pct"])
        vol_str = str(perf["volume"]) if perf["volume"] != "—" else "N/A"
        print(f"{code:<8} {perf['name']:<10} {close_str:<10} {chg_str:<10} {vol_str:<12} {status}")

    print(f"\n验证结果: {hits}只正收益 / {misses}只负收益或数据缺失")

    # 策略归因分析
    print("\n" + "=" * 70)
    print("策略归因分析")
    print("=" * 70)

    print("""
【三孚股份 +8.15%】✓ 超预期
  归因: 电子化工/高纯硅，半导体材料涨价潮受益，机构低配预期差兑现
  验证: Step1初筛正确锁定（国产化率15%+扩产36月+毛利率连扩）

【云南锗业 涨停 +10%】✓ 超预期
  归因: 稀土战略小金属板块暴涨6.73%，《矿产资源法条例》落地催化
  验证: Step1初筛正确锁定（稀散金属垄断+供需缺口20%）

【南大光电 -0.66%】✗ 低于预期
  归因: 光刻胶板块虽涨3.5%，但主力净流出3.64亿，高位换手9.3%分歧加大
  分析: 链式反应信号标的，但短期获利盘兑现压力大于板块催化

【神工股份 -0.25%】✗ 低于预期
  归因: 半导体板块涨4.15%，但个股未跟涨，可能因市值偏小流动性不足

【晶瑞电材 -1.26%】✗ 低于预期
  归因: 电子化学品板块仅涨0.54%，个股缺乏催化事件
""")

    # 化学反应引擎复盘
    print("=" * 70)
    print("化学反应引擎复盘")
    print("=" * 70)

    engine = SuperpowerFusionEngine()
    results = engine.run_full_fusion(PRESET_UNIVERSE)

    # 输出总结
    print("\n" + "=" * 70)
    print("6/18验证总结")
    print("=" * 70)
    print(f"""
市场判断:
  ✓ 科技成长赛道主升浪确认（科创50+3.84%创新高，创业板+2.05%创新高）
  ✓ AI算力/半导体/PCB为主线（半导体+4.15%，PCB+5%）
  ✗ 极致分化超预期（超3300只个股下跌，赚钱效应极差）

X大神策略:
  ✓ 三孚股份+8.15%验证（电子化工涨价+机构低配）
  ✓ 云南锗业涨停验证（稀土战略催化+供需缺口）
  ✗ 南大光电-0.66%未达预期（主力流出+高位分歧）
  → 策略在板块催化行情中有效，但在个股分化中需要更精细的择时

化学反应引擎:
  南大光电链式反应信号 → 短期失效（板块涨但个股跌）
  → 需要加入"板块涨幅 vs 个股涨幅背离"检测因子
  → 当板块大涨但个股逆势下跌时，触发"负反馈"降级

改进方向:
  1. 加入板块-个股背离检测因子
  2. 加入主力资金流向因子（净流出>3亿触发降级）
  3. 加入换手率异常因子（>9%触发分歧预警）
  4. 动态候选池替换硬编码（接入实时数据）
""")

    # 保存验证结果
    output = {
        "date": "2026-06-18",
        "market": MARKET_DATA_0618,
        "stock_performance": STOCK_PERFORMANCE_0618,
        "validation_summary": {
            "hits": hits,
            "misses": misses,
            "market_judgment": "科技成长主升浪确认，极致分化超预期",
            "strategy_effectiveness": "板块催化有效，个股择时需优化",
            "improvements": [
                "板块-个股背离检测",
                "主力资金流向因子",
                "换手率异常预警",
                "动态候选池"
            ]
        }
    }

    output_path = os.path.join(os.path.dirname(__file__), "validation_2026-06-18.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"验证结果已保存: {output_path}")


if __name__ == "__main__":
    validate_market_prediction()
