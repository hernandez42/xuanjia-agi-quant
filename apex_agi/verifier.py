"""
ApexAGI Sandbox Verifier (V_t)
==============================
V_t 容器重放验证模块。

公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u,  O ∩ T = ∅

本模块实现 SandboxVerifier 类，支持三种沙箱后端：
- local : 使用临时目录 + subprocess 运行测试
- cube  : 调用 CubeSandbox API（如果可用）
- docker: 调用 docker run（如果可用）

约束:
- 所有外部调用必须通过 subprocess，不能使用直接网络库
- 每个外部调用必须有 try/except + fallback
- 所有操作记录到日志
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("apex_agi.verifier")
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
# SandboxVerifier
# ---------------------------------------------------------------------------

class SandboxVerifier:
    """沙箱验证器：在隔离环境中重放代码修改并验证无回归。

    支持三种沙箱类型:
        - local : 本地临时目录 + subprocess
        - cube  : Tencent Cloud CubeSandbox (subprocess 调用 cube CLI 或 curl API)
        - docker: Docker 容器 (subprocess 调用 docker run)
    """

    def __init__(self, sandbox_type: str = "local"):
        self.sandbox_type = sandbox_type  # local / cube / docker
        self._last_report: Optional[Dict[str, Any]] = None
        logger.info(f"SandboxVerifier initialized (sandbox_type={sandbox_type})")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay_in_sandbox(
        self,
        code_before: str,
        code_after: str,
        test_command: str,
        file_name: str = "main.py",
    ) -> dict:
        """在沙箱中重放代码修改，验证无 bug。

        流程:
            1. 创建临时沙箱环境
            2. 写入修改前代码，运行测试（基线）
            3. 写入修改后代码，运行测试（验证）
            4. 对比结果，检测回归
        """
        logger.info(f"Starting sandbox replay (type={self.sandbox_type})")
        start = time.time()

        try:
            baseline_results = self._run_baseline(code_before, test_command, file_name)
            new_results = self._run_verification(code_after, test_command, file_name)
            regression = self.verify_no_regression(baseline_results, new_results)

            report = self._build_report(
                baseline_results, new_results, regression, elapsed=time.time() - start
            )
            self._last_report = report
            logger.info(f"Sandbox replay completed in {report['elapsed']:.2f}s")
            return report

        except Exception as e:
            logger.exception("Sandbox replay failed.")
            return {
                "status": "failed",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "elapsed": time.time() - start,
            }

    def verify_no_regression(
        self, baseline_results: dict, new_results: dict
    ) -> dict:
        """验证无回归。

        对比基线和修改后的测试结果，检测:
            - 测试通过率下降
            - 新增错误输出
            - 新增异常
        """
        regression = {
            "has_regression": False,
            "details": [],
        }

        # 1. 对比 returncode
        baseline_rc = baseline_results.get("returncode", 0)
        new_rc = new_results.get("returncode", 0)
        if baseline_rc == 0 and new_rc != 0:
            regression["has_regression"] = True
            regression["details"].append(
                f"Tests passed before but failed after (rc {baseline_rc} -> {new_rc})."
            )

        # 2. 对比 stderr 中新增的错误
        baseline_err = baseline_results.get("stderr", "")
        new_err = new_results.get("stderr", "")
        if new_err and new_err not in baseline_err:
            # 简单启发式: 新的 stderr 内容
            regression["has_regression"] = True
            regression["details"].append("New stderr output detected after changes.")

        # 3. 对比 stdout 中 FAILED / ERROR 数量变化
        baseline_failures = self._count_failures(baseline_results.get("stdout", ""))
        new_failures = self._count_failures(new_results.get("stdout", ""))
        if new_failures > baseline_failures:
            regression["has_regression"] = True
            regression["details"].append(
                f"Test failures increased ({baseline_failures} -> {new_failures})."
            )

        # 4. 检测新增异常
        if new_results.get("error") and not baseline_results.get("error"):
            regression["has_regression"] = True
            regression["details"].append(
                f"New execution error: {new_results['error']}"
            )

        logger.info(
            f"Regression check: has_regression={regression['has_regression']}"
        )
        return regression

    def generate_verification_report(self) -> dict:
        """生成验证报告。"""
        if self._last_report is None:
            return {
                "status": "no_data",
                "message": "No verification has been performed yet.",
            }
        return {
            "status": "success",
            "report": self._last_report,
        }

    # ------------------------------------------------------------------
    # Internal sandbox runners
    # ------------------------------------------------------------------

    def _run_baseline(
        self, code_before: str, test_command: str, file_name: str
    ) -> Dict[str, Any]:
        """运行基线测试（修改前代码）。"""
        logger.debug("Running baseline test...")
        return self._run_in_sandbox(code_before, test_command, file_name, label="baseline")

    def _run_verification(
        self, code_after: str, test_command: str, file_name: str
    ) -> Dict[str, Any]:
        """运行验证测试（修改后代码）。"""
        logger.debug("Running verification test...")
        return self._run_in_sandbox(code_after, test_command, file_name, label="verification")

    def _run_in_sandbox(
        self,
        code: str,
        test_command: str,
        file_name: str,
        label: str = "run",
    ) -> Dict[str, Any]:
        """根据 sandbox_type 选择合适的沙箱运行代码。"""
        if self.sandbox_type == "local":
            return self._run_local(code, test_command, file_name, label)
        elif self.sandbox_type == "cube":
            return self._run_cube(code, test_command, file_name, label)
        elif self.sandbox_type == "docker":
            return self._run_docker(code, test_command, file_name, label)
        else:
            raise ValueError(f"Unsupported sandbox_type: {self.sandbox_type}")

    # ------------------------------------------------------------------
    # local sandbox
    # ------------------------------------------------------------------

    def _run_local(
        self,
        code: str,
        test_command: str,
        file_name: str,
        label: str,
    ) -> Dict[str, Any]:
        """使用本地临时目录 + subprocess 运行测试。"""
        with tempfile.TemporaryDirectory(prefix=f"apex_verify_{label}_") as tmpdir:
            code_path = Path(tmpdir) / file_name
            code_path.write_text(code, encoding="utf-8")

            # 解析 test_command
            cmd_parts = test_command.strip().split()
            if not cmd_parts:
                cmd_parts = [sys.executable, "-m", "pytest", str(code_path), "-v"]

            result = _run_subprocess(cmd_parts, cwd=tmpdir, timeout=120)
            return {
                "label": label,
                "sandbox": "local",
                "returncode": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "error": result.get("error"),
            }

    # ------------------------------------------------------------------
    # cube sandbox
    # ------------------------------------------------------------------

    def _run_cube(
        self,
        code: str,
        test_command: str,
        file_name: str,
        label: str,
    ) -> Dict[str, Any]:
        """使用 CubeSandbox 运行测试（subprocess 调用 cube CLI 或 curl API）。"""
        cube_cmd = "cube"
        api_url = os.environ.get("CUBE_API_URL", "")

        with tempfile.TemporaryDirectory(prefix=f"apex_verify_{label}_") as tmpdir:
            code_path = Path(tmpdir) / file_name
            code_path.write_text(code, encoding="utf-8")

            # 优先尝试 cube CLI
            if _command_exists(cube_cmd):
                test_script = Path(tmpdir) / "run_test.sh"
                test_script.write_text(
                    f"#!/bin/sh\ncd {tmpdir}\n{test_command}\n", encoding="utf-8"
                )
                test_script.chmod(0o755)

                cmd = [
                    cube_cmd,
                    "run",
                    "--dir", tmpdir,
                    "--cmd", str(test_script),
                    "--timeout", "120",
                ]
                result = _run_subprocess(cmd, timeout=130)
                return {
                    "label": label,
                    "sandbox": "cube",
                    "returncode": result["returncode"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "error": result.get("error"),
                }

            # Fallback 到 curl API
            if api_url:
                payload = {
                    "code": code,
                    "test_command": test_command,
                    "file_name": file_name,
                    "label": label,
                }
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, dir=tmpdir
                ) as f:
                    json.dump(payload, f, ensure_ascii=False)
                    payload_file = f.name

                cmd = [
                    "curl", "-s", "-X", "POST",
                    "-H", "Content-Type: application/json",
                    "-d", f"@{payload_file}",
                    f"{api_url}/run",
                ]
                result = _run_subprocess(cmd, timeout=130)
                os.unlink(payload_file)

                if result["returncode"] == 0:
                    try:
                        data = json.loads(result["stdout"])
                        return {
                            "label": label,
                            "sandbox": "cube",
                            "returncode": data.get("returncode", -1),
                            "stdout": data.get("stdout", ""),
                            "stderr": data.get("stderr", ""),
                            "error": None,
                        }
                    except json.JSONDecodeError:
                        return {
                            "label": label,
                            "sandbox": "cube",
                            "returncode": 0,
                            "stdout": result["stdout"],
                            "stderr": result["stderr"],
                            "error": None,
                        }
                else:
                    return {
                        "label": label,
                        "sandbox": "cube",
                        "returncode": result["returncode"],
                        "stdout": result["stdout"],
                        "stderr": result["stderr"],
                        "error": result.get("error"),
                    }

            # 若 cube CLI 和 API 都不可用，降级到 local
            logger.warning("Cube sandbox unavailable, falling back to local.")
            return self._run_local(code, test_command, file_name, label)

    # ------------------------------------------------------------------
    # docker sandbox
    # ------------------------------------------------------------------

    def _run_docker(
        self,
        code: str,
        test_command: str,
        file_name: str,
        label: str,
    ) -> Dict[str, Any]:
        """使用 Docker 容器运行测试。"""
        if not _command_exists("docker"):
            logger.warning("Docker not available, falling back to local.")
            return self._run_local(code, test_command, file_name, label)

        with tempfile.TemporaryDirectory(prefix=f"apex_verify_{label}_") as tmpdir:
            code_path = Path(tmpdir) / file_name
            code_path.write_text(code, encoding="utf-8")

            # 构建测试脚本
            test_script = Path(tmpdir) / "run_test.sh"
            test_script.write_text(
                f"#!/bin/sh\ncd /workspace\n{test_command}\n", encoding="utf-8"
            )
            test_script.chmod(0o755)

            # 检测语言以选择基础镜像
            image = self._detect_docker_image(file_name)

            cmd = [
                "docker", "run", "--rm",
                "-v", f"{tmpdir}:/workspace",
                "-w", "/workspace",
                image,
                "/workspace/run_test.sh",
            ]
            result = _run_subprocess(cmd, timeout=180)
            return {
                "label": label,
                "sandbox": "docker",
                "returncode": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "error": result.get("error"),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_failures(self, stdout: str) -> int:
        """从测试输出中统计 FAILED / ERROR 数量。"""
        count = 0
        for line in stdout.splitlines():
            if "FAILED" in line or "ERROR" in line:
                count += 1
        return count

    def _build_report(
        self,
        baseline_results: Dict[str, Any],
        new_results: Dict[str, Any],
        regression: Dict[str, Any],
        elapsed: float,
    ) -> Dict[str, Any]:
        """构建完整的验证报告。"""
        return {
            "status": "regression_detected" if regression["has_regression"] else "passed",
            "sandbox_type": self.sandbox_type,
            "elapsed": elapsed,
            "baseline": {
                "returncode": baseline_results.get("returncode"),
                "stdout_preview": baseline_results.get("stdout", "")[:500],
                "stderr_preview": baseline_results.get("stderr", "")[:500],
            },
            "verification": {
                "returncode": new_results.get("returncode"),
                "stdout_preview": new_results.get("stdout", "")[:500],
                "stderr_preview": new_results.get("stderr", "")[:500],
            },
            "regression": regression,
        }

    def _detect_docker_image(self, file_name: str) -> str:
        """根据文件扩展名选择 Docker 基础镜像。"""
        ext = Path(file_name).suffix.lower()
        mapping = {
            ".py": "python:3.11-slim",
            ".js": "node:20-slim",
            ".ts": "node:20-slim",
            ".go": "golang:1.22",
            ".rs": "rust:1.78",
            ".java": "openjdk:21-slim",
        }
        return mapping.get(ext, "python:3.11-slim")

    # ------------------------------------------------------------------
    # VerificationInterface compatibility
    # ------------------------------------------------------------------

    def verify(self, artifacts: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """兼容 orchestrator.VerificationInterface 的 verify 方法。

        参数 artifacts 为文件路径列表，context 可包含 test_command、code_before、code_after 等。
        """
        if not artifacts:
            return {"status": "skipped", "message": "No artifacts to verify."}

        results = []
        for artifact in artifacts:
            code_after = Path(artifact).read_text(encoding="utf-8")
            # 尝试从 context 获取修改前代码，否则用当前代码作为基线（无修改）
            code_before = context.get("code_before", code_after)
            test_command = context.get("test_command", f"{sys.executable} -m pytest {artifact} -v")
            file_name = Path(artifact).name

            report = self.replay_in_sandbox(code_before, code_after, test_command, file_name)
            results.append({"artifact": artifact, "report": report})

        overall_passed = all(r["report"].get("status") == "passed" for r in results)
        return {
            "status": "passed" if overall_passed else "regression_detected",
            "results": results,
        }

    def health_check(self) -> bool:
        """验证服务健康状态。"""
        if self.sandbox_type == "local":
            return True
        elif self.sandbox_type == "cube":
            cube_cmd = "cube"
            api_url = os.environ.get("CUBE_API_URL", "")
            if _command_exists(cube_cmd):
                result = _run_subprocess([cube_cmd, "status"], timeout=10)
                return result["returncode"] == 0
            if api_url:
                result = _run_subprocess(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{api_url}/health"],
                    timeout=10,
                )
                return result["stdout"].strip() in ("200", "204")
            return False
        elif self.sandbox_type == "docker":
            if not _command_exists("docker"):
                return False
            result = _run_subprocess(["docker", "info"], timeout=10)
            return result["returncode"] == 0
        return False
