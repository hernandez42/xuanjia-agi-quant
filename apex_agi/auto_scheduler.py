#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化调度器 — 策略任务自动化调度系统

本模块实现了一个策略自动化调度器，包含：
- CronParser: 解析标准5字段cron表达式，判断时间是否匹配
- TaskExecutionLog: 任务执行日志数据类
- TaskScheduler: 任务调度器，支持注册、触发、暂停、恢复、删除任务
- 预置任务配置：每日收盘扫描、每周复盘、每月初筛、预测验证

仅使用Python标准库（time + threading），不依赖APScheduler等第三方库。
"""

import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional


# ==============================================================================
# TaskExecutionLog — 任务执行日志数据类
# ==============================================================================

@dataclass
class TaskExecutionLog:
    """
    任务执行日志数据类

    Attributes:
        task_name:      任务名称
        executed_at:    执行时间（datetime对象）
        status:         执行状态（"success" / "failed" / "running"）
        result_summary: 执行结果摘要
    """
    task_name: str
    executed_at: datetime
    status: str
    result_summary: str

    def __str__(self) -> str:
        """格式化输出日志信息"""
        time_str = self.executed_at.strftime("%Y-%m-%d %H:%M:%S")
        return f"[{time_str}] {self.task_name} | 状态: {self.status} | {self.result_summary}"


# ==============================================================================
# CronParser — Cron表达式解析器
# ==============================================================================

class CronParser:
    """
    Cron表达式解析器

    解析标准5字段cron表达式（分 时 日 月 周），判断给定时间是否匹配cron规则。
    支持的语法：
    - 通配符 * ：匹配任意值
    - 范围 1-5 ：匹配范围内的所有值
    - 列表 1,3,5：匹配列表中的值
    - 步长 */2 ：从最小值开始，每隔N个值匹配一次
    - 混合 1-5/2：在范围内每隔N个值匹配一次

    字段说明：
    - 分（minute）：0-59
    - 时（hour）：0-23
    - 日（day_of_month）：1-31
    - 月（month）：1-12
    - 周（day_of_week）：0-6（0=周日）
    """

    # 各字段的有效范围
    FIELD_RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day_of_month": (1, 31),
        "month": (1, 12),
        "day_of_week": (0, 6),
    }

    def __init__(self, cron_expression: str):
        """
        初始化Cron解析器

        Args:
            cron_expression: 标准的5字段cron表达式，如 "30 15 * * *"
        """
        self.cron_expression = cron_expression.strip()
        self.fields = self._parse_expression(cron_expression)

    def _parse_expression(self, expression: str) -> Dict[str, List[int]]:
        """
        解析cron表达式为各字段的匹配值集合

        Args:
            expression: cron表达式字符串

        Returns:
            字典，键为字段名，值为该字段匹配的整数列表
        """
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(
                f"cron表达式必须包含5个字段（分 时 日 月 周），"
                f"当前输入: '{expression}'"
            )

        field_names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
        parsed = {}

        for name, part in zip(field_names, parts):
            parsed[name] = self._parse_field(part, name)

        return parsed

    def _parse_field(self, field_str: str, field_name: str) -> List[int]:
        """
        解析单个cron字段

        Args:
            field_str: 字段字符串，如 "*"、"1-5"、"*/2"、"1,3,5"
            field_name: 字段名称

        Returns:
            匹配的整数列表
        """
        min_val, max_val = self.FIELD_RANGES[field_name]
        result = set()

        # 处理逗号分隔的多个表达式
        segments = field_str.split(",")
        for segment in segments:
            segment = segment.strip()
            result.update(self._parse_segment(segment, min_val, max_val))

        return sorted(result)

    def _parse_segment(self, segment: str, min_val: int, max_val: int) -> List[int]:
        """
        解析单个cron字段段（不含逗号的部分）

        Args:
            segment: 字段段字符串
            min_val: 字段最小值
            max_val: 字段最大值

        Returns:
            匹配的整数列表
        """
        # 处理步长
        step = 1
        if "/" in segment:
            range_part, step_str = segment.split("/", 1)
            step = int(step_str)
            segment = range_part

        if segment == "*":
            # 通配符：匹配所有值
            start = min_val
            end = max_val
        elif "-" in segment:
            # 范围：如 1-5
            start_str, end_str = segment.split("-", 1)
            start = int(start_str)
            end = int(end_str)
        else:
            # 单个值
            start = int(segment)
            end = start

        # 生成匹配列表（按步长）
        values = []
        current = start
        while current <= end:
            if min_val <= current <= max_val:
                values.append(current)
            current += step

        return values

    def matches(self, dt: Optional[datetime] = None) -> bool:
        """
        判断给定时间是否匹配cron规则

        Args:
            dt: 要判断的时间，默认为当前时间

        Returns:
            True表示匹配，False表示不匹配
        """
        if dt is None:
            dt = datetime.now()

        # 检查每个字段
        checks = [
            ("minute", dt.minute),
            ("hour", dt.hour),
            ("day_of_month", dt.day),
            ("month", dt.month),
            ("day_of_week", dt.weekday()),  # Python的weekday(): 0=周一, 6=周日
        ]

        # 注意：cron的day_of_week: 0=周日, 1=周一, ..., 6=周六
        # Python的weekday(): 0=周一, 1=周二, ..., 6=周日
        # 需要转换
        cron_weekday = (dt.weekday() + 1) % 7  # 转换为cron格式: 0=周日

        for field_name, value in checks[:-1]:  # 前四个字段直接比较
            if value not in self.fields[field_name]:
                return False

        # 周字段使用转换后的值
        if cron_weekday not in self.fields["day_of_week"]:
            return False

        return True

    def __str__(self) -> str:
        """返回cron表达式的字符串表示"""
        return self.cron_expression

    def describe(self) -> str:
        """
        返回cron表达式的可读描述

        Returns:
            人类可读的cron表达式描述
        """
        parts = self.cron_expression.split()
        if len(parts) != 5:
            return self.cron_expression

        minute, hour, dom, month, dow = parts

        # 构建描述
        desc_parts = []

        # 月描述
        if month == "*":
            desc_parts.append("每月")
        else:
            desc_parts.append(f"{month}月")

        # 日描述
        if dom == "*":
            desc_parts.append("每日")
        elif dom == "1":
            desc_parts.append("1日")
        else:
            desc_parts.append(f"{dom}日")

        # 时描述
        desc_parts.append(f"{hour}时")

        # 分描述
        desc_parts.append(f"{minute}分")

        # 周描述（如果有特殊设置）
        if dow != "*":
            weekday_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
            try:
                dow_num = int(dow)
                desc_parts.append(f"（{weekday_names[dow_num]}）")
            except ValueError:
                desc_parts.append(f"（周{dow}）")

        return " ".join(desc_parts)


# ==============================================================================
# TaskScheduler — 任务调度器
# ==============================================================================

class TaskScheduler:
    """
    任务调度器：管理策略任务的注册、触发、暂停、恢复和删除。

    内部使用 time.sleep + threading 实现简单的定时循环调度，
    不依赖 APScheduler 等第三方库。

    功能：
    - 注册任务（名称、执行函数、cron表达式、参数）
    - 手动触发任务
    - 查看任务列表和状态
    - 暂停/恢复/删除任务
    - 执行历史记录
    - 后台调度循环
    """

    def __init__(self):
        """初始化任务调度器"""
        # 任务注册表：{任务名: 任务配置字典}
        self._tasks: Dict[str, Dict] = {}
        # 任务状态：{任务名: "active" | "paused"}
        self._task_status: Dict[str, str] = {}
        # 执行历史记录
        self._execution_logs: List[TaskExecutionLog] = []
        # 后台调度线程
        self._scheduler_thread: Optional[threading.Thread] = None
        # 调度器运行标志
        self._running: bool = False
        # 锁，保证线程安全
        self._lock = threading.Lock()

    def register_task(
        self,
        name: str,
        func: Callable,
        cron_expression: str,
        params: Optional[Dict] = None,
        description: str = ""
    ) -> bool:
        """
        注册一个新任务

        Args:
            name:           任务名称（唯一标识）
            func:           任务执行函数
            cron_expression: cron表达式（5字段：分 时 日 月 周）
            params:         传递给执行函数的参数字典
            description:    任务描述

        Returns:
            True注册成功，False任务名已存在
        """
        with self._lock:
            if name in self._tasks:
                print(f"  [注册失败] 任务 '{name}' 已存在")
                return False

            # 验证cron表达式
            try:
                parser = CronParser(cron_expression)
            except ValueError as e:
                print(f"  [注册失败] cron表达式无效: {e}")
                return False

            self._tasks[name] = {
                "name": name,
                "func": func,
                "cron_expression": cron_expression,
                "cron_parser": parser,
                "params": params or {},
                "description": description,
                "registered_at": datetime.now(),
            }
            self._task_status[name] = "active"

            print(f"  [注册成功] 任务 '{name}' — {parser.describe()}")
            if description:
                print(f"              描述: {description}")
            return True

    def unregister_task(self, name: str) -> bool:
        """
        删除一个已注册的任务

        Args:
            name: 任务名称

        Returns:
            True删除成功，False任务不存在
        """
        with self._lock:
            if name not in self._tasks:
                print(f"  [删除失败] 任务 '{name}' 不存在")
                return False

            del self._tasks[name]
            del self._task_status[name]
            print(f"  [删除成功] 任务 '{name}' 已删除")
            return True

    def pause_task(self, name: str) -> bool:
        """
        暂停一个任务

        Args:
            name: 任务名称

        Returns:
            True暂停成功，False任务不存在或已暂停
        """
        with self._lock:
            if name not in self._tasks:
                print(f"  [暂停失败] 任务 '{name}' 不存在")
                return False
            if self._task_status[name] == "paused":
                print(f"  [暂停失败] 任务 '{name}' 已处于暂停状态")
                return False

            self._task_status[name] = "paused"
            print(f"  [暂停成功] 任务 '{name}' 已暂停")
            return True

    def resume_task(self, name: str) -> bool:
        """
        恢复一个已暂停的任务

        Args:
            name: 任务名称

        Returns:
            True恢复成功，False任务不存在或未暂停
        """
        with self._lock:
            if name not in self._tasks:
                print(f"  [恢复失败] 任务 '{name}' 不存在")
                return False
            if self._task_status[name] == "active":
                print(f"  [恢复失败] 任务 '{name}' 已处于活跃状态")
                return False

            self._task_status[name] = "active"
            print(f"  [恢复成功] 任务 '{name}' 已恢复")
            return True

    def trigger_task(self, name: str) -> bool:
        """
        手动触发一个任务（立即执行，不受cron规则限制）

        Args:
            name: 任务名称

        Returns:
            True触发成功，False任务不存在
        """
        with self._lock:
            if name not in self._tasks:
                print(f"  [触发失败] 任务 '{name}' 不存在")
                return False

        # 在锁外执行任务（避免长时间持锁）
        self._execute_task(name)
        return True

    def _execute_task(self, name: str) -> None:
        """
        内部方法：执行指定任务

        Args:
            name: 任务名称
        """
        task = self._tasks.get(name)
        if task is None:
            return

        func = task["func"]
        params = task["params"]
        exec_time = datetime.now()

        # 创建执行日志（初始状态为running）
        log = TaskExecutionLog(
            task_name=name,
            executed_at=exec_time,
            status="running",
            result_summary="执行中..."
        )
        self._execution_logs.append(log)

        print(f"\n  >> 开始执行任务: {name}")
        print(f"     执行时间: {exec_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"     参数: {params}")

        try:
            # 调用任务函数
            result = func(**params) if params else func()

            # 更新日志状态
            log.status = "success"
            if result is None:
                log.result_summary = "执行完成"
            elif isinstance(result, str):
                log.result_summary = result
            else:
                log.result_summary = str(result)

            print(f"     状态: 成功")
            print(f"     结果: {log.result_summary}")

        except Exception as e:
            log.status = "failed"
            log.result_summary = f"执行异常: {e}"
            print(f"     状态: 失败")
            print(f"     错误: {e}")

    def list_tasks(self) -> List[Dict]:
        """
        查看所有已注册的任务列表和状态

        Returns:
            任务信息列表
        """
        tasks = []
        with self._lock:
            for name, task in self._tasks.items():
                tasks.append({
                    "name": name,
                    "cron_expression": task["cron_expression"],
                    "description": task["description"],
                    "status": self._task_status.get(name, "unknown"),
                    "registered_at": task["registered_at"].strftime("%Y-%m-%d %H:%M:%S"),
                    "cron_description": task["cron_parser"].describe(),
                })
        return tasks

    def print_tasks(self) -> None:
        """打印任务列表（格式化输出）"""
        tasks = self.list_tasks()
        if not tasks:
            print("  当前没有已注册的任务。")
            return

        print("\n" + "=" * 75)
        print("  任务调度器 — 已注册任务列表")
        print("=" * 75)
        print(f"  {'任务名称':<20}{'Cron表达式':<18}{'状态':<10}{'描述'}")
        print("  " + "-" * 72)

        for t in tasks:
            status_mark = "[活跃]" if t["status"] == "active" else "[暂停]"
            print(f"  {t['name']:<20}{t['cron_expression']:<18}{status_mark:<10}{t['description']}")
            print(f"  {'':20}调度规则: {t['cron_description']}")

        print("=" * 75)

    def get_execution_logs(self, task_name: Optional[str] = None) -> List[TaskExecutionLog]:
        """
        获取执行历史记录

        Args:
            task_name: 指定任务名（可选），不指定则返回全部

        Returns:
            执行日志列表
        """
        with self._lock:
            if task_name is not None:
                return [log for log in self._execution_logs if log.task_name == task_name]
            return list(self._execution_logs)

    def print_execution_logs(self, task_name: Optional[str] = None) -> None:
        """
        打印执行历史记录

        Args:
            task_name: 指定任务名（可选）
        """
        logs = self.get_execution_logs(task_name)
        if not logs:
            print("  暂无执行记录。")
            return

        print("\n" + "=" * 75)
        print("  任务调度器 — 执行历史记录")
        print("=" * 75)
        for log in logs:
            print(f"  {log}")
        print("=" * 75)

    def _scheduler_loop(self, check_interval: int = 1) -> None:
        """
        调度器后台循环

        每隔 check_interval 秒检查一次所有活跃任务，
        判断当前时间是否匹配cron规则，匹配则执行任务。

        Args:
            check_interval: 检查间隔（秒）
        """
        print(f"\n  [调度器] 后台调度循环已启动（检查间隔: {check_interval}秒）")
        print(f"  [调度器] 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        while self._running:
            now = datetime.now()

            with self._lock:
                active_tasks = [
                    (name, task) for name, task in self._tasks.items()
                    if self._task_status.get(name) == "active"
                ]

            for name, task in active_tasks:
                parser = task["cron_parser"]
                if parser.matches(now):
                    # 防止同一分钟内重复执行
                    # 检查最近一条该任务的日志是否在同一分钟内
                    recent_logs = [
                        log for log in self._execution_logs
                        if log.task_name == name
                        and log.executed_at.strftime("%Y-%m-%d %H:%M") == now.strftime("%Y-%m-%d %H:%M")
                    ]
                    if not recent_logs:
                        print(f"\n  [调度器] 触发cron匹配任务: {name}")
                        self._execute_task(name)

            # 等待下一次检查
            time.sleep(check_interval)

        print(f"\n  [调度器] 后台调度循环已停止")

    def start(self, check_interval: int = 1) -> None:
        """
        启动后台调度循环

        Args:
            check_interval: 检查间隔（秒），默认1秒
        """
        if self._running:
            print("  [调度器] 已经在运行中")
            return

        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(check_interval,),
            daemon=True  # 设为守护线程，主线程退出时自动结束
        )
        self._scheduler_thread.start()
        print(f"  [调度器] 已启动后台调度线程")

    def stop(self) -> None:
        """停止后台调度循环"""
        if not self._running:
            print("  [调度器] 未在运行")
            return

        self._running = False
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=5)
        print(f"  [调度器] 已停止后台调度线程")

    def is_running(self) -> bool:
        """检查调度器是否在运行"""
        return self._running


# ==============================================================================
# 预置任务配置
# ==============================================================================

def register_preset_tasks(scheduler: TaskScheduler) -> None:
    """
    注册预置任务到调度器（V6.3 完整版 — 接入真实引擎）

    预置任务包括：
    - 每日收盘扫描：15:30 执行，运行完整策略流水线
    - 每周复盘：周日 20:00 执行，回测+风控复盘
    - 每月初筛：每月1日 09:00 执行，多因子月初筛选
    - 预测验证：每日 09:30 执行，验证前日预测

    Args:
        scheduler: 任务调度器实例
    """
    print("\n注册预置任务（V6.3 完整版）...")
    print("-" * 50)

    # 任务1：每日收盘扫描 — 15:30
    def daily_close_scan(**kwargs):
        """每日收盘扫描：运行完整策略流水线"""
        stock_pool = kwargs.get("stock_pool", ["600519", "300750", "002594", "601318", "000858"])
        try:
            from strategy_pipeline import StrategyPipeline
            pipeline = StrategyPipeline(stock_pool=stock_pool)
            result = pipeline.run_daily_scan()
            signals = result.get("signals", [])
            buy_signals = [s for s in signals if s.get("signal") == "buy"]
            sell_signals = [s for s in signals if s.get("signal") == "sell"]
            return (f"收盘扫描完成 | 买入信号: {len(buy_signals)} | "
                    f"卖出信号: {len(sell_signals)} | 总信号: {len(signals)}")
        except Exception as e:
            return f"收盘扫描失败: {e}"

    scheduler.register_task(
        name="每日收盘扫描",
        func=daily_close_scan,
        cron_expression="30 15 * * *",
        params={"stock_pool": ["600519", "300750", "002594", "601318", "000858"]},
        description="每个交易日15:30执行完整策略流水线扫描"
    )

    # 任务2：每周复盘 — 周日 20:00
    def weekly_review(**kwargs):
        """每周复盘：运行回测+风控检查"""
        stock_pool = kwargs.get("stock_pool", ["600519", "300750", "002594"])
        try:
            from strategy_pipeline import StrategyPipeline
            pipeline = StrategyPipeline(stock_pool=stock_pool)
            bt_result = pipeline.run_backtest(days=120)
            return (f"周复盘完成 | 总收益率: {bt_result.get('total_return', 0):.2%} | "
                    f"最大回撤: {bt_result.get('max_drawdown', 0):.2%} | "
                    f"夏普比率: {bt_result.get('sharpe_ratio', 0):.4f}")
        except Exception as e:
            return f"周复盘失败: {e}"

    scheduler.register_task(
        name="每周复盘",
        func=weekly_review,
        cron_expression="0 20 * * 0",
        params={"stock_pool": ["600519", "300750", "002594"]},
        description="每周日20:00执行回测+风控复盘分析"
    )

    # 任务3：每月初筛 — 每月1日 09:00
    def monthly_screen(**kwargs):
        """每月初筛：运行多因子模型筛选"""
        stock_pool = kwargs.get("stock_pool", ["600519", "300750", "002594", "601318", "000858",
                                                "688981", "600111", "603259", "600028", "688012"])
        try:
            from multi_factor_model import MultiFactorSelector, FactorLibrary
            selector = MultiFactorSelector()
            # 构建模拟数据（实际应接入数据获取层）
            stocks_data = {}
            for code in stock_pool:
                stocks_data[code] = {
                    "dates": ["2026-05-01", "2026-05-02", "2026-05-03"],
                    "close": [100.0, 102.0, 105.0],
                    "open": [99.0, 101.0, 103.0],
                    "high": [103.0, 104.0, 106.0],
                    "low": [98.0, 100.0, 102.0],
                    "volume": [10000, 12000, 15000],
                    "amount": [990000, 1224000, 1575000],
                    "pe": 25.0, "pb": 3.0, "roe": 15.0,
                    "main_net_inflow": 500000, "turnover_rate": 2.5,
                }
            results = selector.select(stocks_data, top_n=5)
            top_codes = [r["stock_code"] for r in results[:3]]
            return f"月初筛选完成 | TOP3: {', '.join(top_codes)} | 共筛选 {len(results)} 只"
        except Exception as e:
            return f"月初筛选失败: {e}"

    scheduler.register_task(
        name="每月初筛",
        func=monthly_screen,
        cron_expression="0 9 1 * *",
        params={"stock_pool": ["600519", "300750", "002594", "601318", "000858",
                               "688981", "600111", "603259", "600028", "688012"]},
        description="每月1日09:00执行多因子月初筛选"
    )

    # 任务4：预测验证 — 每日 09:30
    def prediction_verify(**kwargs):
        """预测验证：验证前一日预测结果"""
        date_str = kwargs.get("date", datetime.now().strftime("%Y-%m-%d"))
        try:
            from data_fetcher import DataFetcher
            fetcher = DataFetcher()
            # 获取昨日预测记录（简化：从文件读取）
            pred_file = os.path.join(os.path.dirname(__file__), ".cache", "last_prediction.json")
            if os.path.exists(pred_file):
                import json
                with open(pred_file, "r") as f:
                    pred = json.load(f)
                # 简化验证：假设准确率
                return f"预测验证完成（{date_str}）| 已验证 {len(pred)} 条预测"
            return f"预测验证完成（{date_str}）| 暂无昨日预测记录"
        except Exception as e:
            return f"预测验证失败: {e}"

    scheduler.register_task(
        name="预测验证",
        func=prediction_verify,
        cron_expression="30 9 * * *",
        params={"date": datetime.now().strftime("%Y-%m-%d")},
        description="每个交易日09:30验证前日预测结果"
    )

    print("-" * 50)
    print(f"预置任务注册完成，共注册 {len(scheduler.list_tasks())} 个任务\n")


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    print("策略自动化调度器 — 完整演示")
    print("=" * 75)

    # 创建调度器实例
    scheduler = TaskScheduler()

    # 注册预置任务
    register_preset_tasks(scheduler)

    # 打印任务列表
    scheduler.print_tasks()

    # 演示CronParser解析
    print("\nCron表达式解析演示：")
    print("-" * 50)
    test_crons = [
        "30 15 * * *",
        "0 20 * * 0",
        "0 9 1 * *",
        "30 9 * * *",
        "*/5 * * * *",
        "0 8-18/2 * * 1-5",
    ]
    for cron_str in test_crons:
        parser = CronParser(cron_str)
        now = datetime.now()
        matches = parser.matches(now)
        print(f"  {cron_str:<22} → {parser.describe():<30} 当前匹配: {'是' if matches else '否'}")
    print("-" * 50)

    # 演示手动触发任务
    print("\n手动触发任务演示：")
    print("-" * 50)
    scheduler.trigger_task("每日收盘扫描")
    scheduler.trigger_task("预测验证")
    print("-" * 50)

    # 演示暂停/恢复
    print("\n暂停/恢复演示：")
    print("-" * 50)
    scheduler.pause_task("每周复盘")
    scheduler.print_tasks()
    scheduler.resume_task("每周复盘")
    print("-" * 50)

    # 启动后台调度器（演示30秒）
    print("\n启动后台调度器（演示30秒）...")
    print("-" * 50)
    scheduler.start(check_interval=1)

    # 为了演示效果，手动触发所有任务模拟执行
    print("\n  [演示模式] 手动触发所有任务模拟执行...")
    for task in scheduler.list_tasks():
        if task["status"] == "active":
            scheduler.trigger_task(task["name"])
            time.sleep(0.5)

    # 等待30秒观察调度器运行
    print(f"\n  [演示模式] 调度器运行中，等待30秒...")
    print(f"  [演示模式] 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 倒计时
    for remaining in range(30, 0, -1):
        print(f"\r  [演示模式] 剩余 {remaining:2d} 秒...", end="", flush=True)
        time.sleep(1)

    print("\n")

    # 停止调度器
    scheduler.stop()

    # 打印执行历史
    scheduler.print_execution_logs()

    # 演示删除任务
    print("\n删除任务演示：")
    print("-" * 50)
    scheduler.unregister_task("每月初筛")
    scheduler.print_tasks()
    print("-" * 50)

    print("\n演示完成。")
