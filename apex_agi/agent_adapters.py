"""
ApexAGI Agent Adapters (T)
==========================
外部 Agent T 调用适配器模块。

公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u,  O ∩ T = ∅

本模块实现四种 Agent 适配器，均继承自 orchestrator.AgentAdapter：
1. PiAgentAdapter          — 适配 badlogic/pi-mono (Pi Agent)
2. CubeSandboxAdapter      — 适配 Tencent Cloud CubeSandbox
3. LocalAgentAdapter       — 本地降级 Agent（沙箱内可用）
4. GitHubCopilotCLIAdapter — 适配 GitHub Copilot CLI

约束:
- 所有外部调用必须通过 subprocess，不能使用直接网络库
- 每个外部调用必须有 try/except + fallback
- 所有操作记录到日志
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator import AgentAdapter, Task

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("apex_agi.agent_adapters")
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
# Utility functions
# ---------------------------------------------------------------------------

def _run_subprocess(
    cmd: List[str],
    timeout: int = 60,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """安全地运行子进程命令，返回统一格式的结果字典。"""
    result = {
        "returncode": -1,
        "stdout": "",
        "stderr": "",
        "error": None,
    }
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
    except subprocess.TimeoutExpired as e:
        result["error"] = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        result["stderr"] = str(e)
        logger.warning(result["error"])
    except FileNotFoundError as e:
        result["error"] = f"Command not found: {' '.join(cmd)}"
        result["stderr"] = str(e)
        logger.warning(result["error"])
    except Exception as e:
        result["error"] = f"Unexpected error running {' '.join(cmd)}: {e}"
        result["stderr"] = traceback.format_exc()
        logger.exception(result["error"])
    return result


def _command_exists(cmd: str) -> bool:
    """检查命令是否存在于 PATH 中。"""
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# 1. PiAgentAdapter — 适配 badlogic/pi-mono (Pi Agent)
# ---------------------------------------------------------------------------

class PiAgentAdapter(AgentAdapter):
    """适配 badlogic/pi-mono (Pi Agent)。

    通过 subprocess 调用 pi CLI 或 curl 调用其 API。
    能力: code_generation, refactoring, analysis
    """

    def __init__(
        self,
        pi_cmd: str = "pi",
        api_url: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        self._pi_cmd = pi_cmd
        self._api_url = api_url or os.environ.get("PI_API_URL", "")
        self._timeout = timeout
        logger.info(f"PiAgentAdapter initialized (cmd={pi_cmd}, api_url={self._api_url})")

    def name(self) -> str:
        return "pi_agent"

    def capabilities(self) -> List[str]:
        return ["code_generation", "refactoring", "analysis"]

    def health_check(self) -> bool:
        """检查 pi 命令是否可用。"""
        if _command_exists(self._pi_cmd):
            result = _run_subprocess([self._pi_cmd, "--version"], timeout=10)
            if result["returncode"] == 0:
                logger.debug(f"Pi CLI healthy: {result['stdout'].strip()}")
                return True
        # 若 CLI 不可用，尝试 curl API
        if self._api_url:
            curl_cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", self._api_url]
            result = _run_subprocess(curl_cmd, timeout=10)
            if result["stdout"].strip() in ("200", "204"):
                logger.debug("Pi API healthy (HTTP 200/204).")
                return True
        logger.warning("PiAgentAdapter health check failed.")
        return False

    def execute(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """通过 pi CLI 或 API 执行任务。"""
        logger.info(f"PiAgentAdapter executing task {task.id}: {task.name}")
        start = time.time()

        # 构建 prompt
        prompt = self._build_prompt(task, context)

        # 优先尝试 CLI
        if _command_exists(self._pi_cmd):
            result = self._execute_via_cli(prompt, task)
        else:
            result = {"status": "failed", "error": "Pi CLI not available."}

        # CLI 失败且配置了 API，fallback 到 API
        if result.get("status") == "failed" and self._api_url:
            logger.info("Falling back to Pi API.")
            result = self._execute_via_api(prompt, task)

        result["elapsed"] = time.time() - start
        result["agent"] = self.name()
        result["task_id"] = task.id
        logger.info(f"PiAgentAdapter finished task {task.id} in {result['elapsed']:.2f}s")
        return result

    def _build_prompt(self, task: Task, context: Dict[str, Any]) -> str:
        """根据任务构建 prompt 字符串。"""
        lines = [
            f"Task: {task.name}",
            f"Description: {task.description}",
            f"Target files: {', '.join(task.target_files)}",
            f"Context: {json.dumps(context, ensure_ascii=False)}",
        ]
        return "\n".join(lines)

    def _execute_via_cli(self, prompt: str, task: Task) -> Dict[str, Any]:
        """通过 pi CLI 执行。"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(prompt)
                prompt_file = f.name

            cmd = [self._pi_cmd, "-f", prompt_file]
            result = _run_subprocess(cmd, timeout=self._timeout)
            os.unlink(prompt_file)

            if result["returncode"] == 0:
                return {
                    "status": "success",
                    "output": result["stdout"],
                    "stderr": result["stderr"],
                }
            else:
                return {
                    "status": "failed",
                    "error": result.get("error") or result["stderr"],
                    "stdout": result["stdout"],
                }
        except Exception as e:
            logger.exception("Pi CLI execution failed.")
            return {"status": "failed", "error": str(e)}

    def _execute_via_api(self, prompt: str, task: Task) -> Dict[str, Any]:
        """通过 curl 调用 Pi API。"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                payload = {
                    "prompt": prompt,
                    "task_id": task.id,
                    "capabilities": self.capabilities(),
                }
                json.dump(payload, f, ensure_ascii=False)
                payload_file = f.name

            cmd = [
                "curl", "-s", "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", f"@{payload_file}",
                self._api_url,
            ]
            result = _run_subprocess(cmd, timeout=self._timeout)
            os.unlink(payload_file)

            if result["returncode"] == 0:
                try:
                    data = json.loads(result["stdout"])
                    return {"status": "success", "data": data}
                except json.JSONDecodeError:
                    return {"status": "success", "output": result["stdout"]}
            else:
                return {
                    "status": "failed",
                    "error": result.get("error") or result["stderr"],
                }
        except Exception as e:
            logger.exception("Pi API execution failed.")
            return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# 2. CubeSandboxAdapter — 适配 Tencent Cloud CubeSandbox
# ---------------------------------------------------------------------------

class CubeSandboxAdapter(AgentAdapter):
    """适配 Tencent Cloud CubeSandbox。

    通过 subprocess 调用 cube CLI 或 REST API。
    能力: sandbox_execution, code_testing, isolation
    """

    def __init__(
        self,
        cube_cmd: str = "cube",
        api_url: Optional[str] = None,
        timeout: int = 180,
    ) -> None:
        self._cube_cmd = cube_cmd
        self._api_url = api_url or os.environ.get("CUBE_API_URL", "")
        self._timeout = timeout
        logger.info(f"CubeSandboxAdapter initialized (cmd={cube_cmd}, api_url={self._api_url})")

    def name(self) -> str:
        return "cube_sandbox"

    def capabilities(self) -> List[str]:
        return ["sandbox_execution", "code_testing", "isolation"]

    def health_check(self) -> bool:
        """检查 cube 服务是否运行。"""
        if _command_exists(self._cube_cmd):
            result = _run_subprocess([self._cube_cmd, "status"], timeout=10)
            if result["returncode"] == 0 and ("running" in result["stdout"].lower() or "up" in result["stdout"].lower()):
                logger.debug("Cube CLI healthy.")
                return True
        if self._api_url:
            curl_cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{self._api_url}/health"]
            result = _run_subprocess(curl_cmd, timeout=10)
            if result["stdout"].strip() in ("200", "204"):
                logger.debug("Cube API healthy (HTTP 200/204).")
                return True
        logger.warning("CubeSandboxAdapter health check failed.")
        return False

    def execute(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """在 CubeSandbox 中执行任务（代码测试/沙箱执行）。"""
        logger.info(f"CubeSandboxAdapter executing task {task.id}: {task.name}")
        start = time.time()

        # 提取任务参数
        code = task.pipeline_config.get("code", "")
        test_command = task.pipeline_config.get("test_command", "")
        language = task.pipeline_config.get("language", "python")

        if not code and task.target_files:
            # 读取目标文件内容
            try:
                code = Path(task.target_files[0]).read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read target file: {e}")

        # 优先尝试 CLI
        if _command_exists(self._cube_cmd):
            result = self._execute_via_cli(code, test_command, language, task)
        else:
            result = {"status": "failed", "error": "Cube CLI not available."}

        # Fallback 到 API
        if result.get("status") == "failed" and self._api_url:
            logger.info("Falling back to Cube API.")
            result = self._execute_via_api(code, test_command, language, task)

        result["elapsed"] = time.time() - start
        result["agent"] = self.name()
        result["task_id"] = task.id
        logger.info(f"CubeSandboxAdapter finished task {task.id} in {result['elapsed']:.2f}s")
        return result

    def _execute_via_cli(
        self, code: str, test_command: str, language: str, task: Task
    ) -> Dict[str, Any]:
        """通过 cube CLI 在沙箱中执行代码。"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # 写入代码文件
                ext = {"python": ".py", "javascript": ".js", "go": ".go"}.get(language, ".py")
                code_file = Path(tmpdir) / f"main{ext}"
                code_file.write_text(code, encoding="utf-8")

                # 写入测试脚本
                test_file = Path(tmpdir) / "run_test.sh"
                test_file.write_text(f"#!/bin/sh\ncd {tmpdir}\n{test_command}\n", encoding="utf-8")
                test_file.chmod(0o755)

                cmd = [
                    self._cube_cmd,
                    "run",
                    "--dir", tmpdir,
                    "--cmd", str(test_file),
                    "--timeout", str(self._timeout),
                ]
                result = _run_subprocess(cmd, timeout=self._timeout + 10)

                if result["returncode"] == 0:
                    return {
                        "status": "success",
                        "output": result["stdout"],
                        "stderr": result["stderr"],
                    }
                else:
                    return {
                        "status": "failed",
                        "error": result.get("error") or result["stderr"],
                        "stdout": result["stdout"],
                    }
        except Exception as e:
            logger.exception("Cube CLI execution failed.")
            return {"status": "failed", "error": str(e)}

    def _execute_via_api(
        self, code: str, test_command: str, language: str, task: Task
    ) -> Dict[str, Any]:
        """通过 curl 调用 Cube API 在沙箱中执行代码。"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                payload = {
                    "code": code,
                    "test_command": test_command,
                    "language": language,
                    "task_id": task.id,
                }
                json.dump(payload, f, ensure_ascii=False)
                payload_file = f.name

            cmd = [
                "curl", "-s", "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", f"@{payload_file}",
                f"{self._api_url}/run",
            ]
            result = _run_subprocess(cmd, timeout=self._timeout)
            os.unlink(payload_file)

            if result["returncode"] == 0:
                try:
                    data = json.loads(result["stdout"])
                    return {"status": "success", "data": data}
                except json.JSONDecodeError:
                    return {"status": "success", "output": result["stdout"]}
            else:
                return {
                    "status": "failed",
                    "error": result.get("error") or result["stderr"],
                }
        except Exception as e:
            logger.exception("Cube API execution failed.")
            return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# 3. LocalAgentAdapter — 本地降级 Agent（沙箱内可用）
# ---------------------------------------------------------------------------

class LocalAgentAdapter(AgentAdapter):
    """本地降级 Agent（沙箱内可用）。

    纯 Python 实现，不依赖外部服务。
    能力: basic_fix, pattern_replacement, linting
    使用 ast + re 进行简单代码修复。
    """

    def __init__(self) -> None:
        logger.info("LocalAgentAdapter initialized (pure Python, no external deps)")

    def name(self) -> str:
        return "local_agent"

    def capabilities(self) -> List[str]:
        return ["basic_fix", "pattern_replacement", "linting"]

    def health_check(self) -> bool:
        """本地 Agent 始终可用。"""
        return True

    def execute(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """使用纯 Python 逻辑执行任务。"""
        logger.info(f"LocalAgentAdapter executing task {task.id}: {task.name}")
        start = time.time()

        try:
            # 确定操作类型
            action = task.pipeline_config.get("action", "auto")
            if action == "auto":
                action = self._infer_action(task)

            if action == "basic_fix":
                result = self._do_basic_fix(task)
            elif action == "pattern_replacement":
                result = self._do_pattern_replacement(task)
            elif action == "linting":
                result = self._do_linting(task)
            else:
                result = {"status": "failed", "error": f"Unknown action: {action}"}

        except Exception as e:
            logger.exception("LocalAgentAdapter execution failed.")
            result = {"status": "failed", "error": str(e), "traceback": traceback.format_exc()}

        result["elapsed"] = time.time() - start
        result["agent"] = self.name()
        result["task_id"] = task.id
        logger.info(f"LocalAgentAdapter finished task {task.id} in {result['elapsed']:.2f}s")
        return result

    def _infer_action(self, task: Task) -> str:
        """根据任务描述推断操作类型。"""
        desc = task.description.lower()
        if "lint" in desc or "style" in desc:
            return "linting"
        if "pattern" in desc or "replace" in desc:
            return "pattern_replacement"
        return "basic_fix"

    def _do_basic_fix(self, task: Task) -> Dict[str, Any]:
        """执行基本代码修复（如移除 debug print、修复 bare except）。"""
        if not task.target_files:
            return {"status": "failed", "error": "No target files specified."}

        fixes = []
        for file_path in task.target_files:
            path = Path(file_path)
            if not path.exists():
                fixes.append({"file": file_path, "status": "skipped", "reason": "file not found"})
                continue

            try:
                source = path.read_text(encoding="utf-8")
                original = source
                lines = source.splitlines(keepends=True)
                new_lines = []
                changed = False

                for i, line in enumerate(lines):
                    # 修复 bare except
                    if re.search(r"^\s*except\s*:\s*pass\s*$", line):
                        indent = len(line) - len(line.lstrip())
                        new_lines.append(" " * indent + "except Exception:\n")
                        new_lines.append(" " * indent + "    pass\n")
                        changed = True
                        fixes.append({"file": file_path, "line": i + 1, "fix": "bare_except_replaced"})
                        continue

                    # 移除 debug print (简单启发式)
                    if re.search(r"^\s*print\s*\(", line) and "debug" in line.lower():
                        changed = True
                        fixes.append({"file": file_path, "line": i + 1, "fix": "debug_print_removed"})
                        continue

                    new_lines.append(line)

                if changed:
                    path.write_text("".join(new_lines), encoding="utf-8")
                    diff = "".join(difflib.unified_diff(
                        original.splitlines(keepends=True),
                        new_lines,
                        fromfile=file_path,
                        tofile=file_path,
                    ))
                    fixes.append({"file": file_path, "status": "fixed", "diff": diff})
                else:
                    fixes.append({"file": file_path, "status": "no_change"})

            except Exception as e:
                fixes.append({"file": file_path, "status": "failed", "error": str(e)})

        return {"status": "success", "fixes": fixes}

    def _do_pattern_replacement(self, task: Task) -> Dict[str, Any]:
        """执行模式替换。"""
        pattern = task.pipeline_config.get("pattern", "")
        replacement = task.pipeline_config.get("replacement", "")
        if not pattern:
            return {"status": "failed", "error": "No pattern specified."}

        replacements = []
        for file_path in task.target_files:
            path = Path(file_path)
            if not path.exists():
                replacements.append({"file": file_path, "status": "skipped", "reason": "file not found"})
                continue

            try:
                source = path.read_text(encoding="utf-8")
                new_source, count = re.subn(pattern, replacement, source)
                if count > 0:
                    path.write_text(new_source, encoding="utf-8")
                    diff = "".join(difflib.unified_diff(
                        source.splitlines(keepends=True),
                        new_source.splitlines(keepends=True),
                        fromfile=file_path,
                        tofile=file_path,
                    ))
                    replacements.append({"file": file_path, "status": "replaced", "count": count, "diff": diff})
                else:
                    replacements.append({"file": file_path, "status": "no_match"})
            except Exception as e:
                replacements.append({"file": file_path, "status": "failed", "error": str(e)})

        return {"status": "success", "replacements": replacements}

    def _do_linting(self, task: Task) -> Dict[str, Any]:
        """执行简单 linting（AST 语法检查 + 基本风格检查）。"""
        issues = []
        for file_path in task.target_files:
            path = Path(file_path)
            if not path.exists():
                issues.append({"file": file_path, "status": "skipped", "reason": "file not found"})
                continue

            try:
                source = path.read_text(encoding="utf-8")
                # AST 语法检查
                try:
                    ast.parse(source)
                    issues.append({"file": file_path, "status": "syntax_ok"})
                except SyntaxError as e:
                    issues.append({"file": file_path, "status": "syntax_error", "error": str(e)})

                # 基本风格检查
                lines = source.splitlines()
                for i, line in enumerate(lines, start=1):
                    if len(line) > 120:
                        issues.append({
                            "file": file_path,
                            "line": i,
                            "status": "style_warning",
                            "message": "Line too long (>120 chars)",
                        })
                    if line.endswith(" ") or line.endswith("\t"):
                        issues.append({
                            "file": file_path,
                            "line": i,
                            "status": "style_warning",
                            "message": "Trailing whitespace",
                        })
            except Exception as e:
                issues.append({"file": file_path, "status": "failed", "error": str(e)})

        return {"status": "success", "lint_issues": issues}


# ---------------------------------------------------------------------------
# 4. GitHubCopilotCLIAdapter — 适配 GitHub Copilot CLI
# ---------------------------------------------------------------------------

class GitHubCopilotCLIAdapter(AgentAdapter):
    """适配 GitHub Copilot CLI。

    通过 subprocess 调用 `gh copilot`。
    能力: code_generation, explanation, test_generation
    """

    def __init__(
        self,
        gh_cmd: str = "gh",
        timeout: int = 120,
    ) -> None:
        self._gh_cmd = gh_cmd
        self._timeout = timeout
        logger.info(f"GitHubCopilotCLIAdapter initialized (cmd={gh_cmd})")

    def name(self) -> str:
        return "github_copilot_cli"

    def capabilities(self) -> List[str]:
        return ["code_generation", "explanation", "test_generation"]

    def health_check(self) -> bool:
        """检查 gh CLI 和 copilot 扩展是否可用。"""
        if not _command_exists(self._gh_cmd):
            logger.warning("gh CLI not found.")
            return False
        # 检查 gh 版本
        result = _run_subprocess([self._gh_cmd, "--version"], timeout=10)
        if result["returncode"] != 0:
            logger.warning("gh CLI version check failed.")
            return False
        # 检查 copilot 扩展
        result = _run_subprocess([self._gh_cmd, "extension", "list"], timeout=10)
        if result["returncode"] != 0:
            logger.warning("gh extension list failed.")
            return False
        if "copilot" not in result["stdout"]:
            logger.warning("gh copilot extension not installed.")
            return False
        logger.debug("GitHub Copilot CLI healthy.")
        return True

    def execute(self, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        """通过 gh copilot CLI 执行任务。"""
        logger.info(f"GitHubCopilotCLIAdapter executing task {task.id}: {task.name}")
        start = time.time()

        prompt = self._build_prompt(task, context)
        subcommand = self._map_task_to_subcommand(task)

        result = self._execute_via_cli(prompt, subcommand)

        result["elapsed"] = time.time() - start
        result["agent"] = self.name()
        result["task_id"] = task.id
        logger.info(f"GitHubCopilotCLIAdapter finished task {task.id} in {result['elapsed']:.2f}s")
        return result

    def _build_prompt(self, task: Task, context: Dict[str, Any]) -> str:
        """构建 prompt。"""
        lines = [
            f"Task: {task.name}",
            f"Description: {task.description}",
            f"Target files: {', '.join(task.target_files)}",
        ]
        return "\n".join(lines)

    def _map_task_to_subcommand(self, task: Task) -> str:
        """将任务映射到 gh copilot 子命令。"""
        desc = task.description.lower()
        if "test" in desc or "unit test" in desc:
            return "suggest"
        if "explain" in desc or "document" in desc:
            return "explain"
        return "suggest"

    def _execute_via_cli(self, prompt: str, subcommand: str) -> Dict[str, Any]:
        """通过 gh copilot CLI 执行。"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(prompt)
                prompt_file = f.name

            cmd = [self._gh_cmd, "copilot", subcommand, "-f", prompt_file]
            result = _run_subprocess(cmd, timeout=self._timeout)
            os.unlink(prompt_file)

            if result["returncode"] == 0:
                return {
                    "status": "success",
                    "output": result["stdout"],
                    "stderr": result["stderr"],
                }
            else:
                return {
                    "status": "failed",
                    "error": result.get("error") or result["stderr"],
                    "stdout": result["stdout"],
                }
        except Exception as e:
            logger.exception("GitHub Copilot CLI execution failed.")
            return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Adapter Registry
# ---------------------------------------------------------------------------

AGENT_ADAPTER_REGISTRY: Dict[str, type] = {
    "pi_agent": PiAgentAdapter,
    "cube_sandbox": CubeSandboxAdapter,
    "local_agent": LocalAgentAdapter,
    "github_copilot_cli": GitHubCopilotCLIAdapter,
}


def create_adapter(name: str, **kwargs: Any) -> Optional[AgentAdapter]:
    """工厂函数：根据名称创建适配器实例。"""
    adapter_cls = AGENT_ADAPTER_REGISTRY.get(name)
    if adapter_cls is None:
        logger.error(f"Unknown agent adapter: {name}")
        return None
    try:
        return adapter_cls(**kwargs)
    except Exception as e:
        logger.exception(f"Failed to create adapter {name}: {e}")
        return None


def list_available_adapters() -> List[Dict[str, Any]]:
    """列出所有可用适配器及其健康状态。"""
    results = []
    for name, cls in AGENT_ADAPTER_REGISTRY.items():
        try:
            adapter = cls()
            healthy = adapter.health_check()
            results.append({
                "name": name,
                "class": cls.__name__,
                "capabilities": adapter.capabilities(),
                "healthy": healthy,
            })
        except Exception as e:
            results.append({
                "name": name,
                "class": cls.__name__,
                "capabilities": [],
                "healthy": False,
                "error": str(e),
            })
    return results
