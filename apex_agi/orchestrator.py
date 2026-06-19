"""
ApexAGI Orchestrator Core (O)
=============================
Formula: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u,  O ∩ T = ∅

O 的职责:
1. 问题识别 — 接收用户输入/代码库状态，识别需要修复的缺陷
2. 任务批次生成 — 将大问题分解为可并行的小任务批次
3. 全局调度 — 协调 P_7 流水线和外部 Agent T 的执行顺序
4. 状态管理 — 维护整个系统的状态机

Author: ApexAGI Team
Date: 2026-06-07
"""

from __future__ import annotations

import ast
import enum
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    Union,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("apex_agi.orchestrator")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _ch = logging.StreamHandler(sys.stdout)
    _ch.setLevel(logging.DEBUG)
    _fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    _ch.setFormatter(_fmt)
    logger.addHandler(_ch)


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class OrchestratorState(enum.Enum):
    """Orchestrator 状态机状态定义."""

    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    DEPLOYING = "DEPLOYING"
    DONE = "DONE"
    FAILED = "FAILED"


class IssueSeverity(enum.Enum):
    """缺陷严重程度."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class TaskStatus(enum.Enum):
    """任务状态."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """代码缺陷描述."""

    id: str
    file_path: str
    line_number: int
    severity: IssueSeverity
    category: str
    message: str
    suggestion: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """可执行任务单元."""

    id: str
    name: str
    description: str
    target_files: List[str]
    issue_ids: List[str]
    priority: int = 0  # 数值越大优先级越高
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他 task id
    assigned_agent: Optional[str] = None
    pipeline_config: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    logs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_files": self.target_files,
            "issue_ids": self.issue_ids,
            "priority": self.priority,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "assigned_agent": self.assigned_agent,
            "pipeline_config": self.pipeline_config,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "logs": self.logs,
        }


@dataclass
class ExecutionReport:
    """单次执行周期的完整报告."""

    cycle_id: str
    state_transitions: List[Tuple[str, str, float]] = field(default_factory=list)
    issues_found: List[Issue] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    pipeline_results: List[Dict[str, Any]] = field(default_factory=list)
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    authorization_results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    final_state: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "state_transitions": self.state_transitions,
            "issues_found": [i.to_dict() for i in self.issues_found],
            "tasks": [t.to_dict() for t in self.tasks],
            "pipeline_results": self._serialize_pipeline_results(),
            "verification_results": self.verification_results,
            "authorization_results": self.authorization_results,
            "errors": self.errors,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_state": self.final_state,
        }

    def _serialize_pipeline_results(self) -> List[Dict[str, Any]]:
        """序列化 pipeline_results，处理其中的 Task 对象。"""
        serialized = []
        for result in self.pipeline_results:
            if isinstance(result, dict):
                # 深拷贝并转换 Task 对象
                import copy
                result_copy = copy.deepcopy(result)
                self._convert_tasks_in_dict(result_copy)
                serialized.append(result_copy)
            else:
                serialized.append({"raw": str(result)})
        return serialized

    def _convert_tasks_in_dict(self, obj: Any) -> None:
        """递归将 dict 中的 Task 对象转换为 dict。"""
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if hasattr(value, "to_dict"):
                    obj[key] = value.to_dict()
                elif isinstance(value, (dict, list)):
                    self._convert_tasks_in_dict(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if hasattr(item, "to_dict"):
                    obj[i] = item.to_dict()
                elif isinstance(item, (dict, list)):
                    self._convert_tasks_in_dict(item)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Protocols / Abstract Interfaces
# ---------------------------------------------------------------------------

class PipelineInterface(Protocol):
    """P_7 七阶段修复流水线的接口协议."""

    def execute(self, task_batch: List[Task], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行流水线，返回结果字典."""
        ...

    def get_stages(self) -> List[str]:
        """返回流水线阶段名称列表."""
        ...


class VerificationInterface(Protocol):
    """V_t 容器验证模块的接口协议."""

    def verify(self, artifacts: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """对产物进行容器化验证."""
        ...

    def health_check(self) -> bool:
        """验证服务健康状态."""
        ...


class AuthorizationInterface(Protocol):
    """A_u 用户授权+热切换模块的接口协议."""

    def request_approval(self, change_set: Dict[str, Any]) -> bool:
        """请求用户批准变更."""
        ...

    def deploy(self, change_set: Dict[str, Any]) -> Dict[str, Any]:
        """执行热切换部署."""
        ...


class AgentAdapter(ABC):
    """外部 Agent T 的抽象适配器."""

    @abstractmethod
    def name(self) -> str:
        """Agent 名称."""
        ...

    @abstractmethod
    def capabilities(self) -> List[str]:
        """返回该 Agent 支持的能力列表."""
        ...

    @abstractmethod
    def execute(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行给定任务，返回结果."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Agent 健康检查."""
        ...


# ---------------------------------------------------------------------------
# DAG Manager
# ---------------------------------------------------------------------------

class TaskDAG:
    """任务依赖图 (DAG) 管理器.

    负责:
    - 添加任务与依赖边
    - 拓扑排序生成执行顺序
    - 检测循环依赖
    - 按层分组以支持并行执行
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._graph: Dict[str, Set[str]] = defaultdict(set)  # task_id -> dependents
        self._in_degree: Dict[str, int] = defaultdict(int)

    def add_task(self, task: Task) -> None:
        """添加任务节点."""
        if task.id in self._tasks:
            raise ValueError(f"Task {task.id} already exists in DAG.")
        self._tasks[task.id] = task
        self._in_degree[task.id] = 0

    def add_dependency(self, from_task_id: str, to_task_id: str) -> None:
        """添加依赖边: from_task_id 必须在 to_task_id 之前完成."""
        if from_task_id not in self._tasks:
            raise KeyError(f"Source task {from_task_id} not found.")
        if to_task_id not in self._tasks:
            raise KeyError(f"Target task {to_task_id} not found.")
        if to_task_id in self._graph[from_task_id]:
            return
        self._graph[from_task_id].add(to_task_id)
        self._in_degree[to_task_id] += 1

    def topological_sort(self) -> List[str]:
        """返回拓扑排序后的任务 ID 列表."""
        in_deg = dict(self._in_degree)
        queue = deque([tid for tid, deg in in_deg.items() if deg == 0])
        order: List[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbor in self._graph[current]:
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self._tasks):
            raise ValueError("Cycle detected in task DAG.")
        return order

    def get_layers(self) -> List[List[str]]:
        """按依赖层分组，同层任务可并行执行."""
        in_deg = dict(self._in_degree)
        queue = deque([tid for tid, deg in in_deg.items() if deg == 0])
        layers: List[List[str]] = []

        while queue:
            layer = list(queue)
            layers.append(layer)
            queue.clear()
            for tid in layer:
                for neighbor in self._graph[tid]:
                    in_deg[neighbor] -= 1
                    if in_deg[neighbor] == 0:
                        queue.append(neighbor)

        total = sum(len(l) for l in layers)
        if total != len(self._tasks):
            raise ValueError("Cycle detected in task DAG.")
        return layers

    def get_ready_tasks(self, completed: Set[str]) -> List[Task]:
        """获取当前已就绪（依赖全部满足）且未完成的任务."""
        ready: List[Task] = []
        for tid, task in self._tasks.items():
            if task.status != TaskStatus.PENDING:
                continue
            deps = set(task.dependencies)
            if deps.issubset(completed):
                ready.append(task)
        # 按优先级降序排列
        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def detect_cycles(self) -> Optional[List[str]]:
        """检测循环依赖，返回循环路径或 None."""
        try:
            self.topological_sort()
            return None
        except ValueError:
            # 简单 DFS 找环
            visited: Set[str] = set()
            rec_stack: Set[str] = set()
            path: List[str] = []

            def dfs(node: str) -> Optional[List[str]]:
                visited.add(node)
                rec_stack.add(node)
                path.append(node)
                for neighbor in self._graph[node]:
                    if neighbor not in visited:
                        result = dfs(neighbor)
                        if result:
                            return result
                    elif neighbor in rec_stack:
                        cycle_start = path.index(neighbor)
                        return path[cycle_start:] + [neighbor]
                path.pop()
                rec_stack.remove(node)
                return None

            for tid in self._tasks:
                if tid not in visited:
                    result = dfs(tid)
                    if result:
                        return result
            return None

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks


# ---------------------------------------------------------------------------
# Issue Identifiers
# ---------------------------------------------------------------------------

class IssueIdentifier:
    """问题识别引擎.

    支持:
    1. 静态分析 (语法错误、未定义变量)
    2. 运行时分析 (测试失败、异常日志)
    3. 模式匹配 (已知 bug 模式)
    """

    # 已知 bug 模式正则
    KNOWN_PATTERNS: List[Tuple[str, str, IssueSeverity]] = [
        (r"except\s*:\s*pass", "bare_except", IssueSeverity.HIGH),
        (r"print\s*\(", "debug_print", IssueSeverity.LOW),
        (r"TODO|FIXME|XXX|HACK", "todo_marker", IssueSeverity.INFO),
        (r"\.format\(.*\)", "str_format", IssueSeverity.INFO),
        (r"eval\s*\(", "dangerous_eval", IssueSeverity.CRITICAL),
        (r"exec\s*\(", "dangerous_exec", IssueSeverity.CRITICAL),
    ]

    def __init__(self) -> None:
        self._issues: List[Issue] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"ISSUE-{self._counter:04d}"

    def identify(self, codebase_path: str) -> List[Issue]:
        """扫描代码库并返回所有识别到的问题."""
        self._issues = []
        path = Path(codebase_path)
        if not path.exists():
            raise FileNotFoundError(f"Codebase path not found: {codebase_path}")

        python_files = list(path.rglob("*.py"))
        logger.info(f"Scanning {len(python_files)} Python files in {codebase_path}")

        for py_file in python_files:
            self._analyze_file(py_file)

        # 运行时分析
        self._runtime_analysis(path)

        # 按严重程度排序
        severity_order = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 1,
            IssueSeverity.MEDIUM: 2,
            IssueSeverity.LOW: 3,
            IssueSeverity.INFO: 4,
        }
        self._issues.sort(key=lambda i: severity_order[i.severity])
        return self._issues

    def _analyze_file(self, file_path: Path) -> None:
        """对单个文件进行静态分析."""
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Cannot read {file_path}: {e}")
            return

        lines = source.splitlines()

        # 1. AST 语法与语义分析
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            self._issues.append(
                Issue(
                    id=self._next_id(),
                    file_path=str(file_path),
                    line_number=e.lineno or 1,
                    severity=IssueSeverity.CRITICAL,
                    category="syntax_error",
                    message=str(e),
                    suggestion="Fix syntax error before further analysis.",
                )
            )
            return

        # 收集未定义变量 (简单启发式)
        self._check_undefined_names(tree, file_path, lines)

        # 2. 模式匹配
        for line_no, line in enumerate(lines, start=1):
            for pattern, category, severity in self.KNOWN_PATTERNS:
                if re.search(pattern, line):
                    self._issues.append(
                        Issue(
                            id=self._next_id(),
                            file_path=str(file_path),
                            line_number=line_no,
                            severity=severity,
                            category=category,
                            message=f"Matched pattern: {pattern}",
                            suggestion="Review and refactor if necessary.",
                            metadata={"pattern": pattern},
                        )
                    )

    def _check_undefined_names(
        self, tree: ast.AST, file_path: Path, lines: List[str]
    ) -> None:
        """简单检查未定义变量 (启发式，不考虑导入)."""
        defined: Set[str] = set()
        used: Dict[str, int] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    defined.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    used[node.id] = getattr(node, "lineno", 1)
            elif isinstance(node, ast.FunctionDef):
                defined.add(node.name)
                for arg in node.args.args:
                    defined.add(arg.arg)
            elif isinstance(node, ast.AsyncFunctionDef):
                defined.add(node.name)
                for arg in node.args.args:
                    defined.add(arg.arg)
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined.add(alias.asname or alias.name)

        builtins = set(dir(__builtins__))
        for name, line_no in used.items():
            if name not in defined and name not in builtins and not name.startswith("_"):
                self._issues.append(
                    Issue(
                        id=self._next_id(),
                        file_path=str(file_path),
                        line_number=line_no,
                        severity=IssueSeverity.MEDIUM,
                        category="undefined_name",
                        message=f"Potentially undefined name: '{name}'",
                        suggestion="Ensure variable is defined or imported before use.",
                    )
                )

    def _runtime_analysis(self, path: Path) -> None:
        """运行时分析: 尝试运行测试并收集失败信息."""
        # 查找测试目录或测试文件
        test_dirs = [d for d in path.rglob("test*") if d.is_dir()]
        test_files = list(path.rglob("test_*.py")) + list(path.rglob("*_test.py"))

        targets: List[Path] = []
        if test_dirs:
            targets.extend(test_dirs[:1])  # 仅取第一个测试目录
        if test_files:
            targets.extend(test_files[:3])  # 最多 3 个测试文件

        for target in targets:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", str(target), "-v", "--tb=short"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    # 解析失败信息
                    for line in result.stdout.splitlines():
                        if "FAILED" in line or "ERROR" in line:
                            self._issues.append(
                                Issue(
                                    id=self._next_id(),
                                    file_path=str(target),
                                    line_number=0,
                                    severity=IssueSeverity.HIGH,
                                    category="test_failure",
                                    message=line.strip(),
                                    suggestion="Investigate and fix failing tests.",
                                )
                            )
            except Exception as e:
                logger.debug(f"Runtime analysis skipped for {target}: {e}")


# ---------------------------------------------------------------------------
# Task Batch Generator
# ---------------------------------------------------------------------------

class TaskBatchGenerator:
    """任务批次生成器.

    将问题列表按依赖关系分组为可并行执行的任务批次.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"TASK-{self._counter:04d}"

    def generate(self, issues: List[Issue]) -> Tuple[List[Task], TaskDAG]:
        """生成任务列表与依赖图."""
        dag = TaskDAG()
        tasks: List[Task] = []

        # 1. 按文件分组
        file_groups: Dict[str, List[Issue]] = defaultdict(list)
        for issue in issues:
            file_groups[issue.file_path].append(issue)

        # 2. 为每个文件创建任务
        file_task_map: Dict[str, Task] = {}
        for file_path, file_issues in file_groups.items():
            max_severity = min(
                (i.severity for i in file_issues),
                key=lambda s: {
                    IssueSeverity.CRITICAL: 0,
                    IssueSeverity.HIGH: 1,
                    IssueSeverity.MEDIUM: 2,
                    IssueSeverity.LOW: 3,
                    IssueSeverity.INFO: 4,
                }[s],
            )
            priority = {
                IssueSeverity.CRITICAL: 100,
                IssueSeverity.HIGH: 75,
                IssueSeverity.MEDIUM: 50,
                IssueSeverity.LOW: 25,
                IssueSeverity.INFO: 10,
            }[max_severity]

            task = Task(
                id=self._next_id(),
                name=f"Fix issues in {Path(file_path).name}",
                description=f"Address {len(file_issues)} issue(s) in {file_path}",
                target_files=[file_path],
                issue_ids=[i.id for i in file_issues],
                priority=priority,
                pipeline_config={"stages": ["analyze", "plan", "generate", "review"]},
            )
            dag.add_task(task)
            file_task_map[file_path] = task
            tasks.append(task)

        # 3. 检测跨文件依赖 (简单启发式: 导入关系)
        self._detect_cross_file_dependencies(file_task_map, dag)

        # 4. 验证无环
        cycle = dag.detect_cycles()
        if cycle:
            logger.warning(f"Cycle detected in task DAG: {cycle}. Breaking cycle.")
            # 简单破环: 移除最后一个依赖边
            for i in range(len(cycle) - 1):
                if cycle[i + 1] in dag._graph.get(cycle[i], set()):
                    dag._graph[cycle[i]].remove(cycle[i + 1])
                    dag._in_degree[cycle[i + 1]] -= 1
                    break

        return tasks, dag

    def _detect_cross_file_dependencies(
        self, file_task_map: Dict[str, Task], dag: TaskDAG
    ) -> None:
        """基于导入语句检测跨文件依赖."""
        for file_path, task in file_task_map.items():
            try:
                source = Path(file_path).read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod_name = alias.name.split(".")[0]
                        self._try_link_dependency(file_path, mod_name, file_task_map, dag, task)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        mod_name = node.module.split(".")[0]
                        self._try_link_dependency(file_path, mod_name, file_task_map, dag, task)

    def _try_link_dependency(
        self,
        current_file: str,
        module_name: str,
        file_task_map: Dict[str, Task],
        dag: TaskDAG,
        current_task: Task,
    ) -> None:
        """尝试建立当前文件与模块文件之间的依赖."""
        current_dir = Path(current_file).parent
        candidate = current_dir / f"{module_name}.py"
        if candidate.exists() and str(candidate) in file_task_map:
            dep_task = file_task_map[str(candidate)]
            if dep_task.id != current_task.id:
                current_task.dependencies.append(dep_task.id)
                dag.add_dependency(dep_task.id, current_task.id)


# ---------------------------------------------------------------------------
# ApexAGI Orchestrator
# ---------------------------------------------------------------------------

class ApexAGIOrchestrator:
    """ApexAGI 编排核心 O.

    公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u,  O ∩ T = ∅

    状态机:
        IDLE -> ANALYZING -> PLANNING -> EXECUTING -> VERIFYING -> DEPLOYING -> DONE
                                                    |
                                                    v
                                                  FAILED
    """

    def __init__(self) -> None:
        self._state = OrchestratorState.IDLE
        self._tasks: List[Task] = []
        self._dag = TaskDAG()
        self._agents: Dict[str, AgentAdapter] = {}
        self._results: List[Dict[str, Any]] = []
        self._history: List[ExecutionReport] = []
        self._current_report: Optional[ExecutionReport] = None
        self._lock = False  # 简单状态锁

        # 集成接口占位
        self._pipeline: Optional[PipelineInterface] = None
        self._verifier: Optional[VerificationInterface] = None
        self._authorizer: Optional[AuthorizationInterface] = None

        logger.info("ApexAGIOrchestrator initialized.")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> OrchestratorState:
        return self._state

    @property
    def tasks(self) -> List[Task]:
        return list(self._tasks)

    @property
    def agents(self) -> Dict[str, AgentAdapter]:
        return dict(self._agents)

    @property
    def results(self) -> List[Dict[str, Any]]:
        return list(self._results)

    @property
    def history(self) -> List[ExecutionReport]:
        return list(self._history)

    # ------------------------------------------------------------------
    # State Machine
    # ------------------------------------------------------------------

    def _transition(self, new_state: OrchestratorState) -> None:
        """执行状态转换并记录."""
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        ts = time.time()
        if self._current_report:
            self._current_report.state_transitions.append((old.value, new_state.value, ts))
        logger.info(f"State transition: {old.value} -> {new_state.value}")

    def _assert_state(self, expected: OrchestratorState) -> None:
        if self._state != expected:
            raise RuntimeError(
                f"Expected state {expected.value}, but current state is {self._state.value}"
            )

    # ------------------------------------------------------------------
    # Issue Identification
    # ------------------------------------------------------------------

    def identify_issues(self, codebase_path: str) -> List[Issue]:
        """问题识别: 扫描代码库找出缺陷.

        Args:
            codebase_path: 代码库根目录路径.

        Returns:
            识别到的 Issue 列表.
        """
        self._assert_state(OrchestratorState.ANALYZING)
        logger.info(f"Starting issue identification for: {codebase_path}")

        identifier = IssueIdentifier()
        issues = identifier.identify(codebase_path)

        if self._current_report:
            self._current_report.issues_found = issues

        logger.info(f"Identified {len(issues)} issue(s).")
        return issues

    # ------------------------------------------------------------------
    # Task Batch Generation
    # ------------------------------------------------------------------

    def generate_task_batches(self, issues: List[Issue]) -> Tuple[List[Task], TaskDAG]:
        """任务批次生成: 按依赖关系分组.

        Args:
            issues: 识别到的问题列表.

        Returns:
            (任务列表, 任务依赖图 DAG)
        """
        self._assert_state(OrchestratorState.PLANNING)
        logger.info(f"Generating task batches for {len(issues)} issue(s).")

        generator = TaskBatchGenerator()
        tasks, dag = generator.generate(issues)

        self._tasks = tasks
        self._dag = dag

        if self._current_report:
            self._current_report.tasks = tasks

        layers = dag.get_layers()
        logger.info(
            f"Generated {len(tasks)} task(s) in {len(layers)} layer(s)."
        )
        return tasks, dag

    # ------------------------------------------------------------------
    # Global Dispatch
    # ------------------------------------------------------------------

    def dispatch_to_pipeline(
        self, task_batch: List[Task], pipeline: PipelineInterface
    ) -> Dict[str, Any]:
        """全局调度: 将任务分发给 P_7 流水线.

        Args:
            task_batch: 当前批次任务.
            pipeline: P_7 流水线实例.

        Returns:
            流水线执行结果.
        """
        self._assert_state(OrchestratorState.EXECUTING)
        logger.info(f"Dispatching {len(task_batch)} task(s) to P_7 pipeline.")

        context = {
            "orchestrator_state": self._state.value,
            "task_count": len(task_batch),
            "agents_available": list(self._agents.keys()),
        }

        for task in task_batch:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

        try:
            result = pipeline.execute(task_batch, context)
        except Exception as e:
            logger.exception("Pipeline execution failed.")
            result = {"status": "failed", "error": str(e), "tasks": []}
            for task in task_batch:
                task.status = TaskStatus.FAILED
                task.finished_at = time.time()
                task.logs.append(str(e))
            return result

        # 更新任务状态
        for task in task_batch:
            task.finished_at = time.time()
            if result.get("status") == "success":
                task.status = TaskStatus.SUCCESS
            else:
                task.status = TaskStatus.FAILED
            task.result = result.get("task_results", {}).get(task.id, {})

        self._results.append(result)
        if self._current_report:
            self._current_report.pipeline_results.append(result)

        logger.info(f"Pipeline execution completed with status: {result.get('status')}")
        return result

    # ------------------------------------------------------------------
    # Agent Registration
    # ------------------------------------------------------------------

    def register_agent(self, name: str, agent_adapter: AgentAdapter) -> None:
        """注册外部 Agent.

        Args:
            name: Agent 唯一标识名.
            agent_adapter: Agent 适配器实例.
        """
        if name in self._agents:
            logger.warning(f"Agent '{name}' already registered. Overwriting.")
        self._agents[name] = agent_adapter
        logger.info(f"Agent '{name}' registered with capabilities: {agent_adapter.capabilities()}")

    def unregister_agent(self, name: str) -> None:
        """注销外部 Agent."""
        if name in self._agents:
            del self._agents[name]
            logger.info(f"Agent '{name}' unregistered.")

    def dispatch_to_agent(self, task: Task, agent_name: str) -> Dict[str, Any]:
        """将单个任务分发给指定外部 Agent.

        Args:
            task: 待执行任务.
            agent_name: 已注册的 Agent 名称.

        Returns:
            Agent 执行结果.
        """
        if agent_name not in self._agents:
            raise KeyError(f"Agent '{agent_name}' not registered.")

        agent = self._agents[agent_name]
        if not agent.health_check():
            raise RuntimeError(f"Agent '{agent_name}' health check failed.")

        task.assigned_agent = agent_name
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        context = {
            "orchestrator_state": self._state.value,
            "available_agents": list(self._agents.keys()),
        }

        try:
            result = agent.execute(task, context)
            task.status = TaskStatus.SUCCESS
        except Exception as e:
            logger.exception(f"Agent '{agent_name}' execution failed.")
            task.status = TaskStatus.FAILED
            result = {"status": "failed", "error": str(e)}
            task.logs.append(traceback.format_exc())

        task.finished_at = time.time()
        task.result = result
        return result

    # ------------------------------------------------------------------
    # Integration Interfaces
    # ------------------------------------------------------------------

    def set_pipeline(self, pipeline: PipelineInterface) -> None:
        """设置 P_7 流水线集成接口."""
        self._pipeline = pipeline
        logger.info("P_7 pipeline interface registered.")

    def set_verifier(self, verifier: VerificationInterface) -> None:
        """设置 V_t 验证模块集成接口."""
        self._verifier = verifier
        logger.info("V_t verifier interface registered.")

    def set_authorizer(self, authorizer: AuthorizationInterface) -> None:
        """设置 A_u 授权模块集成接口."""
        self._authorizer = authorizer
        logger.info("A_u authorizer interface registered.")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_artifacts(self, artifacts: List[str]) -> Dict[str, Any]:
        """调用 V_t 对产物进行容器化验证.

        Args:
            artifacts: 待验证产物路径列表.

        Returns:
            验证结果.
        """
        self._assert_state(OrchestratorState.VERIFYING)
        if self._verifier is None:
            logger.warning("V_t verifier not set. Skipping verification.")
            return {"status": "skipped", "message": "Verifier not configured."}

        if not self._verifier.health_check():
            raise RuntimeError("V_t verifier health check failed.")

        context = {
            "orchestrator_state": self._state.value,
            "task_count": len(self._tasks),
        }

        logger.info(f"Starting verification for {len(artifacts)} artifact(s).")
        result = self._verifier.verify(artifacts, context)

        if self._current_report:
            self._current_report.verification_results.append(result)

        logger.info(f"Verification completed with status: {result.get('status')}")
        return result

    # ------------------------------------------------------------------
    # Authorization & Deployment
    # ------------------------------------------------------------------

    def request_authorization(self, change_set: Dict[str, Any]) -> bool:
        """调用 A_u 请求用户授权.

        Args:
            change_set: 变更集描述.

        Returns:
            是否获得授权.
        """
        self._assert_state(OrchestratorState.DEPLOYING)
        if self._authorizer is None:
            logger.warning("A_u authorizer not set. Auto-approving.")
            return True

        logger.info("Requesting user authorization for deployment.")
        approved = self._authorizer.request_approval(change_set)

        if self._current_report:
            self._current_report.authorization_results.append(
                {"approved": approved, "change_set": change_set}
            )

        logger.info(f"Authorization result: {'approved' if approved else 'denied'}")
        return approved

    def deploy_changes(self, change_set: Dict[str, Any]) -> Dict[str, Any]:
        """调用 A_u 执行热切换部署.

        Args:
            change_set: 变更集描述.

        Returns:
            部署结果.
        """
        self._assert_state(OrchestratorState.DEPLOYING)
        if self._authorizer is None:
            logger.warning("A_u authorizer not set. Skipping deployment.")
            return {"status": "skipped", "message": "Authorizer not configured."}

        logger.info("Deploying changes via A_u.")
        result = self._authorizer.deploy(change_set)

        if self._current_report:
            self._current_report.authorization_results.append(
                {"deployed": True, "result": result}
            )

        logger.info(f"Deployment completed with status: {result.get('status')}")
        return result

    # ------------------------------------------------------------------
    # Full Execution Cycle
    # ------------------------------------------------------------------

    def run_cycle(self, codebase_path: str) -> ExecutionReport:
        """完整执行周期.

        流程:
            O: 问题识别
            P_7: 七阶段修复
            T: 外部 Agent 编码
            V_t: 容器验证
            A_u: 用户授权+热切换

        Args:
            codebase_path: 代码库根目录路径.

        Returns:
            本次执行周期的完整报告.
        """
        if self._lock:
            raise RuntimeError("Another cycle is already running.")
        self._lock = True

        cycle_id = f"CYCLE-{int(time.time())}"
        report = ExecutionReport(cycle_id=cycle_id)
        self._current_report = report
        self._results = []

        try:
            # ---- O: 问题识别 ----
            self._transition(OrchestratorState.ANALYZING)
            issues = self.identify_issues(codebase_path)

            if not issues:
                logger.info("No issues found. Cycle complete.")
                self._transition(OrchestratorState.DONE)
                report.final_state = self._state.value
                report.finished_at = time.time()
                self._history.append(report)
                return report

            # ---- O: 任务批次生成 ----
            self._transition(OrchestratorState.PLANNING)
            tasks, dag = self.generate_task_batches(issues)

            # ---- O: 全局调度 -> P_7 / T ----
            self._transition(OrchestratorState.EXECUTING)

            completed_tasks: Set[str] = set()
            all_artifacts: List[str] = []

            while len(completed_tasks) < len(tasks):
                ready = dag.get_ready_tasks(completed_tasks)
                if not ready:
                    break

                # 优先尝试使用 P_7 流水线处理批次
                if self._pipeline is not None:
                    batch_result = self.dispatch_to_pipeline(ready, self._pipeline)
                    artifacts = batch_result.get("artifacts", [])
                    all_artifacts.extend(artifacts)
                else:
                    # 回退到外部 Agent
                    for task in ready:
                        agent_name = self._select_agent_for_task(task)
                        if agent_name:
                            self.dispatch_to_agent(task, agent_name)
                        else:
                            task.status = TaskStatus.SKIPPED
                            task.finished_at = time.time()
                            task.logs.append("No suitable agent found.")

                for task in ready:
                    if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.SKIPPED):
                        completed_tasks.add(task.id)

            # 检查是否有失败任务
            failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
            if failed_tasks:
                logger.error(f"{len(failed_tasks)} task(s) failed.")
                report.errors.append(f"{len(failed_tasks)} task(s) failed.")

            # ---- V_t: 容器验证 ----
            self._transition(OrchestratorState.VERIFYING)
            if all_artifacts:
                self.verify_artifacts(all_artifacts)
            else:
                logger.info("No artifacts to verify.")

            # ---- A_u: 用户授权+热切换 ----
            self._transition(OrchestratorState.DEPLOYING)
            change_set = {
                "cycle_id": cycle_id,
                "tasks": [t.to_dict() for t in tasks],
                "artifacts": all_artifacts,
            }
            approved = self.request_authorization(change_set)
            if approved:
                self.deploy_changes(change_set)
                self._transition(OrchestratorState.DONE)
            else:
                logger.info("Deployment not authorized.")
                self._transition(OrchestratorState.DONE)

        except Exception as e:
            logger.exception("Execution cycle failed.")
            report.errors.append(str(e))
            report.errors.append(traceback.format_exc())
            self._transition(OrchestratorState.FAILED)

        finally:
            report.final_state = self._state.value
            report.finished_at = time.time()
            self._history.append(report)
            self._lock = False
            logger.info(f"Cycle {cycle_id} finished with state: {self._state.value}")

        return report

    def _select_agent_for_task(self, task: Task) -> Optional[str]:
        """为任务选择最合适的外部 Agent."""
        candidates = []
        for name, agent in self._agents.items():
            if not agent.health_check():
                continue
            # 简单匹配: 检查 capabilities 是否包含任务描述关键词
            caps = " ".join(agent.capabilities()).lower()
            desc = task.description.lower()
            score = sum(1 for word in desc.split() if word in caps)
            candidates.append((name, score))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self, report: Optional[ExecutionReport] = None) -> str:
        """生成人类可读的执行报告.

        Args:
            report: 指定报告，默认为最近一次.

        Returns:
            格式化报告字符串.
        """
        if report is None:
            if not self._history:
                return "No execution history available."
            report = self._history[-1]

        lines: List[str] = []
        lines.append("=" * 60)
        lines.append(f"ApexAGI Execution Report: {report.cycle_id}")
        lines.append("=" * 60)
        lines.append(f"Final State : {report.final_state}")
        lines.append(f"Started At  : {time.ctime(report.started_at)}")
        if report.finished_at:
            duration = report.finished_at - report.started_at
            lines.append(f"Finished At : {time.ctime(report.finished_at)}")
            lines.append(f"Duration    : {duration:.2f}s")
        lines.append("")

        lines.append("State Transitions:")
        for old, new, ts in report.state_transitions:
            lines.append(f"  {old} -> {new}  ({time.ctime(ts)})")
        lines.append("")

        lines.append(f"Issues Found: {len(report.issues_found)}")
        for issue in report.issues_found:
            lines.append(
                f"  [{issue.severity.value}] {issue.file_path}:{issue.line_number} "
                f"{issue.message}"
            )
        lines.append("")

        lines.append(f"Tasks: {len(report.tasks)}")
        for task in report.tasks:
            lines.append(
                f"  {task.id} | {task.status.value} | P{task.priority} | {task.name}"
            )
        lines.append("")

        if report.errors:
            lines.append("Errors:")
            for err in report.errors:
                lines.append(f"  - {err}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def save_report(self, path: str, report: Optional[ExecutionReport] = None) -> None:
        """将报告保存为 JSON 文件.

        Args:
            path: 输出文件路径.
            report: 指定报告，默认为最近一次.
        """
        if report is None:
            if not self._history:
                raise ValueError("No execution history to save.")
            report = self._history[-1]

        out_path = Path(path)
        out_path.write_text(report.to_json(), encoding="utf-8")
        logger.info(f"Report saved to {out_path}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置 Orchestrator 到初始状态."""
        self._state = OrchestratorState.IDLE
        self._tasks = []
        self._dag = TaskDAG()
        self._results = []
        self._current_report = None
        self._lock = False
        logger.info("Orchestrator reset to IDLE.")

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """按 ID 查找任务."""
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取 Orchestrator 运行统计信息."""
        total_cycles = len(self._history)
        total_tasks = sum(len(r.tasks) for r in self._history)
        total_issues = sum(len(r.issues_found) for r in self._history)
        success_cycles = sum(1 for r in self._history if r.final_state == OrchestratorState.DONE.value)

        return {
            "total_cycles": total_cycles,
            "success_cycles": success_cycles,
            "failed_cycles": total_cycles - success_cycles,
            "total_tasks": total_tasks,
            "total_issues_found": total_issues,
            "registered_agents": list(self._agents.keys()),
            "current_state": self._state.value,
        }
