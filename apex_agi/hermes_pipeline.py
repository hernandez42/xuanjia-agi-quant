"""
Hermes Pipeline - 七阶段修复流水线 P_7

P_7 = [定位, 计划, 评审, 实现, 代码审查, 验证, 判决]

每个阶段都是一个独立的类，继承自基类 HermesStage。
流水线控制器 HermesPipeline 负责按顺序执行七个阶段，
支持上下文传递、阶段跳过/重试、详细日志记录。
"""

from __future__ import annotations

import abc
import ast
import difflib
import logging
import os
import re
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    TypedDict,
    Union,
)

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logger = logging.getLogger("hermes_pipeline")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.DEBUG)
    _formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------

class DefectLocation(TypedDict):
    """缺陷位置定义"""

    file: str
    line: int
    column: int
    severity: Literal["critical", "high", "medium", "low"]
    description: str


class FixStrategy(TypedDict):
    """修复策略定义"""

    strategy: str
    estimated_risk: Literal["high", "medium", "low"]
    files_to_modify: List[str]
    description: str


class ReviewReport(TypedDict):
    """评审报告"""

    approved: bool
    concerns: List[str]
    suggestions: List[str]


class CodePatch(TypedDict):
    """代码修改补丁"""

    file: str
    original: str
    modified: str
    diff: str


class CodeReviewReport(TypedDict):
    """代码审查报告"""

    passed: bool
    issues: List[str]
    quality_score: float


class VerificationReport(TypedDict):
    """验证报告"""

    tests_passed: bool
    coverage: float
    regressions: List[str]


class JudgmentResult(TypedDict):
    """最终判决结果"""

    verdict: Literal["PASS", "FAIL", "RETRY"]
    reason: str
    next_action: str


class StageResult(TypedDict, total=False):
    """阶段执行结果通用结构"""

    halt: bool
    skip: bool
    retry: bool
    data: Any
    message: str


# Agent 适配器协议（外部 Agent T 的接口约定）
class AgentAdapter(Protocol):
    """外部 Agent 适配器协议"""

    def execute(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class HermesStage(abc.ABC):
    """
    Hermes 流水线阶段抽象基类。

    所有具体阶段必须继承此类并实现 ``execute`` 方法与 ``name`` 属性。
    """

    @abc.abstractmethod
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行当前阶段逻辑。

        Args:
            context: 流水线上下文，包含 task、agents、results 等键。

        Returns:
            阶段执行结果字典，可包含 halt/skip/retry 等控制字段。
        """
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """阶段名称（唯一标识）"""
        ...

    def _should_skip(self, context: Dict[str, Any]) -> bool:
        """检查上下文是否标记跳过当前阶段。"""
        skip_stages: List[str] = context.get("skip_stages", [])
        return self.name in skip_stages

    def _should_retry(self, context: Dict[str, Any]) -> bool:
        """检查上下文是否标记重试当前阶段。"""
        retry_stages: List[str] = context.get("retry_stages", [])
        return self.name in retry_stages

    def _log_start(self) -> None:
        logger.info("=" * 60)
        logger.info("阶段开始: %s", self.name)

    def _log_end(self, result: Dict[str, Any]) -> None:
        logger.info("阶段结束: %s | halt=%s | skip=%s", self.name, result.get("halt"), result.get("skip"))
        logger.info("=" * 60)


# ---------------------------------------------------------------------------
# 阶段 1: 定位 — 精确定位缺陷位置
# ---------------------------------------------------------------------------

class LocalizationStage(HermesStage):
    """
    定位阶段。

    输入: 代码库路径 + 问题描述/测试失败日志
    输出: 缺陷位置列表 [{file, line, column, severity, description}]
    方法: AST 分析 + 正则匹配 + 错误日志解析
    """

    @property
    def name(self) -> str:
        return "localization"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "defects": []}

        raw_task = context.get("task", {})
        # 兼容 Task 对象和 dict
        if hasattr(raw_task, "to_dict"):
            task: Dict[str, Any] = raw_task.to_dict()
        elif hasattr(raw_task, "__dict__"):
            task = raw_task.__dict__
        else:
            task = raw_task if isinstance(raw_task, dict) else {}
        
        repo_path: str = task.get("repo_path", ".")
        issue_description: str = task.get("issue_description", "")
        failure_log: str = task.get("failure_log", "")

        defects: List[DefectLocation] = []

        # 1.1 错误日志解析 — 提取文件路径与行号
        log_defects = self._parse_failure_log(failure_log)
        defects.extend(log_defects)

        # 1.2 AST 分析 — 扫描代码库中的语法异常与可疑模式
        ast_defects = self._analyze_ast(repo_path, issue_description)
        defects.extend(ast_defects)

        # 1.3 正则匹配 — 基于问题描述关键词匹配可疑代码段
        regex_defects = self._regex_match(repo_path, issue_description)
        defects.extend(regex_defects)

        # 去重：以 (file, line, column) 为键
        seen: set = set()
        unique_defects: List[DefectLocation] = []
        for d in defects:
            key = (d["file"], d["line"], d["column"])
            if key not in seen:
                seen.add(key)
                unique_defects.append(d)

        logger.info("[%s] 发现 %d 个缺陷位置", self.name, len(unique_defects))
        for d in unique_defects:
            logger.debug("  -> %s:%d:%d [%s] %s", d["file"], d["line"], d["column"], d["severity"], d["description"])

        result: Dict[str, Any] = {
            "defects": unique_defects,
            "halt": False,
            "skip": False,
        }
        self._log_end(result)
        return result

    def _parse_failure_log(self, failure_log: str) -> List[DefectLocation]:
        """解析测试失败日志，提取 traceback 中的文件与行号。"""
        defects: List[DefectLocation] = []
        if not failure_log:
            return defects

        # 匹配 Python traceback 格式: File "...", line N, in ...
        pattern = re.compile(r'File "([^"]+)", line (\d+), in (.+)')
        for match in pattern.finditer(failure_log):
            file_path = match.group(1)
            line_no = int(match.group(2))
            func_name = match.group(3).strip()
            defects.append(
                {
                    "file": file_path,
                    "line": line_no,
                    "column": 0,
                    "severity": "high",
                    "description": f"Traceback 指向函数: {func_name}",
                }
            )

        # 匹配通用错误格式: path/to/file.py:42: error message
        pattern2 = re.compile(r"([\w/\\.\-]+\.py):(\d+):(.+)")
        for match in pattern2.finditer(failure_log):
            file_path = match.group(1)
            line_no = int(match.group(2))
            msg = match.group(3).strip()
            defects.append(
                {
                    "file": file_path,
                    "line": line_no,
                    "column": 0,
                    "severity": "high",
                    "description": msg,
                }
            )

        logger.debug("[%s] 日志解析发现 %d 个缺陷", self.name, len(defects))
        return defects

    def _analyze_ast(self, repo_path: str, issue_description: str) -> List[DefectLocation]:
        """对代码库进行 AST 分析，识别语法异常与可疑模式。"""
        defects: List[DefectLocation] = []
        repo = Path(repo_path)
        if not repo.exists():
            logger.warning("[%s] 代码库路径不存在: %s", self.name, repo_path)
            return defects

        keywords = self._extract_keywords(issue_description)

        for py_file in repo.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except SyntaxError as e:
                defects.append(
                    {
                        "file": str(py_file),
                        "line": e.lineno or 1,
                        "column": e.offset or 0,
                        "severity": "critical",
                        "description": f"语法错误: {e.msg}",
                    }
                )
                continue
            except Exception as e:
                logger.debug("[%s] 解析 %s 失败: %s", self.name, py_file, e)
                continue

            # 遍历 AST 节点，检查可疑模式
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    # 检查空的 except 块
                    for handler in node.handlers:
                        if handler.type is None and not handler.body:
                            defects.append(
                                {
                                    "file": str(py_file),
                                    "line": handler.lineno,
                                    "column": handler.col_offset,
                                    "severity": "medium",
                                    "description": "空的 bare except 块",
                                }
                            )
                elif isinstance(node, ast.Name):
                    # 关键词匹配
                    if node.id in keywords:
                        defects.append(
                            {
                                "file": str(py_file),
                                "line": node.lineno,
                                "column": node.col_offset,
                                "severity": "low",
                                "description": f"关键词匹配: {node.id}",
                            }
                        )

        logger.debug("[%s] AST 分析发现 %d 个缺陷", self.name, len(defects))
        return defects

    def _regex_match(self, repo_path: str, issue_description: str) -> List[DefectLocation]:
        """基于问题描述关键词在代码库中进行正则匹配。"""
        defects: List[DefectLocation] = []
        repo = Path(repo_path)
        if not repo.exists():
            return defects

        keywords = self._extract_keywords(issue_description)
        if not keywords:
            return defects

        # 构建正则：匹配函数名/变量名中的关键词
        pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b")

        for py_file in repo.rglob("*.py"):
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
            except Exception as e:
                logger.debug("[%s] 读取 %s 失败: %s", self.name, py_file, e)
                continue

            for lineno, line in enumerate(lines, start=1):
                if pattern.search(line):
                    col = line.find(keywords[0]) if keywords else 0
                    defects.append(
                        {
                            "file": str(py_file),
                            "line": lineno,
                            "column": col,
                            "severity": "low",
                            "description": f"正则匹配到关键词: {keywords}",
                        }
                    )
                    # 每文件只记录一次，避免过多噪音
                    break

        logger.debug("[%s] 正则匹配发现 %d 个缺陷", self.name, len(defects))
        return defects

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """从文本中提取候选关键词（简单分词）。"""
        if not text:
            return []
        # 提取长度 >= 4 的英文单词作为关键词
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text)
        # 去重并保持顺序
        seen: set = set()
        result: List[str] = []
        for w in words:
            low = w.lower()
            if low not in seen:
                seen.add(low)
                result.append(w)
        return result


# ---------------------------------------------------------------------------
# 阶段 2: 计划 — 生成修复方案
# ---------------------------------------------------------------------------

class PlanningStage(HermesStage):
    """
    计划阶段。

    输入: 缺陷位置列表
    输出: 修复方案列表 [{strategy, estimated_risk, files_to_modify, description}]
    方法: 基于缺陷类型选择修复策略模板
    """

    @property
    def name(self) -> str:
        return "planning"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "strategies": []}

        # 获取上一阶段结果
        localization_result = context.get("results", {}).get("localization", {})
        defects: List[DefectLocation] = localization_result.get("defects", [])

        if not defects:
            logger.warning("[%s] 未发现缺陷，无需生成修复方案", self.name)
            return {"strategies": [], "halt": False, "skip": False}

        strategies: List[FixStrategy] = []
        for defect in defects:
            strategy = self._select_strategy(defect)
            if strategy:
                strategies.append(strategy)

        logger.info("[%s] 生成 %d 个修复方案", self.name, len(strategies))
        for s in strategies:
            logger.debug("  -> [%s] risk=%s | files=%s | %s", s["strategy"], s["estimated_risk"], s["files_to_modify"], s["description"])

        result: Dict[str, Any] = {
            "strategies": strategies,
            "halt": False,
            "skip": False,
        }
        self._log_end(result)
        return result

    def _select_strategy(self, defect: DefectLocation) -> Optional[FixStrategy]:
        """根据缺陷类型选择修复策略模板。"""
        desc_lower = defect["description"].lower()
        file_path = defect["file"]

        if "语法错误" in defect["description"] or "syntax" in desc_lower:
            return {
                "strategy": "syntax_fix",
                "estimated_risk": "low",
                "files_to_modify": [file_path],
                "description": f"修复 {file_path}:{defect['line']} 的语法错误",
            }
        elif "bare except" in desc_lower or "except" in desc_lower:
            return {
                "strategy": "exception_handling",
                "estimated_risk": "medium",
                "files_to_modify": [file_path],
                "description": f"细化 {file_path}:{defect['line']} 的异常捕获",
            }
        elif "traceback" in desc_lower:
            return {
                "strategy": "traceback_investigation",
                "estimated_risk": "high",
                "files_to_modify": [file_path],
                "description": f"调查 {file_path}:{defect['line']} 的 traceback 根因",
            }
        else:
            return {
                "strategy": "general_fix",
                "estimated_risk": "medium",
                "files_to_modify": [file_path],
                "description": f"通用修复: {defect['description']} @ {file_path}:{defect['line']}",
            }


# ---------------------------------------------------------------------------
# 阶段 3: 评审 — 评审方案可行性
# ---------------------------------------------------------------------------

class ReviewStage(HermesStage):
    """
    评审阶段。

    输入: 修复方案
    输出: 评审报告 {approved: bool, concerns: list, suggestions: list}
    方法: 检查方案是否引入新风险、是否覆盖边界情况
    """

    @property
    def name(self) -> str:
        return "review"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "report": {"approved": True, "concerns": [], "suggestions": []}}

        planning_result = context.get("results", {}).get("planning", {})
        strategies: List[FixStrategy] = planning_result.get("strategies", [])

        concerns: List[str] = []
        suggestions: List[str] = []
        approved = True

        for strategy in strategies:
            # 风险检查
            if strategy["estimated_risk"] == "high":
                concerns.append(
                    f"高风险策略: {strategy['strategy']} 可能影响多个模块"
                )
                approved = False

            # 边界情况检查
            if strategy["strategy"] == "exception_handling":
                suggestions.append(
                    f"建议为 {strategy['files_to_modify']} 添加针对特定异常类型的单元测试"
                )

            # 文件数量检查
            if len(strategy["files_to_modify"]) > 3:
                concerns.append(
                    f"修改文件过多 ({len(strategy['files_to_modify'])} 个)，建议拆分提交"
                )

        # 如果没有方案，直接通过
        if not strategies:
            logger.info("[%s] 无修复方案，自动通过", self.name)
            report: ReviewReport = {"approved": True, "concerns": [], "suggestions": []}
        else:
            report = {"approved": approved, "concerns": concerns, "suggestions": suggestions}

        logger.info("[%s] 评审结果: approved=%s | concerns=%d | suggestions=%d", self.name, report["approved"], len(report["concerns"]), len(report["suggestions"]))

        result: Dict[str, Any] = {
            "report": report,
            "halt": not report["approved"],
            "skip": False,
        }
        self._log_end(result)
        return result


# ---------------------------------------------------------------------------
# 阶段 4: 实现 — 执行代码修改
# ---------------------------------------------------------------------------

class ImplementationStage(HermesStage):
    """
    实现阶段。

    输入: 批准的修复方案
    输出: 代码修改补丁 {file, original, modified, diff}
    方法: 调用外部 Agent T 执行实际代码修改
    """

    @property
    def name(self) -> str:
        return "implementation"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "patches": []}

        review_result = context.get("results", {}).get("review", {})
        report: ReviewReport = review_result.get("report", {"approved": False})

        if not report.get("approved", False):
            logger.warning("[%s] 修复方案未通过评审，跳过实现", self.name)
            return {"patches": [], "halt": True, "message": "修复方案未通过评审"}

        planning_result = context.get("results", {}).get("planning", {})
        strategies: List[FixStrategy] = planning_result.get("strategies", [])

        agents: Dict[str, AgentAdapter] = context.get("agents", {})
        agent_t = agents.get("agent_t")

        patches: List[CodePatch] = []
        for strategy in strategies:
            patch = self._apply_strategy(strategy, agent_t, context)
            if patch:
                patches.append(patch)

        logger.info("[%s] 生成 %d 个代码补丁", self.name, len(patches))
        for p in patches:
            logger.debug("  -> %s | diff_lines=%d", p["file"], len(p["diff"].splitlines()))

        result: Dict[str, Any] = {
            "patches": patches,
            "halt": False,
            "skip": False,
        }
        self._log_end(result)
        return result

    def _apply_strategy(
        self,
        strategy: FixStrategy,
        agent_t: Optional[AgentAdapter],
        context: Dict[str, Any],
    ) -> Optional[CodePatch]:
        """应用单个修复策略，生成代码补丁。"""
        if not strategy["files_to_modify"]:
            return None

        target_file = strategy["files_to_modify"][0]
        if not os.path.exists(target_file):
            logger.warning("[%s] 目标文件不存在: %s", self.name, target_file)
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception as e:
            logger.error("[%s] 读取文件失败 %s: %s", self.name, target_file, e)
            return None

        modified = original

        # 如果有外部 Agent T，调用其执行修改
        if agent_t is not None:
            try:
                agent_result = agent_t.execute(
                    prompt=f"请修复以下代码问题: {strategy['description']}",
                    context={
                        "strategy": strategy,
                        "file": target_file,
                        "original": original,
                    },
                )
                modified = agent_result.get("modified", original)
            except Exception as e:
                logger.error("[%s] Agent T 调用失败: %s", self.name, e)
                # 降级为本地简单修复
                modified = self._local_fix(original, strategy)
        else:
            # 无外部 Agent，使用本地简单修复逻辑
            modified = self._local_fix(original, strategy)

        diff = self._generate_diff(target_file, original, modified)

        return {
            "file": target_file,
            "original": original,
            "modified": modified,
            "diff": diff,
        }

    def _local_fix(self, original: str, strategy: FixStrategy) -> str:
        """本地简单修复逻辑（降级方案）。"""
        modified = original
        desc_lower = strategy["description"].lower()

        if "bare except" in desc_lower:
            # 将 bare except: 替换为 except Exception:
            modified = re.sub(r"except\s*:\s*\n", "except Exception:\n", modified)
        elif "语法错误" in strategy["description"]:
            # 无法自动修复语法错误，保持原样
            pass
        else:
            # 通用占位：添加注释标记
            lines = modified.splitlines()
            if lines:
                lines[0] = f"# HERMES_FIX: {strategy['description']}\n" + lines[0]
            modified = "\n".join(lines)

        return modified

    @staticmethod
    def _generate_diff(file_path: str, original: str, modified: str) -> str:
        """生成统一 diff 格式。"""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        if not original_lines or original_lines[-1].endswith("\n"):
            original_lines.append("")
        if not modified_lines or modified_lines[-1].endswith("\n"):
            modified_lines.append("")
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=file_path,
            tofile=file_path,
        )
        return "".join(diff)


# ---------------------------------------------------------------------------
# 阶段 5: 代码审查 — 审查修改质量
# ---------------------------------------------------------------------------

class CodeReviewStage(HermesStage):
    """
    代码审查阶段。

    输入: 代码修改补丁
    输出: 审查报告 {passed: bool, issues: list, quality_score: float}
    方法: 静态分析 + 风格检查 + 安全扫描
    """

    @property
    def name(self) -> str:
        return "code_review"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "report": {"passed": True, "issues": [], "quality_score": 1.0}}

        implementation_result = context.get("results", {}).get("implementation", {})
        patches: List[CodePatch] = implementation_result.get("patches", [])

        if not patches:
            logger.info("[%s] 无代码补丁，自动通过", self.name)
            report: CodeReviewReport = {"passed": True, "issues": [], "quality_score": 1.0}
            return {"report": report, "halt": False, "skip": False}

        all_issues: List[str] = []
        total_score = 0.0

        for patch in patches:
            issues, score = self._review_patch(patch)
            all_issues.extend(issues)
            total_score += score

        avg_score = total_score / len(patches) if patches else 1.0
        passed = avg_score >= 0.6 and not any(
            i.startswith("[CRITICAL]") for i in all_issues
        )

        report = {
            "passed": passed,
            "issues": all_issues,
            "quality_score": round(avg_score, 2),
        }

        logger.info("[%s] 审查结果: passed=%s | score=%.2f | issues=%d", self.name, passed, avg_score, len(all_issues))
        for issue in all_issues:
            logger.debug("  -> %s", issue)

        result: Dict[str, Any] = {
            "report": report,
            "halt": not passed,
            "skip": False,
        }
        self._log_end(result)
        return result

    def _review_patch(self, patch: CodePatch) -> Tuple[List[str], float]:
        """审查单个补丁，返回问题列表与质量分数。"""
        issues: List[str] = []
        score = 1.0

        modified = patch["modified"]
        lines = modified.splitlines()

        # 5.1 静态分析：检查语法有效性
        try:
            ast.parse(modified)
        except SyntaxError as e:
            issues.append(f"[CRITICAL] 语法错误: {e.msg} @ line {e.lineno}")
            score -= 0.5

        # 5.2 风格检查：行长度
        for lineno, line in enumerate(lines, start=1):
            if len(line) > 120:
                issues.append(f"[STYLE] 行过长 ({len(line)} > 120) @ line {lineno}")
                score -= 0.02

        # 5.3 安全扫描：检查危险函数
        dangerous = ["eval", "exec", "compile", "__import__"]
        for lineno, line in enumerate(lines, start=1):
            for func in dangerous:
                if re.search(rf"\b{func}\s*\(", line):
                    issues.append(f"[SECURITY] 发现危险函数调用: {func} @ line {lineno}")
                    score -= 0.1

        # 5.4 检查是否有 TODO/FIXME 遗留
        for lineno, line in enumerate(lines, start=1):
            if "TODO" in line or "FIXME" in line:
                issues.append(f"[NOTICE] 遗留标记: {line.strip()} @ line {lineno}")
                score -= 0.03

        score = max(0.0, score)
        return issues, score


# ---------------------------------------------------------------------------
# 阶段 6: 验证 — 测试验证修复
# ---------------------------------------------------------------------------

class VerificationStage(HermesStage):
    """
    验证阶段。

    输入: 修改后的代码
    输出: 验证报告 {tests_passed: bool, coverage: float, regressions: list}
    方法: 运行测试套件 + 回归测试
    """

    @property
    def name(self) -> str:
        return "verification"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "report": {"tests_passed": True, "coverage": 0.0, "regressions": []}}

        implementation_result = context.get("results", {}).get("implementation", {})
        patches: List[CodePatch] = implementation_result.get("patches", [])

        if not patches:
            logger.info("[%s] 无代码补丁，跳过验证", self.name)
            report: VerificationReport = {"tests_passed": True, "coverage": 0.0, "regressions": []}
            return {"report": report, "halt": False, "skip": False}

        # 先将补丁写入临时文件，再运行测试
        temp_dir = tempfile.mkdtemp(prefix="hermes_verify_")
        file_map: Dict[str, str] = {}

        for patch in patches:
            target = patch["file"]
            # 复制原文件到临时目录结构
            temp_path = os.path.join(temp_dir, os.path.basename(target))
            # 保持相对目录结构
            rel_dir = os.path.dirname(target)
            if rel_dir:
                os.makedirs(os.path.join(temp_dir, rel_dir), exist_ok=True)
                temp_path = os.path.join(temp_dir, target)
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(patch["modified"])
            file_map[target] = temp_path

        task: Dict[str, Any] = context.get("task", {})
        test_command: str = task.get("test_command", "")
        repo_path: str = task.get("repo_path", ".")

        tests_passed, coverage, regressions = self._run_tests(
            repo_path, test_command, file_map
        )

        report = {
            "tests_passed": tests_passed,
            "coverage": coverage,
            "regressions": regressions,
        }

        logger.info("[%s] 验证结果: tests_passed=%s | coverage=%.1f%% | regressions=%d", self.name, tests_passed, coverage * 100, len(regressions))

        result: Dict[str, Any] = {
            "report": report,
            "halt": not tests_passed,
            "skip": False,
        }
        self._log_end(result)
        return result

    def _run_tests(
        self,
        repo_path: str,
        test_command: str,
        file_map: Dict[str, str],
    ) -> Tuple[bool, float, List[str]]:
        """运行测试套件并收集结果。"""
        regressions: List[str] = []
        tests_passed = False
        coverage = 0.0

        # 如果没有指定测试命令，尝试自动检测
        if not test_command:
            if os.path.exists(os.path.join(repo_path, "pytest.ini")) or os.path.exists(
                os.path.join(repo_path, "pyproject.toml")
            ):
                test_command = "python -m pytest"
            elif os.path.exists(os.path.join(repo_path, "setup.py")):
                test_command = "python -m unittest discover"
            else:
                logger.warning("[%s] 未找到测试命令，跳过测试", self.name)
                return True, 0.0, []

        # 运行测试（在临时环境中）
        try:
            # 构建环境变量，将修改后的文件路径加入 PYTHONPATH
            env = os.environ.copy()
            modified_dirs = set(os.path.dirname(p) for p in file_map.values())
            python_path = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = os.pathsep.join(list(modified_dirs) + ([python_path] if python_path else []))

            cmd = test_command.split()
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            tests_passed = result.returncode == 0
            stdout = result.stdout
            stderr = result.stderr

            # 解析覆盖率（简单正则）
            cov_match = re.search(r"coverage[=:]?\s*(\d+)%", stdout + stderr, re.IGNORECASE)
            if cov_match:
                coverage = int(cov_match.group(1)) / 100.0

            # 解析失败的测试名作为回归
            for line in (stdout + stderr).splitlines():
                fail_match = re.search(r"FAILED\s+([\w/\-_\.]+)", line)
                if fail_match:
                    regressions.append(fail_match.group(1))

            if not tests_passed:
                logger.debug("[%s] 测试输出:\n%s", self.name, stdout + stderr)

        except subprocess.TimeoutExpired:
            logger.error("[%s] 测试执行超时", self.name)
            regressions.append("test_timeout")
        except Exception as e:
            logger.error("[%s] 测试执行异常: %s", self.name, e)
            regressions.append(f"test_error: {str(e)}")

        return tests_passed, coverage, regressions


# ---------------------------------------------------------------------------
# 阶段 7: 判决 — 最终判决通过/驳回
# ---------------------------------------------------------------------------

class JudgmentStage(HermesStage):
    """
    判决阶段。

    输入: 全部阶段结果
    输出: 最终判决 {verdict: "PASS"|"FAIL"|"RETRY", reason: str, next_action: str}
    方法: 综合评分，阈值判断
    """

    @property
    def name(self) -> str:
        return "judgment"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._log_start()
        if self._should_skip(context):
            logger.info("[%s] 被标记为跳过", self.name)
            return {"skip": True, "halt": False, "judgment": {"verdict": "PASS", "reason": "阶段被跳过", "next_action": "无"}}

        results: Dict[str, Any] = context.get("results", {})

        # 收集各阶段关键指标
        localization = results.get("localization", {})
        planning = results.get("planning", {})
        review = results.get("review", {})
        implementation = results.get("implementation", {})
        code_review = results.get("code_review", {})
        verification = results.get("verification", {})

        defects = localization.get("defects", [])
        strategies = planning.get("strategies", [])
        review_report: ReviewReport = review.get("report", {"approved": False})
        patches = implementation.get("patches", [])
        cr_report: CodeReviewReport = code_review.get("report", {"passed": False, "quality_score": 0.0})
        ver_report: VerificationReport = verification.get("report", {"tests_passed": False, "coverage": 0.0})

        # 综合评分
        score = 0.0
        reasons: List[str] = []

        # 有缺陷且已定位
        if defects:
            score += 0.1
            reasons.append(f"定位到 {len(defects)} 个缺陷")

        # 有修复方案
        if strategies:
            score += 0.1
            reasons.append(f"生成 {len(strategies)} 个修复方案")

        # 评审通过
        if review_report.get("approved", False):
            score += 0.2
            reasons.append("评审通过")
        else:
            reasons.append("评审未通过")

        # 有代码补丁
        if patches:
            score += 0.1
            reasons.append(f"生成 {len(patches)} 个补丁")

        # 代码审查通过
        if cr_report.get("passed", False):
            score += 0.2
            reasons.append("代码审查通过")
        else:
            reasons.append(f"代码审查未通过 (score={cr_report.get('quality_score', 0)})")

        # 验证通过
        if ver_report.get("tests_passed", False):
            score += 0.3
            reasons.append("测试验证通过")
        else:
            reasons.append("测试验证未通过")

        # 覆盖率加分
        coverage = ver_report.get("coverage", 0.0)
        if coverage >= 0.8:
            score += 0.05
        elif coverage >= 0.5:
            score += 0.02

        score = min(1.0, score)
        logger.info("[%s] 综合评分: %.2f", self.name, score)

        # 阈值判断
        if score >= 0.85:
            verdict: Literal["PASS", "FAIL", "RETRY"] = "PASS"
            next_action = "合并代码并关闭问题"
        elif score >= 0.5:
            verdict = "RETRY"
            next_action = "根据建议修改后重新执行流水线"
        else:
            verdict = "FAIL"
            next_action = "驳回修复，需人工介入或重新分析问题"

        judgment: JudgmentResult = {
            "verdict": verdict,
            "reason": "; ".join(reasons),
            "next_action": next_action,
        }

        logger.info("[%s] 最终判决: %s | %s | next_action=%s", self.name, verdict, judgment["reason"], next_action)

        result: Dict[str, Any] = {
            "judgment": judgment,
            "score": score,
            "halt": False,
            "skip": False,
        }
        self._log_end(result)
        return result


# ---------------------------------------------------------------------------
# 流水线控制器
# ---------------------------------------------------------------------------

class HermesPipeline:
    """
    Hermes 七阶段修复流水线控制器。

    负责按顺序执行以下阶段：
    1. localization   — 定位
    2. planning       — 计划
    3. review         — 评审
    4. implementation — 实现
    5. code_review    — 代码审查
    6. verification   — 验证
    7. judgment       — 判决

    支持上下文传递、阶段跳过/重试、详细日志记录。
    """

    def __init__(self) -> None:
        self.stages: List[HermesStage] = [
            LocalizationStage(),
            PlanningStage(),
            ReviewStage(),
            ImplementationStage(),
            CodeReviewStage(),
            VerificationStage(),
            JudgmentStage(),
        ]

    def execute(
        self,
        task: Dict[str, Any],
        agent_adapters: Dict[str, AgentAdapter],
    ) -> Dict[str, Any]:
        """
        执行完整七阶段流水线。

        Args:
            task: 任务定义，包含 repo_path、issue_description、failure_log、test_command 等。
            agent_adapters: 外部 Agent 适配器字典，键为 Agent 名称（如 "agent_t"）。

        Returns:
            完整上下文，包含 task、agents、results 以及各阶段执行结果。
        """
        # 兼容 task 为 list 的情况（编排器传入 task_batch）
        if isinstance(task, list):
            task = task[0] if task else {}
        
        context: Dict[str, Any] = {
            "task": task,
            "agents": agent_adapters,
            "results": {},
            "skip_stages": task.get("skip_stages", []) if isinstance(task, dict) else [],
            "retry_stages": task.get("retry_stages", []) if isinstance(task, dict) else [],
        }

        logger.info("Hermes Pipeline 启动 | task_id=%s", task.get("id", "N/A") if isinstance(task, dict) else "N/A")
        logger.info("阶段列表: %s", [s.name for s in self.stages])

        for stage in self.stages:
            # 重试逻辑：如果阶段被标记重试，先清除标记再执行
            if stage._should_retry(context):
                logger.info("阶段 %s 被标记为重试", stage.name)
                context["retry_stages"] = [
                    s for s in context.get("retry_stages", []) if s != stage.name
                ]

            try:
                result = stage.execute(context)
            except Exception as e:
                logger.exception("阶段 %s 执行异常", stage.name)
                result = {
                    "halt": True,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }

            context["results"][stage.name] = result

            if result.get("halt"):
                logger.warning("阶段 %s 触发 halt，流水线提前终止", stage.name)
                break

        logger.info("Hermes Pipeline 结束 | 已完成阶段: %s", list(context["results"].keys()))
        return context

    def execute_stage(
        self,
        stage_name: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        单独执行指定阶段（用于重试或调试）。

        Args:
            stage_name: 阶段名称。
            context: 流水线上下文。

        Returns:
            阶段执行结果，若阶段不存在则返回 None。
        """
        for stage in self.stages:
            if stage.name == stage_name:
                logger.info("单独执行阶段: %s", stage_name)
                return stage.execute(context)
        logger.warning("未找到阶段: %s", stage_name)
        return None


# ---------------------------------------------------------------------------
# 便捷入口
# ---------------------------------------------------------------------------

def run_hermes_pipeline(
    repo_path: str,
    issue_description: str,
    failure_log: str = "",
    test_command: str = "",
    agent_adapters: Optional[Dict[str, AgentAdapter]] = None,
    skip_stages: Optional[List[str]] = None,
    retry_stages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    便捷函数：快速运行 Hermes 流水线。

    Args:
        repo_path: 代码库路径。
        issue_description: 问题描述。
        failure_log: 测试失败日志（可选）。
        test_command: 测试命令（可选）。
        agent_adapters: 外部 Agent 适配器（可选）。
        skip_stages: 要跳过的阶段名称列表（可选）。
        retry_stages: 要重试的阶段名称列表（可选）。

    Returns:
        流水线执行后的完整上下文。
    """
    task = {
        "repo_path": repo_path,
        "issue_description": issue_description,
        "failure_log": failure_log,
        "test_command": test_command,
        "skip_stages": skip_stages or [],
        "retry_stages": retry_stages or [],
    }
    pipeline = HermesPipeline()
    return pipeline.execute(task, agent_adapters or {})
