#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲统一数据通道枢纽 (Data Channel Hub)
打通全部模块数据流: 数据获取 → 校验 → 策略适配 → 双引擎预测 → 融合决策 → 存盘

数据流:
  DSA聚合器 / CLI / MCP → 标准化 → 校验层 → v4引擎 + 策略适配 → 双引擎融合 → 存盘

Author: XuanJia ApexAGI
Version: 1.0.0
"""

import json
import os
import sys
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ============================================================
# 路径注册 — 确保所有模块可import
# ============================================================
_THIS_FILE = Path(__file__).resolve()
APEX_AGI_DIR = _THIS_FILE.parent  # /workspace/xuanjia/apex_agi
PROJECT_ROOT = APEX_AGI_DIR.parent  # /workspace/xuanjia
EVOLUTION_DIR = PROJECT_ROOT / "evolution"
WORK_DIR = Path("/data/user/work")

for p in [str(PROJECT_ROOT), str(APEX_AGI_DIR), str(EVOLUTION_DIR), str(WORK_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(APEX_AGI_DIR / "data_channel.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("DataChannelHub")

# ============================================================
# 标准数据契约 (所有模块共用)
# ============================================================

@dataclass
class MarketSnapshot:
    """标准化市场快照 — 所有模块的统一输入格式"""
    timestamp: str = ""
    period: str = "full_day"          # half_day / full_day
    data_time: str = ""

    # 指数
    sh_change: float = 0.0            # 上证涨跌幅%
    sh_price: float = 0.0             # 上证点位
    cy_change: float = 0.0            # 创业板涨跌幅%
    kc_change: float = 0.0            # 科创50涨跌幅%

    # 涨跌家数
    breadth_up: int = 0
    breadth_down: int = 0

    # 量能
    volume_total: float = 0.0         # 全市场成交额(亿)
    volume_change_desc: str = ""       # 如 "缩量1524亿"

    # 热点
    hot_sector_count: int = 0
    hot_sectors: List[str] = field(default_factory=list)

    # 涨停
    limit_up: int = 0

    # 外盘 (可选)
    us_nasdaq: float = 0.0
    hk_hsi: float = 0.0
    us_sp500: float = 0.0
    us_dow: float = 0.0
    oil: float = 0.0
    gold: float = 0.0

    # 元数据
    source: str = "manual"
    reliability: float = 1.0

    def to_v4_format(self) -> dict:
        """转换为 prediction_engine_v4 的输入格式"""
        return {
            "sh_change": self.sh_change,
            "cy_change": self.cy_change,
            "kc_change": self.kc_change,
            "breadth_up": self.breadth_up,
            "breadth_down": self.breadth_down,
            "hot_sector_count": self.hot_sector_count,
            "volume_change": self.volume_change_desc,
            "sh_price": self.sh_price,
            "timestamp": self.timestamp,
            "data_time": self.data_time,
            "period": self.period,
        }

    def to_v4_external(self) -> dict:
        """转换为 v4 的 external 参数"""
        return {
            "us_nasdaq": {"change_pct": self.us_nasdaq},
            "hk_hsi": {"change_pct": self.hk_hsi},
            "us_sp500": {"change_pct": self.us_sp500},
            "us_dow": {"change_pct": self.us_dow},
            "oil": {"change_pct": self.oil},
            "gold": {"change_pct": self.gold},
        }

    def to_v3_format(self) -> dict:
        """转换为 prediction_engine_v3 的输入格式"""
        return {
            "indices": {
                "000001": {"change_pct": self.sh_change, "current": self.sh_price},
                "399006": {"change_pct": self.cy_change},
                "000688": {"change_pct": self.kc_change},
            },
            "breadth": {
                "up": self.breadth_up,
                "down": self.breadth_down,
                "limit_up": str(self.limit_up),
            },
            "volume": f"{self.volume_total / 10000:.2f}万亿({self.volume_change_desc})",
            "hot_sectors": [{"name": s} for s in self.hot_sectors],
        }

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "MarketSnapshot":
        return cls(**json.loads(json_str))

    @classmethod
    def from_v3_today(cls, data: dict) -> "MarketSnapshot":
        """从 v3 格式的 today_data 反向构造"""
        snap = cls()
        indices = data.get("indices", {})
        idx000001 = indices.get("000001", {})
        snap.sh_change = float(idx000001.get("change_pct", 0))
        snap.sh_price = float(idx000001.get("current", 0))
        idx399006 = indices.get("399006", {})
        snap.cy_change = float(idx399006.get("change_pct", 0))
        idx000688 = indices.get("000688", {})
        snap.kc_change = float(idx000688.get("change_pct", 0))
        breadth = data.get("breadth", {})
        snap.breadth_up = int(breadth.get("up", 0))
        snap.breadth_down = int(breadth.get("down", 0))
        snap.limit_up = int(breadth.get("limit_up", 0))
        hot = data.get("hot_sectors", [])
        snap.hot_sectors = [h.get("name", "") for h in hot if isinstance(h, dict)]
        snap.hot_sector_count = len(snap.hot_sectors)
        snap.volume_change_desc = ""
        snap.timestamp = datetime.now().isoformat()
        snap.period = "full_day"
        snap.source = "v3_compat"
        return snap


@dataclass
class PredictionResult:
    """标准化预测结果 — 所有模块的统一输出格式"""
    timestamp: str = ""
    date: str = ""
    period: str = ""

    # v4引擎输出
    base_score: float = 50.0
    corrected_score: float = 50.0
    reliability: float = 0.5
    predicted_change: float = 0.0
    direction: str = "震荡"

    # 因子
    factors: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    corrections: Dict[str, float] = field(default_factory=dict)

    # 区间预测
    interval_mean: float = 0.0
    interval_68: List[float] = field(default_factory=lambda: [0.0, 0.0])
    interval_95: List[float] = field(default_factory=lambda: [0.0, 0.0])

    # 融合层
    fused_score: float = 50.0
    fused_signal: str = "观望"
    fused_trend: str = "震荡"
    consistency: float = 0.5
    risk_level: str = "中低风险"
    action_plan: List[str] = field(default_factory=list)
    warning: str = ""

    # 策略层
    active_strategies: List[str] = field(default_factory=list)
    adjusted_weights: Dict[str, float] = field(default_factory=dict)

    # 元数据
    engine_version: str = "v4.0"
    warnings: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "PredictionResult":
        return cls(**json.loads(json_str))


# ============================================================
# 数据通道枢纽
# ============================================================

class DataChannelHub:
    """
    统一数据通道枢纽

    职责:
    1. 接收原始市场数据 → 标准化为 MarketSnapshot
    2. 调用 v4 引擎预测
    3. 调用策略适配器
    4. 调用双引擎融合
    5. 输出标准化 PredictionResult
    6. 存盘到 JSON
    """

    # 存盘目录
    SAVE_DIR = APEX_AGI_DIR / "predictions"
    SNAPSHOT_DIR = APEX_AGI_DIR / "snapshots"

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self._ensure_dirs()
        self._prediction_cache: Dict[str, PredictionResult] = {}

    def _load_config(self, config_path: Optional[str]) -> dict:
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "engine": "v4",
            "strategies": ["均线金叉死叉", "资金流向", "热点题材"],
            "fusion_weights": {"apex_base": 0.55, "dsa_base": 0.45, "consistency_boost": 0.1, "divergence_penalty": 0.2},
            "auto_save": True,
            "market_condition": {
                "trend": "sideways",
                "volatility": "medium",
                "volume": "medium",
                "sentiment": "neutral",
            },
        }

    def _ensure_dirs(self):
        self.SAVE_DIR.mkdir(parents=True, exist_ok=True)
        self.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 入口: 接收市场快照 ----

    def ingest(self, data: Any, source: str = "manual", period: str = "full_day") -> MarketSnapshot:
        """
        接收任意格式的市场数据，标准化为 MarketSnapshot

        支持的输入:
        - dict (v3/v4格式)
        - MarketSnapshot 实例
        - JSON字符串
        """
        logger.info(f"[Hub] 接收数据 source={source} period={period}")

        if isinstance(data, MarketSnapshot):
            snap = data
            snap.source = source
            snap.period = period
        elif isinstance(data, str):
            snap = MarketSnapshot.from_json(data)
            snap.source = source
            snap.period = period
        elif isinstance(data, dict):
            # 自动检测格式
            if "sh_change" in data:
                # v4 格式
                snap = MarketSnapshot(
                    sh_change=float(data.get("sh_change", 0)),
                    sh_price=float(data.get("sh_price", 0)),
                    cy_change=float(data.get("cy_change", 0)),
                    kc_change=float(data.get("kc_change", 0)),
                    breadth_up=int(data.get("breadth_up", 0)),
                    breadth_down=int(data.get("breadth_down", 0)),
                    hot_sector_count=int(data.get("hot_sector_count", 0)),
                    volume_change_desc=str(data.get("volume_change", "")),
                    timestamp=data.get("timestamp", datetime.now().isoformat()),
                    data_time=data.get("data_time", ""),
                    period=period,
                    source=source,
                )
            elif "indices" in data:
                # v3 格式
                snap = MarketSnapshot.from_v3_today(data)
                snap.period = period
                snap.source = source
            else:
                # 通用dict，尝试逐字段映射
                snap = MarketSnapshot(
                    sh_change=float(data.get("sh_change", data.get("index_change", 0))),
                    sh_price=float(data.get("sh_price", data.get("close", 0))),
                    cy_change=float(data.get("cy_change", 0)),
                    kc_change=float(data.get("kc_change", 0)),
                    breadth_up=int(data.get("breadth_up", data.get("up_count", 0))),
                    breadth_down=int(data.get("breadth_down", data.get("down_count", 0))),
                    hot_sector_count=int(data.get("hot_sector_count", 0)),
                    volume_change_desc=str(data.get("volume_change", "")),
                    timestamp=data.get("timestamp", datetime.now().isoformat()),
                    period=period,
                    source=source,
                )
        else:
            raise ValueError(f"[Hub] 不支持的数据类型: {type(data)}")

        # 存盘快照
        self._save_snapshot(snap)
        return snap

    # ---- 核心: 完整预测流水线 ----

    def run_pipeline(self, snapshot: MarketSnapshot) -> PredictionResult:
        """
        运行完整预测流水线:
        ingest → v4预测 → 策略适配 → 双引擎融合 → 存盘
        """
        logger.info(f"[Hub] ===== 开始预测流水线 =====")
        logger.info(f"[Hub] 快照: {snapshot.sh_price} 涨跌={snapshot.sh_change:+.2f}% period={snapshot.period}")

        result = PredictionResult(
            timestamp=snapshot.timestamp,
            date=snapshot.timestamp[:10] if snapshot.timestamp else datetime.now().strftime("%Y-%m-%d"),
            period=snapshot.period,
            engine_version="v4.0+dsa",
        )

        # Step 1: v4 引擎预测
        try:
            v4_result = self._run_v4_engine(snapshot)
            result.base_score = v4_result.get("base_score", 50)
            result.corrected_score = v4_result.get("corrected_score", 50)
            result.reliability = v4_result.get("reliability", 0.5)
            result.predicted_change = v4_result.get("predicted_change", 0)
            result.direction = v4_result.get("direction", "震荡")
            result.factors = v4_result.get("factors", {})
            result.weights = v4_result.get("weights", {})
            result.corrections = v4_result.get("corrections", {})
            result.warnings = v4_result.get("warnings", [])

            # 区间预测
            interval = v4_result.get("interval", {})
            result.interval_mean = interval.get("mean", 0)
            result.interval_68 = interval.get("ci68", [0, 0])
            result.interval_95 = interval.get("ci95", [0, 0])

            logger.info(f"[Hub] v4引擎: score={result.corrected_score:.1f} dir={result.direction} "
                       f"change={result.predicted_change:+.2f}% reliability={result.reliability:.2f}")
        except Exception as e:
            logger.error(f"[Hub] v4引擎失败: {e}")
            result.warnings.append(f"v4引擎异常: {str(e)}")

        # Step 2: 策略适配
        try:
            strategy_result = self._run_strategy_adapter(snapshot)
            result.active_strategies = strategy_result.get("active_strategies", [])
            result.adjusted_weights = strategy_result.get("final_weights", {})
            logger.info(f"[Hub] 策略适配: {len(result.active_strategies)}个策略激活")
        except Exception as e:
            logger.error(f"[Hub] 策略适配失败: {e}")
            result.warnings.append(f"策略适配异常: {str(e)}")

        # Step 3: 双引擎融合
        try:
            fusion_result = self._run_dual_fusion(result, snapshot)
            result.fused_score = fusion_result.fused_score
            result.fused_signal = fusion_result.signal
            result.fused_trend = fusion_result.trend
            result.consistency = fusion_result.consistency
            result.risk_level = fusion_result.risk_level
            result.action_plan = fusion_result.action_plan
            result.warning = fusion_result.warning or ""
            logger.info(f"[Hub] 融合: fused={result.fused_score:.1f} signal={result.fused_signal} "
                       f"risk={result.risk_level}")
        except Exception as e:
            logger.error(f"[Hub] 双引擎融合失败: {e}")
            result.warnings.append(f"融合异常: {str(e)}")
            result.fused_score = result.corrected_score
            result.fused_signal = "观望"
            result.fused_trend = "震荡"

        # Step 4: 存盘
        if self.config.get("auto_save", True):
            self._save_prediction(result)

        logger.info(f"[Hub] ===== 预测流水线完成 =====")
        return result

    # ---- 内部: 各步骤实现 ----

    def _run_v4_engine(self, snapshot: MarketSnapshot) -> dict:
        """调用预测引擎 (优先v4，回退v3)"""
        predict_fn = None
        engine_ver = "v4"
        # 尝试多个路径导入v4
        for path in [str(WORK_DIR), str(APEX_AGI_DIR), str(EVOLUTION_DIR)]:
            if path not in sys.path:
                sys.path.insert(0, path)
            try:
                from prediction_engine_v4 import predict_v4 as _pv4
                predict_fn = _pv4
                break
            except ImportError:
                continue

        # v4不存在则尝试v3
        if predict_fn is None:
            try:
                from prediction_engine_v3 import predict_v3 as _pv3
                predict_fn = _pv3
                engine_ver = "v3"
            except ImportError:
                pass

        if predict_fn is None:
            logger.warning("[Hub] 预测引擎不可用，使用回退计算")
            return self._fallback_predict(snapshot)

        if engine_ver == "v4":
            v4_input = snapshot.to_v4_format()
            external = snapshot.to_v4_external()
            return predict_fn(
                today_data=v4_input,
                external=external,
                period=snapshot.period,
            )
        else:
            # v3格式
            v3_input = snapshot.to_v3_format()
            return predict_fn(today_data=v3_input)

    def _fallback_predict(self, snapshot: MarketSnapshot) -> dict:
        """v4不可用时的回退预测"""
        # 简单的惯性+方向预测
        score = 50 + snapshot.sh_change * 5
        score = max(10, min(90, score))
        return {
            "base_score": score,
            "corrected_score": score,
            "reliability": 0.3,
            "predicted_change": snapshot.sh_change * 0.3,
            "direction": "小涨" if snapshot.sh_change > 0.3 else ("小跌" if snapshot.sh_change < -0.3 else "震荡"),
            "factors": {"inertia": 0.5, "volume": 0.5, "main_line": 0.5, "sentiment": 0.5, "technical": 0.5, "divergence": 0.5},
            "weights": {},
            "corrections": {},
            "interval": {"mean": snapshot.sh_change * 0.3, "ci68": [snapshot.sh_change * 0.1, snapshot.sh_change * 0.5], "ci95": [-0.5, 0.5]},
            "warnings": ["v4引擎不可用，使用回退计算"],
        }

    def _run_strategy_adapter(self, snapshot: MarketSnapshot) -> dict:
        """调用策略适配器"""
        try:
            from dsa_strategy_adapter import DSAStrategyAdapter
        except ImportError:
            sys.path.insert(0, str(APEX_AGI_DIR))
            from dsa_strategy_adapter import DSAStrategyAdapter

        adapter = DSAStrategyAdapter()
        strategies = self.config.get("strategies", [])

        # 根据市场环境自动选择
        market_condition = self.config.get("market_condition", {})
        # 根据快照数据动态更新市场环境
        if snapshot.sh_change > 0.5:
            market_condition["trend"] = "up"
        elif snapshot.sh_change < -0.5:
            market_condition["trend"] = "down"
        else:
            market_condition["trend"] = "sideways"

        if snapshot.volume_total > 12000:
            market_condition["volume"] = "high"
        elif snapshot.volume_total < 7000:
            market_condition["volume"] = "low"

        for strategy_name in strategies:
            try:
                from dsa_strategy_adapter import DSAStrategy
                adapter.activate_strategy(DSAStrategy(strategy_name))
            except (ImportError, ValueError):
                pass

        return adapter.get_strategy_summary()

    def _run_dual_fusion(self, result: PredictionResult, snapshot: MarketSnapshot):
        """调用双引擎融合"""
        try:
            from dual_engine_fusion import DualEngineFusion, ApexResult, DSAResult
        except ImportError:
            sys.path.insert(0, str(APEX_AGI_DIR))
            from dual_engine_fusion import DualEngineFusion, ApexResult, DSAResult

        apex = ApexResult(
            score=result.corrected_score,
            signal="买入" if result.predicted_change > 0.3 else ("卖出" if result.predicted_change < -0.3 else "观望"),
            trend=result.direction,
            confidence=result.reliability,
            predicted_change=result.predicted_change,
            interval_68=tuple(result.interval_68),
            interval_95=tuple(result.interval_95),
            factors=result.factors,
            warnings=result.warnings,
        )

        # DSA侧: 基于策略适配结果模拟
        dsa_score = result.corrected_score * 0.95 + snapshot.sh_change * 2
        dsa_score = max(10, min(90, dsa_score))
        dsa_signal = "买入" if dsa_score > 60 else ("卖出" if dsa_score < 40 else "观望")
        dsa_trend = "看多" if dsa_score > 60 else ("看空" if dsa_score < 40 else "震荡")

        dsa = DSAResult(
            score=dsa_score,
            signal=dsa_signal,
            trend=dsa_trend,
            confidence=0.6,
            risks=[w for w in result.warnings[:3]],
            catalysts=[],
            checklist=[],
        )

        fusion = DualEngineFusion(weights=self.config.get("fusion_weights"))
        return fusion.fuse(apex, dsa)

    # ---- 存盘 ----

    def _save_prediction(self, result: PredictionResult):
        """存盘预测结果"""
        date_str = result.date or datetime.now().strftime("%Y%m%d")
        filepath = self.SAVE_DIR / f"prediction_{date_str}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.to_json())
        logger.info(f"[Hub] 预测结果已存盘: {filepath}")
        self._prediction_cache[date_str] = result

    def _save_snapshot(self, snapshot: MarketSnapshot):
        """存盘市场快照"""
        date_str = snapshot.timestamp[:10] if snapshot.timestamp else datetime.now().strftime("%Y%m%d")
        period_tag = snapshot.period
        filepath = self.SNAPSHOT_DIR / f"snapshot_{date_str}_{period_tag}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(snapshot.to_json())

    # ---- 查询 ----

    def get_prediction(self, date: str) -> Optional[PredictionResult]:
        """获取历史预测"""
        if date in self._prediction_cache:
            return self._prediction_cache[date]
        filepath = self.SAVE_DIR / f"prediction_{date}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return PredictionResult.from_json(f.read())
        return None

    def list_predictions(self) -> List[str]:
        """列出所有已存盘的预测"""
        return sorted([f.stem.replace("prediction_", "") for f in self.SAVE_DIR.glob("prediction_*.json")])

    def get_snapshot(self, date: str, period: str = "full_day") -> Optional[MarketSnapshot]:
        """获取历史快照"""
        filepath = self.SNAPSHOT_DIR / f"snapshot_{date}_{period}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return MarketSnapshot.from_json(f.read())
        return None

    def format_report(self, result: PredictionResult) -> str:
        """格式化预测报告"""
        lines = [
            "=" * 60,
            f"🎯 玄甲预测报告 | {result.date} | {result.period}",
            "=" * 60,
            "",
            f"📊 v4引擎评分: {result.corrected_score:.1f} (基础={result.base_score:.1f})",
            f"📈 预测方向: {result.direction} ({result.predicted_change:+.2f}%)",
            f"🔍 可靠性: {result.reliability:.2f}",
            "",
            f"🤖 双引擎融合: {result.fused_score:.1f} | 信号={result.fused_signal} | 趋势={result.fused_trend}",
            f"⚡ 风险等级: {result.risk_level}",
            f"🔗 一致性: {result.consistency:.2f}",
        ]

        if result.warning:
            lines.append(f"⚠️ {result.warning}")

        if result.interval_68:
            lines.append(f"")
            lines.append(f"📐 区间预测:")
            lines.append(f"   68%: [{result.interval_68[0]:+.2f}%, {result.interval_68[1]:+.2f}%]")
            lines.append(f"   95%: [{result.interval_95[0]:+.2f}%, {result.interval_95[1]:+.2f}%]")

        if result.factors:
            lines.append(f"")
            lines.append(f"🔬 因子得分:")
            for k, v in result.factors.items():
                lines.append(f"   {k}: {v:.3f}")

        if result.action_plan:
            lines.append(f"")
            lines.append(f"📋 行动计划:")
            for a in result.action_plan[:5]:
                lines.append(f"   {a}")

        if result.warnings:
            lines.append(f"")
            lines.append(f"⚠️ 警告:")
            for w in result.warnings:
                lines.append(f"   - {w}")

        lines.extend(["", "=" * 60])
        return "\n".join(lines)


# ============================================================
# 便捷入口
# ============================================================

# 全局单例
_hub_instance: Optional[DataChannelHub] = None

def get_hub(config_path: Optional[str] = None) -> DataChannelHub:
    """获取全局Hub单例"""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = DataChannelHub(config_path)
    return _hub_instance


def quick_predict(data: dict, period: str = "full_day") -> PredictionResult:
    """
    快速预测入口

    用法:
        from data_channel_hub import quick_predict

        result = quick_predict({
            "sh_change": 1.56,
            "sh_price": 3373.28,
            "cy_change": 2.03,
            "kc_change": 1.82,
            "breadth_up": 4200,
            "breadth_down": 800,
            "hot_sector_count": 5,
            "volume_change": "放量3256亿",
        })
        print(result.fused_signal)
    """
    hub = get_hub()
    snapshot = hub.ingest(data, source="quick", period=period)
    return hub.run_pipeline(snapshot)


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("玄甲数据通道枢纽 - 集成测试")
    print("=" * 60)

    hub = DataChannelHub()

    # 测试1: 用6/12真实数据
    print("\n📊 测试1: 6/12收盘数据完整流水线")
    test_data_612 = {
        "sh_change": 1.56,
        "sh_price": 3373.28,
        "cy_change": 2.03,
        "kc_change": 1.82,
        "breadth_up": 4200,
        "breadth_down": 800,
        "hot_sector_count": 5,
        "volume_change": "放量3256亿",
        "timestamp": "2026-06-12T15:00:00",
        "period": "full_day",
    }

    snapshot = hub.ingest(test_data_612, source="test", period="full_day")
    print(f"  快照标准化完成: sh={snapshot.sh_price} change={snapshot.sh_change:+.2f}%")

    result = hub.run_pipeline(snapshot)
    print(hub.format_report(result))

    # 测试2: v3格式兼容
    print("\n📊 测试2: v3格式兼容测试")
    v3_data = {
        "indices": {
            "000001": {"change_pct": 0.85, "current": 3250.12},
            "399006": {"change_pct": 1.35},
            "000688": {"change_pct": 2.80},
        },
        "breadth": {"up": 3920, "down": 1349, "limit_up": "155"},
        "volume": "1.2万亿(缩量500亿)",
        "hot_sectors": [{"name": "有色金属"}, {"name": "半导体"}, {"name": "PCB"}],
    }

    snap_v3 = hub.ingest(v3_data, source="v3_compat", period="full_day")
    print(f"  v3快照: sh={snap_v3.sh_price} sectors={snap_v3.hot_sectors}")

    # 测试3: 存盘验证
    print("\n📊 测试3: 存盘验证")
    predictions = hub.list_predictions()
    print(f"  已存盘预测: {predictions}")
    snapshots = list(hub.SNAPSHOT_DIR.glob("snapshot_*.json"))
    print(f"  已存盘快照: {len(snapshots)} 个")

    # 测试4: 查询历史
    print("\n📊 测试4: 历史查询")
    if predictions:
        latest = predictions[-1]
        pred = hub.get_prediction(latest)
        if pred:
            print(f"  最新预测 ({latest}): score={pred.corrected_score:.1f} signal={pred.fused_signal}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
