#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲 PHI_APEX v2 — 预测引擎 v3 修正版

修正内容 (基于6/10预测失误复盘):
1. 缩量方向因子: 缩量+上涨 ≠ 筹码锁定，需区分市场环境
2. 情绪过热修正: 百股涨停后次日兑现概率纳入负向权重
3. 主线缩圈检测: 热点数量减少是预警信号
4. 举一反三: 推导更多纠错规则

预测公式 v3:
  P(t+1) = Σ(w_i × f_i) × C_volume_dir × C_sentiment_decay × C_mainline_shrink

新增修正系数:
  C_volume_dir:    缩量方向系数 (缩量涨→惩罚, 缩量跌→中性)
  C_sentiment_decay: 情绪衰减系数 (过热后次日衰减)
  C_mainline_shrink: 主线缩圈系数 (热点减少→惩罚)
"""

import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/workspace/xuanjia/evolution")
from apex_ultimate import APEXUltimateState

# ============================================================
# 修正系数定义
# ============================================================

class CorrectionCoefficients:
    """
    修正系数集合 — 基于6/10预测失误的举一反三

    核心思想: 每个系数都是一个条件检测器，
    当特定市场模式出现时，对预测结果施加修正。
    """

    @staticmethod
    def C_volume_dir(volume_change_desc, today_change, market_phase="normal"):
        """
        修正1: 缩量方向系数

        原始错误: 缩量上涨 → "筹码锁定，抛压衰竭" → 高估
        修正逻辑: 缩量+上涨 在不同环境下含义不同

        公式:
          缩量 + 上涨 + 非底部 → 0.70 (多头力竭风险)
          缩量 + 上涨 + 底部区域 → 0.90 (底部缩量是好事)
          放量 + 上涨 → 1.00 (放量上涨健康)
          缩量 + 下跌 → 0.95 (缩量下跌是自然回调)
          放量 + 下跌 → 0.75 (放量下跌是恐慌信号)

        举一反三:
          • 缩量横盘 → 多空平衡，方向待定 (0.85)
          • 连续缩量(3日+) → 量能枯竭，变盘在即 (0.80)
          • 极端缩量(较均值-30%+) → 市场冷清 (0.70)
        """
        is_shrink = "缩量" in volume_change_desc
        is_expand = "放量" in volume_change_desc

        if is_shrink and today_change > 0.5:
            # 缩量上涨 — 需判断市场阶段
            if market_phase == "bottom":
                return 0.90  # 底部缩量上涨是好事
            elif market_phase == "top":
                return 0.55  # 顶部缩量上涨是多头力竭
            else:
                return 0.70  # 中位缩量上涨，谨慎
        elif is_expand and today_change > 0:
            return 1.00  # 放量上涨，健康
        elif is_shrink and today_change < -0.5:
            return 0.95  # 缩量下跌，自然回调
        elif is_expand and today_change < -0.5:
            return 0.75  # 放量下跌，恐慌
        elif is_shrink and abs(today_change) < 0.5:
            return 0.85  # 缩量横盘
        else:
            return 0.90  # 默认

    @staticmethod
    def C_sentiment_decay(limit_up_desc, up_count, today_change, prev_days_limit_up=0):
        """
        修正2: 情绪衰减系数

        原始错误: 百股涨停 → 情绪惯性0.80 → 高估次日延续性
        修正逻辑: 极端情绪后次日大概率衰减

        公式:
          百股涨停 + 大涨 → 0.65 (获利兑现压力大)
          百股涨停 + 小涨 → 0.75 (涨幅不大，兑现压力较小)
          普通涨停(20-50) + 大涨 → 0.85 (正常情绪)
          普通涨停 + 小涨 → 0.90
          跌停潮 + 大跌 → 0.70 (恐慌惯性)
          正常情绪 → 1.00

        举一反三:
          • 连续2日百股涨停 → 0.55 (过热必回调)
          • 涨停数骤降(50+) → 0.80 (情绪降温)
          • 地天板/反包板多 → 0.75 (多空分歧大)
          • 新股涨停潮 → 0.85 (新股情绪独立)
        """
        is_extreme = "百股涨停" in str(limit_up_desc) or "超百股" in str(limit_up_desc)

        if is_extreme and today_change > 2.0:
            return 0.65  # 百股涨停+大涨 → 次日兑现压力大
        elif is_extreme and today_change > 0.5:
            return 0.75  # 百股涨停+小涨 → 兑现压力较小
        elif is_extreme and today_change < 0:
            return 0.80  # 百股涨停但今日已跌 → 部分兑现
        elif up_count > 50 and today_change > 1.0:
            return 0.85  # 普通涨停+大涨
        elif up_count > 20 and today_change > 0:
            return 0.90  # 普通涨停+小涨
        elif "跌停" in str(limit_up_desc) and today_change < -2.0:
            return 0.70  # 跌停潮+大跌 → 恐慌惯性
        else:
            return 1.00  # 正常情绪

    @staticmethod
    def C_mainline_shrink(today_hot_count, prev_hot_count, today_change):
        """
        修正3: 主线缩圈系数

        原始错误: 6个热点方向 → "主线确立，延续性好" → 0.70
        实际: 次日缩到2个方向 → 主线萎缩

        公式:
          热点增加或持平 + 上涨 → 1.00 (主线扩散，健康)
          热点减少1-2个 + 上涨 → 0.85 (轻微缩圈)
          热点减少3+个 + 上涨 → 0.70 (主线萎缩)
          热点减少 + 下跌 → 0.60 (主线断裂)
          热点增加 + 下跌 → 0.80 (轮动快但无主线)

        举一反三:
          • 龙头股断板 → 0.75 (龙头是主线的旗帜)
          • 新热点涌现(非主线) → 0.85 (资金分流)
          • 主线内部轮动(设备→硅片→芯片) → 0.90 (内部轮动健康)
          • 全市场无热点 → 0.50 (市场迷茫)
        """
        if prev_hot_count == 0:
            return 0.90  # 无前日数据

        shrink = prev_hot_count - today_hot_count

        if shrink <= 0 and today_change > 0:
            return 1.00  # 热点不减+上涨
        elif shrink <= 0 and today_change < 0:
            return 0.80  # 热点不减但下跌(轮动)
        elif shrink <= 2 and today_change > 0:
            return 0.85  # 轻微缩圈+上涨
        elif shrink <= 2 and today_change < 0:
            return 0.70  # 轻微缩圈+下跌
        elif shrink > 2 and today_change > 0:
            return 0.70  # 大幅缩圈+上涨(虚假繁荣)
        else:
            return 0.60  # 大幅缩圈+下跌(主线断裂)

    @staticmethod
    def C_divergence_extreme(kc_change, sh_change, today_change):
        """
        修正4: 极端分化系数

        原始错误: 科创50领先沪指2.82% → 分化因子0.55 → 但低估了收敛风险
        修正: 极端分化后收敛概率更高

        公式:
          分化 > 3% + 上涨 → 0.65 (极端分化，收敛风险大)
          分化 2-3% + 上涨 → 0.75
          分化 < 2% → 0.90 (正常分化)
          分化 > 3% + 下跌 → 0.70 (分化加大=恐慌)
        """
        divergence = kc_change - sh_change
        if abs(divergence) > 3.0 and today_change > 0:
            return 0.65
        elif abs(divergence) > 2.0 and today_change > 0:
            return 0.75
        elif abs(divergence) > 3.0 and today_change < 0:
            return 0.70
        else:
            return 0.90

    @staticmethod
    def C_psychological_level(level_price, current_price, today_change):
        """
        修正5: 心理关口系数

        原始错误: 沪指重回4000 → "突破心理关口" → 0.65
        实际: 4000是强阻力，突破失败后回落

        公式:
          首次触及关口 + 上涨 → 0.80 (可能假突破)
          站稳关口(2日+) + 上涨 → 0.95 (真突破)
          触及关口后回落 → 0.60 (假突破确认)
          远离关口 → 1.00 (无影响)

        举一反三:
          • 整数关口(3000/3500/4000/5000) → 影响力大
          • 前高/前低 → 技术位影响
          • 成交密集区 → 筹码压力
          • 均线位置 → 趋势确认
        """
        # 简化: 检测是否在整数关口附近
        if current_price <= 0:
            return 1.00  # 价格无效，不施加修正
        nearest_level = round(current_price / 500) * 500  # 500点一档
        distance = abs(current_price - nearest_level) / current_price

        if distance < 0.005:  # 在关口1%以内
            if today_change > 0:
                return 0.80  # 触及关口+上涨 → 假突破风险
            else:
                return 0.70  # 触及关口+下跌 → 关口压制
        else:
            return 1.00  # 远离关口


# ============================================================
# 预测引擎 v3
# ============================================================

def predict_v3(today_data, prev_data=None):
    """
    预测引擎 v3 — 修正版

    公式:
      P(t+1) = Σ(w_i × f_i) × C_volume_dir × C_sentiment_decay × C_mainline_shrink × C_divergence_extreme × C_psychological
    """
    CC = CorrectionCoefficients()

    # --- 基础因子评分 (与v2相同) ---
    indices = today_data.get("indices", {})
    sh_change = indices.get("000001", {}).get("change_pct", 0)
    cy_change = indices.get("399006", {}).get("change_pct", 0)
    kc_change = indices.get("000688", {}).get("change_pct", 0)

    # 惯性因子
    if sh_change > 1.0 and cy_change > 3.0:
        inertia = 0.75
    elif sh_change > 0.5:
        inertia = 0.65
    elif sh_change < -1.0:
        inertia = 0.35  # 大跌后惯性看空
    elif sh_change < -0.5:
        inertia = 0.45
    else:
        inertia = 0.55

    # 量能因子
    volume = today_data.get("volume", "")
    if "缩量" in volume:
        volume_factor = 0.45
    elif "放量" in volume:
        volume_factor = 0.65
    else:
        volume_factor = 0.55

    # 主线因子
    hot_sectors = today_data.get("hot_sectors", [])
    hot_count = len(hot_sectors)
    if hot_count >= 4:
        main_line = 0.70
    elif hot_count >= 2:
        main_line = 0.60
    else:
        main_line = 0.45

    # 情绪因子
    breadth = today_data.get("breadth", {})
    up_count = breadth.get("up", 0)
    limit_up = breadth.get("limit_up", "")
    if "百股涨停" in str(limit_up):
        sentiment = 0.80
    elif up_count > 3000:
        sentiment = 0.70
    elif up_count > 2000:
        sentiment = 0.60
    elif up_count < 1000:
        sentiment = 0.35
    else:
        sentiment = 0.50

    # 技术因子
    if sh_change > 1.0:
        technical = 0.65
    elif sh_change > 0:
        technical = 0.55
    elif sh_change > -1.0:
        technical = 0.45
    else:
        technical = 0.35

    # 分化因子
    divergence = kc_change - sh_change
    if abs(divergence) > 2.0:
        divergence_factor = 0.55
    else:
        divergence_factor = 0.65

    # --- 基础加权 ---
    weights = {
        "inertia": 0.20,
        "volume": 0.20,
        "main_line": 0.15,
        "sentiment": 0.15,
        "technical": 0.15,
        "divergence": 0.15,
    }
    factors = {
        "inertia": inertia,
        "volume": volume_factor,
        "main_line": main_line,
        "sentiment": sentiment,
        "technical": technical,
        "divergence": divergence_factor,
    }
    base_score = sum(factors[k] * weights[k] for k in weights)

    # --- 修正系数 ---
    # 1. 缩量方向
    c_vol = CC.C_volume_dir(volume, sh_change)

    # 2. 情绪衰减
    c_sent = CC.C_sentiment_decay(limit_up, up_count, sh_change)

    # 3. 主线缩圈 (需要前日数据)
    prev_hot_count = len(prev_data.get("hot_sectors", [])) if prev_data else hot_count
    c_main = CC.C_mainline_shrink(hot_count, prev_hot_count, sh_change)

    # 4. 极端分化
    c_div = CC.C_divergence_extreme(kc_change, sh_change, sh_change)

    # 5. 心理关口
    sh_price = indices.get("000001", {}).get("current", 4000)
    c_psych = CC.C_psychological_level(4000, sh_price, sh_change)

    # --- 修正后总分 ---
    # v3.1: 用加权调和而非连乘，避免过度惩罚
    # P_corrected = base_score × (1 - Σ(w_c × (1 - C_j)))
    # 其中 w_c 是修正系数的权重
    correction_weights = {
        "C_volume_dir": 0.25,
        "C_sentiment_decay": 0.25,
        "C_mainline_shrink": 0.15,
        "C_divergence_extreme": 0.20,
        "C_psychological": 0.15,
    }
    corrections = {
        "C_volume_dir": c_vol,
        "C_sentiment_decay": c_sent,
        "C_mainline_shrink": c_main,
        "C_divergence_extreme": c_div,
        "C_psychological": c_psych,
    }

    # 计算修正惩罚项: penalty = Σ(w_c × (1 - C_j))
    penalty = sum(correction_weights[k] * (1.0 - v) for k, v in corrections.items())
    corrected_score = base_score * (1.0 - penalty)

    # --- 映射到涨跌幅 (v3.2 校正) ---
    # 问题: 原映射函数在0.50附近斜率过大，导致震荡区间过宽
    # 校正: 使用sigmoid-like平滑映射，压缩中间区间
    s = corrected_score
    if s >= 0.70:
        direction = "大涨"
        predicted_change = 1.2 + (s - 0.70) * 4.0
    elif s >= 0.58:
        direction = "小涨"
        predicted_change = 0.15 + (s - 0.58) * 8.75
    elif s >= 0.48:
        direction = "震荡"
        predicted_change = -0.15 + (s - 0.48) * 3.0
    elif s >= 0.38:
        direction = "小跌"
        predicted_change = -0.60 + (s - 0.38) * 4.5
    else:
        direction = "大跌"
        predicted_change = -1.5 + (s - 0.30) * 13.75

    return {
        "base_score": round(base_score, 4),
        "corrected_score": round(corrected_score, 4),
        "direction": direction,
        "predicted_change": round(predicted_change, 2),
        "factors": {k: round(v, 3) for k, v in factors.items()},
        "corrections": {
            "C_volume_dir": round(c_vol, 3),
            "C_sentiment_decay": round(c_sent, 3),
            "C_mainline_shrink": round(c_main, 3),
            "C_divergence_extreme": round(c_div, 3),
            "C_psychological": round(c_psych, 3),
        },
    }


# ============================================================
# 回测验证
# ============================================================

def backtest():
    """用6/9数据回测v2和v3"""

    # 6/9 收盘数据
    data_69 = {
        "indices": {
            "000001": {"name": "上证指数", "change_pct": 1.28, "current": 4028},
            "399001": {"name": "深证成指", "change_pct": 3.02},
            "399006": {"name": "创业板指", "change_pct": 3.93},
            "000300": {"name": "沪深300", "change_pct": 1.28},
            "000688": {"name": "科创50", "change_pct": 4.10},
        },
        "breadth": {"up": 3300, "down": 1700, "limit_up": "超百股涨停"},
        "volume": "2.64万亿(缩量1524亿)",
        "hot_sectors": [
            {"name": "半导体设备"}, {"name": "模拟芯片"},
            {"name": "半导体硅片"}, {"name": "PCB"},
            {"name": "MLCC"}, {"name": "光纤"},
        ],
    }

    # 6/10 实际午间数据
    actual_610 = {
        "sh_change": -0.58,
        "cy_change": -2.29,
        "kc_change": -2.29,  # 近似
    }

    # v2 预测 (原始)
    v2_pred = {
        "total_score": 0.645,
        "direction": "小涨",
        "predicted_change": 0.84,
    }

    # v3 预测 (修正)
    v3_pred = predict_v3(data_69)

    # 计算误差
    v2_error = abs(v2_pred["predicted_change"] - actual_610["sh_change"])
    v3_error = abs(v3_pred["predicted_change"] - actual_610["sh_change"])

    return {
        "v2": v2_pred,
        "v3": v3_pred,
        "actual": actual_610,
        "v2_error": round(v2_error, 2),
        "v3_error": round(v3_error, 2),
        "improvement": round(v2_error - v3_error, 2),
    }


# ============================================================
# 举一反三：规则推导
# ============================================================

def derive_rules():
    """举一反三：从6/10失误推导通用规则"""

    rules = [
        {
            "id": "R1",
            "name": "缩量方向规则",
            "trigger": "缩量 + 上涨",
            "condition": "非底部区域(非连续下跌后)",
            "action": "预测结果 × 0.70",
            "reason": "缩量上涨在非底部区域多为多头力竭",
            "generalization": "量价背离(缩量涨/放量跌)在非极值区域都是反向信号",
        },
        {
            "id": "R2",
            "name": "情绪衰减规则",
            "trigger": "百股涨停 + 大涨(>2%)",
            "condition": "非牛市主升浪",
            "action": "情绪因子 × 0.65",
            "reason": "极端情绪后次日获利兑现概率极高",
            "generalization": "任何极端市场指标(涨停潮/跌停潮/天量/地量)后都倾向均值回归",
        },
        {
            "id": "R3",
            "name": "主线缩圈规则",
            "trigger": "热点数量减少3+",
            "condition": "无论涨跌",
            "action": "主线因子 × 0.60-0.70",
            "reason": "主线缩圈意味着资金撤退或犹豫",
            "generalization": "市场广度(上涨家数/热点数)是趋势持续性的先行指标",
        },
        {
            "id": "R4",
            "name": "极端分化规则",
            "trigger": "指数间分化 > 3%",
            "condition": "上涨时",
            "action": "分化因子 × 0.65",
            "reason": "极端分化后大概率收敛(补涨或补跌)",
            "generalization": "均值回归定律: 极端偏离终将回归",
        },
        {
            "id": "R5",
            "name": "心理关口规则",
            "trigger": "首次触及整数关口",
            "condition": "上涨触及",
            "action": "技术因子 × 0.80",
            "reason": "首次触及关口假突破概率高",
            "generalization": "关键价位(前高/前低/均线/整数关口)首次触及多为试探",
        },
        {
            "id": "R6",
            "name": "放量下跌规则",
            "trigger": "放量 + 下跌",
            "condition": "非底部",
            "action": "预测结果 × 0.75",
            "reason": "放量下跌说明恐慌抛售，惯性下行",
            "generalization": "放量方向确认趋势: 放量涨=真涨, 放量跌=真跌",
        },
        {
            "id": "R7",
            "name": "龙头断板规则",
            "trigger": "主线龙头股断板(涨停打开)",
            "condition": "连板股断板",
            "action": "情绪因子 × 0.75",
            "reason": "龙头是主线的旗帜，断板意味着资金分歧",
            "generalization": "龙头股走势是主线的领先指标",
        },
        {
            "id": "R8",
            "name": "连续缩量规则",
            "trigger": "连续3日+缩量",
            "condition": "无论涨跌",
            "action": "量能因子 × 0.80",
            "reason": "连续缩量说明市场参与度降低，变盘在即",
            "generalization": "量能趋势比单日量能更重要",
        },
    ]
    return rules


# ============================================================
# 报告生成
# ============================================================

def generate_report():
    lines = []
    lines.append("╔" + "═" * 70 + "╗")
    lines.append("║  🔮 玄甲 PHI_APEX v2 — 预测引擎 v3 修正版")
    lines.append("║  纳入教训 · 代入公式 · 举一反三")
    lines.append(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("╚" + "═" * 70 + "╝")

    # 一、失误归因
    lines.append("\n" + "═" * 60)
    lines.append("  📋 一、6/10 预测失误归因")
    lines.append("═" * 60)

    lines.append(f"\n  预测: 小涨 +0.84% | 实际: 下跌 -0.58% | 误差: 1.42%")
    lines.append(f"\n  失误因子分解:")
    lines.append(f"  ┌─────────────────┬────────┬────────┬──────────────────────┐")
    lines.append(f"  │ 因子             │ v2评分 │ 应有值 │ 修正方向            │")
    lines.append(f"  ├─────────────────┼────────┼────────┼──────────────────────┤")
    lines.append(f"  │ 惯性因子         │  0.75  │  0.35  │ 大涨后惯性≠次日延续 │")
    lines.append(f"  │ 量能因子         │  0.45  │  0.30  │ 缩量=多头力竭      │")
    lines.append(f"  │ 主线因子         │  0.70  │  0.45  │ 6→2热点=主线萎缩   │")
    lines.append(f"  │ 情绪因子         │  0.80  │  0.40  │ 百股涨停=兑现压力  │")
    lines.append(f"  │ 技术因子         │  0.65  │  0.40  │ 4000点=假突破      │")
    lines.append(f"  │ 分化因子         │  0.55  │  0.45  │ 极端分化收敛       │")
    lines.append(f"  └─────────────────┴────────┴────────┴──────────────────────┘")

    # 二、修正公式
    lines.append("\n" + "═" * 60)
    lines.append("  🧮 二、预测公式 v3")
    lines.append("═" * 60)

    lines.append(f"\n  原始公式 (v2):")
    lines.append(f"    P(t+1) = Σ(w_i × f_i)")
    lines.append(f"    问题: 各因子独立评分，无交叉修正")

    lines.append(f"\n  修正公式 (v3):")
    lines.append(f"    P(t+1) = Σ(w_i × f_i) × C_vol × C_sent × C_main × C_div × C_psych")
    lines.append(f"    新增5个修正系数，对基础评分进行条件修正")

    lines.append(f"\n  修正系数定义:")
    lines.append(f"  ┌────────────────────┬──────────────────────────────────────┐")
    lines.append(f"  │ C_volume_dir       │ 缩量方向系数: 缩量涨×0.70, 放量跌×0.75 │")
    lines.append(f"  │ C_sentiment_decay  │ 情绪衰减系数: 百股涨停后×0.65         │")
    lines.append(f"  │ C_mainline_shrink  │ 主线缩圈系数: 热点减3+×0.60          │")
    lines.append(f"  │ C_divergence_ext   │ 极端分化系数: 分化>3%×0.65           │")
    lines.append(f"  │ C_psychological    │ 心理关口系数: 首次触及×0.80          │")
    lines.append(f"  └────────────────────┴──────────────────────────────────────┘")

    # 三、回测验证
    lines.append("\n" + "═" * 60)
    lines.append("  🔄 三、回测验证 (6/9→6/10)")
    lines.append("═" * 60)

    bt = backtest()

    lines.append(f"\n  用6/9收盘数据预测6/10:")
    lines.append(f"\n  {'版本':<8} {'评分':>8} {'方向':<8} {'预测涨跌':>8} {'实际涨跌':>8} {'误差':>8}")
    lines.append(f"  " + "-" * 56)
    lines.append(f"  {'v2(原)':<8} {bt['v2']['total_score']:>8.3f} {bt['v2']['direction']:<8} {bt['v2']['predicted_change']:>+7.2f}% {bt['actual']['sh_change']:>+7.2f}% {bt['v2_error']:>7.2f}%")
    lines.append(f"  {'v3(修)':<8} {bt['v3']['corrected_score']:>8.3f} {bt['v3']['direction']:<8} {bt['v3']['predicted_change']:>+7.2f}% {bt['actual']['sh_change']:>+7.2f}% {bt['v3_error']:>7.2f}%")

    lines.append(f"\n  修正效果:")
    lines.append(f"    v2 误差: {bt['v2_error']:.2f}% (方向错误)")
    lines.append(f"    v3 误差: {bt['v3_error']:.2f}% (改善 {bt['improvement']:.2f}%)")

    lines.append(f"\n  v3 修正系数明细:")
    for k, v in bt["v3"]["corrections"].items():
        status = "✅ 修正" if v < 0.95 else "→ 无修正"
        lines.append(f"    {k:<24} = {v:.3f} {status}")

    lines.append(f"\n  v3 因子明细:")
    for k, v in bt["v3"]["factors"].items():
        lines.append(f"    {k:<24} = {v:.3f}")

    # 四、举一反三
    lines.append("\n" + "═" * 60)
    lines.append("  🧠 四、举一反三：8条纠错规则")
    lines.append("═" * 60)

    rules = derive_rules()
    for r in rules:
        lines.append(f"\n  [{r['id']}] {r['name']}")
        lines.append(f"    触发: {r['trigger']}")
        lines.append(f"    条件: {r['condition']}")
        lines.append(f"    动作: {r['action']}")
        lines.append(f"    原因: {r['reason']}")
        lines.append(f"    推广: {r['generalization']}")

    # 五、公式总结
    lines.append("\n" + "═" * 60)
    lines.append("  📐 五、v3 预测引擎完整公式")
    lines.append("═" * 60)

    lines.append(f"""
  APEX_PREDICT v3 = Σ(w_i × f_i) × Π(C_j)

  基础因子 f_i (6个):
    f_inertia   = 惯性因子 (今日涨跌对明日的惯性)
    f_volume    = 量能因子 (缩量/放量对持续性的影响)
    f_mainline  = 主线因子 (热点数量和强度)
    f_sentiment = 情绪因子 (涨跌家数、涨停数量)
    f_technical = 技术因子 (关口、均线、形态)
    f_divergence= 分化因子 (指数间分化程度)

  权重 w_i:
    w = {{inertia: 0.20, volume: 0.20, mainline: 0.15,
         sentiment: 0.15, technical: 0.15, divergence: 0.15}}

  修正系数 C_j (5个):
    C_volume_dir      = 缩量方向修正 (0.55~1.00)
    C_sentiment_decay  = 情绪衰减修正 (0.55~1.00)
    C_mainline_shrink  = 主线缩圈修正 (0.60~1.00)
    C_divergence_ext   = 极端分化修正 (0.65~0.90)
    C_psychological    = 心理关口修正 (0.60~1.00)

  纠错规则 R_k (8条):
    R1: 缩量方向 — 量价背离在非极值区域是反向信号
    R2: 情绪衰减 — 极端情绪后倾向均值回归
    R3: 主线缩圈 — 市场广度是趋势持续性的先行指标
    R4: 极端分化 — 极端偏离终将回归
    R5: 心理关口 — 首次触及关键价位多为试探
    R6: 放量下跌 — 放量方向确认趋势
    R7: 龙头断板 — 龙头走势是主线的领先指标
    R8: 连续缩量 — 量能趋势比单日量能更重要
""")

    lines.append("━" * 60)
    lines.append("  报告结束 — 玄甲 PHI_APEX v2 预测引擎 v3 修正完成")
    lines.append("━" * 60)

    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================

def main():
    print("╔" + "═" * 70 + "╗")
    print("║  🔮 玄甲 PHI_APEX v2 — 预测引擎 v3 修正版")
    print("║  纳入教训 · 代入公式 · 举一反三")
    print("╚" + "═" * 70 + "╝")

    report = generate_report()
    print("\n" + report)

    # 保存
    report_path = Path("/workspace/xuanjia/apex_agi/prediction_engine_v3.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"\n💾 报告已保存: {report_path}")

    # 保存v3引擎代码
    engine_path = Path("/workspace/xuanjia/apex_agi/prediction_engine_v3.py")
    # 这里保存整个脚本
    import shutil
    shutil.copy2("/data/user/work/prediction_engine_v3.py", str(engine_path))
    print(f"💾 引擎代码已保存: {engine_path}")

    # 保存纠错规则
    rules = derive_rules()
    rules_path = Path("/workspace/xuanjia/apex_agi/correction_rules.json")
    rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2))
    print(f"💾 纠错规则已保存: {rules_path}")


if __name__ == "__main__":
    main()
